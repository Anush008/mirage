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

import type { GitHubAccessor } from '../../accessor/github.ts'
import type { FindOptions } from '../../resource/base.ts'
import type { PathSpec } from '../../types.ts'
import { buildTree, keep } from '../../commands/builtin/findEval.ts'
import { stripSlash } from '../../utils/slash.ts'

function strip(path: PathSpec): string {
  const prefix = path.prefix
  let p = path.original
  if (prefix !== '' && p.startsWith(prefix)) p = p.slice(prefix.length) || '/'
  return stripSlash(p)
}

export function find(
  accessor: GitHubAccessor,
  path: PathSpec,
  options: FindOptions = {},
): Promise<string[]> {
  const base = strip(path)
  const prefix = base === '' ? '' : `${base}/`
  const baseDepth = base === '' ? 0 : (base.match(/\//g) ?? []).length + 1
  const results: string[] = []
  const tree =
    options.tree ??
    buildTree({
      name: options.name,
      iname: options.iname,
      pathPattern: options.pathPattern,
      type: options.type,
      nameExclude: options.nameExclude,
      orNames: options.orNames,
    })
  const sortedKeys = Object.keys(accessor.tree).sort()
  for (const p of sortedKeys) {
    if (p !== base && !p.startsWith(prefix)) continue
    const entry = accessor.tree[p]
    if (entry === undefined) continue
    const isDir = entry.type === 'tree'
    const fullPath = `/${p}`
    const depth = (p.match(/\//g) ?? []).length + 1 - baseDepth
    if (options.maxDepth !== null && options.maxDepth !== undefined && depth > options.maxDepth) {
      continue
    }
    const entryName = p.split('/').pop() ?? p
    if (
      !keep(
        { key: fullPath, name: entryName, kind: isDir ? 'd' : 'f', depth },
        tree,
        options.minDepth,
      )
    ) {
      continue
    }
    const size = entry.size ?? 0
    if (options.minSize !== null && options.minSize !== undefined && size < options.minSize) {
      continue
    }
    if (options.maxSize !== null && options.maxSize !== undefined && size > options.maxSize) {
      continue
    }
    results.push(fullPath)
  }
  return Promise.resolve(results)
}
