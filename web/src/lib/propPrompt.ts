// "Build with AI": a self-contained prompt that teaches any chat AI (web or CLI) the custom prop format, and the
// importer for what it sends back. The server (schema PropShape / CustomProp) still checks everything on save.
import type { CustomProp, PropShape } from './props'
import { PTS_CHECK, aiCheck } from './aiCheck'
import { slugify } from './slug'


// three built-ins, written in the custom format: the AI copies their scale and style
const EXAMPLES: CustomProp[] = [
  { id: 'bottle', name: 'Bottle', shapes: [
    { shape: 'rect', pts: [[-7, -96], [7, -68]], fill: '#7fb8d6', width: 7 },
    { shape: 'rect', pts: [[-9, -108], [9, -96]], fill: '#d84a3a', width: 6 },
    { shape: 'rect', pts: [[-15, -72], [15, 22]], fill: '#7fb8d6', width: 8 },
    { shape: 'rect', pts: [[-15, -42], [15, -14]], fill: '#ffffff', width: 4 },
  ] },
  { id: 'stopwatch', name: 'Stopwatch', shapes: [
    { shape: 'rect', pts: [[2, -66], [14, -54]], fill: '#cfd3d6', width: 6 },
    { shape: 'circle', pts: [[8, -26]], r: 30, fill: '#cfd3d6', width: 8 },
    { shape: 'circle', pts: [[8, -26]], r: 20, fill: '#ffffff', width: 4 },
    { shape: 'line', pts: [[8, -26], [17, -38]], width: 4 },
  ] },
  { id: 'syringe', name: 'Syringe', shapes: [
    { shape: 'line', pts: [[-10, 0], [-36, 0]], width: 7 },
    { shape: 'line', pts: [[-36, -13], [-36, 13]], width: 7 },
    { shape: 'rect', pts: [[-10, -12], [70, 12]], fill: '#eef6f8', width: 7 },
    { shape: 'rect', pts: [[22, -6], [66, 6]], fill: '#e05656', width: 0 },
    { shape: 'line', pts: [[-4, -22], [-4, 22]], width: 6 },
    { shape: 'line', pts: [[70, 0], [106, 0]], width: 3 },
  ] },
]
const compact = (p: CustomProp) =>
  `{"id": "${p.id}", "name": "${p.name}", "shapes": [\n${p.shapes.map((s) => `  ${JSON.stringify(s)}`).join(',\n')}\n]}`

/** the prompt for a prop called "name": paste it into any AI chat; taken = prop ids already in use; details = what it
 *  should look like (optional); id = the id the story already uses (default: from the name) */
export function buildPrompt(name: string, taken: string[], details = '', id = ''): string {
  const thing = name.trim() || 'a prop'
  id = slugify(id || thing) || 'prop'
  const title = name.trim() ? JSON.stringify(name.trim().slice(0, 40)) : '"<display name, max 40 chars>"'
  const brief = details.trim() ? `\n\nWhat it should look like: ${details.trim()}` : ''
  return `You are drawing a prop for a hand-drawn stick-figure cartoon renderer. Design: **${thing}**.${brief}

Reply with ONE JSON object in a \`\`\`json code block and nothing else.

## Format
{"id": "${id}", "name": ${title}, "shapes": [ <shape>, ... ]}

- id and name: use exactly the ones above (the id is lowercase a-z, 0-9 and single dashes). Must NOT be one of: ${taken.join(', ')}.
- shapes: 3 to 15 shapes (max 40), drawn in order, later ones on top.

Each shape is one of:
- {"shape": "rect",   "pts": [[x0, y0], [x1, y1]], "fill": "#rrggbb", "width": 8}   two opposite corners
- {"shape": "circle", "pts": [[cx, cy]], "r": 20, "fill": "#rrggbb", "width": 8}      centre + radius (r required, only on circles)
- {"shape": "poly",   "pts": [[x, y], [x, y], [x, y], ...], "fill": "#rrggbb", "width": 8}   3 to 24 points, closed
- {"shape": "line",   "pts": [[x, y], [x, y], ...], "width": 6}                        2 to 24 points, open stroke, no fill

- fill: 6-digit hex colour, or null / left out for outline only (lines never fill).
- width: black ink outline / stroke width, 0 to 24. Use 6-8 for main outlines, 3-5 for small details, 0 for no outline.
- Every coordinate must be a number within -300..300. No other keys anywhere.

## Coordinate space (hand space)
- The character's hand is at (0, 0). The hand GRIPS the prop there: put the handle / grip / held part over (0, 0).
- y goes DOWN (negative y = up). x goes AWAY from the body (positive x = outward, the way a held object points).
- The arm hangs down at the side, so things held upright stand above the hand (negative y); pointing things (tools,
  weapons, wands) extend along +x.
- Scale: the figure's head has radius 150 and the whole figure is about 1000 tall. Hand-held props span roughly
  -40..110 in x and -110..70 in y. Keep it about that size; something big may reach ~200, never more than 300.

## Style
Flat, bold, readable cartoon: few simple shapes, flat fills, thick black outlines, no gradients, no tiny details
(they vanish at video size). The renderer adds a slight hand-drawn wobble itself. Pick clear colours that read on
a light background. Build it back to front: big body shapes first, details on top.

## Examples (built-in props, in this exact format)
${EXAMPLES.map((e) => `\`\`\`json\n${compact(e)}\n\`\`\``).join('\n\n')}

${aiCheck([
  'Picture the object as a simple icon and name its 2-4 defining features (a bag: round body, tied neck, coin sign). Those, big and clear, are what make it readable; skip everything else.',
  'Block the silhouette with 1-3 big shapes so it is recognisable from its outline alone, then add a few details on top.',
  'Overlap the pieces a little so nothing floats or leaves a gap (a lid sits on the jar, a strap crosses the body).',
  'Use 2-3 main colours plus at most one light highlight; neighbouring shapes in clearly different shades.',
  'Place the grip over the hand at (0, 0) and size it against the 1000-tall figure.',
], [
  PTS_CHECK,
  'Circles have "r"; lines have no "fill" colour other than their stroke; polys have at least 3 points.',
  'The held part covers (0, 0) and the whole prop sits roughly within x -40..110, y -110..70 (bigger only if it must be).',
])}

Now design **${thing}** and reply with only its JSON object.`
}

/** the AI's reply (raw JSON, a fenced block, or JSON inside other text; a {"props": [...]} file takes the first) ->
 *  a prop to load into the editor, or an error message */
export function importProp(text: string): { prop?: CustomProp; error?: string } {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(text)?.[1]
  const raw = fenced ?? text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1)
  let j: unknown
  try {
    j = JSON.parse(raw)
  } catch (e) {
    return { error: `Not valid JSON: ${(e as Error).message}` }
  }
  const p = (Array.isArray((j as { props?: unknown })?.props) ? (j as { props: unknown[] }).props[0] : j) as Partial<CustomProp>
  if (!p || typeof p !== 'object' || !Array.isArray(p.shapes) || !p.shapes.length) return { error: 'Expected an object with a non-empty "shapes" array.' }
  const shapes: PropShape[] = []
  for (const [i, s] of (p.shapes as Partial<PropShape>[]).entries()) {
    const ok = s && ['rect', 'circle', 'line', 'poly'].includes(s.shape as string) && Array.isArray(s.pts)
      && s.pts.every((pt) => Array.isArray(pt) && pt.length === 2 && pt.every((v) => typeof v === 'number'))
    if (!ok) return { error: `Shape #${i + 1}: needs "shape" (rect, circle, line, poly) and "pts" as [[x, y], ...].` }
    shapes.push({ shape: s.shape!, pts: s.pts!, r: s.shape === 'circle' ? s.r ?? 20 : null, fill: s.fill ?? null, width: s.width ?? 8 })
  }
  const name = typeof p.name === 'string' && p.name.trim() ? p.name.trim().slice(0, 40) : 'New prop'
  return { prop: { id: slugify(typeof p.id === 'string' ? p.id : name) || 'prop', name, shapes } }
}
