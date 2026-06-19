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
import sys
import types

import pytest


def _fail_mount(*_args, **_kwargs):
    raise RuntimeError("fuse failed")


def _load_mount_module(monkeypatch):
    fake_fuse = types.SimpleNamespace(FUSE=_fail_mount, Operations=object)
    monkeypatch.setitem(sys.modules, "mfusepy", fake_fuse)
    sys.modules.pop("mirage.fuse.mount", None)
    sys.modules.pop("mirage.fuse.fs", None)
    return importlib.import_module("mirage.fuse.mount")


def test_mount_background_propagates_worker_startup_exception(
        monkeypatch, tmp_path):
    # Regression: startup errors happen in the worker thread, but callers need
    # them synchronously so setup can fail and clean up generated mountpoints.
    fuse_mount = _load_mount_module(monkeypatch)
    monkeypatch.setattr(fuse_mount, "MirageFS",
                        lambda *_args, **_kwargs: object())

    try:
        with pytest.raises(RuntimeError, match="fuse failed"):
            fuse_mount.mount_background(object(), str(tmp_path))
    finally:
        sys.modules.pop("mirage.fuse.mount", None)
        sys.modules.pop("mirage.fuse.fs", None)
