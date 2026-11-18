import { describe, expect, it } from 'vitest'
import { buildCreationPrompt, chosen, parseReply, reviewItems, TYPES, uniqueId, type Library } from './aiCreations'

const LIB = {
  props: { builtin: ['bottle'], custom: [{ id: 'gun', name: 'Gun', shapes: [] }], cleared: [] },
  sets: { builtin: [{ id: 'office', kind: 'indoor' }], custom: [] },
  creatures: { builtin: [{ id: 'cat', rig: 'quadruped' }], custom: [], cleared: [] },
  actions: { builtin: ['wave'], do: [], custom: [] },
} as unknown as Library
const PROP = (id: string) => ({ id, name: id, shapes: [{ shape: 'circle', pts: [[0, 0]], r: 10, width: 6 }] })
const fence = (j: unknown) => '```json\n' + JSON.stringify(j) + '\n```'

describe('type switching', () => {
  it('each type gets its own prompt; a series is not one of them (Story Writer)', () => {
    expect(TYPES).not.toContain('series')
    const b = { description: 'A shiny red umbrella', rig: 'bird' as const, cast: ['bob'] }
    const p = Object.fromEntries(TYPES.map((t) => [t, buildCreationPrompt(t, b, LIB, 'GUIDE')]))
    expect(p.prop).toContain('drawing a prop')
    expect(p.set).toContain('designing a set')
    expect(p.creature).toMatch(/bird/)
    expect(p.action).toContain('animating a stick figure')
    expect(p.cast).toContain('use different ones: bob')
    expect(new Set(Object.values(p)).size).toBe(TYPES.length)
  })
  it('each type reads its own reply shape', () => {
    expect(parseReply('prop', fence(PROP('umbrella'))).plan?.props[0].id).toBe('umbrella')
    expect(parseReply('cast', fence({ cast: [{ id: 'cy', name: 'Cy' }] })).plan?.cast).toHaveLength(1)
    expect(parseReply('cast', fence({ cast: [{ name: 'Cy' }] })).error).toMatch(/Cast #1/)
  })
})

describe('id clash', () => {
  it('suffixes', () => expect(uniqueId('gun', new Set(['gun', 'gun-2']))).toBe('gun-3'))
  it('a single asset never overwrites: the id gets a suffix and shows what it was', () => {
    const [i] = reviewItems(parseReply('prop', fence(PROP('gun'))).plan!, LIB)
    expect(i).toMatchObject({ id: 'gun-2', was: 'gun', status: 'new', checked: true })
    expect((i.data as { id: string }).id).toBe('gun-2')
  })
  it('a cast member taken in the series gets a suffix', () => {
    const cast = reviewItems({ props: [], sets: [], creatures: [], actions: [], cast: [{ id: 'bob', name: 'Bob' }] }, LIB, ['bob'])
    expect(cast[0]).toMatchObject({ id: 'bob-2', was: 'bob' })
  })
})

describe('review unchecking', () => {
  it('imports checked new items only', () => {
    const xs = reviewItems(parseReply('cast', fence({ cast: [{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }] })).plan!, LIB)
    xs[0].checked = false
    expect(chosen(xs).map((i) => i.id)).toEqual(['b'])
  })
})
