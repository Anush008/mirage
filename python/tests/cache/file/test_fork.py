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

import pytest

from mirage.cache.file.ram import RAMFileCacheStore


def test_cache_fork_fresh_drain_tasks_and_size():
    live = RAMFileCacheStore()
    staged = live.fork()
    assert staged.cache_size == live.cache_size
    assert staged._drain_tasks is not live._drain_tasks
    assert staged._drain_tasks == {}
    assert staged._entries is not live._entries


@pytest.mark.asyncio
async def test_cache_fork_payload_shared_then_isolated():
    live = RAMFileCacheStore()
    await live.set("/a", b"hello")
    staged = live.fork()
    assert await staged.get("/a") == b"hello"
    assert staged._store.files["/a"] is live._store.files["/a"]

    await staged.set("/a", b"world")
    assert await live.get("/a") == b"hello"
    assert await staged.get("/a") == b"world"

    await staged.remove("/a")
    assert await live.get("/a") == b"hello"

    await staged.set("/b", b"x")
    assert await live.get("/b") is None


@pytest.mark.asyncio
async def test_cache_fork_size_accounting_diverges():
    live = RAMFileCacheStore()
    await live.set("/a", b"hello")
    base = live.cache_size
    staged = live.fork()
    await staged.set("/b", b"world")
    assert staged.cache_size > base
    assert live.cache_size == base


def test_redis_cache_fork_raises():
    pytest.importorskip("redis")
    from mirage.cache.file.redis import RedisFileCacheStore

    # fork() refuses before any I/O, so call the unbound method with a
    # dummy self to exercise the contract without a live Redis server.
    with pytest.raises(NotImplementedError):
        RedisFileCacheStore.fork(object())
