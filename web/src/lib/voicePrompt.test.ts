import { describe, expect, it } from 'vitest'
import { parseVoiceReply, voicePrompt, voiceStory } from './voicePrompt'

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
    const p = voicePrompt({ title: 'Caligula', parts: 3, cast: ['Cassius'] })
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
