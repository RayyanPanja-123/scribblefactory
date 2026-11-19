<script setup lang="ts">
import { computed } from 'vue'
import { api } from '../api/client'
import { allCreatures } from '../lib/creatures'
import { propOptions } from '../lib/props'
import { SLOT_LABEL, SLOTS, wardrobeOptions } from '../lib/wardrobe'
import { useApi } from '../composables/useApi'

// Every story.md directive in one place (the full rules for the AI live in docs/STORY_GUIDE.md section 5; keep the
// two in step). The lists of sets, bodies, actions and props are live: built-ins plus this library's custom ones.
const { data } = useApi(async () => {
  const [sets, creatures, actions, props, wardrobe, sfx] = await Promise.all([api.sets(), api.creatures(), api.actions(), api.props(), api.wardrobe(), api.sfx()])
  return { sets, creatures, actions, props, wardrobe, sfx }
})
const live = computed(() => {
  const d = data.value
  if (!d) return null
  return {
    sets: [...d.sets.builtin.map((s) => `${s.id} (${s.kind})`), ...d.sets.custom.map((s) => `${s.id} (${s.kind}, custom)`)],
    bodies: allCreatures(d.creatures).map((c) => `${c.id} (${c.rig})`),
    actions: [...d.actions.do, ...d.actions.custom.map((a) => `${a.id} (custom)`)],
    props: propOptions(d.props).map((p) => p.id),
    sounds: d.sfx.sfx.map((s) => `${s.id} (${s.purpose || s.name}${s.anchor === 'end_on_line' ? ', ends on line' : s.anchor === 'after_line' ? ', after the line' : ''})`),
    wardrobe: SLOTS.map((s) => ({ slot: s, ids: wardrobeOptions(d.wardrobe).filter((w) => w.slot === s).map((w) => w.id) })),
  }
})

type Directive = { id: string; syntax: string; what: string; rules: string[]; example: string; list?: 'sets' | 'bodies' | 'actions' | 'props' | 'sounds'; nav?: string }
const DIRECTIVES: Directive[] = [
  { id: 'set', syntax: '@set <name>', what: 'Where the scene is, for the following lines.', list: 'sets',
    rules: ['Default: room. Put one before the first narration line.', 'Indoor sets have a back wall; outdoor sets allow travelling shots.',
      'Changing the set adds a wipe and an establishing wide shot.', 'Custom sets come from the Sets page.'],
    example: '@set office' },
  { id: 'cast', syntax: '@cast a, b, c', what: 'Who is on stage, for the following lines.', list: 'bodies',
    rules: ['Default: the first two cast members.', 'Up to 6 stand in one row; 7 to 12: those named in the lines stand in front, the rest further back.',
      'Never more than 12: use @crowd for a big group.', 'Each cast member has a body (default human). Humanoids are stickmen with every action; bird, quadruped and crawler bodies have no hands.'],
    example: '@cast bob, karen' },
  { id: 'do', syntax: '@do <cast>: <action> [target | prop]', what: 'Forces an action for every shot of the next narration line only.', list: 'actions',
    rules: ['The narration line must follow directly; a second @do before it replaces the first.', 'Everyone named must be in the current @cast. Several clauses: @do fred: lie, amy: wave.',
      'eat [prop] (default apple) · give <prop> <target> · carry <target> (2 carriers) · support <target> (1–2 helpers).',
      'collapse falls once, then lies; walk / run / stagger cross the stage.', 'angry, gasp, react and cheer set the face too (angry, surprised, happy) unless the line names a mood; a mood word in a line sets the face for all of it.', '@do car: broken stalls the car on stage.',
      'Custom actions (Actions page) are in-place moves: humanoids play them, other creatures stand idle.'],
    example: '@do trainer1, trainer2: carry thomas' },
  { id: 'look', syntax: '@look <cast>: <look>', what: 'From the next line on, a cast member wears one of its named looks.',
    rules: ['Lasts until another @look for them, across @set changes, for the rest of the part.', '@look mike: default brings back their own look.',
      'Several at once: @look amy, bob: wedding.', 'Looks are defined per cast member (series cast JSON "looks").',
      'A look is a whole outfit: it swaps every wardrobe slot it sets at once; "none" takes an item off.'],
    example: '@look mike: headless' },
  { id: 'face', syntax: '@face <cast>: <expression>', what: 'A cast member’s face for the next narration line only.',
    rules: ['neutral, happy, sad, angry, surprised, sleepy, cheeky, exhausted or worried. Several at once: @face amy, bob: happy.',
      'Without it, faces follow the words: a line’s first mood word (angry, laughed, sobbed, gasped…) sets the face from the line’s start, and each later one switches it on that word.',
      '@do angry, gasp, react and cheer set the face when the line has no mood word.', 'neutral shows the cast member’s own default face (set in the cast).'],
    example: '@face caligula: angry\nCaligula stomped his little boots.' },
  { id: 'car', syntax: '@car arrive | ride | leave | off', what: 'A car on stage.',
    rules: ['arrive: drives in and parks beside the main character.', 'ride: the current @cast (at most 3) sit in it; outdoors it is a travelling shot. Only @do car: broken is allowed while riding.',
      'leave: the parked car drives off. off: no car (default).'],
    example: '@car ride' },
  { id: 'dogs', syntax: '@dogs N', what: '0 to 6 dogs.', rules: ['In travelling shots they chase; otherwise they idle or bark at the edges.'], example: '@dogs 3' },
  { id: 'crowd', syntax: '@crowd <cheer | angry | gasp | neutral> [N]', what: 'Background crowd extras (not cast).',
    rules: ['N from 1 to 12, default 8. @crowd off removes them.', 'Not shown in travelling shots. A @set change resets the crowd.'], example: '@crowd cheer 10' },
  { id: 'runners', syntax: '@runners N', what: '0 to 6 background runners.', rules: ['A @set change resets them.'], example: '@runners 4' },
  { id: 'fx', syntax: '@fx drop | shake | pop | none', what: 'Caption effect for the next narration line.', rules: ['For emphasis: use sparingly.'], example: '@fx shake' },
  { id: 'weather', syntax: '@weather <type> [intensity]', what: 'The weather over the scene, drawn in ink: clear, rain, snow, fog, wind or storm.',
    rules: ['Intensity light, medium or heavy (default medium); clear takes none.', 'Lasts until the next @weather or @set. A @set starts clear, or the set’s default weather (Sets page), so put @weather after its @set.',
      'Fog drifts behind the cast; rain, snow and wind fall in front. storm: slanted rain, a darker sky, the odd distant flash.', 'A change within one scene fades in over half a second.',
      'Match the mood: gods, sea battles, villains: storm; sadness: rain; mystery: fog; calm: clear.'],
    example: '@set countryside\n@weather storm heavy' },
  { id: 'lightning', nav: '@fx lightning', syntax: '@fx lightning [cast | prop]', what: 'One lightning strike (bolt + brief flash) at the start of the next narration line.', list: 'props',
    rules: ['With a target it strikes beside that cast member (on stage) or whoever holds that prop.', 'At most 3 per part, on dramatic beats; a narration line must follow it.',
      'Works under any weather, strongest in a storm.'],
    example: '@do poseidon: raise_trident\n@fx lightning\nPoseidon raised his trident, and the sky split open.' },
  { id: 'sfx', syntax: '@sfx <id> [volume 0-1]', what: 'A sound effect from the Sounds page, mixed under the voice, for the next narration line.', list: 'sounds',
    rules: ['Alone on its line, directly above the narration line it belongs to (next to @do / @fx is fine).',
      'Line start sounds play as that line starts; ends-on-line sounds (risers) end exactly as it starts; after-line sounds (fahhh) play once it has been said.',
      'Volume 0 to 1 overrides the sound’s default. Sounds always sit under the voice and duck while it speaks.',
      'At most 5 per part, only where the moment needs one: risers only before a payoff, vine_boom only for comedy, money only for money.',
      'The Review tab suggests some from the stills on; nothing is added without your OK.'],
    example: '@sfx riser\n!! The tower was never his to sell.' },
  { id: 'twist', syntax: '!! <text>', what: 'The twist: a dramatic push-in, the music stops, a low hit sounds.', list: undefined,
    rules: ['Starts a narration line; the text is read aloud.', 'Exactly once per part, on the last or second-to-last narration line.'],
    example: '!! The tower was never his to sell.' },
]
</script>

<template>
  <div class="max-w-5xl space-y-6">
    <div>
      <h2 class="font-display text-2xl font-semibold">Help: script directives</h2>
      <p class="text-sm text-muted">Lines in <code>story.md</code> that start with <code>@</code> direct the video and are never read
        aloud. Each goes on its own line. The lists below are live: built-ins plus this library’s custom items.</p>
    </div>
    <nav aria-label="Directives" class="flex flex-wrap gap-1.5">
      <a v-for="d in DIRECTIVES" :key="d.id" :href="`#${d.id}`" class="chip font-mono hover:underline">{{ d.nav ?? d.syntax.split(' ')[0] }}</a>
    </nav>
    <section v-for="d in DIRECTIVES" :id="d.id" :key="d.id" class="raised scroll-mt-4 space-y-3 p-5">
      <div>
        <h3 class="font-mono text-base font-semibold">{{ d.syntax }}</h3>
        <p class="text-sm text-muted">{{ d.what }}</p>
      </div>
      <ul class="list-disc space-y-1 pl-5 text-sm">
        <li v-for="r in d.rules" :key="r">{{ r }}</li>
      </ul>
      <pre class="inset overflow-x-auto rounded-md px-3 py-2 font-mono text-xs select-all">{{ d.example }}</pre>
      <div v-if="d.list && live" class="text-xs text-muted">
        <span class="font-semibold">Available:</span>
        <span class="ml-1 inline-flex flex-wrap gap-1 align-middle"><code v-for="x in live[d.list]" :key="x" class="chip">{{ x }}</code></span>
      </div>
    </section>
    <section id="props" class="raised scroll-mt-4 space-y-2 p-5">
      <h3 class="font-semibold">Props</h3>
      <p class="text-sm text-muted">Held in a hand (cast JSON <code>"props"</code>, or a look), eaten with <code>@do … eat</code>,
        handed over with <code>@do … give</code>. Custom ones come from the Props page.</p>
      <p v-if="live" class="flex flex-wrap gap-1"><code v-for="x in live.props" :key="x" class="chip">{{ x }}</code></p>
    </section>
    <section id="wardrobe" class="raised scroll-mt-4 space-y-2 p-5">
      <h3 class="font-semibold">Wardrobe</h3>
      <p class="text-sm text-muted">What humanoid cast members wear, one item per slot (accessory and face: up to 3), in the cast JSON:
        <code>"hair": "wild_hair"</code> or <code>"hair": {"id": "wild_hair", "color": "#e8e8e8"}</code>, <code>null</code> for none.
        <code>@look</code> swaps a whole outfit. Custom items come from the Wardrobe page.</p>
      <dl v-if="live" class="grid gap-1 text-xs sm:grid-cols-[8rem_1fr]">
        <template v-for="g in live.wardrobe" :key="g.slot">
          <dt class="font-semibold">{{ SLOT_LABEL[g.slot] }} <code class="text-muted">{{ g.slot }}</code></dt>
          <dd class="flex flex-wrap gap-1"><code v-for="x in g.ids" :key="x" class="chip">{{ x }}</code><span v-if="!g.ids.length" class="text-muted">none yet</span></dd>
        </template>
      </dl>
    </section>
  </div>
</template>
