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
from mirage.types import PathSpec
from tests.integration.s3_mock import patch_s3_multi

rename_mod = importlib.import_module("mirage.core.s3.rename")

BUCKET = "test-bucket"


def _accessor() -> S3Accessor:
    return S3Accessor(S3Config(bucket=BUCKET, region="us-east-1"))


def _spec(name: str) -> PathSpec:
    return PathSpec(original=name, directory="/", prefix="", resolved=True)


@pytest.mark.asyncio
async def test_rename_same_path_preserves_file():
    # #150: copy_object onto the same key succeeds on lenient S3-compatible
    # stores, then the unconditional delete_object destroys the only copy.
    buckets = {BUCKET: {"a.txt": b"payload"}}
    with patch_s3_multi(buckets):
        await rename_mod.rename(_accessor(), _spec("/a.txt"), _spec("/a.txt"))
    assert buckets[BUCKET].get("a.txt") == b"payload"


@pytest.mark.asyncio
async def test_rename_missing_source_raises_after_stat():
    buckets = {BUCKET: {}}
    with patch_s3_multi(buckets):
        with pytest.raises(FileNotFoundError):
            await rename_mod.rename(_accessor(), _spec("/missing.txt"),
                                    _spec("/missing.txt"))


@pytest.mark.asyncio
async def test_rename_different_paths_still_moves():
    buckets = {BUCKET: {"a.txt": b"payload"}}
    with patch_s3_multi(buckets):
        await rename_mod.rename(_accessor(), _spec("/a.txt"), _spec("/b.txt"))
    assert "a.txt" not in buckets[BUCKET]
    assert buckets[BUCKET].get("b.txt") == b"payload"
