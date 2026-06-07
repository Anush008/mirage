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

import asyncio

from mirage.accessor.ram import RAMAccessor
from mirage.resource.ram import RAMResource
from mirage.types import MountMode
from mirage.workspace import Workspace


def _aliased_ws():
    # Two distinct mounts whose accessors share one backing store — the #154
    # alias (e.g. the same ram store mounted twice). mv /a/x /b/x then resolves
    # to a single physical object.
    ram1 = RAMResource()
    ram2 = RAMResource()
    ram1._store.files["/x.txt"] = b"keepme"
    ram2._store = ram1._store
    ram2.accessor = RAMAccessor(ram1._store)
    return Workspace({
        "/a/": (ram1, MountMode.WRITE),
        "/b/": (ram2, MountMode.WRITE),
    })


def _distinct_ws():
    ram1 = RAMResource()
    ram2 = RAMResource()
    ram1._store.files["/x.txt"] = b"keepme"
    return Workspace({
        "/a/": (ram1, MountMode.WRITE),
        "/b/": (ram2, MountMode.WRITE),
    }), ram1, ram2


def _run(ws, cmd):

    async def _inner():
        io = await ws.execute(cmd)
        return await io.stdout_str(), await io.stderr_str(), io.exit_code

    return asyncio.run(_inner())


def test_cross_mv_same_backend_object_preserves_file():
    ws = _aliased_ws()
    out, err, code = _run(ws, "mv /a/x.txt /b/x.txt")
    assert code == 1
    assert "are the same file" in err
    # The only copy must survive: no unlink ran.
    cat_out, _, cat_code = _run(ws, "cat /a/x.txt")
    assert cat_code == 0
    assert cat_out == "keepme"


def test_cross_cp_same_backend_object_errors():
    ws = _aliased_ws()
    out, err, code = _run(ws, "cp /a/x.txt /b/x.txt")
    assert code == 1
    assert "cp:" in err
    assert "are the same file" in err
    cat_out, _, cat_code = _run(ws, "cat /a/x.txt")
    assert cat_code == 0
    assert cat_out == "keepme"


def test_cross_mv_distinct_backends_still_moves():
    ws, ram1, ram2 = _distinct_ws()
    out, err, code = _run(ws, "mv /a/x.txt /b/y.txt")
    assert code == 0
    assert ram2._store.files.get("/y.txt") == b"keepme"
    assert "/x.txt" not in ram1._store.files
