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

import { describe, expect, it } from 'vitest'
import { compilePattern, isRegexPattern } from './grep_helper.ts'

describe('compilePattern', () => {
  it('single pattern keeps regex semantics', () => {
    const pat = compilePattern('fo+')
    expect(pat.test('foo')).toBe(true)
    expect(pat.test('f')).toBe(false)
  })

  it('single fixed string escapes regex chars', () => {
    const pat = compilePattern('a.b', false, true)
    expect(pat.test('xa.by')).toBe(true)
    expect(pat.test('axb')).toBe(false)
  })

  it('newline-separated patterns match any', () => {
    const pat = compilePattern('foo\nbar')
    expect(pat.test('a foo b')).toBe(true)
    expect(pat.test('a bar b')).toBe(true)
    expect(pat.test('baz')).toBe(false)
  })

  it('newline-separated regex alternation grouping', () => {
    const pat = compilePattern('ab+\ncd')
    expect(pat.test('abb')).toBe(true)
    expect(pat.test('xcdy')).toBe(true)
    expect(pat.test('ax')).toBe(false)
  })

  it('newline-separated fixed strings escape each', () => {
    const pat = compilePattern('a.b\nc+', false, true)
    expect(pat.test('xa.by')).toBe(true)
    expect(pat.test('c+')).toBe(true)
    expect(pat.test('axb')).toBe(false)
    expect(pat.test('cc')).toBe(false)
  })

  it('newline-separated whole word applies per pattern', () => {
    const pat = compilePattern('foo\nbar', false, false, true)
    expect(pat.test('a foo b')).toBe(true)
    expect(pat.test('bar.')).toBe(true)
    expect(pat.test('foobar')).toBe(false)
  })

  it('newline-separated ignore case', () => {
    const pat = compilePattern('foo\nbar', true)
    expect(pat.test('FOO')).toBe(true)
    expect(pat.test('Bar')).toBe(true)
  })
})

describe('isRegexPattern', () => {
  it('treats a newline-joined pattern list as non-literal', () => {
    expect(isRegexPattern('foo\nbar', false)).toBe(true)
    expect(isRegexPattern('foo\nbar', true)).toBe(true)
  })

  it('keeps plain literals non-regex', () => {
    expect(isRegexPattern('foo bar', false)).toBe(false)
  })
})
