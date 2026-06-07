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

mv_mod = importlib.import_module("mirage.commands.builtin.s3.mv")


def _accessor() -> S3Accessor:
    return S3Accessor(S3Config(bucket="b"))


def _spec(name: str) -> PathSpec:
    return PathSpec(original=name, directory="/", prefix="", resolved=True)


async def _passthrough_glob(accessor, paths, index=None):
    return paths


@pytest.mark.asyncio
async def test_mv_same_path_errors_without_rename(monkeypatch):
    renamed = []

    async def fake_rename(accessor, src, dst):
        renamed.append((src, dst))

    monkeypatch.setattr(mv_mod, "resolve_glob", _passthrough_glob)
    monkeypatch.setattr(mv_mod, "rename", fake_rename)

    out, io = await mv_mod.mv(_accessor(), [_spec("/a.txt"), _spec("/a.txt")])

    assert io.exit_code == 1
    assert io.stderr.decode() == (
        "mv: '/a.txt' and '/a.txt' are the same file\n")
    assert renamed == []


@pytest.mark.asyncio
async def test_mv_different_path_still_renames(monkeypatch):
    renamed = []

    async def fake_rename(accessor, src, dst):
        renamed.append((src, dst))

    monkeypatch.setattr(mv_mod, "resolve_glob", _passthrough_glob)
    monkeypatch.setattr(mv_mod, "rename", fake_rename)

    out, io = await mv_mod.mv(_accessor(), [_spec("/a.txt"), _spec("/b.txt")])

    assert io.exit_code == 0
    assert len(renamed) == 1
