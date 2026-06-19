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

import subprocess
import sys
import tempfile
import types

import pytest

from mirage.workspace.fuse import FuseManager


def _fail_mount_startup(*_args, **_kwargs):
    raise RuntimeError("fuse failed")


class TestFuseManager:

    def test_initial_state(self):
        fm = FuseManager()
        assert fm.mountpoint is None

    def test_set_mountpoint(self):
        fm = FuseManager()
        fm.mountpoint = "/tmp/test-fuse"
        assert fm.mountpoint == "/tmp/test-fuse"

    def test_close_without_auto_does_nothing(self):
        fm = FuseManager()
        fm.mountpoint = "/tmp/test-fuse"
        fm.close()
        assert fm.mountpoint == "/tmp/test-fuse"

    def test_close_without_mountpoint_does_nothing(self):
        fm = FuseManager()
        fm.close()
        assert fm.mountpoint is None

    def test_close_keeps_caller_owned_mountpoint(self, monkeypatch, tmp_path):
        # Regression: explicit mountpoints are caller-owned deployment paths.
        # close() should unmount FUSE, not remove the directory given by the
        # caller.
        fuse_mount = pytest.importorskip("mirage.fuse.mount")
        monkeypatch.setattr(fuse_mount, "mount_background",
                            lambda *_args, **_kwargs: None)
        monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: None)

        fm = FuseManager()
        fm.setup(object(), mountpoint=str(tmp_path))
        fm.close()

        assert tmp_path.exists()
        assert fm.mountpoint is None

    def test_close_removes_generated_mountpoint(self, monkeypatch, tmp_path):
        # Generated temp mountpoints are Mirage-owned, so close() removes the
        # directory it created with an empty-directory rmdir.
        fuse_mount = pytest.importorskip("mirage.fuse.mount")
        generated = tmp_path / "mirage-generated"
        generated.mkdir()
        monkeypatch.setattr(fuse_mount, "mount_background",
                            lambda *_args, **_kwargs: None)
        monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(tempfile, "mkdtemp",
                            lambda *_args, **_kwargs: str(generated))

        fm = FuseManager()
        fm.setup(object())
        fm.close()

        assert not generated.exists()
        assert fm.mountpoint is None

    def test_setup_cleans_generated_mountpoint_when_mount_startup_fails(
            self, monkeypatch, tmp_path):
        # Regression: if FUSE never starts, Mirage still owns the generated
        # temp mountpoint and should leave no stale manager state behind.
        generated = tmp_path / "mirage-generated"
        generated.mkdir()

        fake_mount = types.ModuleType("mirage.fuse.mount")
        fake_mount.mount_background = _fail_mount_startup
        monkeypatch.setitem(sys.modules, "mirage.fuse.mount", fake_mount)
        monkeypatch.setattr(tempfile, "mkdtemp",
                            lambda *_args, **_kwargs: str(generated))

        fm = FuseManager()
        with pytest.raises(RuntimeError, match="fuse failed"):
            fm.setup(object())

        assert not generated.exists()
        assert fm.mountpoint is None
