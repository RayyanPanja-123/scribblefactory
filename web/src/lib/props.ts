import type { components } from '../api/types'

export type Prop = components['schemas']['Prop']
export type Hand = Prop['hand']
// angle has a server default (0): optional when writing one
export type CustomProp = Omit<components['schemas']['CustomProp'], 'angle'> & { angle?: number }
export type PropShape = components['schemas']['PropShape']
export type PropCatalog = components['schemas']['PropCatalog']
export type BuiltinProp = PropCatalog['builtin'][number]

export const HANDS: Hand[] = ['left', 'right']

const NOTES: Record<BuiltinProp, string> = {
  clipboard: 'officials, coaches, anyone keeping score',
  stopwatch: 'timekeepers at the start and finish',
  bottle: 'water, or something stronger',
  syringe: 'the trainer’s “tonic”',
  apple: 'default for @do eat',
  medal: 'handed over with @do give',
}
export const builtinNote = (k: BuiltinProp) => NOTES[k]

/** every kind a cast member can hold, with a display name: built-ins first, then the library's custom props */
export const propOptions = (c: PropCatalog | null | undefined) =>
  [...(c?.builtin ?? []).map((id) => ({ id: id as string, name: id as string })), ...(c?.custom ?? []).map((p) => ({ id: p.id, name: p.name }))]
