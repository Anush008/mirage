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

import { join, sep } from 'node:path'
import { describe, expect, it } from 'vitest'
import { PathOutsideRootError, resolveWithinRoot, validatePathSegment } from './paths.ts'

describe('resolveWithinRoot', () => {
  const root = `${sep}srv${sep}snapshots`

  it('accepts a relative path under the root', () => {
    expect(resolveWithinRoot(root, 'seed.tar')).toBe(join(root, 'seed.tar'))
  })

  it('accepts an absolute path inside the root', () => {
    const inside = join(root, 'nested', 'a.tar')
    expect(resolveWithinRoot(root, inside)).toBe(inside)
  })

  it('returns the root itself', () => {
    expect(resolveWithinRoot(root, '.')).toBe(root)
  })

  it('rejects traversal escaping the root', () => {
    expect(() => resolveWithinRoot(root, '../../etc/passwd')).toThrow(PathOutsideRootError)
  })

  it('rejects an absolute path outside the root', () => {
    expect(() => resolveWithinRoot(root, `${sep}etc${sep}passwd`)).toThrow(PathOutsideRootError)
  })

  it('rejects a sibling that shares the root prefix', () => {
    expect(() => resolveWithinRoot(root, `${sep}srv${sep}snapshots-evil${sep}x`)).toThrow(
      PathOutsideRootError,
    )
  })
})

describe('validatePathSegment', () => {
  it('accepts safe segments', () => {
    expect(validatePathSegment('ws_abc123')).toBe('ws_abc123')
    expect(validatePathSegment('a.b-c_d')).toBe('a.b-c_d')
  })

  it('rejects empty, dot, and dotdot', () => {
    expect(() => validatePathSegment('')).toThrow(PathOutsideRootError)
    expect(() => validatePathSegment('.')).toThrow(PathOutsideRootError)
    expect(() => validatePathSegment('..')).toThrow(PathOutsideRootError)
  })

  it('rejects separators and other unsafe characters', () => {
    expect(() => validatePathSegment('a/b')).toThrow(PathOutsideRootError)
    expect(() => validatePathSegment('a\\b')).toThrow(PathOutsideRootError)
    expect(() => validatePathSegment('a b')).toThrow(PathOutsideRootError)
    expect(() => validatePathSegment('a$b')).toThrow(PathOutsideRootError)
  })
})
