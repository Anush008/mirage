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

import dataclasses
from typing import Any, Self

from mirage.accessor.databricks_volume import DatabricksVolumeAccessor
from mirage.commands.builtin.databricks_volume import \
    COMMANDS as DATABRICKS_VOLUME_COMMANDS
from mirage.core.databricks_volume.client import (DatabricksFilesClient,
                                                  SdkDatabricksFilesClient)
from mirage.core.databricks_volume.copy import copy
from mirage.core.databricks_volume.create import create
from mirage.core.databricks_volume.exists import exists
from mirage.core.databricks_volume.glob import resolve_glob as _resolve_glob
from mirage.core.databricks_volume.mkdir import mkdir
from mirage.core.databricks_volume.read import read_bytes
from mirage.core.databricks_volume.readdir import readdir
from mirage.core.databricks_volume.rename import rename
from mirage.core.databricks_volume.rm import rm_recursive
from mirage.core.databricks_volume.rmdir import rmdir
from mirage.core.databricks_volume.stat import stat as databricks_stat
from mirage.core.databricks_volume.stream import range_read, read_stream
from mirage.core.databricks_volume.unlink import unlink
from mirage.core.databricks_volume.write import write_bytes
from mirage.ops.databricks_volume import OPS as DATABRICKS_VOLUME_OPS
from mirage.resource.base import BaseResource
from mirage.resource.databricks_volume.config import DatabricksVolumeConfig
from mirage.resource.databricks_volume.prompt import PROMPT
from mirage.resource.databricks_volume.token_provider import TokenProvider
from mirage.types import PathSpec, ResourceName

_DATABRICKS_VOLUME_OPS = {
    "read_bytes": read_bytes,
    "readdir": readdir,
    "stat": databricks_stat,
    "read_stream": read_stream,
    "range_read": range_read,
    "exists": exists,
    "write": write_bytes,
    "create": create,
    "unlink": unlink,
    "mkdir": mkdir,
    "rmdir": rmdir,
    "copy": copy,
    "rename": rename,
    "rm_recursive": rm_recursive,
}


class DatabricksVolumeResource(BaseResource):
    name: str = ResourceName.DATABRICKS_VOLUME
    is_remote: bool = True
    _ops: dict[str, Any] = _DATABRICKS_VOLUME_OPS
    PROMPT: str = PROMPT

    def __init__(
        self,
        config: DatabricksVolumeConfig,
        token_provider: TokenProvider,
    ) -> None:
        self._initialize(
            config,
            SdkDatabricksFilesClient(config, token_provider),
        )

    @classmethod
    def _from_files_client(
        cls,
        config: DatabricksVolumeConfig,
        files_client: DatabricksFilesClient,
    ) -> Self:
        resource = cls.__new__(cls)
        resource._initialize(config, files_client)
        return resource

    def _initialize(
        self,
        config: DatabricksVolumeConfig,
        files_client: DatabricksFilesClient,
    ) -> None:
        super().__init__()
        self.config = config
        self.accessor = DatabricksVolumeAccessor(self.config, files_client)

        for fn in DATABRICKS_VOLUME_COMMANDS:
            self.register(fn)
        for fn in DATABRICKS_VOLUME_OPS:
            self.register_op(fn)

    async def resolve_glob(self, paths, prefix: str = ""):
        if prefix:
            paths = [
                dataclasses.replace(p, prefix=prefix)
                if isinstance(p, PathSpec) and not p.prefix else p
                for p in paths
            ]
        return await _resolve_glob(self.accessor, paths, self._index)

    def get_state(self) -> dict:
        return {
            "type": self.name,
            # Token providers are runtime-only and cannot be reconstructed
            # from the serialized volume location.
            "needs_override": True,
            "config": self.config.model_dump(),
        }

    def load_state(self, state: dict) -> None:
        pass
