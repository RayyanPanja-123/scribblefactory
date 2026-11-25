import { describe, expect, it } from 'vitest'
import { buildCaptionPrompt, composeUpload, parseUpload } from './captionPrompt'

describe('upload.md captions', () => {
  it('round-trips the four fields', () => {
    const c = { title: 'T 🌊', description: 'Hook.\nPart 1 of 3.\n\n#shorts #rome', pinned: 'Rome or the sea? 👇', instagram: 'Hook\n\nStory\n\n#reels' }
    expect(parseUpload(composeUpload('S — Part 1', c))).toEqual(c)
  })
  it('loads the older "Title:" format', () => {
    const old = '# S — Part 1\n\n## YouTube\n\nTitle: Big hook\n\nLine one.\n\n#shorts #x\n\n## Instagram\n\nIG text\n\n#reels\n'
    expect(parseUpload(old)).toEqual({ title: 'Big hook', description: 'Line one.\n\n#shorts #x', pinned: '', instagram: 'IG text\n\n#reels' })
    expect(parseUpload('')).toEqual({ title: '', description: '', pinned: '', instagram: '' })
  })
  it('puts the handle in the prompt', () => {
    const p = buildCaptionPrompt({ series: 'S', number: 1, parts: 2, title: 't', story: '# t\n@cast x\nHello.', handles: { instagram: '@sf' } })
    expect(p).toContain('Follow @sf for Part 2.')
    expect(p).not.toContain('@cast')
  })
  it('gives the story so far and the cast', () => {
    const p = buildCaptionPrompt({ series: 'S', number: 2, parts: 3, title: 't', story: 'Now.',
      before: [{ number: 1, title: 'One', story: '# One\n@set x\nA receipt.' }], cast: [{ name: 'Cat', body: 'cat' }, { name: 'Ethan', body: 'human' }] })
    expect(p).toContain('Part 1, "One":\nA receipt.')
    expect(p).toContain('Characters: Cat (a cat), Ethan')
    expect(p).not.toContain('@set')
  })
})
