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

import tempfile

import pytest

from mirage.resource.disk import DiskResource
from mirage.resource.ram import RAMResource
from mirage.types import DEFAULT_SESSION_ID, CommandSafeguard, MountMode
from mirage.workspace import Workspace


class _SharedRAM(RAMResource):
    """RAM backend that forks by sharing — mimics a live remote backend
    (S3, Slack, ...) whose `fork()` is the BaseResource share-by-ref
    default."""

    def fork(self) -> "_SharedRAM":
        return self


class _FakeRedisCache:
    """Stand-in so the Redis-cache guard can be exercised without a live
    Redis server (a real RedisFileCacheStore connects on construction)."""


class _FakeRedisIndex:
    """Stand-in for RedisIndexCacheStore so the index-rejection guard can
    be exercised without a live Redis server."""


def _ws() -> Workspace:
    ram = RAMResource()
    ram._store.files["/seed.txt"] = b"seed\n"
    ws = Workspace(
        {"/ram/": (ram, MountMode.EXEC)},
        history=None,
    )
    ws.get_session(DEFAULT_SESSION_ID).cwd = "/ram"
    return ws


def _files(ws, prefix="/ram"):
    return ws.mount(prefix).resource._store.files


def _dirs(ws, prefix="/ram"):
    return ws.mount(prefix).resource._store.dirs


@pytest.mark.asyncio
async def test_fork_inherits_live_ram_content():
    ws = _ws()
    staged = await ws.fork()
    result = await staged.execute("cat /ram/seed.txt")
    assert b"seed" in result.stdout


@pytest.mark.asyncio
async def test_fork_ram_write_does_not_leak_to_live():
    ws = _ws()
    staged = await ws.fork()
    await staged.execute("echo hi > /ram/a.txt")
    assert "/a.txt" in staged.mount("/ram").resource._store.files
    assert "/a.txt" not in ws.mount("/ram").resource._store.files


@pytest.mark.asyncio
async def test_fork_live_write_does_not_leak_to_staged():
    ws = _ws()
    staged = await ws.fork()
    await ws.execute("echo bye > /ram/b.txt")
    assert "/b.txt" in ws.mount("/ram").resource._store.files
    assert "/b.txt" not in staged.mount("/ram").resource._store.files


@pytest.mark.asyncio
async def test_fork_session_cwd_inherited_then_isolated():
    ws = _ws()
    staged = await ws.fork()
    assert staged.get_session(DEFAULT_SESSION_ID).cwd == "/ram"
    staged.get_session(DEFAULT_SESSION_ID).cwd = "/"
    assert ws.get_session(DEFAULT_SESSION_ID).cwd == "/ram"


@pytest.mark.asyncio
async def test_fork_shares_remote_style_resource():
    shared = _SharedRAM()
    ws = Workspace({"/s3/": (shared, MountMode.EXEC)}, history=None)
    ws.get_session(DEFAULT_SESSION_ID).cwd = "/s3"
    staged = await ws.fork()
    assert staged.mount("/s3").resource is shared
    await staged.execute("echo hi > /s3/r.txt")
    assert "/r.txt" in shared._store.files


@pytest.mark.asyncio
async def test_fork_copies_history_then_diverges():
    ws = Workspace({"/ram/": (RAMResource(), MountMode.EXEC)}, history=100)
    await ws.execute("echo hi > /ram/a.txt")
    staged = await ws.fork()
    assert len(staged.history.entries()) == len(ws.history.entries())
    await staged.execute("echo bye > /ram/b.txt")
    assert len(staged.history.entries()) == len(ws.history.entries()) + 1


@pytest.mark.asyncio
async def test_fork_on_closed_workspace_raises():
    ws = _ws()
    await ws.close()
    with pytest.raises(RuntimeError):
        await ws.fork()


@pytest.mark.asyncio
async def test_fork_rejects_redis_backed_cache(monkeypatch):
    monkeypatch.setattr("mirage.workspace.fork.RedisFileCacheStore",
                        _FakeRedisCache)
    ws = _ws()
    ws._cache = _FakeRedisCache()
    with pytest.raises(NotImplementedError):
        await ws.fork()


@pytest.mark.asyncio
async def test_fork_staged_overwrite_of_inherited_is_isolated():
    ws = _ws()
    staged = await ws.fork()
    await staged.execute("echo changed > /ram/seed.txt")
    assert (await ws.execute("cat /ram/seed.txt")).stdout == b"seed\n"
    assert b"changed" in (await staged.execute("cat /ram/seed.txt")).stdout


@pytest.mark.asyncio
async def test_fork_staged_delete_of_inherited_is_isolated():
    ws = _ws()
    staged = await ws.fork()
    await staged.execute("rm /ram/seed.txt")
    assert "/seed.txt" in _files(ws)
    assert "/seed.txt" not in _files(staged)


@pytest.mark.asyncio
async def test_fork_staged_append_to_inherited_is_isolated():
    ws = _ws()
    staged = await ws.fork()
    await staged.execute("echo more >> /ram/seed.txt")
    assert (await ws.execute("cat /ram/seed.txt")).stdout == b"seed\n"
    staged_out = (await staged.execute("cat /ram/seed.txt")).stdout
    assert b"seed" in staged_out and b"more" in staged_out


@pytest.mark.asyncio
async def test_fork_shares_payload_by_reference_with_cow_granularity():
    ws = _ws()
    await ws.execute("echo bbb > /ram/b.txt")
    staged = await ws.fork()
    assert _files(staged)["/seed.txt"] is _files(ws)["/seed.txt"]
    assert _files(staged)["/b.txt"] is _files(ws)["/b.txt"]
    await staged.execute("echo b2 > /ram/b.txt")
    assert _files(staged)["/b.txt"] != _files(ws)["/b.txt"]
    assert _files(staged)["/seed.txt"] is _files(ws)["/seed.txt"]
    assert _files(ws)["/b.txt"] == b"bbb\n"


@pytest.mark.asyncio
async def test_fork_three_level_staged_isolation():
    ws = _ws()
    await ws.execute("echo a > /ram/a.txt")
    staged = await ws.fork()
    await staged.execute("echo b > /ram/b.txt")
    grand = await staged.fork()
    await grand.execute("echo c > /ram/c.txt")
    assert "/a.txt" in _files(grand) and "/b.txt" in _files(grand)
    assert "/c.txt" not in _files(staged)
    assert "/b.txt" not in _files(ws) and "/c.txt" not in _files(ws)


@pytest.mark.asyncio
async def test_fork_two_siblings_isolated():
    ws = _ws()
    a = await ws.fork()
    b = await ws.fork()
    await a.execute("echo a > /ram/a.txt")
    await b.execute("echo b > /ram/b.txt")
    assert "/b.txt" not in _files(a)
    assert "/a.txt" not in _files(b)
    assert "/a.txt" not in _files(ws) and "/b.txt" not in _files(ws)


@pytest.mark.asyncio
async def test_fork_dirs_isolation_via_mkdir():
    ws = _ws()
    await ws.execute("mkdir /ram/d")
    staged = await ws.fork()
    await staged.execute("mkdir /ram/e")
    assert "/d" in _dirs(ws) and "/e" not in _dirs(ws)
    assert "/d" in _dirs(staged) and "/e" in _dirs(staged)


@pytest.mark.asyncio
async def test_fork_cross_mount_cp_isolated():
    ws = Workspace(
        {
            "/a/": (RAMResource(), MountMode.EXEC),
            "/b/": (RAMResource(), MountMode.EXEC),
        },
        history=None,
    )
    await ws.execute("echo data > /a/x.txt")
    staged = await ws.fork()
    await staged.execute("cp /a/x.txt /b/y.txt")
    assert "/y.txt" in _files(staged, "/b")
    assert "/y.txt" not in _files(ws, "/b")


@pytest.mark.asyncio
async def test_fork_rejects_disk_mount():
    root = tempfile.mkdtemp(prefix="mirage-test-disk-")
    ws = Workspace({"/disk/": (DiskResource(root=root), MountMode.EXEC)},
                   history=None)
    with pytest.raises(NotImplementedError):
        await ws.fork()


@pytest.mark.asyncio
async def test_fork_session_env_inherited_then_isolated():
    ws = _ws()
    ws.get_session(DEFAULT_SESSION_ID).env["FOO"] = "bar"
    staged = await ws.fork()
    assert staged.get_session(DEFAULT_SESSION_ID).env.get("FOO") == "bar"
    staged.get_session(DEFAULT_SESSION_ID).env["FOO"] = "baz"
    assert ws.get_session(DEFAULT_SESSION_ID).env["FOO"] == "bar"


@pytest.mark.asyncio
async def test_fork_nondefault_session_inherited_and_isolated():
    ws = _ws()
    sess = ws.create_session("work")
    sess.env["K"] = "v"
    staged = await ws.fork()
    assert staged.get_session("work").env.get("K") == "v"
    staged.get_session("work").env["K"] = "changed"
    assert ws.get_session("work").env["K"] == "v"


@pytest.mark.asyncio
async def test_fork_cache_distinct_and_isolated():
    ws = _ws()
    await ws._cache.set("/seedcache", b"v")
    staged = await ws.fork()
    assert staged._cache is not ws._cache
    assert await staged._cache.get("/seedcache") == b"v"
    await staged._cache.set("/probe", b"x")
    assert await ws._cache.get("/probe") is None
    await staged._cache.remove("/seedcache")
    assert await ws._cache.get("/seedcache") == b"v"


@pytest.mark.asyncio
async def test_fork_has_isolated_observer():
    ws = _ws()
    staged = await ws.fork()
    assert staged.observer is not ws.observer
    assert staged.observer.resource is not ws.observer.resource


@pytest.mark.asyncio
async def test_fork_live_usable_after_fork_snapshot_at_fork():
    ws = _ws()
    staged = await ws.fork()
    await ws.execute("echo a2 > /ram/post.txt")
    assert "/post.txt" in _files(ws)
    assert "/post.txt" not in _files(staged)


@pytest.mark.asyncio
async def test_fork_preserves_command_safeguards():
    ws = _ws()
    guard = CommandSafeguard(max_lines=3)
    ws.mount("/ram").command_safeguards["grep"] = guard
    staged = await ws.fork()
    assert staged.mount("/ram").command_safeguards.get("grep") is guard
    staged.mount("/ram").command_safeguards["cat"] = CommandSafeguard(
        max_lines=1)
    assert "cat" not in ws.mount("/ram").command_safeguards


@pytest.mark.asyncio
async def test_fork_rejects_redis_backed_index(monkeypatch):
    monkeypatch.setattr("mirage.workspace.fork.RedisIndexCacheStore",
                        _FakeRedisIndex)
    ws = _ws()
    ws.mount("/ram").resource._index = _FakeRedisIndex()
    with pytest.raises(NotImplementedError):
        await ws.fork()


@pytest.mark.asyncio
async def test_fork_mixed_mounts_ram_isolated_remote_shared():
    ram = RAMResource()
    shared = _SharedRAM()
    ws = Workspace(
        {
            "/ram/": (ram, MountMode.EXEC),
            "/s3/": (shared, MountMode.EXEC),
        },
        history=None,
    )
    staged = await ws.fork()
    await staged.execute("echo hi > /ram/a.txt")
    await staged.execute("echo hi > /s3/r.txt")
    assert "/a.txt" in _files(staged, "/ram")
    assert "/a.txt" not in _files(ws, "/ram")
    assert staged.mount("/s3").resource is shared
    assert "/r.txt" in shared._store.files


@pytest.mark.asyncio
async def test_fork_copies_revision_pins():
    ws = _ws()
    ws.mount("/ram").revisions = {"/seed.txt": "v1"}
    staged = await ws.fork()
    assert staged.mount("/ram").revisions == {"/seed.txt": "v1"}
    staged.mount("/ram").revisions["/seed.txt"] = "v2"
    assert ws.mount("/ram").revisions["/seed.txt"] == "v1"


@pytest.mark.asyncio
async def test_fork_history_maxlen_preserved():
    ws = Workspace({"/ram/": (RAMResource(), MountMode.EXEC)}, history=7)
    staged = await ws.fork()
    assert staged.history._buffer.maxlen == 7


@pytest.mark.asyncio
async def test_fork_propagates_agent_id():
    ws = _ws()
    ws._current_agent_id = "agent-x"
    staged = await ws.fork()
    assert staged._current_agent_id == "agent-x"
