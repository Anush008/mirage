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
import posixpath

from mirage.types import PathSpec
from mirage.utils import key_prefix as kp


def _relative(path: PathSpec | str) -> str:
    if isinstance(path, PathSpec):
        return path.strip_prefix
    return path


def backend_identity(accessor: object, path: PathSpec | str) -> tuple:
    """Resolve ``(accessor, path)`` to a comparable backend identity.

    The identity captures the backend type, the store it addresses, and the
    canonical key/path within that store, so two references compare equal iff
    they name the same underlying object. Paths are normalized (``.``, ``..``
    and redundant separators collapsed) before comparison.

    Backends are recognized by their accessor shape: S3-compatible stores
    expose ``config.bucket``, disk exposes ``root``, and the in-memory and
    Redis stores expose ``store``. Anything else falls back to the accessor
    object identity, which is conservative — distinct accessors never alias.

    Args:
        accessor (object): The backend accessor (``resource.accessor``).
        path (PathSpec | str): A mount-relative path, or a ``PathSpec`` whose
            ``strip_prefix`` yields one.

    Returns:
        tuple: A hashable identity safe to compare with ``==``.
    """
    raw = _relative(path)
    config = getattr(accessor, "config", None)
    bucket = getattr(config, "bucket", None) if config is not None else None
    if bucket is not None:
        prefix = kp.normalize(getattr(config, "key_prefix", None) or "")
        applied = kp.apply(prefix, raw)
        key = posixpath.normpath(applied) if applied else ""
        return (
            "s3",
            bucket,
            getattr(config, "endpoint_url", None),
            getattr(config, "region", None),
            key,
        )
    root = getattr(accessor, "root", None)
    if root is not None:
        resolved = os.path.normpath(os.path.join(str(root), raw.lstrip("/")))
        return ("disk", resolved)
    store = getattr(accessor, "store", None)
    if store is not None:
        return ("store", id(store), "/" + raw.strip("/"))
    return ("accessor", id(accessor), "/" + raw.strip("/"))


def same_backend_file(accessor: object, a: PathSpec | str,
                      b: PathSpec | str) -> bool:
    """Whether ``a`` and ``b`` name the same object on one backend.

    Both paths are resolved against the same ``accessor``; use
    :func:`backend_identity` directly to compare paths across two different
    accessors (e.g. a cross-mount move).

    Args:
        accessor (object): The backend accessor both paths belong to.
        a (PathSpec | str): First path.
        b (PathSpec | str): Second path.

    Returns:
        bool: True when both resolve to the same underlying object.
    """
    return backend_identity(accessor, a) == backend_identity(accessor, b)
