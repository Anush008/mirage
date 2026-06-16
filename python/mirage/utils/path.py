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

import posixpath


def norm(path: str) -> str:
    """Normalize a virtual path to a leading-slash, no-trailing-slash key.

    Args:
        path: A virtual path string.

    Returns:
        The path with surrounding slashes collapsed to a single leading
        slash (``"foo/bar/"`` -> ``"/foo/bar"``, ``""`` -> ``"/"``).
    """
    return "/" + path.strip("/")


def parent(path: str) -> str:
    """Return the parent directory of a normalized virtual key.

    Args:
        path: A normalized virtual path (leading slash, no trailing slash).

    Returns:
        The path with its last segment removed (``"/a/b"`` -> ``"/a"``),
        or ``"/"`` when there is no parent segment.
    """
    i = path.rfind("/")
    return path[:i] if i > 0 else "/"


def resolve_path(path: str, cwd: str) -> str:
    """Resolve a relative path against cwd.

    Example::

        resolve_path("../file.txt", "/data/sub/")
            → "/data/file.txt"
        resolve_path("/abs/path", "/ignored")
            → "/abs/path"
    """
    if not path.startswith("/"):
        path = cwd.rstrip("/") + "/" + path
    return posixpath.normpath(path)


def expand_tilde(word: str, home: str) -> str:
    """Expand a leading ``~`` against the home directory.

    ``~`` alone or ``~/rest`` expands to ``home`` (or ``home/rest``).
    ``~user`` and any non-leading ``~`` are left unchanged, matching
    bash behavior when no matching user exists.

    Args:
        word: The unexpanded word.
        home: The home directory to substitute for ``~``.

    Returns:
        The word with a leading ``~`` resolved, or the word unchanged.
    """
    if word == "~":
        return home
    if word.startswith("~/"):
        return home.rstrip("/") + word[1:]
    return word


def rebase_display(paths: list[str], original: str,
                   display: str | None) -> list[str]:
    """Rewrite the base of walked output paths to the as-typed form.

    Used by walkers like ``find``: results are absolute (start path plus
    subpath), but when the start path was typed relatively the output
    should show it that way (``find .`` -> ``./sub/x``, not ``/data/sub/x``).

    Args:
        paths: Absolute result paths produced by walking ``original``.
        original: The resolved absolute start path.
        display: The as-typed start path, or ``None`` to leave paths as-is.

    Returns:
        Paths with the ``original`` base replaced by ``display``.
    """
    if display is None or display == original:
        return paths
    return [rebase_one(p, original, display) for p in paths]


def rebase_one(path: str, original: str, display: str | None) -> str:
    """Rewrite a single path's ``original`` base to the as-typed ``display``.

    Args:
        path: An absolute path at or under ``original``.
        original: The resolved absolute base (traversal root).
        display: The as-typed base, or ``None``/equal to leave ``path`` as-is.

    Returns:
        ``path`` with its ``original`` base replaced by ``display``.
    """
    if display is None or display == original:
        return path
    base = original.rstrip("/")
    if path == base:
        return display
    if path.startswith(base + "/"):
        return display.rstrip("/") + path[len(base):]
    return path


def gnu_basename(path: str, suffix: str | None = None) -> str:
    i = len(path)
    while i > 0 and path[i - 1] == "/":
        i -= 1
    if i == 0:
        return "/" if path else ""
    j = path.rfind("/", 0, i)
    base = path[j + 1:i]
    if suffix and base != suffix and base.endswith(suffix):
        base = base[:len(base) - len(suffix)]
    return base


def gnu_dirname(path: str) -> str:
    if path == "":
        return "."
    i = len(path)
    while i > 0 and path[i - 1] == "/":
        i -= 1
    if i == 0:
        return "/"
    j = path.rfind("/", 0, i)
    if j == -1:
        return "."
    while j > 0 and path[j - 1] == "/":
        j -= 1
    if j == 0:
        return "/"
    return path[:j]
