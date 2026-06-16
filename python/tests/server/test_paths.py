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

from mirage.server.paths import (PathOutsideRootError, resolve_within_root,
                                 validate_path_segment)


def test_resolve_within_root_relative(tmp_path):
    out = resolve_within_root(tmp_path, "seed.tar")
    assert out == (tmp_path / "seed.tar")


def test_resolve_within_root_absolute_inside(tmp_path):
    inside = tmp_path / "nested" / "a.tar"
    assert resolve_within_root(tmp_path, str(inside)) == inside


def test_resolve_within_root_returns_root(tmp_path):
    assert resolve_within_root(tmp_path, ".") == tmp_path


def test_resolve_within_root_rejects_traversal(tmp_path):
    with pytest.raises(PathOutsideRootError):
        resolve_within_root(tmp_path, "../../etc/passwd")


def test_resolve_within_root_rejects_absolute_outside(tmp_path):
    with pytest.raises(PathOutsideRootError):
        resolve_within_root(tmp_path, "/etc/passwd")


def test_resolve_within_root_rejects_sibling_prefix(tmp_path):
    sibling = str(tmp_path) + "-evil"
    with pytest.raises(PathOutsideRootError):
        resolve_within_root(tmp_path, sibling)


def test_validate_path_segment_accepts_safe():
    assert validate_path_segment("ws_abc123") == "ws_abc123"
    assert validate_path_segment("a.b-c_d") == "a.b-c_d"


@pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "a\\b", "a b", "a$b"])
def test_validate_path_segment_rejects_bad(bad):
    with pytest.raises(PathOutsideRootError):
        validate_path_segment(bad)
