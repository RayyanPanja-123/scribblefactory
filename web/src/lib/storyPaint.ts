// Story Painter: story.md <-> cards. One card per spoken line, holding the @ lines above it in their order, so
// parse -> write gives the same script (blank lines and indents aside). Each directive kind has form fields; an
// argument the fields cannot hold (several people in one @do, odd syntax) stays a plain text box, never lost.
import { EXPRESSIONS } from './expressions'

export type Row = { name: string; arg: string }
export type Beat = { rows: Row[]; text: string; twist: boolean }
export type Painting = { title: string; beats: Beat[] }

const TWIST = /^\s*!!\s+/

export function parseStory(md: string): Painting {
  const out: Painting = { title: '', beats: [] }
  let rows: Row[] = []
  let first = true
  for (const raw of md.replace(/\r\n/g, '\n').split('\n')) {
    const s = raw.trim()
    if (!s) continue
    if (first && s.startsWith('#')) { out.title = s.replace(/^#+\s*/, ''); first = false; continue }
    first = false
    if (s.startsWith('@')) {
      const [name, ...rest] = s.slice(1).split(/\s+/)
      rows.push({ name, arg: rest.join(' ') })
      continue
    }
    out.beats.push({ rows, text: s.replace(TWIST, ''), twist: TWIST.test(s) })
    rows = []
  }
  if (rows.length) out.beats.push({ rows, text: '', twist: false }) // @ lines after the last spoken line
  return out
}

export function writeStory(p: Painting): string {
  const lines = [`# ${p.title}`, '']
  for (const b of p.beats) {
    for (const r of b.rows) lines.push(`@${r.name} ${r.arg}`.trimEnd())
    if (b.text.trim()) lines.push((b.twist ? '!! ' : '') + b.text.trim())
  }
  return lines.join('\n') + '\n'
}

// ---- directive kinds: form fields <-> the argument text ----

export type Ctx = {
  sets: string[]; actions: string[]; props: string[]; sounds: string[]
  cast: { id: string; name: string; looks: string[] }[]
}
export type Field = { key: string; label: string; type: 'select' | 'text' | 'number' | 'cast'; options?: string[]; names?: Record<string, string> }
type Rec = Record<string, string>
export type Kind = {
  label: string; common: boolean; rank: number // rank: where a new row goes among the card's rows
  fields: (c: Ctx, r: Rec) => Field[]
  parse: (arg: string) => Rec | null // null: the fields cannot hold it (shown as text)
  build: (r: Rec) => string
  start: (c: Ctx) => string // argument of a newly added row
}

export const FX = ['pop', 'shake', 'drop', 'none', 'lightning']
export const WEATHER = ['clear', 'rain', 'snow', 'fog', 'wind', 'storm']
export const CAR = ['arrive', 'ride', 'leave', 'off']
export const MOODS = ['cheer', 'angry', 'gasp', 'neutral', 'off', 'fight']
// pipeline/scribble/background_music.py TRACKS: keep in step
export const TRACKS = ['off', 'monkeys-spinning-monkeys', 'comedy-quirky-sneaky', 'sneaky-snitch', 'cartoon-pizzicato',
  'fluffing-a-duck', 'scheming-weasel-faster', 'funny-comedy-quirky']

// volume as words: '' leaves it out (the sound's own level; music: 15%)
const volume = (normal: string): Field => ({ key: 'vol', label: 'Loudness', type: 'select', options: ['', '0.25', '0.5', '0.75', '1'],
  names: { '': `Normal (${normal})`, '0.25': 'Quiet (25%)', '0.5': 'Half (50%)', '0.75': 'Loud (75%)', '1': 'Full (100%)' } })
const words = (s: string) => s.split(/\s+/).filter(Boolean)
const join = (...xs: (string | undefined)[]) => xs.filter((x) => x?.trim()).map((x) => x!.trim()).join(' ')
const ids = (c: Ctx) => c.cast.map((x) => x.id)
const first = (c: Ctx) => c.cast[0]?.id ?? 'someone'
const who = (c: Ctx): Field => ({ key: 'who', label: 'Who', type: 'select', options: ids(c) })
// "<who>: <rest>" with one person
const pair = (arg: string, rest: string) => {
  const m = /^([^:,\s]+)\s*:\s*(.*)$/.exec(arg)
  return m && !m[2].includes(':') ? { who: m[1], [rest]: m[2] } : null
}
const upTo = (arg: string, n: number, keys: string[]) => {
  const w = words(arg)
  return w.length > n ? null : Object.fromEntries(keys.map((k, i) => [k, w[i] ?? '']))
}

export const KINDS: Record<string, Kind> = {
  set: { label: 'Place', common: true, rank: 0, start: (c) => c.sets[0] ?? 'room',
    fields: (c) => [{ key: 'set', label: 'Place', type: 'select', options: c.sets }],
    parse: (a) => upTo(a, 1, ['set']), build: (r) => r.set },
  weather: { label: 'Weather', common: true, rank: 1, start: () => 'rain',
    fields: () => [{ key: 'kind', label: 'Weather', type: 'select', options: WEATHER },
      { key: 'level', label: 'How strong', type: 'select', options: ['', 'light', 'medium', 'heavy'] }],
    parse: (a) => upTo(a, 2, ['kind', 'level']), build: (r) => join(r.kind, r.level) },
  cast: { label: 'On stage', common: true, rank: 2, start: (c) => ids(c).slice(0, 2).join(', '),
    fields: () => [{ key: 'cast', label: 'On stage', type: 'cast' }],
    parse: (a) => ({ cast: a }), build: (r) => r.cast },
  look: { label: 'Look', common: false, rank: 3, start: (c) => `${first(c)}: default`,
    fields: (c, r) => [who(c), { key: 'look', label: 'Look', type: 'select',
      options: ['default', ...(c.cast.find((x) => x.id === r.who)?.looks ?? [])] }],
    parse: (a) => pair(a, 'look'), build: (r) => `${r.who}: ${r.look}` },
  hold: { label: 'Hold', common: false, rank: 3, start: (c) => `${first(c)}: ${c.props[0] ?? 'none'}`,
    fields: (c) => [who(c), { key: 'prop', label: 'Holds', type: 'select', options: ['none', ...c.props] },
      { key: 'hand', label: 'Hand', type: 'select', options: ['', 'right', 'left'], names: { '': 'Right (or both for none)' } }],
    parse: (a) => {
      const p = pair(a, 'rest'), [prop = '', hand = '', ...more] = words(p?.rest ?? '')
      return p && prop && !more.length && ['', 'left', 'right'].includes(hand) ? { who: p.who, prop, hand } : null
    },
    build: (r) => `${r.who}: ${join(r.prop, r.hand)}` },
  do: { label: 'Action', common: true, rank: 5, start: (c) => `${first(c)}: talk`,
    fields: (c) => [who(c), { key: 'action', label: 'Does', type: 'select', options: c.actions },
      { key: 'extra', label: 'Prop / target', type: 'text' }],
    parse: (a) => {
      const p = pair(a, 'rest')
      if (!p || p.rest.includes(',')) return null
      const [action = '', ...extra] = words(p.rest)
      return { who: p.who, action, extra: extra.join(' ') }
    },
    build: (r) => `${r.who}: ${join(r.action, r.extra)}` },
  face: { label: 'Face', common: true, rank: 6, start: (c) => `${first(c)}: happy`,
    fields: (c) => [who(c), { key: 'face', label: 'Face', type: 'select', options: [...EXPRESSIONS] }],
    parse: (a) => pair(a, 'face'), build: (r) => `${r.who}: ${r.face}` },
  fx: { label: 'Effect', common: true, rank: 7, start: () => 'pop',
    fields: (c, r) => [{ key: 'fx', label: 'Effect', type: 'select', options: FX },
      ...(r.fx === 'lightning' ? [{ key: 'at', label: 'Beside', type: 'select' as const, options: ['', ...ids(c), ...c.props] }] : [])],
    parse: (a) => upTo(a, 2, ['fx', 'at']), build: (r) => join(r.fx, r.fx === 'lightning' ? r.at : '') },
  sfx: { label: 'Sound', common: true, rank: 8, start: (c) => c.sounds[0] ?? '',
    fields: (c) => [{ key: 'id', label: 'Sound', type: 'select', options: c.sounds }, volume('as set on Sounds')],
    parse: (a) => upTo(a, 2, ['id', 'vol']), build: (r) => join(r.id, r.vol) },
  car: { label: 'Car', common: false, rank: 4, start: () => 'arrive',
    fields: () => [{ key: 'mode', label: 'Car', type: 'select', options: CAR }],
    parse: (a) => upTo(a, 1, ['mode']), build: (r) => r.mode },
  dogs: { label: 'Dogs', common: false, rank: 4, start: () => '2',
    fields: () => [{ key: 'n', label: 'Dogs 0-6', type: 'number' }],
    parse: (a) => upTo(a, 1, ['n']), build: (r) => r.n },
  runners: { label: 'Runners', common: false, rank: 4, start: () => '2',
    fields: () => [{ key: 'n', label: 'Runners 0-6', type: 'number' }],
    parse: (a) => upTo(a, 1, ['n']), build: (r) => r.n },
  crowd: { label: 'Crowd', common: false, rank: 4, start: () => 'cheer',
    fields: () => [{ key: 'team', label: 'Team (optional)', type: 'text' },
      { key: 'mood', label: 'Mood', type: 'select', options: MOODS }, { key: 'more', label: 'How many / fights', type: 'text' }],
    parse: (a) => {
      const w = words(a)
      const team = w.length && !MOODS.includes(w[0]) ? w.shift()! : ''
      return w.length > 2 ? null : { team, mood: w[0] ?? '', more: w[1] ?? '' }
    },
    build: (r) => join(r.team, r.mood, r.mood === 'off' ? '' : r.more) },
  'crowd-look': { label: 'Crowd outfit', common: false, rank: 4, start: () => 'red: suit',
    fields: () => [{ key: 'who', label: 'Team', type: 'text' }, { key: 'items', label: 'Clothes (comma separated)', type: 'text' }],
    parse: (a) => { const m = /^([^:]+):\s*(.*)$/.exec(a); return m ? { who: m[1].trim(), items: m[2] } : null },
    build: (r) => `${r.who}: ${r.items}` },
  'crowd-weapon': { label: 'Crowd prop', common: false, rank: 4, start: (c) => `red: ${c.props[0] ?? ''}`,
    fields: (c) => [{ key: 'who', label: 'Team', type: 'text' }, { key: 'prop', label: 'Prop', type: 'select', options: c.props }],
    parse: (a) => pair(a, 'prop'), build: (r) => `${r.who}: ${r.prop}` },
  'background-music': { label: 'Music', common: false, rank: 4, start: () => TRACKS[1],
    fields: () => [{ key: 'track', label: 'Track', type: 'select', options: TRACKS }, volume('15%')],
    parse: (a) => upTo(a, 2, ['track', 'vol']), build: (r) => join(r.track, r.track === 'off' ? '' : r.vol) },
}

/** problems with line i that can be told without the server (the Check button still runs the full story check) */
export function lintBeat(beats: Beat[], i: number, c: Ctx): string[] {
  const b = beats[i]
  const out: string[] = []
  if (/\d/.test(b.text)) out.push('Spell numbers out as words ("eighteen", not "18").')
  if (b.twist && i !== beats.length - 1) out.push('The twist goes on the very last line only.')
  const sound = (x?: Beat) => !!x?.rows.some((r) => r.name === 'sfx')
  if (sound(b) && sound(beats[i - 1])) out.push('Sounds on two lines in a row: leave a line between them.')
  for (const r of b.rows) {
    const k = KINDS[r.name]
    if (!k) { out.push(`@${r.name} is not a known direction.`); continue }
    const rec = k.parse(r.arg)
    if (!rec) continue // written by hand in a shape the fields cannot hold (several people in one @do): the full check reads it
    for (const f of k.fields(c, rec)) {
      const v = rec[f.key]?.trim()
      // empty lists: the library has not loaded yet, so nothing can be told
      // a volume is any number 0-1 (the menu only offers presets), not a library id
      if (f.key === 'vol' && v && !(Number(v) >= 0 && Number(v) <= 1)) out.push(`${k.label}: loudness "${v}" must be 0 to 1.`)
      else if (f.type === 'select' && f.key !== 'vol' && v && f.options?.length && !f.options.includes(v)) out.push(`${k.label}: "${v}" is not in the library.`)
      if (f.type === 'cast' && c.cast.length) {
        for (const id of v.split(',').map((x) => x.trim()).filter(Boolean))
          if (!c.cast.some((x) => x.id === id)) out.push(`On stage: "${id}" is not in this series' cast.`)
      }
    }
  }
  return out
}

/** a new row of this kind, put in reading order (place, weather, who is on stage, ... the next-line ones last) */
export function addRow(b: Beat, name: string, c: Ctx): void {
  const rank = KINDS[name].rank
  const at = b.rows.findIndex((r) => (KINDS[r.name]?.rank ?? 4) > rank)
  b.rows.splice(at < 0 ? b.rows.length : at, 0, { name, arg: KINDS[name].start(c) })
}
