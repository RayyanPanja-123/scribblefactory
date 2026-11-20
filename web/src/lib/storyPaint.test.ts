import { describe, expect, it } from 'vitest'
import { addRow, KINDS, parseStory, writeStory, type Ctx } from './storyPaint'

const MD = `# The Lantern Test

@set bakery
@weather rain light
@cast ava, ben
@fx shake
Ava found a lantern that only glows for liars.
@look ava: lit
@do ben: give medal ava
@face ben: angry
@sfx riser 0.6
Ben shrugged.
@crowd red fight blue
@do fred: lie, amy: wave
!! The lantern turned toward Ava and roared.
@background-music off
`

describe('storyPaint', () => {
  it('round-trips a script', () => {
    const p = parseStory(MD)
    expect(p.title).toBe('The Lantern Test')
    expect(p.beats.map((b) => b.rows.length)).toEqual([4, 4, 2, 1])
    expect(p.beats[2].twist).toBe(true)
    expect(writeStory(p)).toBe(MD)
  })

  it('every directive above survives fields -> text unchanged', () => {
    for (const b of parseStory(MD).beats) for (const r of b.rows) {
      const rec = KINDS[r.name].parse(r.arg)
      if (rec) expect(KINDS[r.name].build(rec)).toBe(r.arg)
    }
  })

  it('leaves what the fields cannot hold as text', () => {
    expect(KINDS.do.parse('fred: lie, amy: wave')).toBeNull()
    expect(KINDS.face.parse('a, b: sad')).toBeNull()
  })

  it('puts a new row in reading order', () => {
    const ctx: Ctx = { sets: ['street'], actions: ['talk'], props: [], sounds: [], cast: [{ id: 'ava', name: 'Ava', looks: [] }] }
    const b = { rows: [{ name: 'do', arg: 'ava: talk' }], text: 'Hi.', twist: false }
    addRow(b, 'set', ctx)
    addRow(b, 'sfx', ctx)
    expect(b.rows.map((r) => r.name)).toEqual(['set', 'do', 'sfx'])
  })
})
