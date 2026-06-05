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

import { type CommandSpec, OperandKind } from '../../commands/spec/types.ts'

export function classifyArgvBySpec(
  spec: CommandSpec,
  argv: readonly string[],
): [Set<string>, Set<string>] {
  const boolFlags = new Set<string>()
  const valueFlags = new Set<string>()
  const valueFlagKinds = new Map<string, OperandKind>()
  const longBoolFlags = new Set<string>()
  const longValueFlags = new Set<string>()
  let numericShorthandFlag: string | null = null
  for (const opt of spec.options) {
    if (opt.short !== null) {
      if (opt.valueKind === OperandKind.NONE) boolFlags.add(opt.short)
      else {
        valueFlags.add(opt.short)
        valueFlagKinds.set(opt.short, opt.valueKind)
        if (opt.numericShorthand) numericShorthandFlag = opt.short
      }
    }
    if (opt.long !== null) {
      if (opt.valueKind === OperandKind.NONE) longBoolFlags.add(opt.long)
      else {
        longValueFlags.add(opt.long)
        valueFlagKinds.set(opt.long, opt.valueKind)
      }
    }
  }
  const positional = spec.positional.map((op) => op.kind)
  const restKind = spec.rest?.kind ?? null

  const rawArgs: string[] = []
  const flagTextValues = new Set<string>()
  let i = 0
  let endOfFlags = false
  while (i < argv.length) {
    const tok = argv[i]
    if (tok === undefined) break
    if (tok === '--' && !endOfFlags) {
      endOfFlags = true
      i += 1
      continue
    }
    if (endOfFlags) {
      rawArgs.push(tok)
      i += 1
      continue
    }
    if (spec.ignoreTokens.has(tok)) {
      i += 1
      continue
    }
    if (tok.startsWith('--')) {
      if (longValueFlags.has(tok) && i + 1 < argv.length) {
        if (valueFlagKinds.get(tok) === OperandKind.TEXT) {
          flagTextValues.add(argv[i + 1] ?? '')
        }
        i += 2
      } else {
        if (!longBoolFlags.has(tok)) rawArgs.push(tok)
        i += 1
      }
      continue
    }
    if (tok.startsWith('-') && tok.length > 1) {
      if (numericShorthandFlag !== null && /^-\d+$/.test(tok)) {
        flagTextValues.add(tok.slice(1))
        i += 1
        continue
      }
      let matched = false
      for (const vf of valueFlags) {
        if (tok === vf && i + 1 < argv.length) {
          if (valueFlagKinds.get(vf) === OperandKind.TEXT) {
            flagTextValues.add(argv[i + 1] ?? '')
          }
          i += 2
          matched = true
          break
        }
        if (tok.startsWith(vf) && tok.length > vf.length) {
          if (valueFlagKinds.get(vf) === OperandKind.TEXT) {
            flagTextValues.add(tok.slice(vf.length))
          }
          i += 1
          matched = true
          break
        }
      }
      if (matched) continue
      if (boolFlags.has(tok)) {
        i += 1
        continue
      }
      let allBool = true
      for (const ch of tok.slice(1)) {
        if (!boolFlags.has(`-${ch}`)) {
          allBool = false
          break
        }
      }
      if (allBool && tok.length > 1) {
        i += 1
        continue
      }
      rawArgs.push(tok)
      i += 1
      continue
    }
    rawArgs.push(tok)
    i += 1
  }

  const textSet = new Set<string>()
  const pathSet = new Set<string>()
  for (let j = 0; j < rawArgs.length; j++) {
    const arg = rawArgs[j]
    if (arg === undefined) continue
    let kind: OperandKind | null
    if (j < positional.length) kind = positional[j] ?? null
    else kind = restKind
    if (kind === null) continue
    if (kind === OperandKind.TEXT) textSet.add(arg)
    else if (kind === OperandKind.PATH) pathSet.add(arg)
  }
  for (const v of flagTextValues) textSet.add(v)
  return [textSet, pathSet]
}
