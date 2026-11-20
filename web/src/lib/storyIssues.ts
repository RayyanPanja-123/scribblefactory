// The story check's problems, grouped by what is missing (storycheck.MISSING tags them), so each group gets one fix
// button: add the characters, make the prop with AI, and so on. Everything untagged stays in a plain list.
import type { StoryCheck } from '../api/client'

type Issue = StoryCheck['problems'][number]
export type Kind = NonNullable<Issue['missing']>['kind']
export type Group = { kind: Kind; owner: string | null; ids: string[]; issues: Issue[] }

export const KIND_LABEL: Record<Kind, string> = {
  cast: 'Characters not in the cast', set: 'Missing sets', prop: 'Missing props', action: 'Missing actions',
  look: 'Missing looks', sound: 'Missing sounds', wardrobe: 'Missing wardrobe', unapproved: 'Characters not approved yet',
}
const ORDER: Kind[] = ['cast', 'unapproved', 'look', 'set', 'prop', 'action', 'wardrobe', 'sound']

export function groupIssues(problems: Issue[]): { groups: Group[]; rest: Issue[] } {
  const groups: Group[] = []
  const rest: Issue[] = []
  for (const p of problems) {
    const m = p.missing
    if (!m) { rest.push(p); continue }
    const owner = m.owner ?? null
    let g = groups.find((x) => x.kind === m.kind && x.owner === owner)
    if (!g) groups.push((g = { kind: m.kind, owner, ids: [], issues: [] }))
    g.issues.push(p)
    for (const id of m.ids) if (!g.ids.includes(id)) g.ids.push(id)
  }
  groups.sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind))
  return { groups, rest }
}

/** "fred-lorz" -> "Fred Lorz": a starting name for a character the story already uses */
export const nameOf = (id: string) => id.split(/[-_]/).filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(' ')
