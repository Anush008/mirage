# ========= Copyright 2026 @ Strukto.AI All Rights Reserved. =========
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ========= Copyright 2026 @ Strukto.AI All Rights Reserved. =========

from typing import Any

from mirage.cache.file import io as cache_io
from mirage.io import IOResult
from mirage.observe.context import branch_for
from mirage.resource.base import BaseResource
from mirage.types import ConsistencyPolicy, FileStat, PathSpec
from mirage.workspace.branch_vocab import READ_OPS, WRITE_OPS
from mirage.workspace.mount import Mount, MountRegistry
from mirage.workspace.session import assert_mount_allowed

_DISPATCH_READ_OPS = READ_OPS
_DISPATCH_WRITE_OPS = WRITE_OPS


def _needs_staging(mount: Mount) -> bool:
    """Whether a bound branch must divert this mount's content writes
    into its staging layer instead of the live backend.

    Tests override-identity — ``type(mount.resource).fork is
    BaseResource.fork`` — i.e. "did the resource leave ``fork`` at the
    share-by-reference default?" For today's backends that coincides with
    actual share-by-ref: RAM / cache / Disk override ``fork`` to isolate
    on the fork (→ no staging); S3 / Slack / GDrive and an
    ``is_remote=False`` Redis mount inherit the default and share one live
    object (→ stage). It is an approximation, not a behavioral test — a
    resource that overrode ``fork`` yet still returned a shared live
    client would be misclassified as isolating and leak staged writes to
    live; none do today. Deliberately NOT keyed on ``is_remote`` (Redis is
    local yet shared). F4 (#170) replaces this with a resource strategy
    flag, ideally fail-closed (an explicit ``isolates_on_fork`` opt-out so
    unknown resources default to staging) — swapping the internals here,
    never the call site.

    Args:
        mount (Mount): the mount the op resolved to.
    """
    return type(mount.resource).fork is BaseResource.fork


def policy_for(mount: Mount) -> object | None:
    """Staging/commit policy for ``mount`` — deferred stub, ``None`` today.

    Public (unlike the private ``_needs_staging``) because it is a seam
    other lanes import, parallel to ``READ_OPS`` / ``WRITE_OPS``. Unlike
    ``staged_read`` / ``divert_write`` it has no inert call site in
    ``dispatch``: policy is expected to be resolved at commit time,
    outside the per-op path, so this only reserves the name rather than
    anchoring a dispatch call site. F3/F4 (#169/#170) and the commit lane
    (D) define the real policy type and selection, and may revise this
    signature if they need op / path / branch context.

    Args:
        mount (Mount): the mount to resolve a policy for.
    """
    return None


class Dispatcher:
    """Route a single VFS op to its mount and keep the file cache + index
    consistent.

    Owns the cache/IO coordination that used to live on Workspace: cache
    lookups for remote reads, post-write file-cache eviction, and parent
    index invalidation. Constructed with the registry, cache store, and
    consistency policy; holds no other workspace state. Drift checking
    stays on Workspace (it reads/writes snapshot-owned state), which guards
    its own dispatch wrapper before delegating here.

    Frozen seam (Phase 0 / F2, #168): ``dispatch`` carries inert branch
    hooks — a ``branch_for()`` lookup, the ``_needs_staging`` gate, and
    ``staged_read`` / ``divert_write`` calls on the bound branch — dead
    until Lane A binds a branch. Scope is deliberately narrow: the seam
    covers content read/write routing only (``READ_OPS`` / ``WRITE_OPS``).
    ``stat`` / ``readdir`` / ``find`` are intentionally not diverted —
    with a branch bound they fall through to the live backend (content-
    only staging; metadata stays live). Directory mutations (``mkdir`` /
    ``rmdir`` / ``rename``) run via ``mount.execute_cmd`` and never
    traverse ``dispatch`` at all, so they are outside this seam by
    construction. Within that scope the feature lanes (A–J) extend
    dispatch only by implementing the branch methods, never by reopening
    this content read/write routing. Staging metadata or directory CoW,
    if a later arc needs it, is owned by the ``execute_cmd`` / ``IOResult``
    write-set path or a separate metadata seam — not by editing this block.
    """

    def __init__(self, registry: MountRegistry, cache,
                 consistency: ConsistencyPolicy) -> None:
        self._registry = registry
        self._cache = cache
        self._consistency = consistency

    async def dispatch(self, op: str, path: PathSpec,
                       **kwargs: Any) -> tuple[Any, IOResult]:
        mount = self._registry.mount_for(path.original)
        assert_mount_allowed(mount.prefix)
        branch = branch_for()
        # Dead seam today: ``branch`` is None on every path (Lane A binds
        # it later), so this block never runs and dispatch stays byte-for-
        # byte. Routing contract, scope, and the read-only invariant: see
        # the class docstring. staged_read / divert_write return
        # ``(result, IOResult)`` like dispatch.
        if branch is not None and _needs_staging(mount):
            if op in _DISPATCH_READ_OPS:
                return await branch.staged_read(mount, path, **kwargs)
            if op in _DISPATCH_WRITE_OPS:
                return await branch.divert_write(mount, op, path, **kwargs)
        cacheable = mount.resource.is_remote is True

        if cacheable and op in _DISPATCH_READ_OPS:
            cached = await self._cache.get(path.original)
            if cached is not None:
                if self._consistency == ConsistencyPolicy.ALWAYS:
                    try:
                        remote_stat = await mount.execute_op(
                            "stat", path.original)
                    except FileNotFoundError:
                        await self._cache.remove(path.original)
                        raise
                    if (remote_stat is not None
                            and remote_stat.fingerprint is not None):
                        fresh = await self._cache.is_fresh(
                            path.original, remote_stat.fingerprint)
                        if not fresh:
                            await self._cache.remove(path.original)
                            cached = None
                if cached is not None:
                    return cached, IOResult(reads={path.original: cached})

        result = await mount.execute_op(op, path.original, **kwargs)
        if op in _DISPATCH_WRITE_OPS:
            await self.invalidate_after_write(mount, path.original)
        return result, IOResult()

    async def stat(self, path: str) -> FileStat:
        scope = PathSpec(original=path, directory=path, resolved=True)
        result, _ = await self.dispatch("stat", scope)
        return result

    async def readdir(self, path: str) -> list[str]:
        scope = PathSpec(original=path, directory=path, resolved=False)
        raw, _ = await self.dispatch("readdir", scope)
        return raw

    async def apply_io(self, io: IOResult) -> None:
        await cache_io.apply_io(self._cache, io, self.is_cacheable_path)
        if io.writes:
            await self.invalidate_index_dirs(io)

    def is_cacheable_path(self, path: str) -> bool:
        try:
            mount = self._registry.mount_for(path)
        except ValueError:
            return False
        return mount.resource.is_remote is True

    async def invalidate_after_write_by_path(self, path: str) -> None:
        """Drop file-cache + stale parent index after a write to `path`.

        Single source of truth for post-write invalidation. Called from
        both `Workspace.dispatch()` and `Ops._call(write=True)` so a
        write through any code path sees the same invalidation rules:
        file cache is dropped only for remote-backed mounts, and the
        parent directory index is dirtied for any mount that maintains
        an index. No-op for paths that resolve to no known mount.

        Args:
            path (str): absolute mount path that was written.
        """
        try:
            mount = self._registry.mount_for(path)
        except ValueError:
            return
        await self.invalidate_after_write(mount, path)

    async def invalidate_after_write(self, mount: Mount, path: str) -> None:
        if mount.resource.is_remote is True:
            await self._cache.remove(path)
        idx = getattr(mount.resource, "index", None)
        if idx is not None:
            parent = path.rsplit("/", 1)[0] or "/"
            await idx.invalidate_dir(parent)
            await idx.invalidate_dir(parent + "/")

    async def invalidate_index_dirs(self, io: IOResult) -> None:
        dirs_seen: set[str] = set()
        for path in io.writes:
            try:
                mount = self._registry.mount_for(path)
            except ValueError:
                continue
            parent = path.rsplit("/", 1)[0] or "/"
            if parent in dirs_seen:
                continue
            dirs_seen.add(parent)
            idx = mount.resource.index
            await idx.invalidate_dir(parent)
            await idx.invalidate_dir(parent + "/")
