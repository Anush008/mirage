import asyncio
from contextvars import ContextVar
from io import BytesIO
from types import SimpleNamespace

import pytest

from mirage.core.databricks_volume import client as client_module
from mirage.core.databricks_volume.client import SdkDatabricksFilesClient
from mirage.resource.databricks_volume import (DatabricksVolumeConfig,
                                               StaticTokenProvider)

current_token: ContextVar[str] = ContextVar("current_token")


class AsyncRotatingProvider:

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = iter(tokens)

    async def get_token(self) -> str:
        await asyncio.sleep(0)
        return next(self._tokens)


class ContextTokenProvider:

    def get_token(self) -> str:
        return current_token.get()


class FakeWorkspaceConfig:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.calls.append(kwargs)
        self._header_factory = kwargs["credentials_strategy"](self)

    def authenticate(self) -> dict[str, str]:
        return self._header_factory()


class FakeSdkFiles:

    def __init__(self, config: FakeWorkspaceConfig) -> None:
        self._config = config
        self.auth_calls: list[tuple[str, str]] = []
        self.calls: list[tuple] = []
        self.uploaded: bytes | None = None

    def _authorize(self, operation: str) -> None:
        authorization = self._config.authenticate()["Authorization"]
        self.auth_calls.append((operation, authorization))

    def download(self, path: str) -> object:
        self._authorize(path)
        self.calls.append(("download", path))
        return SimpleNamespace(contents=FakeSdkStream(self._config,
                                                      b"payload"), )

    def get_metadata(self, path: str) -> object:
        self._authorize(path)
        self.calls.append(("get_metadata", path))
        return SimpleNamespace(
            path=path,
            is_directory=False,
            file_size=1,
            modification_time=2,
        )

    def get_directory_metadata(self, path: str) -> None:
        self._authorize(path)
        self.calls.append(("get_directory_metadata", path))

    def list_directory_contents(self, path: str):
        self.calls.append(("list_directory_contents", path))
        return self._directory_entries(path)

    def _directory_entries(self, path: str):
        self._authorize(path)
        yield SimpleNamespace(
            path=f"{path}/report.md",
            is_directory=False,
            file_size=7,
        )

    def upload(
        self,
        path: str,
        contents,
        *,
        overwrite: bool = False,
        use_parallel: bool = True,
    ) -> None:
        self._authorize(path)
        self.uploaded = contents.read()
        self.calls.append(("upload", path, overwrite, use_parallel))

    def delete(self, path: str) -> None:
        self._authorize(path)
        self.calls.append(("delete", path))

    def create_directory(self, path: str) -> None:
        self._authorize(path)
        self.calls.append(("create_directory", path))

    def delete_directory(self, path: str) -> None:
        self._authorize(path)
        self.calls.append(("delete_directory", path))


class FakeSdkStream:

    def __init__(self, config: FakeWorkspaceConfig, data: bytes) -> None:
        self._config = config
        self._contents = BytesIO(data)

    def read(self, size: int = -1) -> bytes:
        self._config.authenticate()
        return self._contents.read(size)

    def close(self) -> None:
        self._contents.close()


class FakeApiClient:

    def __init__(self, config: FakeWorkspaceConfig) -> None:
        self._config = config
        self.calls: list[dict] = []

    def do(self, method: str, path: str, **kwargs) -> dict:
        authorization = self._config.authenticate()["Authorization"]
        self.calls.append({
            "method": method,
            "path": path,
            "authorization": authorization,
            **kwargs,
        })
        return {
            "contents": BytesIO(b"ayl"),
            "content-length": "3",
            "content-range": "bytes 1-3/7",
            "accept-ranges": "bytes",
        }


class FakeWorkspaceClient:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.calls.append(kwargs)
        self.config = kwargs["config"]
        self.files = FakeSdkFiles(self.config)
        self.api_client = FakeApiClient(self.config)


def _config() -> DatabricksVolumeConfig:
    return DatabricksVolumeConfig(
        host="https://example.cloud.databricks.com",
        catalog="main",
        schema="default",
        volume="documents",
        timeout=17,
    )


async def _get_metadata_with_token(
    client: SdkDatabricksFilesClient,
    path: str,
    token: str,
) -> None:
    marker = current_token.set(token)
    try:
        await client.get_metadata(path)
    finally:
        current_token.reset(marker)


@pytest.fixture(autouse=True)
def fake_sdk(monkeypatch):
    FakeWorkspaceConfig.calls = []
    FakeWorkspaceClient.calls = []
    monkeypatch.setattr(
        client_module,
        "WorkspaceConfig",
        FakeWorkspaceConfig,
        raising=False,
    )
    monkeypatch.setattr(
        client_module,
        "WorkspaceClient",
        FakeWorkspaceClient,
        raising=False,
    )


@pytest.mark.asyncio
async def test_sdk_client_resolves_async_provider_for_each_operation():
    client = SdkDatabricksFilesClient(
        _config(),
        AsyncRotatingProvider(["token-a", "token-b"]),
    )

    await client.get_metadata("/a")
    await client.get_metadata("/b")

    sdk_config = FakeWorkspaceConfig.calls[0]
    assert sdk_config["host"] == "https://example.cloud.databricks.com"
    assert sdk_config["http_timeout_seconds"] == 17
    assert sdk_config["auth_type"] == "mirage-token-provider"
    assert "token" not in sdk_config
    assert "profile" not in sdk_config
    assert client._workspace_client.files.auth_calls == [
        ("/a", "Bearer token-a"),
        ("/b", "Bearer token-b"),
    ]


@pytest.mark.asyncio
async def test_sdk_client_keeps_concurrent_operation_tokens_isolated():
    client = SdkDatabricksFilesClient(_config(), ContextTokenProvider())

    await asyncio.gather(
        _get_metadata_with_token(client, "/a", "token-a"),
        _get_metadata_with_token(client, "/b", "token-b"),
    )

    sdk_files = client._workspace_client.files
    assert sorted(sdk_files.auth_calls) == [
        ("/a", "Bearer token-a"),
        ("/b", "Bearer token-b"),
    ]


@pytest.mark.asyncio
async def test_sdk_client_maps_files_api_operations():
    client = SdkDatabricksFilesClient(
        _config(),
        StaticTokenProvider("token"),
    )

    assert await client.read_bytes("/file") == b"payload"
    assert await client.read_bytes("/file", "bytes=1-3") == b"ayl"
    stream = await client.open_read("/file")
    assert await stream.read() == b"payload"
    await stream.close()
    assert (await client.get_metadata("/file")).file_size == 1
    assert await client.get_directory_metadata("/dir") is None
    entries = await client.list_directory("/dir")
    assert [entry.path for entry in entries] == ["/dir/report.md"]
    await client.upload("/new", b"new")
    await client.delete("/file")
    await client.create_directory("/new-dir")
    await client.delete_directory("/old-dir")

    workspace = client._workspace_client
    assert workspace.files.uploaded == b"new"
    assert ("upload", "/new", True, False) in workspace.files.calls
    assert workspace.api_client.calls == [{
        "method":
        "GET",
        "path":
        "/api/2.0/fs/files/file",
        "authorization":
        "Bearer token",
        "headers": {
            "Accept": "application/octet-stream",
            "Range": "bytes=1-3",
        },
        "response_headers": [
            "content-length",
            "content-range",
            "accept-ranges",
            "content-type",
            "last-modified",
        ],
        "raw":
        True,
    }]


@pytest.mark.asyncio
async def test_sdk_client_rejects_empty_token():
    client = SdkDatabricksFilesClient(
        _config(),
        StaticTokenProvider(""),
    )

    with pytest.raises(ValueError, match="empty token"):
        await client.get_metadata("/file")


@pytest.mark.asyncio
async def test_sdk_stream_read_reestablishes_operation_token():
    client = SdkDatabricksFilesClient(
        _config(),
        AsyncRotatingProvider(["open-token", "read-token"]),
    )

    stream = await client.open_read("/file")

    assert await stream.read() == b"payload"
    await stream.close()
