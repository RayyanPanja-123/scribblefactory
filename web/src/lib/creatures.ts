// Creatures: non-human cast bodies (library/creatures.json + the engine's built-ins), the "Build with AI" prompt for
// a new one and the importer for the AI's reply. The server (schema CustomCreature) still checks everything on save.
import type { components } from '../api/types'
// @ts-expect-error plain JS module from the engine, no types
import { BUILTIN, JOINT_OF, RIGS } from '../../../engine/page/creatures.js'

export type CustomCreature = components['schemas']['CustomCreature']
export type CreatureShape = components['schemas']['CreatureShape']
export type CreatureCatalog = components['schemas']['CreatureCatalog']
export type Rig = CustomCreature['rig']

export const builtinCreatures = BUILTIN as CustomCreature[]
export const rigParts = RIGS as Record<Rig, { parts: Record<string, boolean>; hands: boolean }>
export const jointOf = JOINT_OF as Record<string, string>
export const RIG_LIST: Rig[] = ['bird', 'quadruped', 'biped', 'crawler']
export const RIG_NOTES: Record<Rig, string> = {
  bird: 'two legs and a wing: chicken, duck, penguin, crow. Flaps when startled, pecks to eat',
  quadruped: 'four legs: cat, dog, horse, cow, pig. Hops when excited, wags its tail',
  biped: 'stands on two legs with arms: monkey, bear, robot, alien. The only rig with hands (props, give, carry)',
  crawler: 'no legs: snake, worm, slug, caterpillar. The body ripples as it moves',
}

/** every creature by id: built-ins, then the library's (a custom one never shares a built-in id) */
export const allCreatures = (c: CreatureCatalog | null | undefined): CustomCreature[] => [...builtinCreatures, ...(c?.custom ?? [])]
export const isBuiltinCreature = (id: string) => builtinCreatures.some((c) => c.id === id)

const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
const compact = (c: CustomCreature) => JSON.stringify(c)

/** the prompt for a creature called "name" on rig: paste it into any AI chat. taken = ids already in use */
export function buildCreaturePrompt(name: string, rig: Rig, taken: string[], details = '', id = ''): string {
  const thing = name.trim() || 'an animal'
  id = slugify(id || thing) || 'creature'
  const spec = rigParts[rig].parts
  const parts = Object.entries(spec).map(([p, need]) => `- ${p}${need ? ' (required)' : ' (optional)'}${p === 'body' ? ': ground space' : `: around joint "${jointOf[p]}"`}`).join('\n')
  const example = builtinCreatures.find((c) => c.rig === rig)!
  const brief = details.trim() ? `\n\nWhat it should look like: ${details.trim()}` : ''
  return `You are drawing a cartoon animal for a hand-drawn stick-figure video renderer. Design: **${thing}**, on the **${rig}** rig (${RIG_NOTES[rig]}).${brief}

Reply with ONE JSON object in a \`\`\`json code block and nothing else.

## Format
{"id": "${id}", "name": ${JSON.stringify(name.trim().slice(0, 40) || 'New creature')}, "rig": "${rig}", "accent": "#rrggbb",
 "joints": {"<joint>": [x, y], ...}, "face": {"eye": [x, y], "mouth": [x, y]}, "parts": {"<part>": [<shape>, ...], ...}}

- id, name and rig: use exactly the ones above. The id must NOT be one of: ${taken.join(', ') || '(none)'}.
- Parts of a ${rig}:
${parts}
- joints: one per part you draw (besides body), named as above, plus "hip"${rig === 'crawler' ? ' (not used by a crawler)' : ''}. Each joint is where that part attaches, in ground space. No unused joints.
- stump (optional): a short neck stump with a dark red cut on top, drawn instead of the head for a headless character.
- face: eye = a dot that blinks, mouth = opens while it talks (hidden when shut), both in the head's space (in body space if there is no head). Animals have only eyes and a mouth: no eyebrows, no expressions.

Each shape is one of (1 to 60 per part, drawn in order, later on top):
- {"shape": "rect",    "pts": [[x0, y0], [x1, y1]], "fill": "$main", "width": 8}
- {"shape": "circle",  "pts": [[cx, cy]], "r": 40, "fill": "$main", "width": 10}
- {"shape": "ellipse", "pts": [[cx, cy]], "r": 120, "ry": 50, "rot": 0, "fill": "$main", "width": 10}   r = x radius, ry = y radius, rot = degrees clockwise
- {"shape": "poly",    "pts": [[x, y], [x, y], [x, y], ...], "fill": "$accent", "width": 8}   3 to 40 points, closed
- {"shape": "line",    "pts": [[x, y], [x, y], ...], "fill": "#e8a33a", "width": 9}   open stroke; fill is its colour (default black)

- fill: "$main" (the character's colour, chosen per story: use it for fur / feathers / skin), "$accent" (its second colour, else your "accent"), a fixed "#rrggbb" for things that never change colour (a beak, hooves, a red comb), or null for outline only.
- width: black ink outline, 0 to 40: 10-12 for the body, 6-9 for limbs and details, 0 for spots with no outline.
- A tail or a thin limb as a coloured stroke with an ink edge: a black line first (width w + 10), then the same line with "fill": "$main" and width w.

## Coordinate space (canvas px)
- Side view, facing RIGHT (+x is forward). y goes DOWN: negative y is up. The ground is y = 0.
- body: in ground space, around (0, 0) = the ground under the creature's middle.
- every other part: around its own joint at (0, 0), drawn at rest: legs and arms hang straight DOWN from the joint (+y), the foot at y = the joint's height above the ground (so it just touches the ground), a head / neck rises from the neck joint, a tail trails back (-x), a wing lies along the body.
- The rig rotates each part about its joint (legs swing, the head pecks or nods, wings flap, the tail wags), so draw each part around its joint, not where it would be in ground space.
- Scale: a person is about 950 px tall. Keep real proportions roughly (a cat ~250 tall, a horse ~900). The card is x -512..512, y up to -1000. Legs: the hip / shoulder joint y is minus the leg length.

## Style
Flat, bold, readable cartoon: few simple shapes, flat fills, thick black outlines, no gradients, no tiny details. The renderer adds a hand-drawn wobble. Big shapes first, details on top.

## Example (the built-in ${example.name.toLowerCase()}, a ${rig})
\`\`\`json
${compact(example)}
\`\`\`

Now design **${thing}** and reply with only its JSON object.`
}

/** the AI's reply (raw JSON, a fenced block, or JSON inside other text; a {"creatures": [...]} file takes the first)
 *  -> a creature to load into the editor, or an error message. The server checks the rest on save. */
export function importCreature(text: string): { creature?: CustomCreature; error?: string } {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(text)?.[1]
  const raw = fenced ?? text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1)
  let j: unknown
  try {
    j = JSON.parse(raw)
  } catch (e) {
    return { error: `Not valid JSON: ${(e as Error).message}` }
  }
  const c = (Array.isArray((j as { creatures?: unknown })?.creatures) ? (j as { creatures: unknown[] }).creatures[0] : j) as Partial<CustomCreature>
  if (!c || typeof c !== 'object' || !c.parts || typeof c.parts !== 'object' || !c.parts.body) return { error: 'Expected an object with "parts" including "body".' }
  if (!RIG_LIST.includes(c.rig as Rig)) return { error: `"rig" must be one of ${RIG_LIST.join(', ')}.` }
  const name = typeof c.name === 'string' && c.name.trim() ? c.name.trim().slice(0, 40) : 'New creature'
  return { creature: { id: slugify(typeof c.id === 'string' ? c.id : name) || 'creature', name, rig: c.rig as Rig,
    accent: c.accent ?? '#3a2a1e', joints: c.joints ?? {}, face: c.face ?? {}, parts: c.parts } as CustomCreature }
}
