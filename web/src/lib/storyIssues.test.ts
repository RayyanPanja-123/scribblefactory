import { describe, expect, it } from 'vitest'
import { groupIssues, nameOf } from './storyIssues'

describe('groupIssues', () => {
  it('groups missing items by kind (looks by owner), dedupes ids, keeps the rest apart', () => {
    const { groups, rest } = groupIssues([
      { line: 3, message: 'unknown set', missing: { kind: 'set', ids: ['moon'] } },
      { line: 4, message: 'unknown cast id', missing: { kind: 'cast', ids: ['zed', 'kim'] } },
      { line: 6, message: 'unknown cast id', missing: { kind: 'cast', ids: ['zed'] } },
      { line: 8, message: 'no look', missing: { kind: 'look', ids: ['crown'], owner: 'bob' } },
      { line: 9, message: '@do has no text line after it' },
    ])
    expect(groups.map((g) => [g.kind, g.ids, g.issues.length])).toEqual([['cast', ['zed', 'kim'], 2], ['look', ['crown'], 1], ['set', ['moon'], 1]])
    expect(groups[1].owner).toBe('bob')
    expect(rest.map((r) => r.line)).toEqual([9])
    expect(nameOf('fred-lorz')).toBe('Fred Lorz')
  })
})
