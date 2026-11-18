import { describe, expect, it } from 'vitest'
import { buildCreationPrompt, chosen, parseReply, reviewItems, TYPES, uniqueId, type Library } from './aiCreations'

const LIB = {
  props: { builtin: ['bottle'], custom: [{ id: 'gun', name: 'Gun', shapes: [] }], cleared: [] },
  sets: { builtin: [{ id: 'office', kind: 'indoor' }], custom: [] },
  creatures: { builtin: [{ id: 'cat', rig: 'quadruped' }], custom: [], cleared: [] },
  actions: { builtin: ['wave'], do: [], custom: [] },
  series: ['bakers'],
} as unknown as Library
const PROP = (id: string) => ({ id, name: id, shapes: [{ shape: 'circle', pts: [[0, 0]], r: 10, width: 6 }] })
const fence = (j: unknown) => '```json\n' + JSON.stringify(j) + '\n```'
const SERIES = {
  title: 'Night Bakers', slug: 'bakers', cast: [{ id: 'ann', name: 'Ann', color: '#ff0000' }],
  assets: { props: [PROP('gun'), PROP('rolling-pin')] },
  parts: [{ title: 'One', story: '# One\n' }, { title: 'Two', story: '# Two\n' }],
}

describe('type switching', () => {
  it('each type gets its own prompt', () => {
    const b = { description: 'A shiny red umbrella', parts: 4, rig: 'bird' as const, cast: ['bob'] }
    const p = Object.fromEntries(TYPES.map((t) => [t, buildCreationPrompt(t, b, LIB, 'GUIDE')]))
    expect(p.prop).toContain('drawing a prop')
    expect(p.set).toContain('designing a set')
    expect(p.creature).toMatch(/bird/)
    expect(p.action).toContain('animating a stick figure')
    expect(p.cast).toContain('use different ones: bob')
    expect(p.series).toContain('Plan exactly 4 parts')
    expect(new Set(Object.values(p)).size).toBe(TYPES.length)
  })
  it('each type reads its own reply shape', () => {
    expect(parseReply('prop', fence(PROP('umbrella'))).plan?.props[0].id).toBe('umbrella')
    expect(parseReply('cast', fence({ cast: [{ id: 'cy', name: 'Cy' }] })).plan?.cast).toHaveLength(1)
    expect(parseReply('cast', fence({ cast: [{ name: 'Cy' }] })).error).toMatch(/Cast #1/)
    const s = parseReply('series', fence(SERIES)).plan!
    expect([s.series?.title, s.parts.length, s.props.length]).toEqual(['Night Bakers', 2, 2])
    expect(parseReply('series', fence({ title: 'x', cast: [], parts: [] })).error).toBeTruthy()
  })
})

describe('id clash', () => {
  it('suffixes', () => expect(uniqueId('gun', new Set(['gun', 'gun-2']))).toBe('gun-3'))
  it('a single asset never overwrites: the id gets a suffix and shows what it was', () => {
    const [i] = reviewItems('prop', parseReply('prop', fence(PROP('gun'))).plan!, LIB)
    expect(i).toMatchObject({ id: 'gun-2', was: 'gun', status: 'new', checked: true })
    expect((i.data as { id: string }).id).toBe('gun-2')
  })
  it('a series reuses an existing asset, suffixes its slug and new cast ids', () => {
    const items = reviewItems('series', parseReply('series', fence(SERIES)).plan!, LIB)
    expect(items.find((i) => i.kind === 'prop' && i.id === 'gun')).toMatchObject({ status: 'existing', checked: false })
    expect(items.find((i) => i.id === 'rolling-pin')?.status).toBe('new')
    expect(items.find((i) => i.kind === 'series')).toMatchObject({ id: 'bakers-2', was: 'bakers' })
    const cast = reviewItems('cast', { props: [], sets: [], creatures: [], actions: [], parts: [], cast: [{ id: 'bob', name: 'Bob' }] }, LIB, ['bob'])
    expect(cast[0]).toMatchObject({ id: 'bob-2', was: 'bob' })
  })
})

describe('review unchecking', () => {
  const items = () => reviewItems('series', parseReply('series', fence(SERIES)).plan!, LIB)
  it('imports checked new items only', () => {
    const xs = items()
    expect(chosen(xs).map((i) => i.kind)).toEqual(['prop', 'cast', 'series', 'part', 'part'])
    xs.find((i) => i.id === 'rolling-pin')!.checked = false
    xs.find((i) => i.kind === 'part')!.checked = false
    expect(chosen(xs).map((i) => i.kind)).toEqual(['cast', 'series', 'part'])
  })
  it('unchecking the series drops its parts and cast', () => {
    const xs = items()
    xs.find((i) => i.kind === 'series')!.checked = false
    expect(chosen(xs).map((i) => i.id)).toEqual(['rolling-pin'])
  })
})
