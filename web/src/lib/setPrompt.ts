// "Build with AI" for sets: a self-contained prompt that teaches any chat AI the custom set format, and the importer
// for what it sends back. The server (schema CustomSet / SetPiece) and the engine (stage clearance) still check
// everything on save and in the preview.
import type { CustomSet, SetPiece } from './sets'

const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
const SIZES: Record<SetPiece['shape'], number> = { box: 3, cyl: 3, ball: 1, mound: 2 }

// the built-in office, written in the custom format: the AI copies its scale and layout
const EXAMPLE: CustomSet = { id: 'office', name: 'Office', kind: 'indoor', floor: '#4fa39b', back: '#f2bd85', pieces: [
  { shape: 'box', at: [0, 2.4, -2.58], size: [2.4, 1.0, 0.06], color: '#9fd3f5', backdrop: true },
  { shape: 'box', at: [-2.0, 2.3, -2.58], size: [0.7, 0.95, 0.04], color: '#e76f51', backdrop: true },
  { shape: 'box', at: [-1.8, 0.75, -2.05], size: [1.6, 0.08, 0.8], color: '#d99a4e' },
  { shape: 'box', at: [-1.8, 1.07, -2.3], size: [0.62, 0.42, 0.05], color: '#2d3440' },
  { shape: 'box', at: [1.8, 0.75, -2.05], size: [1.6, 0.08, 0.8], color: '#d99a4e' },
  { shape: 'cyl', at: [3.0, 0.45, -2.1], size: [0.25, 0.25, 0.9], color: '#f4f4f4' },
  { shape: 'cyl', at: [-3.0, 0.2, -2.1], size: [0.25, 0.2, 0.4], color: '#c8553d' },
  { shape: 'ball', at: [-3.0, 0.75, -2.1], size: [0.45], color: '#43aa8b' },
] }
const compact = (s: CustomSet) => JSON.stringify({ ...s, pieces: undefined }).replace(/}$/, ', "pieces": [\n')
  + s.pieces!.map((p) => `  ${JSON.stringify(p)}`).join(',\n') + '\n]}'

/** the prompt for a set called "name": paste it into any AI chat; taken = set names already in use; details = what it
 *  should look like (optional); id = the id the story already uses (default: from the name) */
export function buildSetPrompt(name: string, taken: string[], details = '', id = ''): string {
  const thing = name.trim() || 'a set'
  id = slugify(id || thing) || 'set'
  const title = name.trim() ? JSON.stringify(name.trim().slice(0, 40)) : '"<display name, max 40 chars>"'
  const brief = details.trim() ? `\n\nWhat it should look like: ${details.trim()}` : ''
  return `You are designing a set (a scene location) for a 3D cartoon renderer with stick-figure actors. Design: **${thing}**.${brief}

Reply with ONE JSON object in a \`\`\`json code block and nothing else.

## Format
{"id": "${id}", "name": ${title}, "kind": "indoor" | "outdoor",
 "floor": "#rrggbb", "back": "#rrggbb", "pieces": [ <piece>, ... ]}

- id and name: use exactly the ones above (the id is lowercase a-z, 0-9 and single dashes). Must NOT be one of: ${taken.join(', ')}.
- kind: indoor = a floor and a back wall at z -2.6 ("back" is the wall colour). outdoor = a wide floor and a sky
  ("back" is the sky colour); actors can walk and the world scrolls past along x.
- pieces: 5 to 25 (max 60), drawn in order. Each piece is one of:
  - {"shape": "box",   "at": [x, y, z], "size": [width, height, depth], "color": "#rrggbb"}
  - {"shape": "cyl",   "at": [x, y, z], "size": [top radius, bottom radius, height], "color": "#rrggbb"}
  - {"shape": "ball",  "at": [x, y, z], "size": [radius], "color": "#rrggbb"}
  - {"shape": "mound", "at": [x, y, z], "size": [radius, height factor 0.1-1], "color": "#rrggbb"}   squashed half-sphere: hills, bushes
  Optional on any piece: "backdrop": true (wall pictures, windows, far hills: never hidden behind an actor),
  "outline": false (no black ink outline; use for flat things on a wall).
- "at" is the CENTRE of the piece, so a box of height h standing on the floor has y = h / 2.

## Space (world units, about 1 unit = 1 metre)
- Floor at y = 0. Actors stand on z = 0, x between -2 and 2; they are about 1.6 tall. The camera looks from +z.
- STAGE CLEARANCE (hard rule, the renderer refuses otherwise): anything that reaches into |x| < 2.2 must sit entirely
  behind z -1.0 (its front face, z + depth/2, below -1.0). Nothing may come forward of z 0.6 anywhere.
- Indoor: the back wall is at z -2.6, so furniture sits between z -2.5 and -1.0; wall pictures at z about -2.55.
  The visible width is about x -3.5..3.5.
- Outdoor: put near props between z -1.5 and -12, repeated across x -14..14 (the world scrolls and wraps that band);
  far scenery (mounds, big shapes) at z -20..-60 with "backdrop": true.
- Every number within -80..80; sizes 0..80.

## Style
Flat, bold, readable cartoon: simple chunky shapes, saturated clear colours, nothing tiny (it vanishes at video size).
Build each object from 1-4 pieces (a table: top + legs; a tree: trunk cylinder + ball).

## Example (the built-in office, in this exact format)
\`\`\`json
${compact(EXAMPLE)}
\`\`\`

Now design **${thing}** and reply with only its JSON object.`
}

const hex = (v: unknown, fallback: string) => (typeof v === 'string' && /^#[0-9a-fA-F]{6}$/.test(v) ? v : fallback)
const nums = (v: unknown, n: number) => Array.isArray(v) && v.length === n && v.every((x) => typeof x === 'number')

/** the AI's reply (raw JSON, a fenced block, or JSON inside other text; a {"sets": [...]} file takes the first) ->
 *  a set to load into the editor, or an error message */
export function importSet(text: string): { set?: CustomSet; error?: string } {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(text)?.[1]
  const raw = fenced ?? text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1)
  let j: unknown
  try {
    j = JSON.parse(raw)
  } catch (e) {
    return { error: `Not valid JSON: ${(e as Error).message}` }
  }
  const s = (Array.isArray((j as { sets?: unknown })?.sets) ? (j as { sets: unknown[] }).sets[0] : j) as Partial<CustomSet>
  if (!s || typeof s !== 'object' || !Array.isArray(s.pieces)) return { error: 'Expected an object with a "pieces" array.' }
  const pieces: SetPiece[] = []
  for (const [i, p] of (s.pieces as Partial<SetPiece>[]).entries()) {
    const n = SIZES[p?.shape as SetPiece['shape']]
    if (!n || !nums(p.at, 3) || !nums(p.size, n)) {
      return { error: `Piece #${i + 1}: needs "shape" (box, cyl, ball, mound), "at" as [x, y, z] and "size" with ${n ?? 'the right number of'} values.` }
    }
    pieces.push({ shape: p.shape!, at: p.at!, size: p.size!, color: hex(p.color, '#999999'),
      ...(p.backdrop ? { backdrop: true } : {}), ...(p.outline === false ? { outline: false } : {}) })
  }
  const name = typeof s.name === 'string' && s.name.trim() ? s.name.trim().slice(0, 40) : 'New set'
  return { set: { id: slugify(typeof s.id === 'string' ? s.id : name) || 'set', name, kind: s.kind === 'outdoor' ? 'outdoor' : 'indoor',
    floor: hex(s.floor, '#d9c7a3'), back: hex(s.back, '#f6e7c8'), pieces } }
}
