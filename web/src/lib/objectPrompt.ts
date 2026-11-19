import type { ObjectPiece, WorldObject } from './objects'

const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
const sizes: Record<ObjectPiece['shape'], number> = { box: 3, cyl: 3, ball: 1, mound: 2 }
const hex = (v: unknown, fallback: string) => typeof v === 'string' && /^#[0-9a-fA-F]{6}$/.test(v) ? v : fallback
const nums = (v: unknown, n: number) => Array.isArray(v) && v.length === n && v.every((x) => typeof x === 'number')

export function buildObjectPrompt(name: string, taken: string[], details = '') {
  const thing = name.trim() || 'a world object'
  const id = slugify(thing) || 'world-object'
  return `Design a reusable World Object for a flat 3D stick-figure cartoon renderer: ${thing}.${details.trim() ? `\nDescription: ${details.trim()}` : ''}

Reply with ONE JSON object in a \`\`\`json code block and nothing else.

Format:
{"id":"${id}","name":"${name.trim().slice(0, 40) || '<name>'}","category":"vehicle|container|furniture|equipment|debris|other","capabilities":[],"carry_mode":"none|one-hand|two-hand|vehicle","pieces":[]}

Use only these capabilities: move, carry, enter, ride, open, close, break, steal, remove. Use two-hand for large objects such as barrels and crates. The id must be lowercase with dashes and must not be one of: ${taken.join(', ') || '(none)'}.
Each piece uses one primitive: {"shape":"box|cyl|ball|mound","at":[x,y,z],"size":[...],"color":"#rrggbb"}. Box and cylinder use three size values, ball one, mound two. Use 1 to 8 chunky pieces, with coordinates and sizes between -4 and 4. Make it readable at 9:16 video size.`
}

export function importObject(text: string): { object?: WorldObject; error?: string } {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(text)?.[1]
  const raw = fenced ?? text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1)
  let j: unknown
  try { j = JSON.parse(raw) } catch (e) { return { error: `Not valid JSON: ${(e as Error).message}` } }
  const o = (Array.isArray((j as { objects?: unknown })?.objects) ? (j as { objects: unknown[] }).objects[0] : j) as Partial<WorldObject>
  if (!o || typeof o !== 'object' || !Array.isArray(o.pieces)) return { error: 'Expected an object with a non-empty pieces array.' }
  const pieces: ObjectPiece[] = []
  for (const [i, p] of (o.pieces as Partial<ObjectPiece>[]).entries()) {
    const n = sizes[p.shape as ObjectPiece['shape']]
    if (!n || !nums(p.at, 3) || !nums(p.size, n)) return { error: `Piece #${i + 1} has invalid shape, at, or size.` }
    pieces.push({ shape: p.shape!, at: p.at!, size: p.size!, color: hex(p.color, '#8a5a32') })
  }
  const capabilities = (Array.isArray(o.capabilities) ? o.capabilities : []).filter((x): x is WorldObject['capabilities'][number] => ['move','carry','enter','ride','open','close','break','steal','remove'].includes(String(x)))
  const carry_mode = ['none','one-hand','two-hand','vehicle'].includes(String(o.carry_mode)) ? o.carry_mode! : 'none'
  if (carry_mode !== 'none' && !capabilities.includes('carry')) capabilities.push('carry')
  const name = typeof o.name === 'string' && o.name.trim() ? o.name.trim().slice(0, 40) : 'New World Object'
  return { object: { id: slugify(typeof o.id === 'string' ? o.id : name) || 'world-object', name, category: ['vehicle','container','furniture','equipment','debris','other'].includes(String(o.category)) ? o.category! : 'other', capabilities, carry_mode, pieces } }
}
