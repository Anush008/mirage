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

import importlib

import pytest

from mirage.accessor.s3 import S3Accessor
from mirage.resource.s3 import S3Config
from mirage.types import FileStat, FileType, PathSpec
from tests.integration.s3_mock import patch_s3_multi

copy_mod = importlib.import_module("mirage.core.s3.copy")

BUCKET = "test-bucket"


def _accessor() -> S3Accessor:
    return S3Accessor(S3Config(bucket=BUCKET, region="us-east-1"))


def _spec(name: str) -> PathSpec:
    return PathSpec(original=name, directory="/", prefix="", resolved=True)


class _BoomClient:

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def copy_object(self, **kwargs):
        raise AssertionError("copy_object must not run for a same-path copy")


class _BoomSession:

    def client(self, **kwargs):
        return _BoomClient()


async def _fake_stat_ok(accessor, path, index=None):
    return FileStat(name="a.txt", size=7, type=FileType.TEXT)


@pytest.mark.asyncio
async def test_copy_same_path_skips_client_calls(monkeypatch):
    # The guard short-circuits before touching the network: a self-copy on
    # real AWS is rejected outright (and is a no-op everywhere else).
    monkeypatch.setattr(copy_mod, "stat", _fake_stat_ok)
    monkeypatch.setattr(copy_mod, "async_session", lambda config: _BoomSession())
    await copy_mod.copy(_accessor(), _spec("/a.txt"), _spec("/a.txt"))


@pytest.mark.asyncio
async def test_copy_different_path_reaches_client(monkeypatch):
    # Sanity: the guard does not over-fire — a real copy still dispatches.
    monkeypatch.setattr(copy_mod, "stat", _fake_stat_ok)
    monkeypatch.setattr(copy_mod, "async_session", lambda config: _BoomSession())
    with pytest.raises(AssertionError):
        await copy_mod.copy(_accessor(), _spec("/a.txt"), _spec("/b.txt"))


@pytest.mark.asyncio
async def test_copy_missing_source_raises_after_stat():
    buckets = {BUCKET: {}}
    with patch_s3_multi(buckets):
        with pytest.raises(FileNotFoundError):
            await copy_mod.copy(_accessor(), _spec("/missing.txt"),
                                _spec("/missing.txt"))
