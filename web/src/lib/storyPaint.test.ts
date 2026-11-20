import { describe, expect, it } from 'vitest'
import { addRow, KINDS, lintBeat, parseStory, writeStory, type Ctx } from './storyPaint'

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

describe('lintBeat', () => {
  const c: Ctx = { sets: ['street'], actions: ['wave'], props: [], sounds: ['pop', 'boom'], cast: [{ id: 'ava', name: 'Ava', looks: [] }] }
  it('flags digits, a twist that is not last, back-to-back sounds and unknown names', () => {
    const p = parseStory(`# T\n@set moon\n@cast ava, zed\n!! It cost 18 coins.\n@sfx pop\nOne.\n@sfx boom\n@do ava: dance\nTwo.\n`)
    expect(lintBeat(p.beats, 0, c)).toEqual([
      'Spell numbers out as words ("eighteen", not "18").',
      'The twist goes on the very last line only.',
      'Place: "moon" is not in the library.',
      `On stage: "zed" is not in this series' cast.`,
    ])
    expect(lintBeat(p.beats, 1, c)).toEqual([])
    expect(lintBeat(p.beats, 2, c)).toEqual(['Sounds on two lines in a row: leave a line between them.', 'Action: "dance" is not in the library.'])
  })

  it('takes any volume from 0 to 1, not only the menu presets', () => {
    const p = parseStory('# T\n@set street\n@background-music sneaky-snitch 0.15\n@sfx pop 0.6\nOne.\nQuiet.\n@background-music off\n@sfx boom 3\nTwo.\n')
    expect(lintBeat(p.beats, 0, c)).toEqual([])
    expect(lintBeat(p.beats, 2, c)).toEqual(['Sound: loudness "3" must be 0 to 1.'])
  })
})
