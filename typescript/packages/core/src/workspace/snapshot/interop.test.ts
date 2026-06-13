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
import { fileURLToPath } from 'node:url'
import { beforeAll, describe, expect, it } from 'vitest'
import { OpsRegistry } from '../../ops/registry.ts'
import { createShellParser, type ShellParser } from '../../shell/parse.ts'
import { MountMode } from '../../types.ts'
import { Workspace } from '../workspace.ts'

const require = createRequire(import.meta.url)
const engineWasm = readFileSync(require.resolve('web-tree-sitter/web-tree-sitter.wasm'))
const grammarWasm = readFileSync(require.resolve('tree-sitter-bash/tree-sitter-bash.wasm'))
const fixture = (name: string): string =>
  fileURLToPath(new URL(`./__fixtures__/${name}`, import.meta.url))

let parser: ShellParser

beforeAll(async () => {
  parser = await createShellParser({ engineWasm, grammarWasm })
})

describe('cross-language snapshot interop', () => {
  it('loads a Python-written RAM tar and reads the file back', async () => {
    const bytes = new Uint8Array(readFileSync(fixture('py_ram.tar')))
    const ws = await Workspace.load(bytes, {
      mode: MountMode.WRITE,
      ops: new OpsRegistry(),
      shellParser: parser,
    })
    const r = await ws.execute('cat /ram/f.txt')
    expect(new TextDecoder().decode(r.stdout)).toBe('alpha\nbeta\ngamma\n')
    expect(r.exitCode).toBe(0)
    await ws.close()
  })
})
