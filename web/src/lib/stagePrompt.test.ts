import { describe, expect, it } from 'vitest'
import { narration, parseStageReply, stagePrompt } from './stagePrompt'

const story = '# Parade\n\n@set street\n@cast caligula\nCaligula threw a parade.\n!! Neptune watched.\n'
const staged = '# Parade\n\n@set colosseum\n@cast caligula\n@do caligula: cheer\nCaligula threw a parade.\n@fx lightning\n!! Neptune watched.'

describe('stagePrompt', () => {
  it('sends the rules, cast, inventory and only the narration', () => {
    const p = stagePrompt({ series: 'Romans', title: 'Parade', story, cast: [{ id: 'caligula', name: 'Caligula', looks: { coins: { props: [{ kind: 'coin' }] }, toga: {} } }, { id: 'rex', name: 'Rex', body: 'cat' }], inventory: '# LIBRARY INVENTORY\nSETS colosseum' })
    expect(p).toContain('## Directives')
    expect(p).toContain('`caligula` Caligula; looks: default, coins (holds coin), toga')
    expect(p).toContain('`rex` Rex (body cat: no wardrobe); looks: default')
    expect(p).toContain('SETS colosseum')
    expect(p).toContain('Caligula threw a parade.')
    expect(p).not.toContain('@set street')
  })

  it('reads the script and the missing items out of a chatty reply', () => {
    const r = parseStageReply(`Here:\n\`\`\`md\n${staged}\n\`\`\`\nMISSING: prop trident: Neptune holds it`, story)
    expect(r.md).toBe(staged + '\n')
    expect(r.missing).toEqual(['prop trident: Neptune holds it'])
    expect(r.changed).toBe(false)
  })

  it('flags changed narration and rejects a reply without a script', () => {
    expect(parseStageReply(staged.replace('a parade', 'a big parade'), story).changed).toBe(true)
    expect(parseStageReply('Sorry, I cannot.', story).error).toMatch(/No story.md/)
    expect(narration(story)).toEqual(['Caligula threw a parade.', '!! Neptune watched.'])
  })
})
