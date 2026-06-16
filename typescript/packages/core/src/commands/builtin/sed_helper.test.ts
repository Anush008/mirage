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
import { executeProgram, parseProgram } from './sed_helper.ts'

function sed(expr: string, input: string, suppress = false): string {
  return executeProgram(input, parseProgram(expr), suppress)
}

describe('sed line anchors (^ and $)', () => {
  // Regression for #326: ^/$ must anchor per line, matching Python sed / GNU sed.
  it('anchored substitution applies per line', () => {
    expect(sed('s/^#[0-9]*$/#TS/', '#123\nls\n')).toBe('#TS\nls\n')
  })

  it('anchored substitution with -E style + quantifier', () => {
    expect(sed('s/^#[0-9]+$/#TS/', '#123\nls\n')).toBe('#TS\nls\n')
  })

  it('anchored substitution with global flag', () => {
    expect(sed('s/^#[0-9]*$/#TS/g', '#123\nls\n')).toBe('#TS\nls\n')
  })

  it('unanchored substitution still works', () => {
    expect(sed('s/#[0-9][0-9]*/#TS/', '#123\nls\n')).toBe('#TS\nls\n')
  })

  it('$ anchor does not match mid-line', () => {
    expect(sed('s/o$/0/', 'foo\nfox\n')).toBe('fo0\nfox\n')
  })

  it('^ anchor only matches line start', () => {
    expect(sed('s/^a/X/', 'abc\nbac\n')).toBe('Xbc\nbac\n')
  })

  it('anchored substitution on last line without trailing newline', () => {
    expect(sed('s/^bar$/BAR/', 'foo\nbar')).toBe('foo\nBAR')
  })

  it('regex address with $ anchor matches per line', () => {
    // delete lines that consist solely of digits
    expect(sed('/^[0-9]*$/d', '12\nab\n34\n')).toBe('ab\n')
  })
})
