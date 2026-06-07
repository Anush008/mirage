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

from mirage.resource.base import BaseResource
from mirage.resource.ram import RAMResource
from mirage.resource.ram.store import RAMStore


def test_store_fork_shares_payload_by_reference():
    live = RAMStore(files={"/a": b"hello"},
                    dirs={"/", "/d"},
                    modified={"/a": "t"})
    staged = live.fork()
    assert staged.files["/a"] is live.files["/a"]
    assert staged.dirs == live.dirs
    assert staged.modified == live.modified


def test_store_fork_write_isolates():
    live = RAMStore(files={"/a": b"hello"})
    staged = live.fork()
    staged.files["/a"] = b"world"
    staged.files["/b"] = b"new"
    assert live.files["/a"] == b"hello"
    assert "/b" not in live.files


def test_store_fork_delete_isolates():
    live = RAMStore(files={"/a": b"hello"})
    staged = live.fork()
    del staged.files["/a"]
    assert "/a" in live.files


def test_store_fork_dirs_isolate():
    live = RAMStore(dirs={"/"})
    staged = live.fork()
    staged.dirs.add("/sub")
    assert "/sub" not in live.dirs


def test_resource_fork_independent_store_and_index():
    live = RAMResource()
    staged = live.fork()
    assert staged._store is not live._store
    assert staged.accessor.store is staged._store
    assert staged.index is not live.index


def test_resource_fork_shares_bytes_then_isolates():
    live = RAMResource()
    live._store.files["/a"] = b"hello"
    staged = live.fork()
    assert staged._store.files["/a"] is live._store.files["/a"]
    staged._store.files["/a"] = b"bye"
    assert live._store.files["/a"] == b"hello"


def test_base_resource_fork_shares_by_reference():
    r = BaseResource()
    assert r.fork() is r
