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
import os

from dotenv import load_dotenv

from mirage import MountMode, Workspace
from mirage.resource.databricks_volume import (DatabricksProfileTokenProvider,
                                               DatabricksVolumeConfig,
                                               DatabricksVolumeResource,
                                               StaticTokenProvider)

load_dotenv(".env.development")

host = os.environ["DATABRICKS_HOST"]
token = os.environ.get("DATABRICKS_TOKEN")
token_provider = (StaticTokenProvider(token)
                  if token else DatabricksProfileTokenProvider(
                      host,
                      os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT"),
                  ))
config = DatabricksVolumeConfig(
    host=host,
    catalog=os.environ["DATABRICKS_VOLUME_CATALOG"],
    schema=os.environ["DATABRICKS_VOLUME_SCHEMA"],
    volume=os.environ["DATABRICKS_VOLUME_NAME"],
    root_path=os.environ.get("DATABRICKS_VOLUME_ROOT_PATH", "/"),
)
resource = DatabricksVolumeResource(
    config=config,
    token_provider=token_provider,
)


async def _run(ws, cmd):
    print(f"\n>>> {cmd}")
    result = await ws.execute(cmd)
    stdout = (await result.stdout_str()).strip()
    stderr = (await result.stderr_str()).strip()
    if stdout:
        for line in stdout.splitlines()[:12]:
            print(f"  {line[:140]}")
        if len(stdout.splitlines()) > 12:
            print(f"  ... ({len(stdout.splitlines())} lines total)")
    if stderr:
        print(f"  [stderr] {stderr[:140]}")
    if not stdout and not stderr:
        print(f"  (empty, exit={result.exit_code})")
    return result


async def main():
    ws = Workspace({"/dbx/": resource}, mode=MountMode.READ)

    await _run(ws, "ls /dbx/")
    await _run(ws, "tree -L 2 /dbx/")
    await _run(ws, 'find /dbx/ -name "*.md"')

    target = os.environ.get("DATABRICKS_VOLUME_SAMPLE_FILE")
    if target:
        await _run(ws, f'stat "{target}"')
        await _run(ws, f'head -n 20 "{target}"')
        await _run(ws, f'grep -n TODO "{target}"')
    else:
        print("\nSet DATABRICKS_VOLUME_SAMPLE_FILE to run file reads.")


if __name__ == "__main__":
    asyncio.run(main())
