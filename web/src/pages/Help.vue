<script setup lang="ts">
import { computed } from 'vue'
import { api } from '../api/client'
import ActionPreview from '../components/ActionPreview.vue'
import { allCreatures } from '../lib/creatures'
import { propOptions } from '../lib/props'
import { SLOT_LABEL, SLOTS, wardrobeOptions } from '../lib/wardrobe'
import { useApi } from '../composables/useApi'

// Every story.md directive in one place, in plain words (the full rules for the AI live in docs/ai/script.md,
// Directives; keep the two in step). The lists of sets, bodies, actions and props are live: built-ins plus this
// library's custom ones.
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

// Moving previews for the @do section: built-ins one person can do alone, then every custom action
const SOLO: Record<string, string> = {
  talk: 'chats', point: 'points', wave: 'waves hello', cheer: 'cheers', angry: 'shakes fists', gasp: 'gasps',
  react: 'hands up in shock', walk: 'walks', run: 'runs', stagger: 'wobbles', idle: 'stands still',
}
const gallery = computed(() => {
  const d = data.value
  if (!d) return []
  return [
    ...d.actions.do.filter((a) => SOLO[a]).map((a) => ({ key: a, action: a as string | (typeof d.actions.custom)[number], name: a, note: SOLO[a] })),
    ...d.actions.custom.map((a) => ({ key: a.id, action: a, name: a.id, note: a.name })),
  ]
})

type Directive = { id: string; syntax: string; what: string; rules: string[]; example: string; list?: 'sets' | 'bodies' | 'actions' | 'props' | 'sounds'; nav?: string }
const DIRECTIVES: Directive[] = [
  { id: 'set', syntax: '@set <name>', what: 'Where we are. Every line after it happens here.', list: 'sets',
    rules: ['Put one before the first spoken line. If you forget, it is a plain room.', 'Inside places have a back wall. Outside places can have moving travel shots.',
      'A new place gets a wipe and a wide shot so the viewer knows where we are.', 'It resets crowds, crowd costumes/weapons, runners and actor positions, then applies the set weather default.',
      'The car keeps its current state until @car off or another car mode.', 'Make your own places on the Sets page.'],
    example: '@set office' },
  { id: 'cast', syntax: '@cast a, b, c', what: 'Who is on stage. Everyone listed is there until the next @cast.', list: 'bodies',
    rules: ['If you forget, the first two cast members are on stage.', 'Someone who should appear later (a god popping out of the sea): leave them out, then add a new @cast with them right before their line.',
      'The order is left to right. People already on stage stay where they stand.', 'Up to 6 fit in one row; up to 12 with a back row. For a big group use @crowd.',
      'Stickmen can do every action. Birds, four-legged animals and snakes have no hands.'],
    example: '@cast bob, karen' },
  { id: 'do', syntax: '@do <cast>: <action> [target | prop]', what: 'Makes someone do something during the next spoken line only.', list: 'actions',
    rules: ['Put the spoken line right under it. Indented directives work too.', 'Several people at once: @do fred: lie, amy: wave.',
      'With things or people: eat apple · give medal amy · carry tom (needs 2 people) · support tom (1 or 2 people).',
      'eat with no prop uses an apple. give accepts the prop and target in either order.',
      'walk, run and stagger move across the stage. collapse falls down once, then they lie there.',
      'angry, gasp, react and cheer change the face too, unless the line already has a feeling word.',
      'Custom actions can aim at someone: @do marcus: attack-with-spears neptune turns Marcus toward Neptune.',
      '@do car: broken makes the car on stage break down.'],
    example: '@do marcus: attack-with-spears neptune\nMarcus stabbed at the god of the sea.' },
  { id: 'look', syntax: '@look <cast>: <look>', what: 'Changes someone’s outfit, or what they hold, from the next line on.',
    rules: ['Looks come from the cast member (Looks tab of the character editor). default always exists: it puts their normal outfit back.',
      'It stays on until you change it again, even in a new place, and resets at the start of a new part.',
      'A cat or horse wears only headwear, face, accessory and back items from the wardrobe (a crown, a saddle), roughly fitted. No tops, trousers, shoes, hair or built-in hats.',
      'A creature’s look can set it on fire: Flame (off, low, high) and its colour, on the Character tab. @look charro-horse: blazing.',
      'Several people at once: @look amy, bob: wedding.'],
    example: '@look mike: headless' },
  { id: 'hold', syntax: '@hold <cast>: <prop> [left | right]', what: 'Puts a prop in someone’s hand from the next line on.',
    rules: ['Right hand unless you say left. It replaces only that hand, on top of their look, and stays through later @look changes.',
      'It stays until you change it, even in a new place, and resets at the start of a new part.',
      '@hold mike: none empties both hands; @hold mike: none left empties one.',
      'Use it for anything kept in hand; @do give/eat only use a prop for one line. Creatures without hands cannot hold.'],
    example: '@hold ethan: flip-phone' },
  { id: 'ride', syntax: '@ride <rider>: <creature>', what: 'Puts a person in the saddle of a creature from the next line on.',
    rules: ['It stays until @ride <rider>: none, even in a new place, and resets at the start of a new part.',
      'Move the creature (@do horse: walk) and the rider goes along. In the saddle: idle, talk, point, wave, react, gasp, angry, cheer only; other actions fall back to idle.',
      'One rider per creature. Get off (none) before riding another. @car ride seats everyone in the car instead.'],
    example: '@ride charro: charro-horse' },
  { id: 'face', syntax: '@face <cast>: <expression>', what: 'Sets someone’s face for the next spoken line only.',
    rules: ['Faces: neutral, happy, sad, angry, surprised, sleepy, cheeky, exhausted, worried, dead, '
      + 'smug, proud, love, excited, relieved, laughing, wink, furious, annoyed, disgusted, crying, scared, embarrassed, jealous, guilty, confused, thinking, suspicious, shocked, deadpan, bored, facepalm_ready, dizzy, drunk, knocked_out, evil, crazy, blank, sick.',
      'Often you don’t need it: feeling words in the line (angry, laughed, sobbed, gasped…) change the face by themselves, right on that word.',
      'Use @face when the line has no feeling word but the moment does.'],
    example: '@face caligula: angry\nCaligula stomped his little boots.' },
  { id: 'cam', syntax: '@cam [angle] [move] [fast] [shake] [dutch <deg>]', what: 'Picks the camera for the next spoken line’s first shot.',
    rules: ['Angles: wide, medium, close, low, high, over_shoulder (needs two people on stage). Moves: push_in, pull_out, truck_left, truck_right, crane_up, crane_down, or hold (still).',
      'Give only what matters: the rest is picked as usual. fast speeds the move up, shake jolts the camera, dutch 15 tilts the horizon (-25 to 25).',
      'Save it for the big beats, two or three a part. On a !! line the twist keeps its push and roll unless you give a move or dutch.'],
    example: '@cam close push_in fast shake\n!! The king was a goat all along.' },
  { id: 'car', syntax: '@car arrive | ride | leave | off', what: 'Brings a car into the scene.',
    rules: ['arrive: it drives in and parks.', 'ride: up to 3 people sit in it and drive.', 'leave: it drives away. off: no car.'],
    example: '@car ride' },
  { id: 'dogs', syntax: '@dogs N', what: 'Adds 0 to 6 dogs.', rules: ['They chase in travel shots, and bark or sit otherwise.'], example: '@dogs 3' },
  { id: 'crowd', syntax: '@crowd <mood> [N] | @crowd <group> <mood> [N]', what: 'Adds people in the background (an army, a mob, fans).',
    rules: ['1 to 12 people, 8 if you don’t say. @crowd off sends them away.', 'Named groups face each other; use fight <target> for a battle.', '@crowd-look gives a group wardrobe items and @crowd-weapon gives it a library prop.', 'A new place starts with no crowd.'], example: '@crowd red angry 10\n@crowd blue fight red' },
  { id: 'runners', syntax: '@runners N', what: 'Adds 0 to 6 people running past in the background.', rules: ['A new place starts with none.'], example: '@runners 4' },
  { id: 'crowd-look', syntax: '@crowd-look <group>: <wardrobe ids>', what: 'Gives every member of a named crowd team a costume.', list: 'props',
    rules: ['Use up to one top, one headwear item and one legwear item.', 'Built-in and library wardrobe IDs work.',
      'Set it before or after @crowd; it persists until the set changes or another look is assigned.'], example: '@crowd-look red: suit, flat_cap, trousers' },
  { id: 'crowd-weapon', syntax: '@crowd-weapon <group>: <prop>', what: 'Gives every member of a named crowd team the same held prop.', list: 'props',
    rules: ['The prop must be built-in or present in the props library.', 'Use it for weapons, flags, tools, torches or banners.',
      'It persists until the set changes or the team receives another prop.'], example: '@crowd-weapon red: rifle' },
  { id: 'fx', syntax: '@fx drop | shake | pop | none', what: 'Makes the caption of the next line jump out.', rules: ['It applies only to the next spoken line.', 'Use shake for impact, pop for a reveal, and drop for a dramatic entrance.'], example: '@fx shake' },
  { id: 'weather', syntax: '@weather <type> [strength]', what: 'Sky and weather: clear, rain, snow, fog, wind or storm.',
    rules: ['Strength: light, medium or heavy.', 'Put it after @set: a new place resets the weather.',
      'Pick it by mood: storm for gods, sea and villains; rain for sad; fog for mystery; clear for calm.'],
    example: '@set countryside\n@weather storm heavy' },
  { id: 'lightning', nav: '@fx lightning', syntax: '@fx lightning [cast | prop]', what: 'A lightning bolt as the next line starts.', list: 'props',
    rules: ['The target may be a cast ID, a prop ID, or omitted.', 'A prop target strikes whoever holds that prop on the next line.', 'At most 3 per part: save it for big moments.'],
    example: '@do neptune: raise-trident\n@fx lightning\nNeptune raised his trident, and the sky split open.' },
  { id: 'sfx', syntax: '@sfx <id> [volume 0-1]', what: 'Plays a sound effect with the next line.', list: 'sounds',
    rules: ['Put it right above the line it belongs to. Multiple @sfx lines can attach to the same line.', 'Most sounds play as the line starts. Risers end just as it starts. fahhh plays after the line.',
      'Use @sfx id 0.6 for a one-use volume override.', 'At most 5 per part, and not on two lines in a row.', 'The Review tab suggests sounds for you.'],
    example: '@sfx riser\n!! The tower was never his to sell.' },
  { id: 'twist', syntax: '!! <text>', what: 'The big twist: the camera pushes in and a deep boom hits.',
    rules: ['Use it once per part, on the last or second-to-last line.', 'The words are spoken like any other line.'],
    example: '!! The tower was never his to sell.' },
]
</script>

<template>
  <div class="grid items-start gap-6 lg:grid-cols-2">
    <div class="space-y-2 lg:col-span-2">
      <h2 class="font-display text-2xl font-semibold">Help: directing your story</h2>
      <p class="text-sm text-muted">Your <code>story.md</code> has two kinds of lines. Normal lines are <b>spoken</b> by the narrator.
        Lines that start with <code>@</code> are <b>stage directions</b>: they are never spoken, they tell the video what to show.
        Most of them work on the spoken line right under them.</p>
      <pre class="inset overflow-x-auto rounded-md px-3 py-2 font-mono text-xs"><span class="text-muted">@set beach                      ← where
@cast caligula, marcus          ← who is there
@do marcus: run                 ← what Marcus does…</span>
Marcus ran into the waves.      <span class="text-muted">← …while this is spoken</span></pre>
      <div class="rounded-md border border-subtle bg-surface/50 p-3 text-xs text-muted">
        <p class="font-semibold text-foreground">Useful details</p>
        <p class="mt-1">Directive lines may be indented and several may stack above one spoken line. <code>@do</code>,
          <code>@face</code>, <code>@fx</code>, <code>@fx lightning</code>, and <code>@sfx</code> affect the next spoken line;
          other directives persist until changed. Multiple <code>@face</code>/<code>@look</code> targets can be comma-separated.
          Without explicit staging, actions and faces are inferred from narration words. A prop-targeted lightning strike
          resolves to whoever holds that prop on the next line.</p>
      </div>
    </div>
    <nav aria-label="Directives" class="flex flex-wrap gap-1.5 lg:col-span-2">
      <a v-for="d in DIRECTIVES" :key="d.id" :href="`#${d.id}`" class="chip font-mono hover:underline">{{ d.nav ?? d.syntax.split(' ')[0] }}</a>
    </nav>
    <section v-for="d in DIRECTIVES" :id="d.id" :key="d.id" class="raised scroll-mt-4 space-y-3 p-5">
      <div>
        <h3 class="font-mono text-base font-semibold">{{ d.syntax }}</h3>
        <p class="text-sm">{{ d.what }}</p>
      </div>
      <ul class="list-disc space-y-1 pl-5 text-sm text-muted">
        <li v-for="r in d.rules" :key="r">{{ r }}</li>
      </ul>
      <pre class="inset overflow-x-auto rounded-md px-3 py-2 font-mono text-xs select-all">{{ d.example }}</pre>
      <div v-if="d.id === 'do' && gallery.length" class="space-y-1">
        <p class="text-xs font-semibold text-muted">What they look like</p>
        <ul class="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-7">
          <li v-for="g in gallery" :key="g.key" class="text-center">
            <ActionPreview :action="g.action" :label="`Stickman: ${g.note}`" class="aspect-[27/32] w-full" />
            <code class="block truncate text-xs">{{ g.name }}</code>
            <span class="block truncate text-[11px] text-muted">{{ g.note }}</span>
          </li>
        </ul>
      </div>
      <div v-if="d.list && live" class="text-xs text-muted">
        <span class="font-semibold">You can use:</span>
        <span class="ml-1 inline-flex flex-wrap gap-1 align-middle"><code v-for="x in live[d.list]" :key="x" class="chip">{{ x }}</code></span>
      </div>
    </section>
    <section id="props" class="raised scroll-mt-4 space-y-2 p-5">
      <h3 class="font-semibold">Props</h3>
      <p class="text-sm text-muted">Things people hold: set them on a cast member or a look, eat them with <code>@do … eat</code>,
        hand them over with <code>@do … give</code>. Make your own on the Props page.</p>
      <p v-if="live" class="flex flex-wrap gap-1"><code v-for="x in live.props" :key="x" class="chip">{{ x }}</code></p>
    </section>
    <section id="wardrobe" class="raised scroll-mt-4 space-y-2 p-5">
      <h3 class="font-semibold">Wardrobe</h3>
      <p class="text-sm text-muted">What stickmen wear, one item per slot (accessories and face: up to 3), set in the cast:
        <code>"hair": "wild_hair"</code> or <code>"hair": {"id": "wild_hair", "color": "#e8e8e8"}</code>, <code>null</code> for none.
        <code>@look</code> swaps a whole outfit. Make your own on the Wardrobe page.</p>
      <dl v-if="live" class="grid gap-1 text-xs sm:grid-cols-[8rem_1fr]">
        <template v-for="g in live.wardrobe" :key="g.slot">
          <dt class="font-semibold">{{ SLOT_LABEL[g.slot] }} <code class="text-muted">{{ g.slot }}</code></dt>
          <dd class="flex flex-wrap gap-1"><code v-for="x in g.ids" :key="x" class="chip">{{ x }}</code><span v-if="!g.ids.length" class="text-muted">none yet</span></dd>
        </template>
      </dl>
    </section>
  </div>
</template>
