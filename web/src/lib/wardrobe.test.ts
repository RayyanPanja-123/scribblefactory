import { describe, expect, it } from 'vitest'
import { EXAMPLES, SLOTS, buildWardrobePrompt, importWardrobe, wearers } from './wardrobe'

describe('wardrobe prompt', () => {
  it('teaches the format with one example per slot and the taken ids', () => {
    const p = buildWardrobePrompt('Feathered helmet', 'headwear', ['crown', 'bowler'], 'red plume')
    expect(p).toContain('"id": "feathered_helmet"')
    expect(p).toContain('"slot": "headwear"')
    expect(p).toContain('crown, bowler')
    expect(p).toContain('What it should look like: red plume')
    expect(EXAMPLES.map((e) => e.slot)).toEqual(SLOTS)
    for (const e of EXAMPLES) expect(p).toContain(`"id": "${e.id}"`)
  })
})

describe('wardrobe import', () => {
  it('takes a fenced reply, fills layer defaults and keeps the slot', () => {
    const { item } = importWardrobe('Sure!\n```json\n{"id": "Plume Helm", "name": "Plume helm", "slot": "headwear", "layers": [' +
      '{"shape": "ellipse", "anchor": "head_top", "pts": [[0, 0]], "r": 40, "fill": "$color"},' +
      '{"shape": "line", "anchor": "head_top", "pts": [[0, 0], [0, -80]], "behind": true, "when": ["happy"]}]}\n```')
    expect(item).toMatchObject({ id: 'plume_helm', slot: 'headwear', colorable: true, default_color: '#6b4f3a' })
    expect(item!.layers[0]).toMatchObject({ r: 40, ry: 12, width: 8, behind: false, when: null })
    expect(item!.layers[1]).toMatchObject({ r: null, behind: true, when: ['happy'] })
  })
  it('falls back to the editor slot and reports bad layers', () => {
    expect(importWardrobe('{"name": "X", "layers": []}', 'hair').item?.slot).toBe('hair')
    expect(importWardrobe('{"name": "X", "layers": []}').error).toMatch(/slot/)
    expect(importWardrobe('{"slot": "hair", "layers": [{"shape": "blob", "anchor": "head", "pts": [[0, 0]]}]}').error).toMatch(/Layer #1/)
    expect(importWardrobe('{"slot": "hair", "layers": [{"shape": "rect", "anchor": "elbow", "pts": [[0, 0], [1, 1]]}]}').error).toMatch(/anchor/)
    expect(importWardrobe('nope').error).toMatch(/JSON/)
  })
})

describe('wearers', () => {
  it('finds an item in any slot form, in lists and in looks', () => {
    const series = [{ series: { slug: 'rome', title: 'Rome', cast: [
      { name: 'Nero', top: { style: 'toga', color: '#ffffff' }, hair: 'short_hair', face: [{ id: 'scar' }] },
      { name: 'Livia', headwear: { kind: 'bowler', color: '#000000' }, looks: { crowned: { headwear: 'crown' } } },
    ] } }]
    expect(wearers(series, 'toga').map((w) => w.name)).toEqual(['Nero'])
    expect(wearers(series, 'scar').map((w) => w.name)).toEqual(['Nero'])
    expect(wearers(series, 'bowler').map((w) => w.name)).toEqual(['Livia'])
    expect(wearers(series, 'crown').map((w) => w.name)).toEqual(['Livia'])
    expect(wearers(series, 'cape')).toEqual([])
  })
})
