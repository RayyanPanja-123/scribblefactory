// The wardrobe: clothing, hair and cosmetics a humanoid cast member wears, one item per slot (engine/page/wardrobe.js).
// Built-ins are the original tops / headwear / legwear (hand-drawn, read only); custom items are ink layers anchored to
// body points. Also "Build with AI": a self-contained prompt with the format and one example per slot, and the importer
// for the reply. The server (schema WardrobeItem) checks everything on save.
import type { components } from '../api/types'
import seedRaw from '../../../pipeline/scribble/seed/wardrobe.json?raw'
import { PTS_CHECK, aiCheck } from './aiCheck'

export type WardrobeItem = components['schemas']['WardrobeItem']
export type WardrobeLayer = components['schemas']['WardrobeLayer']
export type WardrobeCatalog = components['schemas']['WardrobeCatalog']
export type Slot = WardrobeItem['slot']
export type Anchor = WardrobeLayer['anchor']
export type Build = Partial<Record<'head' | 'body_w' | 'body_h' | 'leg' | 'arm', number>> & { head_color?: string }

/** the API fills a missing top colour with this (schemas BUILTIN_WARDROBE_DEFAULT_COLORS) */
export const DEFAULT_TOP_COLOR = '#4a6fa5'
export const SLOTS: Slot[] = ['hair', 'facial_hair', 'headwear', 'top', 'legwear', 'footwear', 'back', 'accessory', 'face']
export const LIST_SLOTS: Slot[] = ['accessory', 'face']
export const SLOT_LABEL: Record<Slot, string> = {
  hair: 'Hair', facial_hair: 'Facial hair', headwear: 'Headwear', top: 'Top', legwear: 'Legwear', footwear: 'Footwear',
  back: 'Back', accessory: 'Accessory', face: 'Face',
}
/** where a layer hangs; local x across (+ outward on paired anchors), y down / along the limb */
export const ANCHORS: Record<Anchor, string> = {
  head: 'head centre (head radius 150; scales with the head)',
  head_top: 'top of the head (the head centre is at y 145 below it)',
  face: 'face centre (turns with the face: eyes at x ±50, y −8; mouth at y 74)',
  eyes: 'between the eyes (eyes at x ±50, radius 30)',
  mouth: 'the mouth (mouth ±22 wide; the chin is about y 70)',
  neck: 'top of the body (body 184 wide, 300 tall; scales with body_w × body_h)',
  shoulders: 'each shoulder (paired: drawn on both sides, x outward)',
  chest: 'the chest (110 below the neck)',
  waist: 'the waist (about 225 below the neck)',
  hips: 'the hips (the legs start here; the feet are 220 below)',
  back: 'the back (60 below the neck)',
  arms: 'each upper arm (paired: y runs along the arm from the shoulder, elbow at y 91)',
  hands: 'each hand (paired)',
  legs: 'each leg (paired: y runs along the leg from the hip, foot at y 220; follows the stride)',
  feet: 'each foot (paired: x outward, y down; the ground is about y 0)',
}
/** what each preview pose needs on top of its action (stickman.js drawStickman options) */
export const PREVIEW_POSES: Record<string, Record<string, unknown>> = {
  idle: {}, walk: { phase: 0.3 }, run: { phase: 0.7 }, talk: { mouth: 0.7, gesture: { kind: 'palm', k: 1 } }, point: {},
  wave: { wave: { k: 1, swing: 0.4 } }, react: {}, cheer: { mood: { k: 1, bounce: 0, shake: 0 } },
  angry: { mood: { k: 1, bounce: 0, shake: 0.5 } }, gasp: { mood: { k: 1, bounce: 0, shake: 0 } }, salute: { mood: { k: 1, bounce: 0, shake: 0 } },
  stagger: { phase: 0.3, stagger: { sway: 0.6, buckle: 0.3 } }, collapse: { buckle: 0.6 },
  eat: { eat: { k: 1, side: 1 }, props: [{ kind: 'apple', hand: 'right' }] },
  give: { reach: { side: 1, k: 1 }, props: [{ kind: 'medal', hand: 'right' }] },
  carry: { reach: { side: 1, k: 1 }, phase: 0.3 }, support: { reach: { side: 1, k: 1 }, phase: 0.3 },
}

export const SHAPES = ['rect', 'circle', 'ellipse', 'line', 'poly'] as const

const SEED = JSON.parse(seedRaw).wardrobe as WardrobeItem[]
// one example per slot: the seed's first item of it; the seed has no legwear, so one is written here
const LEGWEAR: WardrobeItem = { id: 'breeches', name: 'Breeches', slot: 'legwear', colorable: true, default_color: '#5a4632', default_accent: '#2b1d12', layers: [
  { shape: 'rect', anchor: 'hips', pts: [[-55, -12], [55, 30]], fill: '$accent', width: 8, r: null, ry: null, rot: 0, behind: false, when: null },
  { shape: 'poly', anchor: 'legs', pts: [[-24, 0], [24, 0], [20, 130], [-20, 130]], fill: '$color', width: 8, r: null, ry: null, rot: 0, behind: false, when: null },
] }
export const EXAMPLES: WardrobeItem[] = SLOTS.map((s) => (s === 'legwear' ? LEGWEAR : SEED.find((w) => w.slot === s)!))

/** one layer without its defaults (shorter in a prompt) */
function lean(L: WardrobeLayer): Partial<WardrobeLayer> {
  const o: Record<string, unknown> = { ...L }
  for (const [k, d] of Object.entries({ r: null, ry: null, rot: 0, behind: false, when: null, width: 8, fill: null })) if (o[k] === d) delete o[k]
  return o
}
const compact = (w: WardrobeItem) => `{"id": "${w.id}", "name": "${w.name}", "slot": "${w.slot}", "colorable": ${w.colorable}, ` +
  `"default_color": "${w.default_color}", "default_accent": "${w.default_accent ?? '#3a2a1e'}", "layers": [\n${w.layers.map((L) => `  ${JSON.stringify(lean(L))}`).join(',\n')}\n]}`

const toId = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')

/** the prompt for a wardrobe item called "name" in slot: paste it into any AI chat; taken = ids already in use */
export function buildWardrobePrompt(name: string, slot: Slot, taken: string[], details = '', id = ''): string {
  const thing = name.trim() || `a ${SLOT_LABEL[slot].toLowerCase()} item`
  id = toId(id || thing) || slot
  const title = name.trim() ? JSON.stringify(name.trim().slice(0, 40)) : '"<display name, max 40 chars>"'
  const brief = details.trim() ? `\n\nWhat it should look like: ${details.trim()}` : ''
  return `You are designing a wardrobe item (${SLOT_LABEL[slot].toLowerCase()}) for a hand-drawn stick-figure cartoon renderer. Design: **${thing}**.${brief}

Reply with ONE JSON object in a \`\`\`json code block and nothing else.

## Format
{"id": "${id}", "name": ${title}, "slot": "${slot}", "colorable": true, "default_color": "#rrggbb", "default_accent": "#rrggbb", "layers": [ <layer>, ... ]}

- id, name and slot: use exactly the ones above (ids: lowercase a-z, 0-9, single _ or -). Must NOT be one of: ${taken.join(', ') || '(none)'}.
- colorable: true when a cast member may recolour it ("$color" fills take their main colour, "$accent" fills their
  accent), false for a fixed look. default_color / default_accent: the colours before anyone recolours it.
- layers: 1 to 12 shapes (max 60), drawn in order, later ones on top. Each is one of:
  - {"shape": "rect",    "anchor": A, "pts": [[x0, y0], [x1, y1]], "fill": F, "width": 8}   two corners
  - {"shape": "circle",  "anchor": A, "pts": [[cx, cy]], "r": 20, "fill": F, "width": 8}
  - {"shape": "ellipse", "anchor": A, "pts": [[cx, cy]], "r": 30, "ry": 15, "rot": 0, "fill": F, "width": 8}
  - {"shape": "poly",    "anchor": A, "pts": [[x, y], [x, y], [x, y], ...], "fill": F, "width": 8}   3 to 40 points, closed
  - {"shape": "line",    "anchor": A, "pts": [[x, y], [x, y], ...], "fill": F, "width": 6}   open stroke; fill is its colour (default ink)
- fill: "$color" (the worn main colour), "$accent" (the worn accent: use it for the second colour of a two-tone item,
  e.g. a hat band, trim, stripes, buttons, a tie), a "#rrggbb" hex, or null (outline only). width: black outline 0 to 40 (0: none).
- optional "behind": true draws the layer behind the head and body (long hair falling down the back, a cape).
- optional "when": ["happy", ...] shows the layer only with those expressions (neutral, happy, cheer, sad, angry, surprised,
  sleepy, cheeky, exhausted, worried, dead, smug, proud, love, excited, relieved, laughing, wink, furious, annoyed, disgusted, crying, scared, embarrassed, jealous, guilty, confused, thinking, suspicious, shocked, deadpan, bored, facepalm_ready, dizzy, drunk, knocked_out, evil, crazy, blank, sick, determined).
- Coordinates are numbers within -600..600, in canvas px around the anchor. No other keys.

## Anchors (A): where a layer hangs; x across, y DOWN
${Object.entries(ANCHORS).map(([a, d]) => `- ${a}: ${d}`).join('\n')}

The figure: head radius 150 sitting on a body blob 184 wide and 300 tall, stick arms (175) and legs (220), dot hands.
Head anchors move and scale with the head and turn with the face; body anchors stretch with the character's build;
paired anchors draw the layer on both sides (mirrored on the left) and follow the limbs as they move. The face (eyes,
brows, mouth) is drawn by the renderer and animates: keep hair above the brows (y < -90 from the head centre) and
facial hair below the mouth so talking still shows.

## Draw order (back to front)
behind layers, back, legwear, footwear, the body / top, accessory, the arms, the head and face, face items, facial_hair,
hair, headwear.

## Style
Flat, bold, readable cartoon: few simple shapes, flat fills, thick black outlines, no gradients, no tiny details. The
renderer adds a hand-drawn wobble itself.

## Examples (one per slot, in this exact format)
${EXAMPLES.map((e) => `\`\`\`json\n${compact(e)}\n\`\`\``).join('\n\n')}

${aiCheck([
  'Name the 2-3 features that make this item recognisable at a glance (a pirate hat: wide tricorn brim, skull badge) and draw those big; leave out stitching, folds and tiny patterns.',
  'Choose the anchor that moves with it: hats on head_top, glasses on eyes, sleeves on arms, trousers on legs (paired, so they follow the stride). Use as few anchors as the item needs.',
  'Size it against the figure: the head is 300 across, the body 184 wide and 300 tall. Clothes cover the part they belong to with a little overlap, so no gaps show at the seams.',
  'Main colour as "$color" and one second colour as "$accent", so cast members can recolour it; fixed hex only for things that never change (a gold buckle, a white collar).',
], [
  PTS_CHECK,
  'Every layer has an anchor from the list; circles have "r", ellipses "r" and "ry".',
  'Nothing covers the eyes or mouth unless the item is meant to (glasses, a mask, a beard below the mouth).',
])}

Now design **${thing}** and reply with only its JSON object.`
}

const hex = (v: unknown, fallback: string) => (typeof v === 'string' && /^#[0-9a-f]{6}$/i.test(v) ? v : fallback)

/** the AI's reply (raw JSON, a fenced block, JSON inside other text, or a {"wardrobe": [...]} file: the first) ->
 *  an item to load into the editor, or an error message. The server checks the rest on save. */
export function importWardrobe(text: string, slot?: Slot): { item?: WardrobeItem; error?: string } {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(text)?.[1]
  const raw = fenced ?? text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1)
  let j: unknown
  try {
    j = JSON.parse(raw)
  } catch (e) {
    return { error: `Not valid JSON: ${(e as Error).message}` }
  }
  const w = (Array.isArray((j as { wardrobe?: unknown })?.wardrobe) ? (j as { wardrobe: unknown[] }).wardrobe[0] : j) as Partial<WardrobeItem>
  if (!w || typeof w !== 'object' || !Array.isArray(w.layers)) return { error: 'Expected an object with a "layers" array.' }
  const s = (SLOTS.includes(w.slot as Slot) ? w.slot : slot) as Slot | undefined
  if (!s) return { error: `"slot" must be one of ${SLOTS.join(', ')}.` }
  const layers: WardrobeLayer[] = []
  for (const [i, L] of (w.layers as Partial<WardrobeLayer>[]).entries()) {
    const ok = L && SHAPES.includes(L.shape as never) && (L.anchor as string) in ANCHORS && Array.isArray(L.pts)
      && L.pts.every((pt) => Array.isArray(pt) && pt.length === 2 && pt.every((v) => typeof v === 'number'))
    if (!ok) return { error: `Layer #${i + 1}: needs "shape" (${SHAPES.join(', ')}), "anchor" and "pts" as [[x, y], ...].` }
    const round = L.shape === 'circle' || L.shape === 'ellipse'
    layers.push({ shape: L.shape!, anchor: L.anchor!, pts: L.pts!, r: round ? L.r ?? 20 : null, ry: L.shape === 'ellipse' ? L.ry ?? 12 : null,
      rot: L.rot ?? 0, fill: L.fill ?? null, width: L.width ?? 8, behind: !!L.behind, when: L.when?.length ? L.when : null })
  }
  const name = typeof w.name === 'string' && w.name.trim() ? w.name.trim().slice(0, 40) : 'New item'
  return { item: { id: toId(typeof w.id === 'string' ? w.id : name) || s, name, slot: s, layers, colorable: w.colorable !== false,
    default_color: hex(w.default_color, '#6b4f3a'), default_accent: hex(w.default_accent, '#3a2a1e') } }
}

/** every item a cast slot can use: built-ins first, then the library's */
export const wardrobeOptions = (c: WardrobeCatalog | null | undefined) =>
  [...(c?.builtin ?? []).map((b) => ({ ...b, builtin: true })), ...(c?.custom ?? []).map((w) => ({ id: w.id, name: w.name, slot: w.slot, builtin: false }))]

/** "<slug> · <cast name>" for each cast member wearing item id (own look or a named one) */
export function wearers(series: { series: { slug: string; title: string; cast: Record<string, unknown>[] } }[], id: string) {
  const ids = (v: unknown): string[] => Array.isArray(v) ? v.flatMap(ids) : typeof v === 'string' ? [v]
    : v && typeof v === 'object' ? [((v as Record<string, unknown>).id ?? (v as Record<string, unknown>).kind ?? (v as Record<string, unknown>).style) as string] : []
  const wears = (m: Record<string, unknown>) => SLOTS.some((s) => ids(m[s]).includes(id))
  return series.flatMap((d) => d.series.cast.filter((c) => wears(c) || Object.values((c.looks ?? {}) as Record<string, Record<string, unknown>>).some(wears))
    .map((c) => ({ slug: d.series.slug, title: d.series.title, name: c.name as string })))
}
