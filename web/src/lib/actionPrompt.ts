// "Build with AI" for custom actions: a self-contained prompt that teaches any chat AI the keyframe format, and the
// importer for what it sends back. The server (schema CustomAction) still checks everything on save.
import type { CustomAction } from '../api/client'
import { aiCheck } from './aiCheck'
import { slugify } from './slug'


const EXAMPLES: CustomAction[] = [
  { id: 'salute', name: 'Salute', duration: 1.4, loop: false, keys: [
    { t: 0, lean: 0, ease: 'in-out', snap: false },
    { t: 0.5, arms: [[-16, 0], [150, 70]], lean: 2, ease: 'back-out', snap: false },
  ], facing: 'camera', move: 0 },
  { id: 'dance', name: 'Dance', duration: 1, loop: true, keys: [
    { t: 0, arms: [[-120, -40], [60, 30]], legs: [-20, 6], lean: -8, ease: 'in-out', snap: false },
    { t: 0.5, arms: [[-60, -30], [120, 40]], legs: [-6, 20], lean: 8, ease: 'in-out', snap: false },
  ], facing: 'camera', move: 0 },
]

/** the prompt for an action called "name": paste it into any AI chat; taken = action ids already in use (built-in and
 *  custom); details = how it should move (optional); id = the id a story already uses (default: from the name) */
export function buildActionPrompt(name: string, taken: string[], details = '', id = ''): string {
  const thing = name.trim() || 'an action'
  id = slugify(id || thing) || 'action'
  const title = name.trim() ? JSON.stringify(name.trim().slice(0, 40)) : '"<display name, max 40 chars>"'
  const brief = details.trim() ? `\n\nHow it should move: ${details.trim()}` : ''
  return `You are animating a stick figure for a hand-drawn cartoon video renderer. Create the move: **${thing}**.${brief}

Reply with ONE JSON object in a \`\`\`json code block and nothing else.

## Format
{"id": "${id}", "name": ${title}, "duration": <seconds>, "loop": true | false, "facing": "camera" | "side", "move": <units/s>, "keys": [ <key>, ... ]}

- id and name: use exactly the ones above. The id must NOT be one of: ${taken.join(', ')}.
- duration: seconds for one pass through the keys, 0.2 to 10 (a gesture ~1-2, a dance step ~0.6-1.2).
- loop: true repeats for the whole shot (dancing, clapping, waving); false plays once and holds the last key
  (salute, bow, kneel, facepalm).
- facing: use "camera" for a front-facing gesture, or "side" when the cast member should turn sideways.
- move: 0 for an in-place action; with facing "side", a positive value moves forward and a negative value makes
  the figure glide backward (moonwalk). Use a speed from 0.3 to 2.5 in either direction.
- keys: 2 to 8 keys (max 40) in time order. The engine eases smoothly between them; a looping move wraps from the
  last key back to the first, so make them flow.

Each key: {"t": 0.5, "arms": [[L, Lbend], [R, Rbend]], "legs": [L, R], "knees": [L, R], "lean": 0, "ease": "in-out"}
(ease: how the pose moves into this key: "in-out" smooth (default), "linear" steady, "back-out" overshoots then settles,
good for a snappy salute or a punch)
- t: when, 0 to 1 (share of the duration). Start with a key at t 0.
- arms (optional): [left arm, right arm], each [upper arm angle, forearm bend]. Left out: both arms at rest.
- legs (optional): [left thigh, right thigh] angles, -90..90. Left out: at rest. The lowest foot stays on the ground.
- knees (optional): [left, right] knee bends, 0 (straight) to 170. On a side action the shin folds back, behind
  the figure; on a camera action the knees bend outward (a front-view squat). Left out: straight legs.
- lean (optional): the whole figure, -60..60, about the feet. With bent knees it bends at the hips instead.

## Angles (degrees, the figure faces the camera; side actions use the same angles relative to the facing direction)
- Measured from straight DOWN; positive turns toward screen RIGHT (the figure's left hand side is screen left).
- Upper arm: 0 hangs down, 90 points right, -90 points left, 180 / -180 straight up. Rest: left -16, right 16.
- Forearm bend: turns the forearm relative to the upper arm, same sign rule: for the right arm, + bends the hand
  up and inward; on a camera action use - for the left arm (the mirror image). 0 = straight arm.
  On a side action both arms are seen in profile: both bends are 0..180 (+ folds the forearm forward and up,
  like a real elbow); a negative bend there would bend the elbow backward and is refused.
- Legs: rest -6 (left) and 6 (right); -20 kicks the left leg out to the left, 20 the right leg out to the right.
- Lean: + leans toward screen right.
- Arms are short (about a head and a half): raised hands end beside or just above the head.

## What the figure can and cannot do
- A camera-facing action is a front view, like a paper cut-out. A side action is mirrored into a left/right profile:
  arms[0] is the back arm, arms[1] the front arm, and positive lean bends forward.
  Nothing bends toward or away from the viewer: on a camera action "lean" only tilts the whole figure sideways,
  like a tilted head, so a camera bow is shown with the arms: the right arm [-10, -110] (upper arm down, forearm
  folded across the chest), the left arm out a little [-40, 0], lean at most 5-8. A deep bow is a side action:
  knees [30, 30] and lean 30-45 bend it at the hips.
- Arms out to the side (±90) is a T-pose; ±130..180 is hands up; a forearm folded in (bend ±100..140) brings the
  hand to the chest, face or head.
- Kneeling, crouching and picking things up need a side action ("facing": "side") with knees. One-knee kneel:
  legs [0, 90], knees [90, 90] (back knee on the ground, front shin straight down), lean 0-15. Deep squat:
  legs [85, 85], knees [160, 160]. With bent knees, lean bends forward at the hips. Arms are short: only from
  the deep squat with lean 40 and the front arm [20, 0] does a hand touch the ground (a kneel reaches the knee).
  Use knees for life in any move: a 20-30 dip before a jump, throw or raise; a bent front knee in a lunge or
  thrust; the swinging leg bent in a step or kick. On a camera action bent knees point outward.
- Keep the lean small (0-10) unless the move is a sideways sway or a dance.

## Style
Clear, readable cartoon poses: big silhouettes, 2-4 distinct poses, no jitter. Keep the move in place (no
walking unless the brief asks for a side-facing move; for a walk or moonwalk, use alternating legs and set move.

## Examples (in this exact format)
${EXAMPLES.map((e) => `\`\`\`json\n${JSON.stringify(e)}\n\`\`\``).join('\n\n')}

${aiCheck([
  'Pick facing first: is the move readable from the front (waving, clapping, shrugging) or does it need a profile (bowing, kneeling, kicking, picking up)?',
  'Sketch the 2-4 key poses in words: anticipation (a small wind-up the other way), the action (the strongest, most exaggerated pose), and the follow-through / settle.',
  'Make each key pose a clear silhouette: arms away from the body, not hidden in front of it; push angles further than feels natural, cartoons read bigger.',
  'Time it: the wind-up and settle slower, the hit fast (keys close together, "back-out" on the hit for snap). Loops: make the last key flow back into the first.',
], [
  'The first key has t 0, t values increase, all within 0..1.',
  'arms is [[upper, bend], [upper, bend]], legs and knees are [left, right]; every angle is within its range.',
  'On a side action every forearm bend is 0..180; on a camera action nothing relies on bending toward the viewer.',
])}

Now create **${thing}** and reply with only its JSON object.`
}

const num = (v: unknown, lo: number, hi: number) => typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi
const wrap = (v: number) => ((((v + 180) % 360) + 360) % 360) - 180 // into -180..180 (180 becomes -180: the same)
const pair = (v: unknown, lo: number, hi: number) => Array.isArray(v) && v.length === 2 && v.every((x) => num(x, lo, hi))

/** the AI's reply (raw JSON, a fenced block, or JSON inside other text; an {"actions": [...]} file takes the first)
 *  -> an action to load into the editor (keys sorted by time), or an error message */
export function importAction(text: string): { action?: CustomAction; error?: string } {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(text)?.[1]
  const raw = fenced ?? text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1)
  let j: unknown
  try {
    j = JSON.parse(raw)
  } catch (e) {
    return { error: `Not valid JSON: ${(e as Error).message}` }
  }
  const a = (Array.isArray((j as { actions?: unknown })?.actions) ? (j as { actions: unknown[] }).actions[0] : j) as Partial<CustomAction>
  if (!a || typeof a !== 'object' || !Array.isArray(a.keys) || !a.keys.length) return { error: 'Expected an object with a non-empty "keys" array.' }
  const keys: CustomAction['keys'] = []
  for (const [i, k] of (a.keys as Record<string, unknown>[]).entries()) {
    const bad = (m: string) => ({ error: `Key #${i + 1}: ${m}` })
    if (!k || !num(k.t, 0, 1)) return bad('"t" must be a number from 0 to 1.')
    // arm angles are rotations: 200 is -160, so wrap them into -180..180 instead of refusing
    if (Array.isArray(k.arms)) k.arms = k.arms.map((arm) => (Array.isArray(arm) ? arm.map((v) => (num(v, -1e4, 1e4) ? wrap(v as number) : v)) : arm))
    if (k.arms != null && !(Array.isArray(k.arms) && k.arms.length === 2 && k.arms.every((x) => pair(x, -180, 180))))
      return bad('"arms" must be [[angle, bend], [angle, bend]], each -180..180.')
    if (k.legs != null && !pair(k.legs, -90, 90)) return bad('"legs" must be [left, right], each -90..90.')
    if (k.knees != null && !pair(k.knees, 0, 170)) return bad('"knees" must be [left, right], each 0..170.')
    if (k.lean != null && !num(k.lean, -60, 60)) return bad('"lean" must be a number from -60 to 60.')
    const ease = (['in-out', 'linear', 'back-out'] as const).find((e) => e === k.ease) ?? 'in-out' // unknown: the default
    keys.push({ t: k.t as number, arms: (k.arms ?? null) as never, legs: (k.legs ?? null) as never, knees: (k.knees ?? null) as never, lean: (k.lean as number) ?? 0, ease, snap: k.snap === true })
  }
  const name = typeof a.name === 'string' && a.name.trim() ? a.name.trim().slice(0, 40) : 'New action'
  const duration = num(a.duration, 0.2, 10) ? a.duration! : 1.5
  const facing = a.facing === 'side' ? 'side' : 'camera'
  const backward = facing === 'side' && keys.findIndex((k) => k.arms && Math.min(k.arms[0][1], k.arms[1][1]) < 0)
  if (backward !== false && backward >= 0)
    return { error: `Key #${backward + 1}: on a side action both arm bends must be 0..180 (an elbow only bends forward).` }
  const move = typeof a.move === 'number' && Number.isFinite(a.move) ? Math.max(-2.5, Math.min(2.5, a.move)) : 0
  return { action: { id: slugify(typeof a.id === 'string' ? a.id : name) || 'action', name, duration, loop: a.loop !== false, facing,
    move: facing === 'side' ? move : 0,
    keys: keys.sort((x, y) => x.t - y.t) } }
}
