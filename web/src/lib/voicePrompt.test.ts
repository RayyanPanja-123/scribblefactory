import { describe, expect, it } from 'vitest'
import { parseVoiceReply, spokenWords, voicePrompt, voiceStory } from './voicePrompt'

const reply = `Sure! Here you go:
\`\`\`text
<<<PART 1>>>
# The Seashell Parade
Caligula threw a parade for seashells.
!! Neptune was watching.
<<<PART 2>>>
# The Sandal
Cassius counted the days.
!! He never needed the second sandal.
<<<END>>>
\`\`\``

describe('voicePrompt', () => {
  it('carries the title, part count and writing rules, nothing about directives', () => {
    const p = voicePrompt({ title: 'Caligula', parts: 3, mode: 'narration', cast: [{ id: 'cassius', name: 'Cassius' }] })
    expect(p).toContain('"Caligula"')
    expect(p).toContain('exactly 3 parts')
    expect(p).toContain('Writing rules')
    expect(p).toContain('Cassius')
    expect(p).not.toContain('@set')
  })

  it('reads the parts out of a chatty reply', () => {
    const r = parseVoiceReply(reply, 2)
    expect(r.error).toBeUndefined()
    expect(r.parts![1]).toEqual({ title: 'The Sandal', lines: ['Cassius counted the days.', '!! He never needed the second sandal.'] })
    expect(voiceStory(r.parts![0], ['caligula'])).toBe('# The Seashell Parade\n\n@set street\n@cast caligula\nCaligula threw a parade for seashells.\n!! Neptune was watching.\n')
  })

  it('rejects a wrong count, digits and a missing twist', () => {
    expect(parseVoiceReply(reply, 3).error).toMatch(/Expected 3/)
    expect(parseVoiceReply(reply.replace('for seashells', 'for 100 seashells'), 2).error).toMatch(/numbers as words/)
    expect(parseVoiceReply(reply.replace('!! Neptune', 'Neptune'), 2).error).toMatch(/twist/)
  })
})

describe('voice mode', () => {
  const acted = reply.replace('Cassius counted the days.', 'Cassius counted the days.\ncassius: Nine more sandals to go.')
  it('states the mode the creator picked; cast voice acting lists who may speak by id', () => {
    const solo = voicePrompt({ title: 'C', parts: 1, mode: 'narration', cast: [{ id: 'cassius', name: 'Cassius' }] })
    expect(solo).toContain('**single narration**')
    expect(solo).not.toContain('`cassius`')
    const cast = voicePrompt({ title: 'C', parts: 1, mode: 'cast', cast: [{ id: 'cassius', name: 'Cassius' }] })
    expect(cast).toContain('**cast voice acting**')
    expect(cast).toContain('`cassius` Cassius')
    expect(cast).toContain('cassius: A line Cassius says.')
    expect(cast).toContain('Voice mode (settled with the creator before any script)') // the rules explain both
  })
  it('takes cast lines only from the cast, and none in single narration', () => {
    expect(parseVoiceReply(acted, 2, ['cassius']).parts![1].lines[1]).toBe('cassius: Nine more sandals to go.')
    expect(parseVoiceReply(acted, 2, ['nero']).error).toMatch(/"cassius" is not in this series' cast/)
    expect(parseVoiceReply(acted, 2).error).toMatch(/single narration, but this is a character's line/)
    expect(parseVoiceReply(reply.replace('Cassius counted', "Here's the catch: Cassius counted"), 2).error).toBeUndefined()
  })
  it('counts only the spoken words', () => {
    expect(spokenWords({ title: 'T', lines: ['cassius: "Nine more."', '!! kai: Then we walk.'] })).toBe(5)
  })
})
