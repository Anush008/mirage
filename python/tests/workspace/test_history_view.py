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

import pytest

from mirage.accessor.base import Accessor, NOOPAccessor
from mirage.commands.registry import command
from mirage.commands.spec import SPECS
from mirage.io.types import ByteSource, IOResult
from mirage.resource.ram import RAMResource
from mirage.types import MountMode, PathSpec
from mirage.workspace.workspace import Workspace


@command("history", resource="ram", spec=SPECS["history"])
async def fake_history(
    accessor: Accessor = NOOPAccessor(),
    paths: list[PathSpec] | None = None,
    *texts: str,
    **_extra: object,
) -> tuple[ByteSource | None, IOResult]:
    return b"FAKE\n", IOResult()


def _ws() -> Workspace:
    return Workspace({"/data": (RAMResource(), MountMode.WRITE)})


def _exec(ws: Workspace, cmd: str, **kw) -> IOResult:
    return asyncio.run(ws.execute(cmd, **kw))


def _stdout(io: IOResult) -> str:
    if io.stdout is None:
        return ""
    if isinstance(io.stdout, memoryview):
        return bytes(io.stdout).decode()
    if isinstance(io.stdout, (bytes, bytearray)):
        return bytes(io.stdout).decode()
    return ""


def test_history_command_per_session():
    ws = _ws()
    ws.create_session("s2")
    _exec(ws, "ls /data")
    _exec(ws, "pwd")
    _exec(ws, "ls /", session_id="s2")
    mine = _stdout(_exec(ws, "history"))
    other = _stdout(_exec(ws, "history", session_id="s2"))
    assert "ls /data" in mine
    assert "pwd" in mine
    assert "ls /data" not in other
    assert "ls /" in other


def test_history_builtin_wins_over_mount_command():
    res = RAMResource()
    res.register(fake_history)
    ws = Workspace({"/data": (res, MountMode.WRITE)})
    _exec(ws, "ls /data")
    out = _stdout(_exec(ws, "history", cwd="/data"))
    assert "FAKE" not in out
    assert "ls /data" in out


def test_cat_bash_history_all_sessions():
    ws = _ws()
    ws.create_session("s2")
    _exec(ws, "ls /data")
    _exec(ws, "pwd", session_id="s2")
    io = _exec(ws, "cat /.bash_history")
    assert io.exit_code == 0
    out = _stdout(io)
    assert "ls /data" in out
    assert "pwd" in out
    assert out.count("#") >= 2


def test_grep_and_tail_bash_history():
    ws = _ws()
    _exec(ws, "ls /data")
    _exec(ws, "pwd")
    grep_io = _exec(ws, "grep pwd /.bash_history")
    assert grep_io.exit_code == 0
    grep_out = _stdout(grep_io)
    assert "pwd" in grep_out
    assert "ls /data" not in grep_out
    tail_io = _exec(ws, "tail -n 2 /.bash_history")
    assert tail_io.exit_code == 0
    assert "pwd" in _stdout(tail_io)


def test_ls_root_hides_dotfile_ls_a_shows():
    ws = _ws()
    plain = _stdout(_exec(ws, "ls /"))
    dotted = _stdout(_exec(ws, "ls -a /"))
    assert ".bash_history" not in plain
    assert ".bash_history" in dotted


def test_history_c_clears_only_my_session_file_unchanged():
    ws = _ws()
    ws.create_session("s2")
    _exec(ws, "ls /data")
    _exec(ws, "pwd", session_id="s2")
    clear_io = _exec(ws, "history -c")
    assert clear_io.exit_code == 0
    mine = _stdout(_exec(ws, "history"))
    other = _stdout(_exec(ws, "history", session_id="s2"))
    file_out = _stdout(_exec(ws, "cat /.bash_history"))
    assert "ls /data" not in mine
    assert "pwd" in other
    assert "ls /data" in file_out


def test_append_to_bash_history_rejected():
    ws = _ws()
    io = _exec(ws, "echo hacked >> /.bash_history")
    assert io.exit_code != 0


def test_sessions_path_no_longer_resolves():
    ws = _ws()
    io = _exec(ws, "ls /.sessions")
    assert io.exit_code != 0


def test_unmount_history_view_rejected():
    ws = _ws()
    with pytest.raises(ValueError, match="history view"):
        asyncio.run(ws.unmount("/.bash_history"))


def test_snapshot_roundtrip_preserves_tombstones(tmp_path):
    ws = _ws()
    _exec(ws, "ls /data")
    _exec(ws, "history -c")
    _exec(ws, "pwd")
    snap = tmp_path / "ws.tar"
    asyncio.run(ws.snapshot(snap))
    dst = asyncio.run(Workspace.load(snap))
    mine = _stdout(_exec(dst, "history"))
    file_out = _stdout(_exec(dst, "cat /.bash_history"))
    assert "ls /data" not in mine
    assert "pwd" in mine
    assert "ls /data" in file_out


def test_workspace_history_method():
    ws = _ws()
    _exec(ws, "ls /data")
    _exec(ws, "pwd")
    events = asyncio.run(ws.history())
    assert [e["command"] for e in events] == ["ls /data", "pwd"]
    assert all(e["type"] == "command" for e in events)
