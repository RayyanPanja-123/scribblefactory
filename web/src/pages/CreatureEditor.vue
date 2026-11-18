<script setup lang="ts">
import { ArrowLeft, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import CreaturePreview from '../components/CreaturePreview.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { act, confirm, toast } from '../composables/feedback'
import { useApi } from '../composables/useApi'
import { DEFAULT_BUILD, RIG_LIST, RIG_NOTES, allCreatures, builtinCreatures, isBuiltinCreature, rigParts, type CustomCreature, type Rig } from '../lib/creatures'

// Create (/creatures/new, ?from=<id> copies one) or edit one custom creature: rig, colours and the drawing as JSON
// (joints, face, parts), or for a humanoid (a stickman) its build: proportions and head colour. Previewed live in
// every pose by the engine's own drawing code. The server (schema CustomCreature) has the final say on every field.
const props = defineProps<{ id: string }>()
const route = useRoute()
const router = useRouter()
const isNew = computed(() => props.id === 'new')
const { data, error, loading, reload } = useApi(() => api.creatures())

const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
// one shape per line, points as [x, y]
const drawingOf = (c: CustomCreature) => JSON.stringify({ joints: c.joints, face: c.face, parts: c.parts }, null, 2)
  .replace(/\[\s+(-?[\d.]+),\s+(-?[\d.]+)\s+\]/g, '[$1, $2]')
const form = reactive({ id: '', name: '', idEdited: false, rig: 'bird' as Rig, accent: '#3a2a1e', drawing: '', build: { ...DEFAULT_BUILD } })
const load = (c: CustomCreature, keepId = false) => Object.assign(form, {
  ...(keepId ? {} : { id: c.id, idEdited: true }), name: c.name, rig: c.rig, accent: c.accent ?? '#3a2a1e', drawing: drawingOf(c),
  build: { ...DEFAULT_BUILD, ...(c.build ?? {}) } })

watch(data, (cat) => {
  if (!cat) return
  if (!isNew.value) {
    const c = cat.custom.find((x) => x.id === props.id)
    if (c) load(c)
    return
  }
  const from = allCreatures(cat).find((x) => x.id === route.query.from) ?? builtinCreatures.find((x) => x.rig !== 'humanoid')!
  load(from, true)
  Object.assign(form, { id: '', idEdited: false, name: route.query.from ? `${from.name} copy` : '' })
}, { immediate: true })
const missing = computed(() => !isNew.value && data.value && !data.value.custom.some((x) => x.id === props.id))
watch(() => form.name, (n) => { if (isNew.value && !form.idEdited) form.id = slugify(n) })

const humanoid = computed(() => form.rig === 'humanoid')
/** the drawing JSON -> joints / face / parts, or an error. A humanoid has none: it is a stickman with a build */
const parsed = computed<{ value?: Pick<CustomCreature, 'joints' | 'face' | 'parts'>; err?: string }>(() => {
  if (humanoid.value) return { value: { joints: {}, face: {}, parts: {} } }
  try {
    const j = JSON.parse(form.drawing)
    if (!j || typeof j !== 'object' || !j.parts?.body) return { err: 'needs "parts" with at least "body"' }
    const spec = rigParts[form.rig].parts
    const bad = Object.keys(j.parts).filter((p) => !(p in spec))
    if (bad.length) return { err: `${bad.join(', ')}: not a ${form.rig} part (parts: ${Object.keys(spec).join(', ')})` }
    const missingParts = Object.entries(spec).filter(([p, need]) => need && !j.parts[p]?.length).map(([p]) => p)
    if (missingParts.length) return { err: `a ${form.rig} needs ${missingParts.join(', ')}` }
    return { value: { joints: j.joints ?? {}, face: j.face ?? {}, parts: j.parts } }
  } catch (e) {
    return { err: `Not valid JSON: ${(e as Error).message}` }
  }
})
const draft = computed<CustomCreature | null>(() => parsed.value.value
  ? { id: form.id || 'draft', name: form.name, rig: form.rig, accent: form.accent, ...parsed.value.value,
      ...(humanoid.value ? { build: { ...form.build } } : {}) } : null)
const taken = computed(() => isBuiltinCreature(form.id) || form.id === 'stickman' || (isNew.value && data.value?.custom.some((c) => c.id === form.id)))
const valid = computed(() => form.name.trim() && /^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.id) && !taken.value && draft.value)

const POSES = ['idle', 'walk', 'run', 'talk', 'eat', 'cheer', 'stagger', 'lie']
// a biped or humanoid lies down like a stickman: the renderer tips the whole card over, so there is no lying drawing
const poses = computed(() => (form.rig === 'biped' || humanoid.value ? POSES.filter((a) => a !== 'lie') : POSES))
const BUILD_SLIDERS = [['head', 'Head size'], ['body_w', 'Body width'], ['body_h', 'Body height'], ['leg', 'Leg length'],
  ['arm', 'Arm length']] as const
const color = ref('#c98a4b')

const saving = ref(false)
async function save() {
  if (!draft.value) return
  saving.value = true
  const body = { ...draft.value, name: form.name.trim() }
  const c = await act(() => api.saveCreature(body), `Creature “${body.name}” saved`)
  saving.value = false
  if (!c) return
  if (c.cleared.length) toast(`Drawing changed: approval cleared for ${c.cleared.join(', ')}. Re-run their cast sheets.`, 'info')
  data.value = c
  if (isNew.value) router.replace(`/creatures/${body.id}`)
}
async function remove() {
  const ok = await confirm({ title: `Delete “${form.name}”?`, body: 'Only possible while no cast member uses it.', confirm: 'Delete creature', danger: true })
  if (ok && (await act(() => api.deleteCreature(props.id), 'Creature deleted'))) router.push('/creatures')
}

const field = 'inset mt-1 block h-10 w-full rounded-md px-4 text-sm text-ink outline-none focus:border-blue'
</script>

<template>
  <div class="max-w-6xl space-y-6">
    <RouterLink to="/creatures" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> All creatures</RouterLink>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading creature" />
    <ErrorCard v-else-if="missing" :message="`No custom creature “${id}”.`" @retry="reload" />
    <form v-else class="raised grid gap-6 p-6 lg:grid-cols-[1fr_360px]" @submit.prevent="save">
      <div class="min-w-0 space-y-5">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="font-display text-3xl font-semibold">{{ isNew ? 'New creature' : form.name || id }}</h2>
          <RouterLink :to="{ path: '/ai-creations', query: { type: 'creature', name: form.name || undefined, id: form.id || undefined, rig: form.rig } }" class="btn btn-secondary ml-auto">
            <Sparkles :size="16" aria-hidden="true" /> Build with AI
          </RouterLink>
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block text-xs font-semibold text-muted">Name
            <input v-model="form.name" required maxlength="40" placeholder="Dog" :class="field" />
          </label>
          <label class="block text-xs font-semibold text-muted">Id (the cast entry's "body")
            <input v-model="form.id" required :readonly="!isNew" pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="dog"
              :class="[field, !isNew && 'opacity-70']" :aria-invalid="!!taken" @input="form.idEdited = true" />
            <span v-if="taken" class="mt-1 block text-red-ink" role="alert">“{{ form.id }}” is already taken</span>
          </label>
          <label class="block text-xs font-semibold text-muted">Rig (how it moves)
            <select v-model="form.rig" :class="field">
              <option v-for="r in RIG_LIST" :key="r" :value="r">{{ r }}</option>
            </select>
            <span class="mt-1 block font-normal">{{ RIG_NOTES[form.rig] }}</span>
          </label>
          <label v-if="humanoid" class="block text-xs font-semibold text-muted">Head colour (skin)
            <input v-model="form.build.head_color" type="color" class="mt-1 block h-11 w-20 cursor-pointer rounded-md" />
          </label>
          <label v-else class="block text-xs font-semibold text-muted">Accent colour ($accent when the cast member has none)
            <input v-model="form.accent" type="color" class="mt-1 block h-11 w-20 cursor-pointer rounded-md" />
          </label>
        </div>

        <fieldset v-if="humanoid" class="grid gap-4 sm:grid-cols-2">
          <legend class="mb-2 text-xs font-semibold text-muted">Build: proportions of the default human (1×)</legend>
          <label v-for="[k, label] in BUILD_SLIDERS" :key="k" class="block text-xs font-semibold text-muted">
            <span class="flex justify-between">{{ label }} <span class="font-mono font-normal">{{ form.build[k].toFixed(2) }}×</span></span>
            <input v-model.number="form.build[k]" type="range" min="0.7" max="1.3" step="0.05" class="mt-2 block w-full" />
          </label>
          <p class="text-xs text-muted sm:col-span-2">A humanoid is a stickman: the cast entry's top, headwear, legwear,
            props, eyes and expressions all apply. A build taller than the card is drawn a little smaller to fit.</p>
        </fieldset>
        <template v-else>
          <label class="block text-xs font-semibold text-muted" for="drawing">Drawing: joints, face and parts (JSON)
            <textarea id="drawing" v-model="form.drawing" rows="22" spellcheck="false" :aria-invalid="!!parsed.err"
              class="inset mt-1 block w-full resize-y rounded-md p-4 font-mono text-xs leading-5 text-ink outline-none focus:border-blue" />
          </label>
          <p v-if="parsed.err" class="text-sm text-red-ink" role="alert">{{ parsed.err }}</p>
          <p class="text-xs text-muted">Side view facing right, y down, the ground at y 0. The body is drawn around the ground
            point; every other part around its joint, at rest (legs hang down to the ground). Fills: <code>$main</code>,
            <code>$accent</code>, or a fixed colour. Easiest: Build with AI, or copy a built-in from the Creatures page.</p>
        </template>

        <div class="flex flex-wrap justify-end gap-2">
          <button v-if="!isNew" type="button" class="btn btn-secondary mr-auto text-red-ink" @click="remove"><Trash2 :size="16" aria-hidden="true" /> Delete</button>
          <button class="btn btn-primary" :disabled="!valid || saving">{{ saving ? 'Saving…' : isNew ? 'Create creature' : 'Save creature' }}</button>
        </div>
      </div>

      <aside class="space-y-3 lg:sticky lg:top-0 lg:self-start">
        <div class="flex items-center justify-between gap-2">
          <h3 class="font-display text-lg font-semibold">Poses</h3>
          <label class="flex items-center gap-2 text-xs text-muted">Colour
            <input v-model="color" type="color" class="h-9 w-12 cursor-pointer rounded-md" aria-label="Preview colour ($main)" />
          </label>
        </div>
        <div v-if="draft" class="grid grid-cols-2 gap-2">
          <figure v-for="a in poses" :key="a">
            <CreaturePreview :creature="draft" :action="a" :color="color" :label="`${form.name || 'Creature'}: ${a}`" class="h-28" />
            <figcaption class="text-center text-xs text-muted">{{ a }}</figcaption>
          </figure>
          <figure v-if="draft.parts.stump">
            <CreaturePreview :creature="draft" headless :color="color" :label="`${form.name || 'Creature'}: headless`" class="h-28" />
            <figcaption class="text-center text-xs text-muted">headless</figcaption>
          </figure>
        </div>
        <p class="text-center text-xs text-muted">Drawn by the render engine: what you see is what renders.</p>
      </aside>
    </form>
  </div>
</template>

<style scoped>
.step-no {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: var(--radius-sm);
  background: var(--color-ink);
  color: var(--on-ink);
  font-size: 0.8125rem;
  font-weight: 700;
}
</style>
