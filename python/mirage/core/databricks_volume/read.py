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

import time

from mirage.accessor.databricks_volume import DatabricksVolumeAccessor
from mirage.cache.index import IndexCacheStore
from mirage.core.databricks_volume.errors import is_not_found
from mirage.core.databricks_volume.path import backend_path
from mirage.observe.context import record
from mirage.types import PathSpec


def _range_header(offset: int, size: int | None) -> str | None:
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if size is not None and size < 0:
        raise ValueError("size must be non-negative")
    if offset == 0 and size is None:
        return None
    if size is None:
        return f"bytes={offset}-"
    return f"bytes={offset}-{offset + size - 1}"


async def read_bytes(
    accessor: DatabricksVolumeAccessor,
    path: PathSpec,
    index: IndexCacheStore = None,
    offset: int = 0,
    size: int | None = None,
) -> bytes:
    if isinstance(path, str):
        path = PathSpec(original=path, directory=path)
    virtual = path.original
    remote_path = backend_path(accessor.config, path)
    start_ms = int(time.monotonic() * 1000)
    if size == 0:
        record("read", virtual, "databricks_volume", 0, start_ms)
        return b""
    try:
        data = await accessor.client.read_bytes(
            remote_path,
            _range_header(offset, size),
        )
    except Exception as exc:
        if is_not_found(exc):
            raise FileNotFoundError(path.strip_prefix) from exc
        raise
    record("read", virtual, "databricks_volume", len(data), start_ms)
    return data
