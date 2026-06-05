// ========= Copyright 2026 @ Strukto.AI All Rights Reserved. =========
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
// ========= Copyright 2026 @ Strukto.AI All Rights Reserved. =========

import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { DEFAULT_COMMAND_SAFEGUARDS } from '../commands/safeguard.ts'
import { OpsRegistry } from '../ops/registry.ts'
import { RAMResource } from '../resource/ram/ram.ts'
import { createShellParser, type ShellParser } from '../shell/parse.ts'
import { CommandSafeguard, MountMode } from '../types.ts'
import { Workspace } from './workspace.ts'

const require = createRequire(import.meta.url)
const engineWasm = readFileSync(require.resolve('web-tree-sitter/web-tree-sitter.wasm'))
const grammarWasm = readFileSync(require.resolve('tree-sitter-bash/tree-sitter-bash.wasm'))
const DEC = new TextDecoder()

let parser: ShellParser

beforeAll(async () => {
  parser = await createShellParser({ engineWasm, grammarWasm })
})

afterEach(() => {
  delete DEFAULT_COMMAND_SAFEGUARDS.sleep
})

function buildWs(): Workspace {
  const ram = new RAMResource()
  const registry = new OpsRegistry()
  registry.registerResource(ram)
  return new Workspace({ '/': ram }, { mode: MountMode.WRITE, ops: registry, shellParser: parser })
}

describe('command timeout', () => {
  it('quick command under default does not fire', async () => {
    DEFAULT_COMMAND_SAFEGUARDS.sleep = new CommandSafeguard({ timeoutSeconds: 1 })
    const ws = buildWs()
    try {
      const r = await ws.execute('sleep 0.05')
      expect(r.exitCode).toBe(0)
    } finally {
      await ws.close()
    }
  })

  it('default safeguard fires with attributed stderr and exit 124', async () => {
    DEFAULT_COMMAND_SAFEGUARDS.sleep = new CommandSafeguard({ timeoutSeconds: 0.05 })
    const ws = buildWs()
    try {
      const r = await ws.execute('sleep 2')
      expect(r.exitCode).toBe(124)
      expect(DEC.decode(r.stderr)).toContain('sleep: timed out after 0.05s')
    } finally {
      await ws.close()
    }
  })

  it('pipeline: first stage to trip wins', async () => {
    DEFAULT_COMMAND_SAFEGUARDS.sleep = new CommandSafeguard({ timeoutSeconds: 0.05 })
    const ws = buildWs()
    try {
      const r = await ws.execute('sleep 2 | echo done')
      expect(r.exitCode).toBe(124)
      expect(DEC.decode(r.stderr)).toContain('sleep: timed out')
    } finally {
      await ws.close()
    }
  })

  it('timeout of zero disables the guard', async () => {
    DEFAULT_COMMAND_SAFEGUARDS.sleep = new CommandSafeguard({ timeoutSeconds: 0 })
    const ws = buildWs()
    try {
      const r = await ws.execute('sleep 0.05')
      expect(r.exitCode).toBe(0)
    } finally {
      await ws.close()
    }
  })
})
