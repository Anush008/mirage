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

from mirage.accessor.databricks_volume import DatabricksVolumeAccessor
from mirage.cache.index import IndexCacheStore
from mirage.core.databricks_volume._helpers import ensure_path_spec
from mirage.core.databricks_volume.path import backend_path
from mirage.core.databricks_volume.read import read_bytes
from mirage.core.databricks_volume.stat import stat
from mirage.core.databricks_volume.write import write_bytes
from mirage.types import FileType, PathSpec


async def _copy_tree(
    accessor: DatabricksVolumeAccessor,
    remote_src: str,
    remote_dst: str,
) -> None:
    await accessor.client.create_directory(remote_dst)
    for entry in await accessor.client.list_directory(remote_src):
        name = entry.path.rstrip("/").rsplit("/", 1)[-1]
        child_dst = remote_dst.rstrip("/") + "/" + name
        if getattr(entry, "is_directory", False):
            await _copy_tree(accessor, entry.path, child_dst)
        else:
            data = await accessor.client.read_bytes(entry.path)
            await accessor.client.upload(child_dst, data)


async def copy(
    accessor: DatabricksVolumeAccessor,
    src: PathSpec,
    dst: PathSpec,
    index: IndexCacheStore = None,
    recursive: bool = False,
) -> None:
    src = ensure_path_spec(src)
    dst = ensure_path_spec(dst)
    src_stat = await stat(accessor, src, index)
    # Same-path guard runs after stat (and the non-recursive directory check)
    # so a missing source or `cp` of a directory still raises.
    same_path = backend_path(accessor.config,
                             src) == backend_path(accessor.config, dst)
    if src_stat.type == FileType.DIRECTORY:
        if not recursive:
            raise IsADirectoryError(src.strip_prefix)
        if same_path:
            return
        remote_src = backend_path(accessor.config, src)
        remote_dst = backend_path(accessor.config, dst)
        if remote_dst.startswith(remote_src + "/"):
            # Copying a directory into its own subtree creates the destination
            # inside the source, so the walk would descend into the fresh copy
            # forever. Refuse before any create_directory/upload.
            raise ValueError(f"cannot copy a directory, '{src.strip_prefix}', "
                             f"into itself, '{dst.strip_prefix}'")
        await _copy_tree(accessor, remote_src, remote_dst)
        return
    if same_path:
        # Copying a file onto itself would re-upload it; skip.
        return
    data = await read_bytes(accessor, src, index)
    await write_bytes(accessor, dst, data, index)
