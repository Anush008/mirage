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
import json
import time

from mirage.observe import OpRecord
from mirage.observe.observer import Observer
from mirage.resource.ram import RAMResource
from mirage.utils.dates import utc_date_folder
from mirage.workspace.types import ExecutionNode, ExecutionRecord


def test_log_op_writes_jsonl():
    resource = RAMResource()
    obs = Observer(resource=resource)
    rec = OpRecord(
        op="read",
        path="/data/f.csv",
        source="s3",
        bytes=100,
        timestamp=1000,
        duration_ms=5,
    )
    asyncio.run(obs.log_op(rec, agent="agent-1", session="sess-1"))
    data = resource._store.files[f"/{utc_date_folder()}/sess-1.jsonl"]
    parsed = json.loads(data.decode().strip())
    assert parsed["type"] == "op"
    assert parsed["agent"] == "agent-1"
    assert parsed["session"] == "sess-1"
    assert parsed["op"] == "read"


def test_log_command_writes_jsonl():
    resource = RAMResource()
    obs = Observer(resource=resource)
    rec = ExecutionRecord(
        agent="agent-1",
        command="ls /data",
        stdout=b"file.csv\n",
        stdin=None,
        exit_code=0,
        tree=ExecutionNode(command="ls /data"),
        timestamp=time.time(),
        session_id="sess-1",
    )
    asyncio.run(obs.log_command(rec))
    data = resource._store.files[f"/{utc_date_folder()}/sess-1.jsonl"]
    parsed = json.loads(data.decode().strip())
    assert parsed["type"] == "command"
    assert parsed["session"] == "sess-1"
    assert parsed["command"] == "ls /data"


def test_multiple_entries_appended():
    resource = RAMResource()
    obs = Observer(resource=resource)
    for i in range(3):
        rec = OpRecord(
            op="read",
            path=f"/f{i}",
            source="s3",
            bytes=i,
            timestamp=1000 + i,
            duration_ms=1,
        )
        asyncio.run(obs.log_op(rec, agent="a", session="s"))
    data = resource._store.files[f"/{utc_date_folder()}/s.jsonl"]
    lines = data.decode().strip().split("\n")
    assert len(lines) == 3


def _command_record(command: str, session: str, ts: float) -> ExecutionRecord:
    return ExecutionRecord(
        agent="a",
        command=command,
        stdout=b"",
        stdin=None,
        exit_code=0,
        tree=ExecutionNode(command=command),
        timestamp=ts,
        session_id=session,
    )


def test_log_clear_appends_tombstone():
    resource = RAMResource()
    obs = Observer(resource=resource)
    asyncio.run(obs.log_clear(session="s1", agent="a1"))
    events = obs.events()
    assert events[-1]["type"] == "clear"
    assert events[-1]["session"] == "s1"


def test_command_events_all_sessions_ordered():
    resource = RAMResource()
    obs = Observer(resource=resource)
    asyncio.run(obs.log_command(_command_record("ls /a", "s2", 2.0)))
    asyncio.run(obs.log_command(_command_record("ls /b", "s1", 1.0)))
    op = OpRecord(
        op="read",
        path="/f",
        source="ram",
        bytes=0,
        timestamp=1500,
        duration_ms=1,
    )
    asyncio.run(obs.log_op(op, agent="a", session="s1"))
    events = obs.command_events()
    assert [e["command"] for e in events] == ["ls /b", "ls /a"]
    assert all(e["type"] == "command" for e in events)


def test_command_events_same_timestamp_keeps_append_order():
    resource = RAMResource()
    obs = Observer(resource=resource)
    asyncio.run(obs.log_command(_command_record("first", "s2", 1.0)))
    asyncio.run(obs.log_command(_command_record("second", "s1", 1.0)))
    asyncio.run(obs.log_command(_command_record("third", "s2", 1.0)))
    events = obs.command_events()
    assert [e["command"] for e in events] == ["first", "second", "third"]


def test_session_command_events_respects_last_clear():
    resource = RAMResource()
    obs = Observer(resource=resource)
    asyncio.run(obs.log_command(_command_record("cmd A", "s1", 1.0)))
    asyncio.run(obs.log_clear(session="s1", agent="a"))
    asyncio.run(obs.log_command(_command_record("cmd B", "s1", 2.0)))
    asyncio.run(obs.log_command(_command_record("cmd C", "s2", 3.0)))
    s1 = obs.session_command_events("s1")
    s2 = obs.session_command_events("s2")
    assert [e["command"] for e in s1] == ["cmd B"]
    assert [e["command"] for e in s2] == ["cmd C"]


def test_observer_sessions_tracked():
    resource = RAMResource()
    obs = Observer(resource=resource)
    rec = OpRecord(
        op="stat",
        path="/f",
        source="ram",
        bytes=0,
        timestamp=1000,
        duration_ms=1,
    )
    asyncio.run(obs.log_op(rec, agent="a", session="sess-1"))
    asyncio.run(obs.log_op(rec, agent="a", session="sess-2"))
    assert obs.sessions == {"sess-1", "sess-2"}
