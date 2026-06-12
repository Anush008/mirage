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

from collections.abc import Awaitable
from threading import Lock
from typing import Any, Protocol

try:
    from databricks.sdk.config import Config as WorkspaceConfig
except ImportError:
    WorkspaceConfig = None


class TokenProvider(Protocol):

    def get_token(self) -> str | Awaitable[str]:
        ...


class StaticTokenProvider:

    def __init__(self, token: str) -> None:
        self._token = token

    def get_token(self) -> str:
        return self._token


class DatabricksProfileTokenProvider:

    def __init__(self, host: str, profile: str = "DEFAULT") -> None:
        self._host = host
        self._profile = profile
        self._config: Any | None = None
        self._config_lock = Lock()

    def get_token(self) -> str:
        if WorkspaceConfig is None:
            raise ImportError("DatabricksProfileTokenProvider requires the "
                              "'databricks' extra. Install with: "
                              "pip install mirage-ai[databricks]")
        with self._config_lock:
            if self._config is None:
                self._config = WorkspaceConfig(
                    host=self._host,
                    profile=self._profile,
                )
        authorization = self._config.authenticate().get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token:
            raise ValueError(
                "Databricks profile did not provide a bearer token")
        return token
