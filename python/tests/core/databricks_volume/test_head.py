import pytest

from mirage.commands.builtin.databricks_volume.head import head
from mirage.types import PathSpec


async def collect_bytes(source) -> bytes:
    return b"".join([chunk async for chunk in source])


@pytest.mark.asyncio
async def test_head_bytes_mode_uses_single_small_range_request(
    accessor,
    files,
    remote_root,
):
    files.downloads[f"{remote_root}/reports/latest.md"] = b"abcdef"
    path = PathSpec.from_str_path("/volume/reports/latest.md", "/volume")

    source, _io = await head(accessor, [path], c="3")

    assert await collect_bytes(source) == b"abc"
    assert accessor.client.read_calls == [(f"{remote_root}/reports/latest.md",
                                           "bytes=0-2")]
