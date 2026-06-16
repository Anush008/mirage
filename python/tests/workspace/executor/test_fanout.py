import asyncio
from types import SimpleNamespace

from mirage.resource.ram import RAMResource
from mirage.types import MountMode
from mirage.workspace import Workspace
from mirage.workspace.executor.fanout import (_adjust_depth_texts,
                                              _synthesize_find_mount_entries)


def _mounts(*prefixes):
    return [SimpleNamespace(prefix=p) for p in prefixes]


def test_synthesize_no_expression_emits_all():
    desc = _mounts("/ram/", "/disk/")
    assert _synthesize_find_mount_entries("/", desc, []) == "/ram\n/disk"


def test_synthesize_positive_name():
    desc = _mounts("/ram/", "/disk/")
    assert _synthesize_find_mount_entries("/", desc,
                                          ["-name", "ram"]) == "/ram"


def test_synthesize_honors_not():
    desc = _mounts("/ram/", "/disk/", "/notes/")
    out = _synthesize_find_mount_entries("/", desc, ["-not", "-name", "ram"])
    assert out == "/disk\n/notes"


def test_synthesize_honors_or():
    desc = _mounts("/ram/", "/disk/", "/notes/")
    out = _synthesize_find_mount_entries(
        "/", desc, ["-name", "ram", "-o", "-name", "disk"])
    assert out == "/ram\n/disk"


def test_synthesize_type_file_excludes_mount_dirs():
    desc = _mounts("/ram/", "/disk/")
    assert _synthesize_find_mount_entries("/", desc, ["-type", "f"]) == ""


def test_synthesize_type_dir_includes_mount_dirs():
    desc = _mounts("/ram/", "/disk/")
    assert _synthesize_find_mount_entries("/", desc,
                                          ["-type", "d"]) == "/ram\n/disk"


def test_synthesize_maxdepth_window():
    desc = _mounts("/ram/", "/a/b/")
    assert _synthesize_find_mount_entries("/", desc,
                                          ["-maxdepth", "1"]) == "/ram"


def test_adjust_depth_texts_reduces_maxdepth_by_delta():
    out = _adjust_depth_texts(["-maxdepth", "3", "-name", "x"], "/",
                              "/data/sub")
    assert out == ["-maxdepth", "1", "-name", "x"]


def test_adjust_depth_texts_clamps_mindepth_at_zero():
    out = _adjust_depth_texts(["-mindepth", "1"], "/", "/data")
    assert out == ["-mindepth", "0"]


def test_adjust_depth_texts_no_depth_tokens_unchanged():
    out = _adjust_depth_texts(["-name", "x", "-o", "-name", "y"], "/", "/data")
    assert out == ["-name", "x", "-o", "-name", "y"]


def test_adjust_depth_texts_same_mount_unchanged():
    assert _adjust_depth_texts(["-maxdepth", "3"], "/data",
                               "/data") == ["-maxdepth", "3"]


def test_maxdepth_applies_to_child_mount_depth_end_to_end():
    parent = RAMResource()
    child = RAMResource()
    child._store.dirs.add("/a")
    child._store.files["/a/b.txt"] = b"deep\n"
    ws = Workspace(resources={
        "/": (parent, MountMode.EXEC),
        "/data/": (child, MountMode.EXEC),
    }, )
    io = asyncio.run(ws.execute("find / -maxdepth 2"))
    out = (io.stdout if isinstance(io.stdout, bytes) else b"").decode()
    assert "/data/a" in out
    assert "/data/a/b.txt" not in out
