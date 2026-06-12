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

import os

import pytest
import pytest_asyncio

from mirage.observe.observer import Observer
from mirage.observe.redis_store import RedisObserverStore
from mirage.observe.store import ObserverStore

REDIS_URL = os.environ.get("REDIS_URL", "")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="REDIS_URL not set")


@pytest_asyncio.fixture()
async def store():
    s = RedisObserverStore(url=REDIS_URL, key_prefix="test:observer:")
    await s.clear()
    yield s
    await s.clear()


@pytest.mark.asyncio
async def test_append_creates_and_extends(store):
    await store.append("/d/s.jsonl", b"a\n")
    await store.append("/d/s.jsonl", b"b\n")
    files = await store.read_all()
    assert files == {"/d/s.jsonl": b"a\nb\n"}


@pytest.mark.asyncio
async def test_write_overwrites(store):
    await store.append("/d/s.jsonl", b"old\n")
    await store.write("/d/s.jsonl", b"new\n")
    files = await store.read_all()
    assert files == {"/d/s.jsonl": b"new\n"}


@pytest.mark.asyncio
async def test_clear_empties_namespace(store):
    await store.append("/d/a.jsonl", b"x\n")
    await store.append("/d/b.jsonl", b"y\n")
    await store.clear()
    assert await store.read_all() == {}


@pytest.mark.asyncio
async def test_observer_over_redis_round_trip(store):
    obs = Observer(store=store)
    await obs.log_clear(session="s1", agent="a")
    events = await obs.events()
    assert events[-1]["type"] == "clear"
    assert events[-1]["session"] == "s1"


def test_redis_store_satisfies_protocol():
    assert isinstance(
        RedisObserverStore(url=REDIS_URL, key_prefix="test:observer:"),
        ObserverStore)
