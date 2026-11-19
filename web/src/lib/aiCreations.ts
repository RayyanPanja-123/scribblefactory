// AI Creations: one place to create a library item or cast with AI. Series are created from the Series flow.
// The per-asset prompt builders and importers live in their own files (propPrompt, setPrompt, creatures,
// actionPrompt); this routes a brief to them, adds the cast prompt (docs/STORY_GUIDE.md does the teaching), and turns
// a reply into a reviewable plan that never overwrites.
import type { ActionCatalog, CustomAction, PropCatalog } from '../api/client'
import { buildActionPrompt, importAction } from './actionPrompt'
import { buildCreaturePrompt, importCreature, type CreatureCatalog, type CustomCreature, type Rig } from './creatures'
import { buildPrompt, importProp } from './propPrompt'
import type { CustomProp } from './props'
import { buildSetPrompt, importSet } from './setPrompt'
import type { CustomSet, SetCatalog } from './sets'

export const TYPES = ['prop', 'set', 'creature', 'action', 'cast'] as const
export type Kind = (typeof TYPES)[number]
export const TYPE_LABEL: Record<Kind, string> = { prop: 'Prop', set: 'Set', creature: 'Creature', action: 'Action', cast: 'Cast' }
export const isKind = (k: unknown): k is Kind => TYPES.includes(k as Kind)

export type Library = { props: PropCatalog; sets: SetCatalog; creatures: CreatureCatalog; actions: ActionCatalog }
/** what the user asked for: the description, plus the fields only some types use */
export type Brief = { description: string; name?: string; id?: string; rig?: Rig; series?: string; cast?: string[] }
export type Plan = {
  props: CustomProp[]; sets: CustomSet[]; creatures: CustomCreature[]; actions: CustomAction[]
  cast: Record<string, unknown>[]
}
type ItemKind = 'prop' | 'set' | 'creature' | 'action' | 'cast'
export type Item = { key: string; kind: ItemKind; id: string; was?: string; name: string; status: 'new' | 'existing'; checked: boolean; data: unknown }

export const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60)
/** a short display name from a free description: its first sentence, cut to 40 chars on a word */
export const shortName = (d: string) => {
  const s = d.trim().split(/[\n.;:!?]/)[0].trim()
  return s.length <= 40 ? s : s.slice(0, 40).replace(/\s+\S*$/, '')
}
/** id, or id-2, id-3 … the first one not in taken */
export function uniqueId(id: string, taken: Set<string>): string {
  if (!taken.has(id)) return id
  let n = 2
  while (taken.has(`${id}-${n}`)) n++
  return `${id}-${n}`
}

/** every id already in the library, built in and custom, per asset kind */
export const takenIds = (lib: Library) => ({
  prop: [...lib.props.builtin, ...lib.props.custom.map((p) => p.id)],
  set: [...lib.sets.builtin.map((s) => s.id), ...lib.sets.custom.map((s) => s.id)],
  creature: [...lib.creatures.builtin.map((c) => c.id), 'stickman', ...lib.creatures.custom.map((c) => c.id)],
  action: [...lib.actions.builtin, ...lib.actions.custom.map((a) => a.id)],
})
const inventory = (lib: Library) => JSON.stringify({ props: lib.props, sets: lib.sets, creatures: lib.creatures, actions: lib.actions })

/** the prompt for one brief; guide = docs/STORY_GUIDE.md (cast only) */
export function buildCreationPrompt(kind: Kind, b: Brief, lib: Library, guide = ''): string {
  const name = b.name?.trim() || shortName(b.description)
  const t = takenIds(lib)
  switch (kind) {
    case 'prop': return buildPrompt(name, t.prop, b.description, b.id)
    case 'set': return buildSetPrompt(name, t.set, b.description, b.id)
    case 'creature': return buildCreaturePrompt(name, b.rig ?? 'quadruped', t.creature, b.description, b.id)
    case 'action': return buildActionPrompt(name, t.action, b.description, b.id)
    case 'cast': return `You are designing cast members for a Scribble Factory series. Follow section 6b "Cast JSON" of the attached STORY_GUIDE.md exactly.

Cast to create: ${b.description.trim()}
The series already has these cast ids, use different ones: ${(b.cast ?? []).join(', ') || 'none'}.

Return ONLY valid JSON, with this shape: {"cast": [ <cast entry>, ... ]}
Use only props and creature bodies from the inventory below. No explanations.

CURRENT LIBRARY INVENTORY:
${inventory(lib)}

STORY_GUIDE.md:
${guide}`
  }
}

/** the JSON out of a reply: a fenced block, or the outermost {…} / […] */
function extractJson(text: string): unknown {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/i.exec(text)?.[1]
  if (fenced) return JSON.parse(fenced)
  const a = text.search(/[[{]/)
  return JSON.parse(text.slice(a, Math.max(text.lastIndexOf('}'), text.lastIndexOf(']')) + 1))
}
const empty = (): Plan => ({ props: [], sets: [], creatures: [], actions: [], cast: [] })
const isObj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x)
const castOk = (c: unknown) => isObj(c) && typeof c.id === 'string' && typeof c.name === 'string'

/** a reply -> the plan it describes, or an error message. Every asset goes through its own importer. */
export function parseReply(kind: Kind, text: string): { plan?: Plan; error?: string } {
  const one = <T>(r: { error?: string } & Record<string, unknown>, key: string, list: keyof Plan) => {
    if (r.error) return { error: r.error }
    return { plan: { ...empty(), [list]: [r[key] as T] } }
  }
  if (kind === 'prop') return one(importProp(text), 'prop', 'props')
  if (kind === 'set') return one(importSet(text), 'set', 'sets')
  if (kind === 'creature') return one(importCreature(text), 'creature', 'creatures')
  if (kind === 'action') return one(importAction(text), 'action', 'actions')
  let j: unknown
  try {
    j = extractJson(text)
  } catch (e) {
    return { error: `Not valid JSON: ${(e as Error).message}` }
  }
  const cast = Array.isArray(j) ? j : isObj(j) ? j.cast : null
  if (!Array.isArray(cast) || !cast.length) return { error: 'Expected {"cast": [ … ]} with at least one entry.' }
  const bad = cast.findIndex((c) => !castOk(c))
  if (bad >= 0) return { error: `Cast #${bad + 1}: needs "id" and "name".` }
  return { plan: { ...empty(), cast: cast as Record<string, unknown>[] } }
}

/** the review list. Nothing existing is ever overwritten: on an id clash an asset or cast member gets a suffixed id */
export function reviewItems(plan: Plan, lib: Library, targetCast: string[] = []): Item[] {
  const items: Item[] = []
  const t = takenIds(lib)
  const add = (k: 'prop' | 'set' | 'creature' | 'action', xs: { id: string; name: string }[]) => {
    const taken = new Set(t[k])
    for (const x of xs) {
      const id = uniqueId(x.id, taken)
      taken.add(id)
      items.push({ key: `${k}:${id}`, kind: k, id, was: id !== x.id ? x.id : undefined, name: x.name, status: 'new', checked: true, data: { ...x, id } })
    }
  }
  add('prop', plan.props)
  add('set', plan.sets)
  add('creature', plan.creatures)
  add('action', plan.actions)
  const castTaken = new Set(targetCast)
  for (const c of plan.cast) {
    const id = uniqueId(c.id as string, castTaken)
    castTaken.add(id)
    items.push({ key: `cast:${id}`, kind: 'cast', id, was: id !== c.id ? (c.id as string) : undefined, name: c.name as string, status: 'new', checked: true, data: { ...c, id } })
  }
  return items
}

/** what Import writes: the checked new items */
export const chosen = (items: Item[]): Item[] => items.filter((i) => i.checked && i.status === 'new')
