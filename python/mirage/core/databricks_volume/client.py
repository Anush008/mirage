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
import inspect
from contextvars import ContextVar
from io import BytesIO
from typing import Any, BinaryIO, Callable, Protocol, TypeVar
from urllib.parse import quote

from mirage.resource.databricks_volume.config import DatabricksVolumeConfig
from mirage.resource.databricks_volume.token_provider import TokenProvider

try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.config import Config as WorkspaceConfig
    from databricks.sdk.credentials_provider import CredentialsStrategy
except ImportError:
    WorkspaceClient = None
    WorkspaceConfig = None

    class CredentialsStrategy:
        pass


_operation_token: ContextVar[str | None] = ContextVar(
    "databricks_volume_operation_token",
    default=None,
)
T = TypeVar("T")


def _response_contents(response: object) -> object:
    if isinstance(response, dict):
        return response.get("contents", response)
    return getattr(response, "contents", response)


def _response_bytes(response: object) -> bytes:
    contents = _response_contents(response)
    if isinstance(contents, bytes):
        return contents
    if hasattr(contents, "read"):
        return contents.read()
    return bytes(contents)


def _response_stream(response: object) -> BinaryIO:
    contents = _response_contents(response)
    if not hasattr(contents, "read"):
        raise RuntimeError("Databricks download response has no readable body")
    return contents


class DatabricksFilesClient(Protocol):

    async def read_bytes(
        self,
        path: str,
        range_header: str | None = None,
    ) -> bytes:
        ...

    async def open_read(self, path: str) -> "DatabricksReadStream":
        ...

    async def get_metadata(self, path: str) -> object:
        ...

    async def get_directory_metadata(self, path: str) -> object:
        ...

    async def list_directory(self, path: str) -> list[object]:
        ...

    async def upload(self, path: str, data: bytes) -> None:
        ...

    async def delete(self, path: str) -> None:
        ...

    async def create_directory(self, path: str) -> None:
        ...

    async def delete_directory(self, path: str) -> None:
        ...


class DatabricksReadStream(Protocol):

    async def read(self, size: int = -1) -> bytes:
        ...

    async def close(self) -> None:
        ...


class _OperationCredentials:

    def __call__(self) -> dict[str, str]:
        token = _operation_token.get()
        if token is None:
            raise RuntimeError("Databricks request has no operation token")
        return {"Authorization": f"Bearer {token}"}


class _TokenProviderCredentialsStrategy(CredentialsStrategy):

    def auth_type(self) -> str:
        return "mirage-token-provider"

    def __call__(self, config: Any) -> _OperationCredentials:
        return _OperationCredentials()


class _SdkDatabricksReadStream:

    def __init__(
        self,
        client: "SdkDatabricksFilesClient",
        contents: BinaryIO,
    ) -> None:
        self._client = client
        self._contents = contents

    async def read(self, size: int = -1) -> bytes:
        return await self._client._run_sdk(self._contents.read, size)

    async def close(self) -> None:
        await asyncio.to_thread(self._contents.close)


class SdkDatabricksFilesClient:

    def __init__(
        self,
        config: DatabricksVolumeConfig,
        token_provider: TokenProvider,
    ) -> None:
        self.config = config
        self.token_provider = token_provider
        self._workspace: Any | None = None

    @property
    def _workspace_client(self) -> Any:
        if self._workspace is None:
            if WorkspaceClient is None or WorkspaceConfig is None:
                raise ImportError("DatabricksVolumeResource requires the "
                                  "'databricks' extra. Install with: "
                                  "pip install mirage-ai[databricks]")
            strategy = _TokenProviderCredentialsStrategy()
            sdk_config = WorkspaceConfig(
                host=self.config.host,
                auth_type=strategy.auth_type(),
                credentials_strategy=strategy,
                http_timeout_seconds=self.config.timeout,
            )
            self._workspace = WorkspaceClient(config=sdk_config)
        return self._workspace

    async def _resolve_token(self) -> str:
        value = await asyncio.to_thread(self.token_provider.get_token)
        if inspect.isawaitable(value):
            value = await value
        if not isinstance(value, str) or not value:
            raise ValueError("token provider returned an empty token")
        return value

    async def _run_sdk(
        self,
        fn: Callable[..., T],
        *args: object,
        **kwargs: object,
    ) -> T:
        token = await self._resolve_token()
        marker = _operation_token.set(token)
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        finally:
            _operation_token.reset(marker)

    def _read_bytes_sync(
        self,
        path: str,
        range_header: str | None,
    ) -> bytes:
        if range_header is None:
            return _response_bytes(self._workspace_client.files.download(path))
        headers = {
            "Accept": "application/octet-stream",
            "Range": range_header,
        }
        workspace_id = getattr(self._workspace_client.config, "workspace_id",
                               None)
        if workspace_id:
            headers["X-Databricks-Org-Id"] = workspace_id
        response = self._workspace_client.api_client.do(
            "GET",
            f"/api/2.0/fs/files{quote(path)}",
            headers=headers,
            response_headers=[
                "content-length",
                "content-range",
                "accept-ranges",
                "content-type",
                "last-modified",
            ],
            raw=True,
        )
        return _response_bytes(response)

    def _list_directory_sync(self, path: str) -> list[object]:
        entries = self._workspace_client.files.list_directory_contents(path)
        return list(entries)

    async def read_bytes(
        self,
        path: str,
        range_header: str | None = None,
    ) -> bytes:
        return await self._run_sdk(self._read_bytes_sync, path, range_header)

    async def open_read(self, path: str) -> DatabricksReadStream:
        response = await self._run_sdk(
            self._workspace_client.files.download,
            path,
        )
        return _SdkDatabricksReadStream(self, _response_stream(response))

    async def get_metadata(self, path: str) -> object:
        return await self._run_sdk(
            self._workspace_client.files.get_metadata,
            path,
        )

    async def get_directory_metadata(self, path: str) -> object:
        return await self._run_sdk(
            self._workspace_client.files.get_directory_metadata,
            path,
        )

    async def list_directory(self, path: str) -> list[object]:
        return await self._run_sdk(self._list_directory_sync, path)

    async def upload(self, path: str, data: bytes) -> None:
        await self._run_sdk(
            self._workspace_client.files.upload,
            path,
            BytesIO(data),
            overwrite=True,
            use_parallel=False,
        )

    async def delete(self, path: str) -> None:
        await self._run_sdk(self._workspace_client.files.delete, path)

    async def create_directory(self, path: str) -> None:
        await self._run_sdk(
            self._workspace_client.files.create_directory,
            path,
        )

    async def delete_directory(self, path: str) -> None:
        await self._run_sdk(
            self._workspace_client.files.delete_directory,
            path,
        )
