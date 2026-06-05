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

import {
  CommandSafeguard,
  DEFAULT_COMMAND_SAFEGUARDS,
  ExecuteResult,
  MountMode,
  OnExceed,
  RAMResource,
  SafeguardExceededError,
  Workspace,
} from '@struktoai/mirage-node'

const A_LINES = '1\n2\n3\n4\n5\n'
const B_LINES = '6\n7\n8\n9\n10\n'
const SMALL_LINES = 'x\ny\n'
const C_BYTES = 'abcdefgh'
const SUB_MATCHES = 'match\nmatch\nmatch\n'

const CASES: [string, string][] = [
  ['single_cat_truncate', 'cat /a/f.txt'],
  ['single_cat_error', 'cat /b/f.txt'],
  ['within_limit_no_fire', 'cat /a/small.txt'],
  ['max_bytes_truncate', 'cat /c/f.txt'],
  ['pipe_rightmost_truncate', 'cat /a/f.txt | head'],
  ['pipe_rightmost_error', 'cat /a/f.txt | grep .'],
  ['command_limit_under_safeguard', 'cat /a/f.txt | head -n 2'],
  ['semicolon_rightmost_truncate', 'cat /b/f.txt ; cat /a/f.txt'],
  ['and_rightmost_error', 'cat /a/f.txt && cat /b/f.txt'],
  ['or_rightmost_truncate', 'false || cat /a/f.txt'],
  ['subshell_rightmost', '( cat /b/f.txt ; cat /a/f.txt )'],
  ['cross_mount_cat_tightest', 'cat /a/f.txt /b/f.txt'],
  ['traversal_grep_r_tightest', 'grep -r match /a'],
  ['timeout_fires', 'sleep 2'],
  ['timeout_in_pipe', 'sleep 2 | cat'],
]

const VFS_CASES: [string, string][] = [
  ['vfs_read_truncate', '/c/f.txt'],
  ['vfs_read_error', '/d/f.txt'],
]

function buildWs(): Workspace {
  DEFAULT_COMMAND_SAFEGUARDS.head = new CommandSafeguard({ maxLines: 3, onExceed: OnExceed.TRUNCATE })
  DEFAULT_COMMAND_SAFEGUARDS.grep = new CommandSafeguard({ maxLines: 2, onExceed: OnExceed.ERROR })
  DEFAULT_COMMAND_SAFEGUARDS.sleep = new CommandSafeguard({ timeoutSeconds: 0.1 })
  return new Workspace(
    {
      '/a/': new RAMResource(),
      '/a/sub/': new RAMResource(),
      '/b/': new RAMResource(),
      '/c/': new RAMResource(),
      '/d/': new RAMResource(),
    },
    {
      mode: MountMode.WRITE,
      commandSafeguards: {
        '/a/': {
          cat: new CommandSafeguard({ maxLines: 4, onExceed: OnExceed.TRUNCATE }),
          grep: new CommandSafeguard({ maxLines: 2, onExceed: OnExceed.ERROR }),
        },
        '/a/sub/': {
          grep: new CommandSafeguard({ maxLines: 1, onExceed: OnExceed.ERROR }),
        },
        '/b/': {
          cat: new CommandSafeguard({ maxLines: 2, onExceed: OnExceed.ERROR }),
        },
        '/c/': {
          cat: new CommandSafeguard({ maxBytes: 5, onExceed: OnExceed.TRUNCATE }),
          read: new CommandSafeguard({ maxBytes: 4, onExceed: OnExceed.TRUNCATE }),
        },
        '/d/': {
          read: new CommandSafeguard({ maxBytes: 4, onExceed: OnExceed.ERROR }),
        },
      },
    },
  )
}

async function main(): Promise<void> {
  const ws = buildWs()
  try {
    await ws.execute('mkdir -p /a/sub')
    await ws.execute(`printf '${A_LINES}' > /a/f.txt`)
    await ws.execute(`printf '${B_LINES}' > /b/f.txt`)
    await ws.execute(`printf '${SMALL_LINES}' > /a/small.txt`)
    await ws.execute(`printf '${C_BYTES}' > /c/f.txt`)
    await ws.execute(`printf '${C_BYTES}' > /d/f.txt`)
    await ws.execute(`printf '${SUB_MATCHES}' > /a/sub/g.txt`)

    for (const [name, cmd] of CASES) {
      const result = (await ws.execute(cmd)) as ExecuteResult
      const out = result.stdoutText
      const err = result.stderrText
      console.log(`=== ${name} ===`)
      console.log(`exit=${result.exitCode}`)
      if (out) process.stdout.write(out.endsWith('\n') ? out : out + '\n')
      if (err.includes('output truncated')) console.log('note=truncated')
      if (err.includes('timed out')) console.log('note=timed_out')
    }

    for (const [name, path] of VFS_CASES) {
      console.log(`=== ${name} ===`)
      try {
        const value = (await ws.dispatch('read', path)) as Uint8Array
        console.log(`read=${new TextDecoder().decode(value)}`)
      } catch (err) {
        if (err instanceof SafeguardExceededError) {
          console.log('read=<raised SafeguardExceededError>')
        } else {
          throw err
        }
      }
    }
  } finally {
    await ws.close()
  }
}

main().catch((err: unknown) => {
  process.stderr.write(String(err) + '\n')
  process.exit(1)
})
