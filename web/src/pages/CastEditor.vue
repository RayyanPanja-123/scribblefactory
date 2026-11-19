<script setup lang="ts">
// Edit one cast member (/series/:slug/cast/:id): name, body, eyes, expression, held props and every wardrobe slot,
// previewed live by the engine's own drawing code (humanoid bodies). Saving a new look clears the approval and makes
// the member's render stale; "Save and render" queues its re-render (only this member). The server checks every field.
import { ArrowLeft, Plus, RefreshCw, X } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, type CastMember } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import WardrobePreview from '../components/WardrobePreview.vue'
import { act } from '../composables/feedback'
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
type Worn = { id: string; color: string | null } // id '': nothing
type Obj = Record<string, unknown>

const creatures = computed(() => allCreatures(data.value?.creatures))
const creature = (body: string) => creatures.value.find((c) => c.id === body)
const items = computed(() => wardrobeOptions(data.value?.wardrobe))
const custom = (id: string) => data.value?.wardrobe.custom.find((w) => w.id === id)
const ofSlot = (s: Slot) => items.value.filter((w) => w.slot === s)
/** null: no colour control (a custom item the cast can't recolour) */
const defaultColor = (id: string) => { const w = custom(id); return !w ? '#333333' : w.colorable ? w.default_color : null }

// ---- the draft: built from the member once loaded, sent back over the member's own entry (looks etc. kept) ----
const draft = ref<{
  name: string; eyes: CastMember['eyes']; expression: string; body: string; headless: boolean; hands: Record<Hand, string>
  top: { style: string; color: string; accent: string | null; number: string }
  one: Record<string, Worn>; many: Record<string, Worn[]>
}>()
const worn = (v: unknown): Worn => {
  const o = (v ?? {}) as Obj, id = (o.id ?? o.kind ?? '') as string
  return { id: id === 'none' ? '' : id, color: (o.color as string | null | undefined) ?? null }
}
watch(member, (c) => {
  if (!c || draft.value) return
  const hands: Record<Hand, string> = { left: '', right: '' }
  for (const x of c.props ?? []) hands[x.hand ?? 'right'] = x.kind
  const m = c as unknown as Obj
  draft.value = {
    name: c.name, eyes: c.eyes, expression: c.default_expression ?? 'neutral', body: c.body ?? 'human', headless: !!c.headless, hands,
    top: { style: c.top.style ?? 'plain', color: c.top.color ?? DEFAULT_TOP_COLOR, accent: c.top.accent_color ?? null, number: c.top.number ?? '' },
    one: Object.fromEntries(ONE.map((s) => [s, worn(m[s])])),
    many: Object.fromEntries(MANY.map((s) => [s, ((m[s] ?? []) as unknown[]).map(worn)])),
  }
}, { immediate: true })

function pick(w: Worn) { // a new item: its own default colour (built-ins need one), none if it can't be recoloured
  w.color = w.id ? defaultColor(w.id) : null
}
const handOptions = computed(() => {
  const o = propOptions(data.value?.propCatalog), d = draft.value
  return [...o, ...(d ? HANDS.map((h) => d.hands[h]).filter((k) => k && !o.some((x) => x.id === k)).map((k) => ({ id: k, name: `${k} (unknown)` })) : [])]
})

const entry = computed(() => {
  const c = member.value, d = draft.value
  if (!c || !d) return null
  const { approved_at: _, ...rest } = c
  const one = Object.fromEntries(ONE.map((s) => {
    const w = d.one[s]
    return [s, KIND_SLOTS.includes(s) ? { kind: w.id || 'none', color: w.id ? w.color : null } : w.id ? { id: w.id, color: w.color } : null]
  }))
  return {
    ...rest, ...one, name: d.name.trim(), eyes: d.eyes, default_expression: d.expression, body: d.body,
    headless: d.headless && !!creature(d.body)?.parts.stump,
    top: { ...c.top, style: d.top.style, color: d.top.color, accent_color: d.top.accent, number: d.top.number.trim() || null },
    props: HANDS.filter((h) => d.hands[h]).map((h) => ({ kind: d.hands[h], hand: h })),
    ...Object.fromEntries(MANY.map((s) => [s, d.many[s].filter((w) => w.id).map((w) => ({ id: w.id, color: w.color }))])),
  }
})
const humanoid = computed(() => creature(draft.value?.body ?? 'human')?.rig === 'humanoid')
const library = computed(() => ({ props: data.value?.propCatalog.custom ?? [], wardrobe: data.value?.wardrobe.custom ?? [] }))

const saving = ref(false)
async function save(andRender: boolean) {
  const body = entry.value
  if (!body) return
  saving.value = true
  const s = await act(() => api.editCast(props.slug, props.id, body), `${body.name} saved`)
  if (s && andRender) {
    const part = data.value!.detail.series.parts[0]
    if (part) await act(() => api.submitJob(props.slug, part, [`cast-sheet ${props.id}`]), `${body.name} render queued`)
  }
  saving.value = false
  if (s) router.push(`/series/${props.slug}#cast`)
}
const field = 'inset mt-1 block h-10 w-full rounded-md px-3 text-sm text-ink outline-none focus:border-blue'
const swatch = 'mt-1 block h-10 w-14 shrink-0 cursor-pointer rounded-md'
</script>

<template>
  <div class="max-w-6xl space-y-6">
    <RouterLink :to="`/series/${slug}#cast`" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> Back to the series</RouterLink>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading cast member" />
    <ErrorCard v-else-if="!member" :message="`No cast member “${id}” in ${slug}.`" @retry="reload" />
    <form v-else-if="draft" class="raised grid gap-6 p-6 lg:grid-cols-[1fr_300px]" @submit.prevent="save(true)">
      <div class="min-w-0 space-y-6">
        <div>
          <h2 class="font-display text-3xl font-semibold">{{ draft.name || id }}</h2>
          <p class="mt-1 text-sm text-muted">Id <code>{{ id }}</code> stays (stories use it). A new look clears the approval and needs a re-render of this character only.</p>
        </div>

        <fieldset class="grid gap-4 sm:grid-cols-2">
          <legend class="mb-2 font-display text-lg font-semibold">Character</legend>
          <label class="block text-xs font-semibold text-muted">Name
            <input v-model="draft.name" required :class="field" />
          </label>
          <label class="block text-xs font-semibold text-muted">Body
            <select v-model="draft.body" :class="field">
              <option v-for="b in creatures" :key="b.id" :value="b.id">{{ b.name }} ({{ b.rig }})</option>
              <option v-if="!creature(draft.body)" :value="draft.body">{{ draft.body }} (unknown)</option>
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
          <label v-if="creature(draft.body)?.parts.stump" class="flex items-center gap-2 text-sm">
            <input v-model="draft.headless" type="checkbox" class="size-4" /> Headless (the stump instead of the head)
          </label>
        </fieldset>

        <fieldset class="grid gap-4 sm:grid-cols-2">
          <legend class="mb-2 font-display text-lg font-semibold">Props in hand</legend>
          <label v-for="h in HANDS" :key="h" class="block text-xs font-semibold text-muted">{{ h === 'left' ? 'Left hand' : 'Right hand' }}
            <select v-model="draft.hands[h]" :class="field">
              <option value="">nothing</option>
              <option v-for="o in handOptions" :key="o.id" :value="o.id">{{ o.name }}</option>
            </select>
          </label>
        </fieldset>

        <fieldset class="space-y-4">
          <legend class="mb-2 font-display text-lg font-semibold">Wardrobe</legend>
          <p v-if="!humanoid" class="text-xs text-muted">This body is not a humanoid: it ignores the wardrobe and draws in the top colour (main) and accent.</p>

          <div class="grid gap-4 sm:grid-cols-[1fr_auto_auto_6rem]">
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

          <div v-for="s in ONE" :key="s" class="flex items-end gap-3">
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
          </div>

          <div v-for="s in MANY" :key="s">
            <span class="block text-xs font-semibold text-muted">{{ SLOT_LABEL[s] }} (up to 3)</span>
            <div v-for="(w, i) in draft.many[s]" :key="i" class="mt-1 flex items-end gap-3">
              <select v-model="w.id" :class="field" class="flex-1" :aria-label="`${SLOT_LABEL[s]} ${i + 1}`" @change="pick(w)">
                <option v-for="o in ofSlot(s)" :key="o.id" :value="o.id">{{ o.name }}</option>
                <option v-if="!ofSlot(s).some((o) => o.id === w.id)" :value="w.id">{{ w.id }} (unknown)</option>
              </select>
              <input v-if="defaultColor(w.id)" :value="w.color ?? defaultColor(w.id)" type="color" :class="swatch"
                :aria-label="`${SLOT_LABEL[s]} ${i + 1} colour`" @input="w.color = ($event.target as HTMLInputElement).value" />
              <button type="button" class="btn btn-secondary size-10 justify-center p-0" :aria-label="`Remove ${SLOT_LABEL[s]} ${i + 1}`"
                @click="draft.many[s].splice(i, 1)"><X :size="14" aria-hidden="true" /></button>
            </div>
            <button v-if="draft.many[s].length < 3 && ofSlot(s).length" type="button" class="btn btn-secondary mt-2"
              @click="draft.many[s].push({ id: ofSlot(s)[0].id, color: defaultColor(ofSlot(s)[0].id) })">
              <Plus :size="14" aria-hidden="true" /> Add {{ SLOT_LABEL[s].toLowerCase() }}
            </button>
          </div>
        </fieldset>
      </div>

      <aside class="space-y-4 lg:sticky lg:top-6 lg:self-start">
        <figure>
          <WardrobePreview v-if="humanoid && entry" class="h-80" :wear="entry" :library="library" :build="creature(draft.body)?.build"
            :expression="draft.expression" :seed="`${slug}:${id}`" :label="`${draft.name}, live preview`" />
          <div v-else class="drawing grid h-80 place-items-center rounded-md p-4 text-center text-sm text-muted">No live preview for this body: save and render to see it.</div>
          <figcaption class="mt-2 text-center text-xs text-muted">Live preview (idle)</figcaption>
        </figure>
        <figure v-if="render?.idle">
          <img :src="render.idle" :alt="`${member.name}, last render`" class="mx-auto aspect-[3/4] w-36 rounded-md object-cover object-bottom"
            :class="{ 'opacity-50': !render.current }" />
          <figcaption class="mt-2 text-center text-xs text-muted">Last render{{ render.current ? '' : ' (out of date)' }}</figcaption>
        </figure>
        <div class="flex flex-col gap-2">
          <button class="btn btn-primary justify-center" :disabled="saving || busy || !draft.name.trim()"
            :title="busy ? 'a job is running in this series' : undefined">
            <RefreshCw :size="16" aria-hidden="true" /> {{ saving ? 'Saving…' : 'Save and render' }}
          </button>
          <button type="button" class="btn btn-secondary justify-center" :disabled="saving || busy || !draft.name.trim()" @click="save(false)">Save only</button>
        </div>
      </aside>
    </form>
  </div>
</template>
