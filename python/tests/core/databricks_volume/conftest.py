import posixpath
from io import BytesIO
from types import SimpleNamespace

import pytest

from mirage.accessor.databricks_volume import DatabricksVolumeAccessor
from mirage.cache.index import RAMIndexCacheStore
from mirage.core.databricks_volume.path import backend_path
from mirage.resource.databricks_volume import DatabricksVolumeConfig


class NotFoundError(Exception):
    status_code = 404


class FakeDownload:

    def __init__(self, data: bytes) -> None:
        self.contents = BytesIO(data)


class FakeFiles:

    def __init__(self) -> None:
        self.downloads: dict[str, bytes] = {}
        self.metadata: dict[str, object] = {}
        self.directory_metadata: set[str] = set()
        self.directories: dict[str, list[object]] = {}
        self.metadata_errors: dict[str, Exception] = {}
        self.directory_metadata_errors: dict[str, Exception] = {}
        self.download_calls: list[str] = []
        self.get_metadata_calls: list[str] = []
        self.get_directory_metadata_calls: list[str] = []
        self.list_directory_calls: list[str] = []
        self.upload_calls: list[tuple[str, bytes, bool]] = []
        self.delete_calls: list[str] = []
        self.create_directory_calls: list[str] = []
        self.delete_directory_calls: list[str] = []

    def download(self, path: str) -> FakeDownload:
        self.download_calls.append(path)
        if path not in self.downloads:
            raise NotFoundError(path)
        return FakeDownload(self.downloads[path])

    def get_metadata(self, path: str) -> object:
        self.get_metadata_calls.append(path)
        if path in self.metadata_errors:
            raise self.metadata_errors[path]
        if path not in self.metadata:
            raise NotFoundError(path)
        return self.metadata[path]

    def get_directory_metadata(self, path: str) -> None:
        self.get_directory_metadata_calls.append(path)
        if path in self.directory_metadata_errors:
            raise self.directory_metadata_errors[path]
        if path not in self.directory_metadata:
            raise NotFoundError(path)

    def list_directory_contents(self, path: str) -> list[object]:
        self.list_directory_calls.append(path)
        if path not in self.directories:
            raise NotFoundError(path)
        return self.directories[path]

    def create_directory(self, path: str) -> None:
        self.create_directory_calls.append(path)
        cur = ""
        for part in path.strip("/").split("/"):
            cur = cur + "/" + part
            if cur in self.directory_metadata:
                continue
            self.directory_metadata.add(cur)
            self.metadata[cur] = SimpleNamespace(is_directory=True)
            self.directories.setdefault(cur, [])
            parent = posixpath.dirname(cur) or "/"
            self._upsert_directory_entry(
                parent, SimpleNamespace(path=cur, is_directory=True))

    def delete_directory(self, path: str) -> None:
        self.delete_directory_calls.append(path)
        if path not in self.directory_metadata:
            raise NotFoundError(path)
        if self.directories.get(path):
            raise OSError(f"directory not empty: {path}")
        self.directory_metadata.discard(path)
        self.metadata.pop(path, None)
        self.directories.pop(path, None)
        parent = posixpath.dirname(path.rstrip("/")) or "/"
        self.directories[parent] = [
            entry for entry in self.directories.get(parent, [])
            if getattr(entry, "path", None) != path
        ]

    def upload(self, path: str, contents, overwrite: bool = False) -> None:
        data = contents.read()
        self.upload_calls.append((path, data, overwrite))
        parent = posixpath.dirname(path.rstrip("/")) or "/"
        if parent not in self.directory_metadata:
            if parent in self.metadata:
                raise NotADirectoryError(parent)
            raise NotFoundError(parent)
        if path in self.directory_metadata:
            raise IsADirectoryError(path)
        self.downloads[path] = data
        self.metadata[path] = file_metadata(len(data))
        self._upsert_directory_entry(parent, file_entry(path, len(data)))

    def delete(self, path: str) -> None:
        self.delete_calls.append(path)
        if path in self.directory_metadata:
            raise IsADirectoryError(path)
        if path not in self.metadata and path not in self.downloads:
            raise NotFoundError(path)
        self.metadata.pop(path, None)
        self.downloads.pop(path, None)
        parent = posixpath.dirname(path.rstrip("/")) or "/"
        self.directories[parent] = [
            entry for entry in self.directories.get(parent, [])
            if getattr(entry, "path", None) != path
        ]

    def _upsert_directory_entry(self, parent: str, entry: object) -> None:
        entries = [
            existing for existing in self.directories.get(parent, [])
            if getattr(existing, "path", None) != getattr(entry, "path", None)
        ]
        entries.append(entry)
        self.directories[parent] = sorted(
            entries, key=lambda item: getattr(item, "path", ""))


def _apply_range_header(data: bytes, range_header: str) -> bytes:
    if not range_header.startswith("bytes="):
        raise ValueError(f"unsupported range header: {range_header}")
    start_text, end_text = range_header.removeprefix("bytes=").split("-", 1)
    start = int(start_text) if start_text else 0
    end = int(end_text) + 1 if end_text else None
    return data[start:end]


class FakeDatabricksFilesClient:

    def __init__(self, files: FakeFiles) -> None:
        self.files = files
        self.read_calls: list[tuple[str, str | None]] = []

    async def read_bytes(
        self,
        path: str,
        range_header: str | None = None,
    ) -> bytes:
        self.read_calls.append((path, range_header))
        response = self.files.download(path)
        payload = response.contents.read()
        if range_header is not None:
            payload = _apply_range_header(payload, range_header)

        return payload

    async def open_read(self, path: str):
        return FakeReadStream(self.files.download(path).contents)

    async def get_metadata(self, path: str) -> object:
        return self.files.get_metadata(path)

    async def get_directory_metadata(self, path: str) -> object:
        return self.files.get_directory_metadata(path)

    async def list_directory(self, path: str) -> list[object]:
        return list(self.files.list_directory_contents(path))

    async def upload(self, path: str, data: bytes) -> None:
        self.files.upload(path, BytesIO(data), overwrite=True)

    async def delete(self, path: str) -> None:
        self.files.delete(path)

    async def create_directory(self, path: str) -> None:
        self.files.create_directory(path)

    async def delete_directory(self, path: str) -> None:
        self.files.delete_directory(path)


class FakeReadStream:

    def __init__(self, contents) -> None:
        self.contents = contents

    async def read(self, size: int = -1) -> bytes:
        return self.contents.read(size)

    async def close(self) -> None:
        self.contents.close()


@pytest.fixture
def databricks_config() -> DatabricksVolumeConfig:
    return DatabricksVolumeConfig(
        host="https://example.cloud.databricks.com",
        catalog="main",
        schema="default",
        volume="agent_files",
        root_path="/root",
    )


@pytest.fixture
def remote_root(databricks_config: DatabricksVolumeConfig) -> str:
    return backend_path(databricks_config, "/")


@pytest.fixture
def files() -> FakeFiles:
    return FakeFiles()


@pytest.fixture
def accessor(
    databricks_config: DatabricksVolumeConfig,
    files: FakeFiles,
) -> DatabricksVolumeAccessor:
    return DatabricksVolumeAccessor(
        databricks_config,
        FakeDatabricksFilesClient(files),
    )


@pytest.fixture
def index() -> RAMIndexCacheStore:
    return RAMIndexCacheStore(ttl=600)


def file_metadata(size: int = 0, modified: int | None = None) -> object:
    return SimpleNamespace(
        is_directory=False,
        file_size=size,
        modification_time=modified,
    )


def directory_entry(path: str) -> object:
    return SimpleNamespace(path=path, is_directory=True, file_size=None)


def file_entry(path: str, size: int = 0) -> object:
    return SimpleNamespace(path=path, is_directory=False, file_size=size)
