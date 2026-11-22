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
})
