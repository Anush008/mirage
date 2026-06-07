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

import asyncio

try:
    from mirage.cache.file.redis import RedisFileCacheStore
except ImportError:
    RedisFileCacheStore = None  # type: ignore[misc, assignment]

try:
    from mirage.cache.index import RedisIndexCacheStore
except ImportError:
    RedisIndexCacheStore = None  # type: ignore[misc, assignment]

DEV_PREFIX = "/dev/"


def _norm_prefix(prefix: str) -> str:
    stripped = prefix.strip("/")
    return "/" + stripped + "/" if stripped else "/"


def _assert_forkable(ws) -> None:
    if ws._closed:
        raise RuntimeError("Workspace is closed")
    if RedisFileCacheStore is not None and isinstance(ws._cache,
                                                      RedisFileCacheStore):
        raise NotImplementedError(
            "Workspace.fork() requires the default RAM cache: a Redis-backed "
            "cache lives outside the process and cannot be cheaply forked "
            "(an empty staged workspace would silently lose "
            "default-mount scratch).")
    if RedisIndexCacheStore is not None:
        for m in ws._registry.mounts():
            if isinstance(m.resource.index, RedisIndexCacheStore):
                raise NotImplementedError(
                    f"Workspace.fork() does not support the Redis-backed "
                    f"index on mount {m.prefix!r}: its state lives outside "
                    "the process and cannot be cheaply forked.")


def _auto_prefixes(ws) -> set[str]:
    prefixes = {DEV_PREFIX}
    if ws.observer is not None:
        prefixes.add(_norm_prefix(ws.observer.prefix))
    return prefixes


def _fork_resources(ws) -> dict:
    auto = _auto_prefixes(ws)
    resources: dict = {}
    for m in ws._registry.mounts():
        if m.prefix in auto:
            continue
        resources[m.prefix] = (
            m.resource.fork(),
            m.mode,
            dict(m.command_safeguards),
        )
    return resources


def _copy_sessions(ws, staged) -> None:
    mgr = staged._session_mgr
    for sess in ws._session_mgr.list():
        mgr._sessions[sess.session_id] = sess.fork()
        if sess.session_id not in mgr._locks:
            mgr._locks[sess.session_id] = asyncio.Lock()


def _copy_history(ws, staged) -> None:
    if ws.history is None or staged.history is None:
        return
    for rec in ws.history.entries():
        staged.history.append(rec)


def _copy_revisions(ws, staged) -> None:
    for cm in staged._registry.mounts():
        try:
            pm = ws._registry.mount_for_prefix(cm.prefix)
        except ValueError:
            continue
        if pm.revisions:
            cm.revisions = dict(pm.revisions)


def _history_limit(ws) -> int | None:
    if ws.history is None:
        return None
    return ws.history._buffer.maxlen


async def fork_workspace(ws):
    """Build a copy-on-write staged fork of ``ws`` (the live workspace).

    Constructed via ``type(ws)`` so this module never imports Workspace
    (avoids a cycle). Remote backends are shared by reference; RAM-backed
    mounts and the cache are forked copy-on-write; disk mounts are not
    yet forkable (raise ``NotImplementedError`` — deferred to Lane C,
    #178); sessions, history, and revision pins are copied by value.

    Args:
        ws: the live Workspace to fork.
    """
    _assert_forkable(ws)
    staged = type(ws)(
        _fork_resources(ws),
        consistency=ws._consistency,
        session_id=ws._default_session_id,
        agent_id=ws._default_agent_id,
        history=_history_limit(ws),
        observe_prefix=ws.observer.prefix,
        _cache_store=ws._cache.fork(),
    )
    staged._current_agent_id = ws._current_agent_id
    _copy_sessions(ws, staged)
    _copy_history(ws, staged)
    _copy_revisions(ws, staged)
    return staged
