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

from pathlib import Path

from mirage.accessor.disk import DiskAccessor
from mirage.accessor.ram import RAMAccessor
from mirage.accessor.s3 import S3Accessor
from mirage.core._shared.path_guard import (backend_identity,
                                             same_backend_file)
from mirage.resource.ram.store import RAMStore
from mirage.resource.s3 import S3Config
from mirage.types import PathSpec


def _spec(name: str) -> PathSpec:
    return PathSpec(original=name, directory="/", prefix="", resolved=True)


def _s3(bucket: str = "b", **kw) -> S3Accessor:
    return S3Accessor(S3Config(bucket=bucket, **kw))


def test_s3_same_key_is_same():
    acc = _s3()
    assert same_backend_file(acc, _spec("/a.txt"), _spec("/a.txt"))


def test_s3_different_key_is_not_same():
    acc = _s3()
    assert not same_backend_file(acc, _spec("/a.txt"), _spec("/b.txt"))


def test_s3_normalizes_dot_and_separators():
    acc = _s3()
    assert same_backend_file(acc, _spec("/./a.txt"), _spec("/a.txt"))
    assert same_backend_file(acc, _spec("/dir//a.txt"), _spec("/dir/a.txt"))
    assert same_backend_file(acc, _spec("/dir/../a.txt"), _spec("/a.txt"))


def test_s3_key_prefix_applied():
    acc = _s3(key_prefix="team")
    assert backend_identity(acc, _spec("/a.txt"))[-1] == "team/a.txt"


def test_s3_different_bucket_is_not_same():
    assert backend_identity(_s3("one"), _spec("/a")) != backend_identity(
        _s3("two"), _spec("/a"))


def test_s3_different_endpoint_is_not_same():
    a = _s3("b", endpoint_url="https://one.example")
    b = _s3("b", endpoint_url="https://two.example")
    assert backend_identity(a, _spec("/a")) != backend_identity(b, _spec("/a"))


def test_s3_same_bucket_mounted_twice_is_same():
    # "the same bucket mounted twice" — distinct accessor objects, one store.
    a = _s3("shared", endpoint_url="https://r2.example")
    b = _s3("shared", endpoint_url="https://r2.example")
    assert backend_identity(a, _spec("/x")) == backend_identity(b, _spec("/x"))


def test_disk_same_root_same_relative_is_same():
    # "two disk mounts rooted at the same directory".
    a = DiskAccessor(Path("/srv/data"))
    b = DiskAccessor(Path("/srv/data"))
    assert backend_identity(a, _spec("/x")) == backend_identity(b, _spec("/x"))


def test_disk_different_root_is_not_same():
    a = DiskAccessor(Path("/srv/one"))
    b = DiskAccessor(Path("/srv/two"))
    assert backend_identity(a, _spec("/x")) != backend_identity(b, _spec("/x"))


def test_disk_normalizes_within_root():
    acc = DiskAccessor(Path("/srv/data"))
    assert same_backend_file(acc, _spec("/dir/../x"), _spec("/x"))


def test_store_shared_across_accessors_is_same():
    # "two ram/redis mounts sharing one store".
    store = RAMStore()
    a = RAMAccessor(store)
    b = RAMAccessor(store)
    assert backend_identity(a, _spec("/x")) == backend_identity(b, _spec("/x"))


def test_store_distinct_stores_is_not_same():
    a = RAMAccessor(RAMStore())
    b = RAMAccessor(RAMStore())
    assert backend_identity(a, _spec("/x")) != backend_identity(b, _spec("/x"))
