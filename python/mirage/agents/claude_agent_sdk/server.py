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

import shlex
from typing import Any

try:
    from claude_agent_sdk import ToolAnnotations, create_sdk_mcp_server, tool
except ImportError as exc:
    raise ImportError(
        "`claude-agent-sdk` not installed. "
        "Install with: pip install 'mirage-ai[claude-agent-sdk]'"
    ) from exc

from mirage.io.types import IOResult
from mirage.workspace.workspace import Workspace

_EXECUTE_DESCRIPTION = (
    "Run a shell-style command on the Mirage virtual filesystem. "
    "Supports cat, grep, find, head, tail, ls, wc, sort, uniq, tee, pipe, "
    "and any other Unix command on mounted resources (S3, disk, RAM, etc.). "
    "Also supports reading structured files: cat on .parquet/.orc/.csv returns a table."
)

_READ_DESCRIPTION = (
    "Read the contents of a file on the Mirage virtual filesystem. "
    "Returns line-numbered text. "
    "Optionally pass 'offset' (default 0) to start at a given line "
    "and 'limit' (default 2000) to cap the number of lines returned."
)

_WRITE_DESCRIPTION = (
    "Write content to a new file on the Mirage virtual filesystem. "
    "Fails if the file already exists — use edit to modify an existing file."
)

_EDIT_DESCRIPTION = (
    "Replace a string in an existing file on the Mirage virtual filesystem. "
    "Fails if old_string is not found or appears more than once. "
    "Pass replace_all=true (default false) to replace every occurrence."
)

_LS_DESCRIPTION = "List files and directories at the given path on the Mirage virtual filesystem."

_GREP_DESCRIPTION = (
    "Search for a pattern in files on the Mirage virtual filesystem. "
    "Supports regex. Searches recursively under path."
)


def _decode(value: bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace")


def _io_to_str(io: IOResult) -> str:
    stdout = _decode(io.stdout if isinstance(io.stdout, bytes) else None)
    stderr = _decode(io.stderr if isinstance(io.stderr, bytes) else None)
    if stderr:
        return f"{stdout}\n{stderr}" if stdout else stderr
    return stdout


class _MirageTools:
    def __init__(self, workspace: Workspace) -> None:
        self._ws = workspace

    async def execute_command(self, args: dict[str, Any]) -> dict[str, Any]:
        io = await self._ws.execute(args["command"])
        return {"content": [{"type": "text", "text": _io_to_str(io)}]}

    async def read(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args["path"]
        offset = int(args.get("offset", 0))
        limit = int(args.get("limit", 2000))
        ops = self._ws.ops
        try:
            data = await ops.read(path)
        except (FileNotFoundError, ValueError) as exc:
            return {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "is_error": True,
            }
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        sliced = lines[offset:offset + limit]
        numbered = [f"{i + offset + 1:>6}\t{line}" for i, line in enumerate(sliced)]
        return {"content": [{"type": "text", "text": "".join(numbered)}]}

    async def write(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args["path"]
        content = args["content"]
        ops = self._ws.ops
        try:
            await ops.stat(path)
            return {
                "content": [{"type": "text", "text": f"Error: file '{path}' already exists"}],
                "is_error": True,
            }
        except (FileNotFoundError, ValueError):
            pass
        parent = "/".join(path.rstrip("/").split("/")[:-1]) or "/"
        try:
            await ops.mkdir(parent)
        except (FileExistsError, ValueError):
            pass
        data = content.encode("utf-8") if isinstance(content, str) else content
        await ops.write(path, data)
        return {"content": [{"type": "text", "text": f"Written: {path}"}]}

    async def edit(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args["path"]
        old_string = args["old_string"]
        new_string = args["new_string"]
        replace_all = bool(args.get("replace_all", False))
        ops = self._ws.ops
        try:
            data = await ops.read(path)
        except (FileNotFoundError, ValueError):
            return {
                "content": [{"type": "text", "text": f"Error: file '{path}' not found"}],
                "is_error": True,
            }
        content = data.decode("utf-8", errors="replace")
        count = content.count(old_string)
        if count == 0:
            return {
                "content": [{"type": "text", "text": f"Error: string not found in file: '{old_string}'"}],
                "is_error": True,
            }
        if count > 1 and not replace_all:
            return {
                "content": [{"type": "text", "text": f"Error: string appears {count} times. Pass replace_all=true"}],
                "is_error": True,
            }
        new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
        await ops.write(path, new_content.encode("utf-8"))
        occurrences = count if replace_all else 1
        return {"content": [{"type": "text", "text": f"Edited: {path} ({occurrences} occurrence(s))"}]}

    async def ls(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args["path"]
        io = await self._ws.execute(f"ls {shlex.quote(path)}")
        return {"content": [{"type": "text", "text": _io_to_str(io)}]}

    async def grep(self, args: dict[str, Any]) -> dict[str, Any]:
        pattern = args["pattern"]
        path = args["path"]
        io = await self._ws.execute(f"grep -rn {shlex.quote(pattern)} {shlex.quote(path)}")
        return {"content": [{"type": "text", "text": _io_to_str(io)}]}


def MirageServer(workspace: Workspace):
    """Create an in-process Mirage server for the Claude Agent SDK.

    Args:
        workspace (Workspace): The workspace to serve.

    Returns:
        An SDK server object to pass to ClaudeAgentOptions(mcp_servers=...).
    """
    tools_impl = _MirageTools(workspace)
    return create_sdk_mcp_server(
        name="mirage",
        version="1.0.0",
        tools=[
            tool("execute_command", _EXECUTE_DESCRIPTION, {"command": str})(tools_impl.execute_command),
            tool("read", _READ_DESCRIPTION, {"path": str}, annotations=ToolAnnotations(readOnlyHint=True))(tools_impl.read),
            tool("write", _WRITE_DESCRIPTION, {"path": str, "content": str})(tools_impl.write),
            tool("edit", _EDIT_DESCRIPTION, {"path": str, "old_string": str, "new_string": str})(tools_impl.edit),
            tool("ls", _LS_DESCRIPTION, {"path": str}, annotations=ToolAnnotations(readOnlyHint=True))(tools_impl.ls),
            tool("grep", _GREP_DESCRIPTION, {"pattern": str, "path": str}, annotations=ToolAnnotations(readOnlyHint=True))(tools_impl.grep),
        ],
    )
