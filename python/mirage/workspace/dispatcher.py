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
    """Whether writes to ``mount`` must be diverted into a branch's
    staging layer instead of hitting the live backend.

    True iff the resource shares its backend by reference across a fork
    — i.e. it did not override ``BaseResource.fork`` — so the live and
    staged workspaces hold the same live object and a staged write would
    otherwise leak to the live side. S3 / Slack / GDrive and an
    in-memory-but-externally-owned Redis mount all share by reference;
    RAM / cache / Disk override ``fork`` to isolate on the fork and need
    no diversion.

    Deliberately NOT keyed on ``is_remote``: a Redis mount is
    ``is_remote=False`` yet still shares by reference and must be staged.
    F4 (#170) formalizes this into a resource strategy flag / WriteLayer
    protocol and may swap this predicate's internals — but not its call
    site in :meth:`Dispatcher.dispatch`.

    Args:
        mount (Mount): the mount the op resolved to.
    """
    return type(mount.resource).fork is BaseResource.fork


def policy_for(mount: Mount) -> object | None:
    """Staging/commit policy for ``mount`` — placeholder stub.

    Returns ``None`` today: no policy is defined until the commit
    contract lands. F3/F4 (#169/#170) and the commit lane (D) fill in
    the real policy type and per-mount selection; this stub freezes the
    call shape so they need not reopen the dispatcher.

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
    ``staged_read`` / ``divert_write`` calls on the bound branch — that
    are dead until Lane A binds a branch. After this freeze the feature
    lanes (A–J) plug in only by implementing those branch methods; they
    never reopen ``dispatch``. dispatcher.py is read-only for all
    downstream lanes.
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
        # Dead seam until Lane A binds a branch: ``branch`` is None on
        # every path today, so this block never runs and dispatch stays
        # byte-for-byte. When a branch is bound, a share-by-ref mount
        # serves reads through its staging layer and diverts writes into
        # it. ``staged_read`` / ``divert_write`` are the frozen contract
        # Lane A implements; both return ``(result, IOResult)`` like
        # dispatch. F4 may refine ``_needs_staging`` internals, never
        # this call site — dispatcher.py is read-only for other lanes.
        if branch is not None and _needs_staging(mount):
            if op in READ_OPS:
                return await branch.staged_read(mount, path, **kwargs)
            if op in WRITE_OPS:
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
