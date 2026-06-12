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

from mirage.accessor.history import HistoryAccessor
from mirage.commands.registry import command
from mirage.commands.spec import SPECS
from mirage.core.history.render import render_history_listing
from mirage.io.types import ByteSource, IOResult
from mirage.types import PathSpec

DEFAULT_SESSION = "default"


@command("history", resource="history", spec=SPECS["history"])
async def history_cmd(
    accessor: HistoryAccessor,
    paths: list[PathSpec] | None = None,
    *texts: str,
    stdin: bytes | None = None,
    c: bool = False,
    session_id: str | None = None,
    **_extra: object,
) -> tuple[ByteSource | None, IOResult]:
    observer = accessor.observer
    session = session_id if session_id is not None else DEFAULT_SESSION
    if c:
        await observer.log_clear(session=session)
        return None, IOResult()
    n = None
    if texts:
        try:
            n = int(texts[0])
        except ValueError:
            err = f"history: {texts[0]}: numeric argument required\n".encode()
            return None, IOResult(exit_code=1, stderr=err)
    events = await observer.session_command_events(session)
    output = render_history_listing(events, n=n)
    return output.encode(), IOResult()
