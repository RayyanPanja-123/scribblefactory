<script setup lang="ts">
// Edit one cast member (/series/:slug/cast/:id), tab by tab (character, head, body, arms, legs, looks), previewed live
// by the engine's own drawing code (humanoid bodies). The tabs edit the base outfit or a named look (@look <cast>:
// <name>); a look is saved as only what differs from the base (pipeline CastMember.with_look merges it back), so later
// base changes still reach every field a look leaves alone. Saving a new look clears the approval and makes the
// member's render stale; "Save and render" queues its re-render (only this member). The server checks every field.
import { ArrowLeft, Pencil, Plus, RefreshCw, Trash2, X } from 'lucide-vue-next'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CastMember, type TtsVoice, type TtsVoices } from '../api/client'
import CreaturePreview from '../components/CreaturePreview.vue'
import ErrorCard from '../components/ErrorCard.vue'
import VoicePicker from '../components/VoicePicker.vue'
import WardrobePreview from '../components/WardrobePreview.vue'
import { act, confirm } from '../composables/feedback'
import { seriesBusy } from '../composables/live'
import { useApi } from '../composables/useApi'
import { allCreatures } from '../lib/creatures'
import { HANDS, propOptions, type Hand } from '../lib/props'
import { DEFAULT_TOP_COLOR, SLOT_LABEL, wardrobeOptions, type Slot } from '../lib/wardrobe'
import { EXPRESSIONS } from '../lib/expressions'

const props = defineProps<{ slug: string; id: string }>()
const router = useRouter()
const { data, error, loading, reload } = useApi(async () => {
  const [detail, wardrobe, propCatalog, creatures] = await Promise.all([
    api.seriesDetail(props.slug), api.wardrobe(), api.props(), api.creatures()])
  return { detail, wardrobe, propCatalog, creatures }
})
const member = computed(() => data.value?.detail.series.cast.find((c) => c.id === props.id))
const render = computed(() => data.value?.detail.cast[props.id])
const busy = computed(() => seriesBusy(props.slug))

const ONE: Slot[] = ['hair', 'facial_hair', 'headwear', 'legwear', 'footwear', 'back'] // one item each
const MANY: Slot[] = ['accessory', 'face'] // up to 3 each
const KIND_SLOTS: Slot[] = ['headwear', 'legwear'] // stored as {kind, color}; the rest as {id, color} or null
/** what a look can change (pipeline CastLook); name and body stay the member's own */
const LOOK_FIELDS = ['top', 'headwear', 'legwear', 'hair', 'facial_hair', 'footwear', 'back', 'accessory', 'face', 'props',
  'default_expression', 'eyes', 'headless', 'flame', 'flame_color'] as const
const FLAMES = ['off', 'low', 'high'] as const
type Worn = { id: string; color: string | null; accent?: string | null } // id '': nothing
type Obj = Record<string, unknown>

// ---- tabs: one body area at a time ----
const TABS = [
  { id: 'character', label: 'Character' }, { id: 'head', label: 'Head' }, { id: 'body', label: 'Body' },
  { id: 'arms', label: 'Arms' }, { id: 'legs', label: 'Legs' }, { id: 'looks', label: 'Looks' },
] as const
type Tab = (typeof TABS)[number]['id']
const SLOTS_IN: Partial<Record<Tab, { one: Slot[]; many: Slot[] }>> = {
  head: { one: ['hair', 'facial_hair', 'headwear'], many: ['face'] },
  body: { one: ['back'], many: ['accessory'] },
  legs: { one: ['legwear', 'footwear'], many: [] },
}
const tab = ref<Tab>('character')
function onTabKey(e: KeyboardEvent) { // arrow keys move between tabs (WAI-ARIA tabs pattern)
  const k = ({ ArrowRight: 1, ArrowLeft: -1 } as Record<string, number>)[e.key]
  if (!k) return
  e.preventDefault()
  const ids = TABS.map((t) => t.id)
  tab.value = ids[(ids.indexOf(tab.value) + k + ids.length) % ids.length]
  nextTick(() => document.getElementById(`cast-tab-${tab.value}`)?.focus())
}

const creatures = computed(() => allCreatures(data.value?.creatures))
const creature = (body: string) => creatures.value.find((c) => c.id === body)
const items = computed(() => wardrobeOptions(data.value?.wardrobe))
const custom = (id: string) => data.value?.wardrobe.custom.find((w) => w.id === id)
const ofSlot = (s: Slot) => items.value.filter((w) => w.slot === s && (humanoid.value || s === 'top' || custom(w.id)))
/** a creature wears custom items of these slots only (engine/page/creatures.js CREATURE_SLOTS) */
const CREATURE_SLOTS: Slot[] = ['headwear', 'face', 'accessory', 'back']
const shown = (slots: Slot[]) => slots.filter((s) => humanoid.value || CREATURE_SLOTS.includes(s))
/** null: no colour control (a custom item the cast can't recolour) */
const defaultColor = (id: string) => { const w = custom(id); return !w ? '#333333' : w.colorable ? w.default_color : null }
/** null: no accent control (a built-in, a fixed item, or one with no "$accent" layer) */
const defaultAccent = (id: string) => { const w = custom(id); return w?.colorable && w.layers.some((L) => L.fill === '$accent') ? w.default_accent ?? '#3a2a1e' : null }
/** a slot as saved: the accent only when one is set (an unset one stays out of series.json) */
const accentOf = (w: Worn) => (w.id && w.accent ? { accent: w.accent } : {})

// ---- drafts: an outfit as form state; one for the base, one for the look being edited ----
type Draft = {
  name: string; eyes: CastMember['eyes']; expression: string; body: string; headless: boolean; hands: Record<Hand, string>
  flame: (typeof FLAMES)[number]; flameColor: string | null // creatures only; null colour: fire
  top: { style: string; color: string; accent: string | null; number: string }
  one: Record<string, Worn>; many: Record<string, Worn[]>
}
const worn = (v: unknown): Worn => {
  const o = (v ?? {}) as Obj, id = (o.id ?? o.kind ?? '') as string
  return { id: id === 'none' ? '' : id, color: (o.color as string | null | undefined) ?? null, accent: (o.accent as string | null | undefined) ?? null }
}
/** a cast entry (the member, or the member with a look merged in) -> form state */
function toDraft(c: Obj): Draft {
  const hands: Record<Hand, string> = { left: '', right: '' }
  for (const x of (c.props ?? []) as { kind: string; hand?: Hand }[]) hands[x.hand ?? 'right'] = x.kind
  const t = (c.top ?? {}) as Obj
  return {
    name: c.name as string, eyes: c.eyes as CastMember['eyes'], expression: (c.default_expression as string) ?? 'neutral',
    body: (c.body as string) ?? 'human', headless: !!c.headless, hands,
    flame: (c.flame as Draft['flame']) ?? 'off', flameColor: (c.flame_color as string) ?? null,
    top: { style: (t.style as string) ?? 'plain', color: (t.color as string) ?? DEFAULT_TOP_COLOR, accent: (t.accent_color as string) ?? null, number: (t.number as string) ?? '' },
    one: Object.fromEntries(ONE.map((s) => [s, worn(c[s])])),
    many: Object.fromEntries(MANY.map((s) => [s, ((c[s] ?? []) as unknown[]).map(worn)])),
  }
}
/** form state -> a cast entry, over the member's own entry (id, approval-free; looks replaced on save) */
function toEntry(d: Draft): Obj {
  const c = member.value!
  const { approved_at: _, ...rest } = c
  const one = Object.fromEntries(ONE.map((s) => {
    const w = d.one[s]
    return [s, KIND_SLOTS.includes(s) ? { kind: w.id || 'none', color: w.id ? w.color : null, ...accentOf(w) } : w.id ? { id: w.id, color: w.color, ...accentOf(w) } : null]
  }))
  return {
    ...rest, ...one, name: d.name.trim(), eyes: d.eyes, default_expression: d.expression, body: d.body,
    headless: d.headless && !!creature(d.body)?.parts.stump,
    flame: d.flame, flame_color: d.flame !== 'off' ? d.flameColor : null, // the server stores off as unset
    top: { ...c.top, style: d.top.style, color: d.top.color, accent_color: d.top.accent, number: d.top.number.trim() || null },
    props: HANDS.filter((h) => d.hands[h]).map((h) => ({ kind: d.hands[h], hand: h })),
    ...Object.fromEntries(MANY.map((s) => [s, d.many[s].filter((w) => w.id).map((w) => ({ id: w.id, color: w.color, ...accentOf(w) }))])),
  }
}
const nonNull = (o: Obj) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== null && v !== undefined))
/** a look as only what differs from the base; an item the base wears and the look doesn't is "none" (taken off) */
function lookDiff(look: Obj, base: Obj): Obj {
  const out: Obj = {}
  for (const k of LOOK_FIELDS) {
    if (JSON.stringify(look[k] ?? null) === JSON.stringify(base[k] ?? null)) continue
    if (k === 'flame_color' && look[k] == null) continue // a look keeps the base's flame colour (null: unchanged)
    out[k] = look[k] ?? { id: 'none' } // only the plain slots (hair, facial_hair, footwear, back) are ever null
  }
  return out
}

const base = ref<Draft>()
const looks = ref<Record<string, Obj>>({}) // name -> overrides
const active = ref('') // '' = the base outfit
const lookDraft = ref<Draft>()
const newId = ref(props.id) // editing it renames the member; the server rewrites story.md and moves the render
const idError = computed(() => !LOOK_ID.test(newId.value) ? 'Lowercase letters, digits and dashes only.'
  : newId.value !== props.id && data.value?.detail.series.cast.some((c) => c.id === newId.value) ? 'That id is taken.' : '')
// the TTS voice of this member's own lines ("<id>: line" in story.md): not part of the look, no new approval
const voice = ref<TtsVoice | null>(null)
const voices = ref<TtsVoices | null>(null)
api.ttsVoices().then((v) => { voices.value = v }).catch(() => {})
watch(member, (c) => {
  if (!c || base.value) return
  voice.value = c.voice ?? null
  base.value = toDraft(c as unknown as Obj)
  looks.value = Object.fromEntries(Object.entries(c.looks ?? {}).map(([k, v]) => [k, nonNull(v as Obj)]))
}, { immediate: true })

const draft = computed(() => (active.value ? lookDraft.value : base.value))
const baseEntry = computed(() => (member.value && base.value ? toEntry(base.value) : null))
const entry = computed(() => (active.value && lookDraft.value ? toEntry(lookDraft.value) : baseEntry.value))

/** keep the edited look's overrides in step, then switch the tabs to another outfit */
function commitLook() {
  if (active.value && lookDraft.value && baseEntry.value) looks.value[active.value] = lookDiff(toEntry(lookDraft.value), baseEntry.value)
}
function editOutfit(name: string) {
  commitLook()
  active.value = name
  lookDraft.value = name && baseEntry.value ? toDraft({ ...baseEntry.value, ...looks.value[name] }) : undefined
  if (tab.value === 'looks') tab.value = 'head'
}
/** what each look changes, for the list (the edited one live) */
const changes = (name: string) => Object.keys(name === active.value && lookDraft.value && baseEntry.value
  ? lookDiff(toEntry(lookDraft.value), baseEntry.value) : looks.value[name] ?? {})
  .map((k) => (k === 'props' ? 'props in hand' : k === 'default_expression' ? 'expression' : SLOT_LABEL[k as Slot]?.toLowerCase() ?? k))

// ---- managing looks ----
const LOOK_ID = /^[a-z0-9][a-z0-9-]*$/
const lookError = (name: string, was = '') => !LOOK_ID.test(name) ? 'Lowercase letters, digits and dashes only.'
  : name === 'default' ? '“default” is reserved: it means the base outfit.' : name !== was && name in looks.value ? 'That look already exists.' : ''
const newName = ref('')
const newError = computed(() => (newName.value ? lookError(newName.value) : ''))
function addLook() {
  const n = newName.value.trim()
  if (!n || lookError(n)) return
  looks.value[n] = {}
  newName.value = ''
  editOutfit(n)
}
const renaming = ref<{ from: string; to: string } | null>(null)
function renameLook() {
  const r = renaming.value
  if (!r || lookError(r.to, r.from)) return
  commitLook()
  if (r.to !== r.from) {
    looks.value = Object.fromEntries(Object.entries(looks.value).map(([k, v]) => [k === r.from ? r.to : k, v]))
    if (active.value === r.from) active.value = r.to
  }
  renaming.value = null
}
async function deleteLook(name: string) {
  if (!(await confirm({ title: `Delete the look “${name}”?`, body: `Stories with @look ${props.id}: ${name} stop working until you change them. Nothing is saved until you click Save.`, confirm: 'Delete', danger: true }))) return
  if (active.value === name) editOutfit('')
  const { [name]: _, ...rest } = looks.value
  looks.value = rest
}

function pick(w: Worn) { // a new item: its own default colour (built-ins need one), none if it can't be recoloured
  w.color = w.id ? defaultColor(w.id) : null
  w.accent = null // the item's own default_accent until picked
}
const handOptions = computed(() => {
  const o = propOptions(data.value?.propCatalog), d = draft.value
  return [...o, ...(d ? HANDS.map((h) => d.hands[h]).filter((k) => k && !o.some((x) => x.id === k)).map((k) => ({ id: k, name: `${k} (unknown)` })) : [])]
})
const humanoid = computed(() => creature(base.value?.body ?? 'human')?.rig === 'humanoid')
const library = computed(() => ({ props: data.value?.propCatalog.custom ?? [], wardrobe: data.value?.wardrobe.custom ?? [] }))

const saving = ref(false)
async function save(andRender: boolean) {
  commitLook()
  if (!baseEntry.value || idError.value) return
  const body: Obj = { ...baseEntry.value, id: newId.value, looks: looks.value, voice: voice.value }
  saving.value = true
  const s = await act(() => api.editCast(props.slug, props.id, body), `${body.name as string} saved`)
  if (s && andRender) {
    const part = data.value!.detail.series.parts[0]
    if (part) await act(() => api.submitJob(props.slug, part, [`cast-sheet ${newId.value}`]), `${body.name as string} render queued`)
  }
  saving.value = false
  if (s) router.push(back.value)
}
// where Save and Back go: the page that opened the editor (a part or the series), else the series' cast
const route = useRoute()
const back = computed(() => { const b = route.query.back; return typeof b === 'string' && b.startsWith('/') && !b.startsWith('//') ? b : `/series/${props.slug}#cast` })
const field = 'inset mt-1 block h-10 w-full rounded-md px-3 text-sm text-ink outline-none focus:border-blue'
const swatch = 'mt-1 block h-10 w-14 shrink-0 cursor-pointer rounded-md'
</script>

<template>
  <div class="space-y-6">
    <RouterLink :to="back" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> Back</RouterLink>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading cast member" />
    <ErrorCard v-else-if="!member" :message="`No cast member “${id}” in ${slug}.`" @retry="reload" />
    <form v-else-if="base && draft" class="grid items-start gap-6 lg:grid-cols-[1fr_300px]" @submit.prevent="save(true)">
      <div class="raised min-w-0 space-y-5 p-6">
        <div>
          <h2 class="font-display text-3xl font-semibold">{{ base.name || id }}</h2>
          <p class="mt-1 text-sm text-muted">Id <code>{{ id }}</code> (stories use it; change it on the Character tab). A new look clears the approval and needs a re-render of this character only.</p>
        </div>

        <!-- which outfit the tabs edit -->
        <div class="flex flex-wrap items-center gap-2" role="group" aria-label="Outfit to edit">
          <span class="text-xs font-semibold text-muted">Editing</span>
          <button type="button" class="chip" :class="!active ? 'chip-blue' : 'hover:text-ink'" :aria-pressed="!active" @click="editOutfit('')">Base outfit</button>
          <button v-for="n in Object.keys(looks)" :key="n" type="button" class="chip" :class="active === n ? 'chip-blue' : 'hover:text-ink'"
            :aria-pressed="active === n" @click="editOutfit(n)">look: {{ n }}</button>
          <button type="button" class="chip hover:text-ink" @click="tab = 'looks'"><Plus :size="12" aria-hidden="true" /> Look</button>
        </div>
        <p v-if="active" class="inset px-3 py-2 text-xs text-muted">
          Editing the look <strong class="text-ink">{{ active }}</strong> (<code>@look {{ id }}: {{ active }}</code>). Only what you change from the
          base outfit is saved{{ changes(active).length ? `: ${changes(active).join(', ')}` : ' (nothing yet)' }}. Name and body stay the base's.
        </p>

        <div class="flex gap-1 overflow-x-auto border-b border-rule" role="tablist" aria-label="Cast member parts">
          <button v-for="t in TABS" :id="`cast-tab-${t.id}`" :key="t.id" type="button" role="tab" :aria-selected="tab === t.id"
            :aria-controls="`cast-panel-${t.id}`" :tabindex="tab === t.id ? 0 : -1"
            class="relative shrink-0 px-4 py-2.5 text-sm font-semibold" :class="tab === t.id ? 'text-ink' : 'text-muted hover:text-ink'"
            @click="tab = t.id" @keydown="onTabKey">
            <span v-if="tab === t.id" class="absolute inset-x-2 -bottom-px h-[3px] rounded-t-sm bg-ink" aria-hidden="true" />
            {{ t.label }}<span v-if="t.id === 'looks' && Object.keys(looks).length" class="ml-1 text-xs text-muted">{{ Object.keys(looks).length }}</span>
          </button>
        </div>

        <!-- character -->
        <div v-show="tab === 'character'" id="cast-panel-character" role="tabpanel" aria-labelledby="cast-tab-character" class="grid gap-4 sm:grid-cols-2">
          <label class="block text-xs font-semibold text-muted">Name
            <input v-model="base.name" required :disabled="!!active" :class="field" />
          </label>
          <label class="block text-xs font-semibold text-muted">Id
            <input v-model.trim="newId" required :disabled="!!active || busy" :class="field" />
            <span v-if="idError" class="mt-1 block font-normal text-red-ink" role="alert">{{ idError }}</span>
            <span v-else-if="newId !== id" class="mt-1 block font-normal">Story lines and directives using <code>{{ id }}</code> are rewritten to <code>{{ newId }}</code>.</span>
          </label>
          <label class="block text-xs font-semibold text-muted">Body
            <select v-model="base.body" :disabled="!!active" :class="field">
              <option v-for="b in creatures" :key="b.id" :value="b.id">{{ b.name }} ({{ b.rig }})</option>
              <option v-if="!creature(base.body)" :value="base.body">{{ base.body }} (unknown)</option>
            </select>
          </label>
          <label class="block text-xs font-semibold text-muted">Eyes
            <select v-model="draft.eyes" :class="field">
              <option value="dots">dots</option>
              <option value="half_closed">half closed</option>
            </select>
          </label>
          <label class="block text-xs font-semibold text-muted">Default expression
            <select v-model="draft.expression" :class="field">
              <option v-for="e in EXPRESSIONS" :key="e" :value="e">{{ e }}</option>
            </select>
          </label>
          <template v-if="!humanoid">
            <label class="block text-xs font-semibold text-muted">Flame (mane, tail, hooves; eyes glow)
              <select v-model="draft.flame" :class="field">
                <option v-for="f in FLAMES" :key="f" :value="f">{{ f }}</option>
              </select>
            </label>
            <label v-if="draft.flame !== 'off'" class="block text-xs font-semibold text-muted">Flame colour
              <span class="flex items-center gap-1">
                <input :value="draft.flameColor ?? '#d8432a'" type="color" :class="[swatch, !draft.flameColor && 'opacity-40']"
                  :aria-label="draft.flameColor ? 'Flame colour' : 'Flame colour: fire (pick one to recolour)'"
                  @input="draft.flameColor = ($event.target as HTMLInputElement).value" />
                <button v-if="draft.flameColor" type="button" class="btn btn-secondary mt-1 size-8 justify-center p-0" aria-label="Back to fire colours" @click="draft.flameColor = null">
                  <X :size="14" aria-hidden="true" />
                </button>
                <span v-if="!draft.flameColor" class="ml-1 text-xs">fire</span>
              </span>
            </label>
          </template>
          <label v-if="creature(base.body)?.parts.stump" class="flex items-center gap-2 text-sm">
            <input v-model="draft.headless" type="checkbox" class="size-4" /> Headless (the stump instead of the head)
          </label>
          <fieldset class="sm:col-span-2">
            <legend class="text-xs font-semibold text-muted">TTS voice: how {{ base.name || id }} sounds on their own lines (<code>{{ id }}: line</code>)</legend>
            <VoicePicker v-model="voice" :voices="voices" none="The narrator's voice" :sample="`Hi, I'm ${base.name || id}. Nice to meet you.`" class="mt-1" />
          </fieldset>
        </div>

        <!-- head, body, legs: wardrobe slots -->
        <template v-for="t in (['head', 'body', 'legs'] as const)" :key="t">
          <div v-show="tab === t" :id="`cast-panel-${t}`" role="tabpanel" :aria-labelledby="`cast-tab-${t}`" class="space-y-4">
            <p v-if="!humanoid" class="text-xs text-muted">This body is a creature: it draws in the top colour (main) and accent, and wears only custom headwear, face, accessory and back items (fitted to its head and body, roughly).</p>

            <div v-if="t === 'body'" class="grid gap-4 sm:grid-cols-[1fr_auto_auto_6rem]">
              <label class="block text-xs font-semibold text-muted">Top
                <select v-model="draft.top.style" :class="field">
                  <option v-for="w in ofSlot('top')" :key="w.id" :value="w.id">{{ w.name }}</option>
                </select>
              </label>
              <label class="block text-xs font-semibold text-muted">Colour
                <input v-model="draft.top.color" type="color" :class="swatch" />
              </label>
              <label class="block text-xs font-semibold text-muted">Accent
                <span class="flex items-center gap-1">
                  <input :value="draft.top.accent ?? '#b71c1c'" type="color" :class="[swatch, !draft.top.accent && 'opacity-40']"
                    @input="draft.top.accent = ($event.target as HTMLInputElement).value" />
                  <button v-if="draft.top.accent" type="button" class="btn btn-secondary mt-1 size-8 justify-center p-0" aria-label="No accent" @click="draft.top.accent = null">
                    <X :size="14" aria-hidden="true" />
                  </button>
                </span>
              </label>
              <label class="block text-xs font-semibold text-muted">Number
                <input v-model="draft.top.number" inputmode="numeric" pattern="[0-9]{1,3}" placeholder="none" :class="field" />
              </label>
            </div>

            <div v-for="s in shown(SLOTS_IN[t]!.one)" :key="s" class="flex items-end gap-3">
              <label class="block min-w-0 flex-1 text-xs font-semibold text-muted">{{ SLOT_LABEL[s] }}
                <select v-model="draft.one[s].id" :class="field" @change="pick(draft.one[s])">
                  <option value="">none</option>
                  <option v-for="w in ofSlot(s)" :key="w.id" :value="w.id">{{ w.name }}</option>
                  <option v-if="draft.one[s].id && !ofSlot(s).some((w) => w.id === draft!.one[s].id)" :value="draft.one[s].id">{{ draft.one[s].id }} (unknown)</option>
                </select>
              </label>
              <input v-if="draft.one[s].id && defaultColor(draft.one[s].id)" :value="draft.one[s].color ?? defaultColor(draft.one[s].id)"
                type="color" :class="swatch" :aria-label="`${SLOT_LABEL[s]} colour`"
                @input="draft.one[s].color = ($event.target as HTMLInputElement).value" />
              <input v-if="draft.one[s].id && defaultAccent(draft.one[s].id)" :value="draft.one[s].accent ?? defaultAccent(draft.one[s].id)"
                type="color" :class="swatch" :aria-label="`${SLOT_LABEL[s]} accent`" :title="`${SLOT_LABEL[s]} accent`"
                @input="draft.one[s].accent = ($event.target as HTMLInputElement).value" />
            </div>

            <div v-for="s in shown(SLOTS_IN[t]!.many)" :key="s">
              <span class="block text-xs font-semibold text-muted">{{ SLOT_LABEL[s] }} (up to 3)</span>
              <div v-for="(w, i) in draft.many[s]" :key="i" class="mt-1 flex items-end gap-3">
                <select v-model="w.id" :class="field" class="flex-1" :aria-label="`${SLOT_LABEL[s]} ${i + 1}`" @change="pick(w)">
                  <option v-for="o in ofSlot(s)" :key="o.id" :value="o.id">{{ o.name }}</option>
                  <option v-if="!ofSlot(s).some((o) => o.id === w.id)" :value="w.id">{{ w.id }} (unknown)</option>
                </select>
                <input v-if="defaultColor(w.id)" :value="w.color ?? defaultColor(w.id)" type="color" :class="swatch"
                  :aria-label="`${SLOT_LABEL[s]} ${i + 1} colour`" @input="w.color = ($event.target as HTMLInputElement).value" />
                <input v-if="defaultAccent(w.id)" :value="w.accent ?? defaultAccent(w.id)" type="color" :class="swatch"
                  :aria-label="`${SLOT_LABEL[s]} ${i + 1} accent`" :title="`${SLOT_LABEL[s]} ${i + 1} accent`"
                  @input="w.accent = ($event.target as HTMLInputElement).value" />
                <button type="button" class="btn btn-secondary size-10 justify-center p-0" :aria-label="`Remove ${SLOT_LABEL[s]} ${i + 1}`"
                  @click="draft.many[s].splice(i, 1)"><X :size="14" aria-hidden="true" /></button>
              </div>
              <button v-if="draft.many[s].length < 3 && ofSlot(s).length" type="button" class="btn btn-secondary mt-2"
                @click="draft.many[s].push({ id: ofSlot(s)[0].id, color: defaultColor(ofSlot(s)[0].id) })">
                <Plus :size="14" aria-hidden="true" /> Add {{ SLOT_LABEL[s].toLowerCase() }}
              </button>
            </div>
          </div>
        </template>

        <!-- arms: props in hand -->
        <div v-show="tab === 'arms'" id="cast-panel-arms" role="tabpanel" aria-labelledby="cast-tab-arms" class="space-y-3">
          <p class="text-xs text-muted">Held props, one per hand. Long props draw at their own angle (set on the Props page).</p>
          <div class="grid gap-4 sm:grid-cols-2">
            <label v-for="h in HANDS" :key="h" class="block text-xs font-semibold text-muted">{{ h === 'left' ? 'Left hand' : 'Right hand' }}
              <select v-model="draft.hands[h]" :class="field">
                <option value="">nothing</option>
                <option v-for="o in handOptions" :key="o.id" :value="o.id">{{ o.name }}</option>
              </select>
            </label>
          </div>
        </div>

        <!-- looks -->
        <div v-show="tab === 'looks'" id="cast-panel-looks" role="tabpanel" aria-labelledby="cast-tab-looks" class="space-y-4">
          <p class="text-sm text-muted">A look is a named change a story switches on with <code>@look {{ id }}: &lt;name&gt;</code> (and off with
            <code>default</code>): a held spear, a crown, a different top. It stores only what differs from the base outfit.</p>
          <ul v-if="Object.keys(looks).length" class="divide-y divide-rule">
            <li v-for="n in Object.keys(looks)" :key="n" class="flex flex-wrap items-center gap-2 py-2">
              <template v-if="renaming?.from === n">
                <label class="sr-only" :for="`rename-${n}`">New name for {{ n }}</label>
                <input :id="`rename-${n}`" v-model.trim="renaming.to" :class="field" class="!mt-0 max-w-48" @keydown.enter.prevent="renameLook" @keydown.esc.prevent="renaming = null" />
                <button type="button" class="btn btn-primary" :disabled="!!lookError(renaming.to, n)" @click="renameLook">Rename</button>
                <button type="button" class="btn btn-secondary" @click="renaming = null">Cancel</button>
                <span v-if="lookError(renaming.to, n)" class="w-full text-xs text-red-ink" role="alert">{{ lookError(renaming.to, n) }}</span>
                <span v-else-if="renaming.to !== n" class="w-full text-xs text-muted">Stories using <code>@look {{ id }}: {{ n }}</code> need the new name.</span>
              </template>
              <template v-else>
                <code class="font-semibold">{{ n }}</code>
                <span class="text-xs text-muted">{{ changes(n).length ? `changes ${changes(n).join(', ')}` : 'no changes yet' }}</span>
                <span class="ml-auto flex gap-2">
                  <button type="button" class="btn btn-secondary" @click="editOutfit(n)">Edit</button>
                  <button type="button" class="btn btn-secondary size-10 justify-center p-0" :aria-label="`Rename ${n}`" @click="renaming = { from: n, to: n }"><Pencil :size="14" aria-hidden="true" /></button>
                  <button type="button" class="btn btn-secondary size-10 justify-center p-0" :aria-label="`Delete ${n}`" @click="deleteLook(n)"><Trash2 :size="14" aria-hidden="true" /></button>
                </span>
              </template>
            </li>
          </ul>
          <p v-else class="text-sm text-muted">No looks yet.</p>
          <div class="flex flex-wrap items-end gap-2">
            <label class="block text-xs font-semibold text-muted">New look
              <input v-model.trim="newName" placeholder="e.g. crowned" :class="field" class="max-w-56" :aria-invalid="!!newError" @keydown.enter.prevent="addLook" />
            </label>
            <button type="button" class="btn btn-secondary" :disabled="!newName || !!newError" @click="addLook"><Plus :size="14" aria-hidden="true" /> Add and edit</button>
            <p v-if="newError" class="w-full text-xs text-red-ink" role="alert">{{ newError }}</p>
          </div>
        </div>
      </div>

      <aside class="raised p-6 space-y-4 lg:sticky lg:top-6 lg:self-start">
        <figure>
          <WardrobePreview v-if="humanoid && entry" class="h-80" :wear="entry" :library="library" :build="creature(base.body)?.build"
            :expression="draft.expression" :seed="`${slug}:${id}`" :label="`${base.name}${active ? `, look ${active}` : ''}, live preview`" />
          <CreaturePreview v-else-if="creature(base.body)" class="h-80" :creature="creature(base.body)!" :color="draft.top.color" :headless="draft.headless"
            :flame="draft.flame" :flame-color="draft.flameColor" :wear="entry ?? undefined" :library="library" :label="`${base.name}${active ? `, look ${active}` : ''}, live preview`" />
          <div v-else class="drawing grid h-80 place-items-center rounded-md p-4 text-center text-sm text-muted">No live preview for this body: save and render to see it.</div>
          <figcaption class="mt-2 text-center text-xs text-muted">Live preview (idle){{ active ? `: look ${active}` : '' }}</figcaption>
        </figure>
        <figure v-if="render?.idle">
          <img :src="render.idle" :alt="`${member.name}, last render`" class="mx-auto aspect-[3/4] w-36 rounded-md object-cover object-bottom"
            :class="{ 'opacity-50': !render.current }" />
          <figcaption class="mt-2 text-center text-xs text-muted">Last render{{ render.current ? '' : ' (out of date)' }}</figcaption>
        </figure>
        <div class="flex flex-col gap-2">
          <button class="btn btn-primary justify-center" :disabled="saving || busy || !base.name.trim()"
            :title="busy ? 'a job is running in this series' : undefined">
            <RefreshCw :size="16" aria-hidden="true" /> {{ saving ? 'Saving…' : 'Save and render' }}
          </button>
          <button type="button" class="btn btn-secondary justify-center" :disabled="saving || busy || !base.name.trim()" @click="save(false)">Save only</button>
          <p class="text-center text-xs text-muted">Saves the base outfit and every look.</p>
        </div>
      </aside>
    </form>
  </div>
</template>
