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

import json
import time

from mirage.observe.log_entry import LogEntry
from mirage.observe.record import OpRecord
from mirage.resource.base import BaseResource
from mirage.utils.dates import utc_date_folder


class Observer:
    """Persists LogEntry records to a resource as JSONL files.

    The hidden recorder: its resource is never mounted, so the log is
    invisible to agents. Views (/.bash_history, the history builtin)
    render from the query methods below.

    Args:
        resource (BaseResource): Storage backend for log files.
    """

    def __init__(self, resource: BaseResource) -> None:
        self._resource = resource
        self._sessions: set[str] = set()
        self._seq = 0

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq += 1
        return seq

    @property
    def resource(self) -> BaseResource:
        return self._resource

    @property
    def sessions(self) -> set[str]:
        return set(self._sessions)

    async def log_op(
        self,
        rec: OpRecord,
        agent: str,
        session: str,
        cwd: str | None = None,
    ) -> None:
        """Persist an OpRecord as a JSONL line.

        Args:
            rec (OpRecord): The operation record.
            agent (str): Agent ID.
            session (str): Session ID.
            cwd (str | None): Session cwd at log time.
        """
        entry = LogEntry.from_op_record(rec, agent, session, cwd)
        entry.seq = self._next_seq()
        self._sessions.add(session)
        line = (entry.to_json_line() + "\n").encode()
        await self._append(f"/{utc_date_folder()}/{session}.jsonl", line)

    async def log_command(self, rec, cwd: str | None = None) -> None:
        """Persist an ExecutionRecord as a JSONL line.

        Args:
            rec (ExecutionRecord): The execution record.
            cwd (str | None): Session cwd at log time.
        """
        entry = LogEntry.from_execution_record(rec, cwd)
        entry.seq = self._next_seq()
        self._sessions.add(rec.session_id)
        line = (entry.to_json_line() + "\n").encode()
        await self._append(f"/{utc_date_folder()}/{rec.session_id}.jsonl",
                           line)

    async def log_clear(self, session: str, agent: str = "") -> None:
        """Append a clear tombstone for a session.

        Args:
            session (str): Session ID whose history view is cleared.
            agent (str): Agent ID issuing the clear.
        """
        entry = LogEntry(
            type="clear",
            agent=agent,
            session=session,
            timestamp=int(time.time() * 1000),
            seq=self._next_seq(),
        )
        self._sessions.add(session)
        line = (entry.to_json_line() + "\n").encode()
        await self._append(f"/{utc_date_folder()}/{session}.jsonl", line)

    def events(self) -> list[dict]:
        """All recorded events across sessions, in append order.

        Ordered by the monotonic per-recorder seq (total order even
        when timestamps tie), timestamp as a fallback for events
        loaded from sources that lack one.

        Returns:
            list[dict]: Parsed LogEntry dicts.
        """
        out: list[dict] = []
        store = self._resource._store
        for key in sorted(store.files.keys()):
            if not key.endswith(".jsonl"):
                continue
            for line in store.files[key].decode().splitlines():
                if line:
                    out.append(json.loads(line))
        out.sort(key=lambda e: (e.get("timestamp", 0), e.get("seq", 0)))
        return out

    def command_events(self) -> list[dict]:
        """Command events across all sessions, ordered by timestamp.

        Returns:
            list[dict]: Events with type == "command".
        """
        return [e for e in self.events() if e.get("type") == "command"]

    def session_command_events(self, session: str) -> list[dict]:
        """One session's command events after its last clear tombstone.

        Args:
            session (str): Session ID to project.

        Returns:
            list[dict]: Events with type == "command", append order.
        """
        entries: list[dict] = []
        store = self._resource._store
        for key in sorted(store.files.keys()):
            if not key.endswith(f"/{session}.jsonl"):
                continue
            for line in store.files[key].decode().splitlines():
                if line:
                    entries.append(json.loads(line))
        last_clear = -1
        for i, e in enumerate(entries):
            if e.get("type") == "clear":
                last_clear = i
        return [
            e for e in entries[last_clear + 1:] if e.get("type") == "command"
        ]

    def load_events(self, events: list[dict]) -> None:
        """Load events back into the store (snapshot restore path).

        Groups by session and rewrites each session's JSONL under
        today's date folder; original date folders are not preserved,
        which the views never depend on (they filter by the session
        field and sort by timestamp).

        Args:
            events (list[dict]): LogEntry dicts from StateKey.HISTORY.
        """
        store = self._resource._store
        day = utc_date_folder()
        by_session: dict[str, list[str]] = {}
        max_seq = self._seq - 1
        for i, e in enumerate(events):
            if e.get("seq") is None:
                e = {**e, "seq": i}
            max_seq = max(max_seq, e["seq"])
            session = e.get("session", "default")
            by_session.setdefault(session, []).append(
                json.dumps(e, separators=(",", ":")))
        self._seq = max_seq + 1
        for session, lines in by_session.items():
            self._sessions.add(session)
            key = f"/{day}/{session}.jsonl"
            store.dirs.add(f"/{day}")
            store.files[key] = ("\n".join(lines) + "\n").encode()

    async def _append(self, path: str, data: bytes) -> None:
        store = self._resource._store
        key = path if path.startswith("/") else "/" + path
        last_slash = key.rfind("/")
        parent = "/" if last_slash <= 0 else key[:last_slash]
        store.dirs.add(parent)
        if key in store.files:
            store.files[key] += data
        else:
            store.files[key] = data
