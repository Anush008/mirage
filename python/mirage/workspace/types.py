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

from dataclasses import asdict, dataclass, field

from mirage.observe import OpRecord


@dataclass
class ExecutionNode:
    """A node in the execution tree capturing per-command stderr and exit code.

    Args:
        command (str | None): Leaf command string, None for operators.
        op (str | None): Operator ("|", ";", "&&", "||"), None for leaf nodes.
        stderr (bytes): This node's stderr output.
        exit_code (int): This node's exit code.
        children (list[ExecutionNode]): Child nodes (empty for leaf commands).
        records (list[OpRecord]): I/O operation records for this node.
    """

    command: str | None = None
    op: str | None = None
    stderr: bytes = b""
    exit_code: int = 0
    children: list["ExecutionNode"] = field(default_factory=list)
    records: list[OpRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {}
        if self.command is not None:
            d["command"] = self.command
        if self.op is not None:
            d["op"] = self.op
        d["stderr"] = self.stderr.decode(errors="replace")
        d["exit_code"] = self.exit_code
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        if self.records:
            d["records"] = [asdict(r) for r in self.records]
        return d
