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

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from mirage.io import IOResult
from mirage.observe.context import push_branch, reset_branch
from mirage.resource.ram.ram import RAMResource
from mirage.resource.redis.redis import RedisResource
from mirage.resource.s3.s3 import S3Resource
from mirage.types import ConsistencyPolicy, PathSpec
from mirage.workspace.dispatcher import Dispatcher, _needs_staging, policy_for
from mirage.workspace.mount import Mount


def _mount(resource) -> Mount:
    return Mount("/m/", resource)


def test_needs_staging_ram_isolates_on_fork():
    mount = _mount(RAMResource())
    assert _needs_staging(mount) is False


def test_needs_staging_redis_shares_by_ref_despite_local():
    # is_remote=False yet share-by-ref, so it must still be staged. The
    # real RedisResource.__init__ connects to a live server; the gate
    # only inspects type(resource).fork, so a bare instance of the real
    # class proves the classification and keeps the test hermetic.
    resource = object.__new__(RedisResource)
    mount = _mount(resource)
    assert mount.resource.is_remote is False
    assert _needs_staging(mount) is True


def test_needs_staging_s3_remote_shares_by_ref():
    resource = object.__new__(S3Resource)
    mount = _mount(resource)
    assert mount.resource.is_remote is True
    assert _needs_staging(mount) is True


def test_policy_for_default_is_none():
    assert policy_for(_mount(RAMResource())) is None


class _FakeBranch:

    def __init__(self) -> None:
        self.reads: list[tuple] = []
        self.writes: list[tuple] = []

    async def staged_read(self, mount, path, **kwargs):
        self.reads.append((mount, path.original))
        return "staged", IOResult()

    async def divert_write(self, mount, op, path, **kwargs):
        self.writes.append((op, path.original))
        return "diverted", IOResult()


def _dispatcher_for(resource):
    mount = SimpleNamespace(prefix="/m/",
                            resource=resource,
                            execute_op=AsyncMock(return_value="live"))
    registry = SimpleNamespace(mount_for=Mock(return_value=mount))
    cache = SimpleNamespace(get=AsyncMock(return_value=None))
    disp = Dispatcher(registry, cache, ConsistencyPolicy.LAZY)
    return disp, mount


def _path(p: str) -> PathSpec:
    return PathSpec(original=p,
                    directory=p.rsplit("/", 1)[0] or "/",
                    resolved=True)


@pytest.mark.asyncio
async def test_bound_branch_routes_read_to_staged_read():
    branch = _FakeBranch()
    disp, mount = _dispatcher_for(object.__new__(RedisResource))
    token = push_branch(branch)
    try:
        result, _ = await disp.dispatch("read_bytes", _path("/m/a.txt"))
    finally:
        reset_branch(token)
    assert branch.reads == [(mount, "/m/a.txt")]
    assert branch.writes == []
    assert result == "staged"
    mount.execute_op.assert_not_awaited()


@pytest.mark.asyncio
async def test_bound_branch_diverts_write():
    branch = _FakeBranch()
    disp, mount = _dispatcher_for(object.__new__(RedisResource))
    token = push_branch(branch)
    try:
        result, _ = await disp.dispatch("write", _path("/m/a.txt"), data=b"x")
    finally:
        reset_branch(token)
    assert branch.writes == [("write", "/m/a.txt")]
    assert branch.reads == []
    assert result == "diverted"
    mount.execute_op.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_vocab_op_falls_through_to_live():
    branch = _FakeBranch()
    disp, mount = _dispatcher_for(object.__new__(RedisResource))
    token = push_branch(branch)
    try:
        result, _ = await disp.dispatch("stat", _path("/m/a.txt"))
    finally:
        reset_branch(token)
    assert branch.reads == []
    assert branch.writes == []
    mount.execute_op.assert_awaited_once_with("stat", "/m/a.txt")
    assert result == "live"


@pytest.mark.asyncio
async def test_isolating_mount_bypasses_branch_even_for_read():
    branch = _FakeBranch()
    disp, mount = _dispatcher_for(RAMResource())
    token = push_branch(branch)
    try:
        result, _ = await disp.dispatch("read_bytes", _path("/m/a.txt"))
    finally:
        reset_branch(token)
    assert branch.reads == []
    assert branch.writes == []
    mount.execute_op.assert_awaited_once_with("read_bytes", "/m/a.txt")
    assert result == "live"
