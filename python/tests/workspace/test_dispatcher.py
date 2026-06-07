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

from mirage.resource.ram.ram import RAMResource
from mirage.resource.redis.redis import RedisResource
from mirage.resource.s3.s3 import S3Resource
from mirage.workspace.dispatcher import _needs_staging, policy_for
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
