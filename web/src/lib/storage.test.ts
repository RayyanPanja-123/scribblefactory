import { describe, expect, it } from 'vitest'
import type { StoredFile } from '../api/client'
import { biggest, byKind, duration, kindOf } from './storage'

const file = (filename: string, content_type: string, size_bytes: number, duration_s: number | null = null): StoredFile => ({
  slug: 's', part: 'part-01', path: 's/01-t', filename, size_bytes, content_type, duration_s, sha256: 'x',
  created_at: '2026-11-23T00:00:00Z', updated_at: '2026-11-23T00:00:00Z',
})

describe('stored files', () => {
  const files = [file('final.mp4', 'video/mp4', 900, 36.1), file('voice.mp3', 'audio/mpeg', 300, 37.6),
    file('voice-tight.wav', 'audio/wav', 600, 37), file('story.md', 'text/markdown', 10), file('qa.json', 'application/json', 5)]

  it('sorts content types into kinds; json and captions count as text', () => {
    expect([kindOf('video/mp4'), kindOf('audio/wav'), kindOf('image/png'), kindOf('application/json'), kindOf('text/x-ssa')])
      .toEqual(['video', 'audio', 'image', 'text', 'text'])
  })

  it('totals each kind, lists empty kinds, and scales bars to the largest', () => {
    const t = Object.fromEntries(byKind(files).map((k) => [k.key, k]))
    expect([t.video.files, t.video.bytes, t.audio.files, t.audio.bytes, t.image.files, t.text.bytes]).toEqual([1, 900, 2, 900, 0, 15])
    expect(t.audio.seconds).toBeCloseTo(74.6)
    expect([t.video.pct, t.audio.pct, t.image.pct]).toEqual([100, 100, 0])
  })

  it('picks the biggest files and writes durations', () => {
    expect(biggest(files, 2).map((f) => f.filename)).toEqual(['final.mp4', 'voice-tight.wav'])
    expect([duration(196.1), duration(36.1), duration(0)]).toEqual(['3 min 16 s', '36 s', '0 s'])
  })
})
