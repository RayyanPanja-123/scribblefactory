<script setup lang="ts">
import { ArrowDown, ArrowLeft, ArrowUp, Plus, Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import SetPreview from '../components/SetPreview.vue'
import { useLibraryEditor } from '../composables/libraryEditor'
import { useApi } from '../composables/useApi'
import { SHAPES, STARTER, type CustomSet, type SetKind, type SetPiece } from '../lib/sets'
import type { ObjectCatalog } from '../lib/objects'

// Create (/sets/new) or edit one custom set: floor, back wall or sky, and a list of primitive pieces in world units,
// previewed live by the engine's own set builder. The server (schema CustomSet) and the engine (stage clearance) have
// the final say.
const props = defineProps<{ id: string }>()
const { data, error, loading, reload } = useApi(() => api.sets())
const { data: objectData } = useApi<ObjectCatalog>(() => api.objects())

const copy = <T,>(v: T): T => JSON.parse(JSON.stringify(v))

type Weather = NonNullable<CustomSet['default_weather']>
const WEATHER = ['clear', 'rain', 'snow', 'fog', 'wind', 'storm'] as const
const INTENSITY = ['light', 'medium', 'heavy'] as const
const form = reactive({ id: '', name: '', use_for: '', idEdited: false, kind: 'indoor' as SetKind, floor: '', back: '', pieces: [] as SetPiece[], objects: [] as NonNullable<CustomSet['objects']>,
  weather: 'clear' as Weather['kind'] | 'clear', intensity: 'medium' as Weather['intensity'] })
function load(s: CustomSet) {
  Object.assign(form, { id: s.id, name: s.name, use_for: s.use_for ?? '', kind: s.kind, floor: s.floor, back: s.back, pieces: copy(s.pieces ?? []), objects: copy(s.objects ?? []),
    weather: s.default_weather?.kind ?? 'clear', intensity: s.default_weather?.intensity ?? 'medium' })
}
const showWeather = ref(true) // preview the default weather over the set
const { isNew, missing, saving, save: saveItem, remove: removeItem } = useLibraryEditor({
  id: () => props.id, base: '/sets', form, custom: () => data.value?.custom })
watch(data, (c) => {
  if (!c) return
  const s = c.custom.find((x) => x.id === props.id)
  if (s) { load(s); form.idEdited = true }
  else if (isNew.value) Object.assign(form, { id: '', name: '', use_for: '', idEdited: false, kind: 'indoor', weather: 'clear', intensity: 'medium', objects: [] }, copy(STARTER.indoor))
}, { immediate: true })

/** a new set: switching kind swaps in that kind's starter until you change a piece */
function setKind(k: SetKind) {
  const untouched = isNew.value && JSON.stringify(form.pieces) === JSON.stringify(STARTER[form.kind].pieces)
  form.kind = k
  if (untouched) Object.assign(form, copy(STARTER[k]))
}

const draft = computed<CustomSet>(() => ({ id: form.id || 'draft', name: form.name, kind: form.kind, floor: form.floor, back: form.back, pieces: form.pieces, objects: form.objects,
  default_weather: form.weather === 'clear' ? null : { kind: form.weather, intensity: form.intensity } }))
const previewList = computed(() => [...(data.value?.custom ?? []).filter((s) => s.id !== draft.value.id), draft.value])
const taken = computed(() => data.value?.builtin.some((b) => b.id === form.id) || (isNew.value && data.value?.custom.some((s) => s.id === form.id)))
const badPiece = (p: SetPiece) => [...p.at, ...p.size].some((v) => typeof v !== 'number' || !Number.isFinite(v) || Math.abs(v) > 80)
  || p.size.some((v) => v < 0)
const valid = computed(() => form.name.trim() && /^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.id) && !taken.value && !form.pieces.some(badPiece))

const addPiece = (shape: SetPiece['shape']) => form.pieces.push(copy(SHAPES[shape].start))
const addObject = (object: string) => form.objects.push({ id: `${object}-${form.objects.length + 1}`, object, at: [0, 0.5, -1.5], visible: true })
const changeShape = (p: SetPiece, shape: SetPiece['shape']) => Object.assign(p, { shape, size: copy(SHAPES[shape].start.size) })
const move = (i: number, d: number) => form.pieces.splice(i + d, 0, ...form.pieces.splice(i, 1))


function save() {
  const body = { ...draft.value, name: form.name.trim(), use_for: form.use_for.trim() || null }
  return saveItem(() => api.saveSet(body), `Set “${body.name}” saved`, body.id, (c) => { data.value = c })
}
const remove = () => removeItem(() => api.deleteSet(props.id), 'set', 'Only possible while no story uses it: change their @set lines first.', 'Set deleted')
const field = 'inset mt-1 block h-10 w-full rounded-md px-4 text-sm text-ink outline-none focus:border-blue'
const num = 'inset mt-1 block h-10 w-full rounded-md px-3 text-sm text-ink outline-none focus:border-blue num'
</script>

<template>
  <div class="space-y-6">
    <RouterLink to="/sets" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> All sets</RouterLink>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading set" />
    <ErrorCard v-else-if="missing" :message="`No custom set “${id}”.`" @retry="reload" />
    <form v-else class="grid items-start gap-6 lg:grid-cols-[1fr_300px]" @submit.prevent="save">
      <div class="raised min-w-0 space-y-5 p-6">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="font-display text-3xl font-semibold">{{ isNew ? 'New set' : form.name || id }}</h2>
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block text-xs font-semibold text-muted">Name
            <input v-model="form.name" required maxlength="40" placeholder="Kitchen" :class="field" />
          </label>
          <label class="block text-xs font-semibold text-muted">Id (used in <code>@set</code>)
            <input v-model="form.id" required :readonly="!isNew" pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="kitchen"
              :class="[field, !isNew && 'opacity-70']" :aria-invalid="!!taken" @input="form.idEdited = true" />
            <span v-if="taken" class="mt-1 block text-red-ink" role="alert">“{{ form.id }}” is already a set</span>
          </label>
          <label class="block text-xs font-semibold text-muted sm:col-span-2">Use for (tells the story AI when to use it)
            <input v-model="form.use_for" maxlength="200" placeholder="ancient Rome: markets, senators, emperors walking by" :class="field" />
          </label>
        </div>

        <div class="flex flex-wrap items-end gap-4">
          <div role="group" aria-label="Kind of set" class="flex gap-2">
            <button v-for="k in (['indoor', 'outdoor'] as const)" :key="k" type="button" class="btn" :class="form.kind === k ? 'btn-primary' : 'btn-secondary'"
              :aria-pressed="form.kind === k" @click="setKind(k)">{{ k }}</button>
          </div>
          <label class="flex items-center gap-2 text-sm">
            <input v-model="form.floor" type="color" class="h-11 w-14 cursor-pointer rounded-md" /> Floor
          </label>
          <label class="flex items-center gap-2 text-sm">
            <input v-model="form.back" type="color" class="h-11 w-14 cursor-pointer rounded-md" /> {{ form.kind === 'indoor' ? 'Back wall' : 'Sky' }}
          </label>
        </div>
        <p class="text-xs text-muted">{{ form.kind === 'indoor'
          ? 'Indoor: a floor and a back wall at z −2.6. No travelling shots.'
          : 'Outdoor: a wide floor and a sky. Walking actors get travelling shots: pieces in x −14…14 wrap around as the world scrolls.' }}</p>

        <div class="flex flex-wrap items-end gap-4">
          <label class="block w-40 text-xs font-semibold text-muted">Default weather
            <select v-model="form.weather" :class="field">
              <option v-for="w in WEATHER" :key="w" :value="w">{{ w }}</option>
            </select>
          </label>
          <label class="block w-40 text-xs font-semibold text-muted">Intensity
            <select v-model="form.intensity" :class="field" :disabled="form.weather === 'clear'">
              <option v-for="i in INTENSITY" :key="i" :value="i">{{ i }}</option>
            </select>
          </label>
        </div>
        <p class="text-xs text-muted">Every <code>@set</code> of this set starts with this weather, until an <code>@weather</code> line changes it.</p>

        <fieldset class="space-y-3">
          <legend class="font-display text-lg font-semibold">World Objects</legend>
          <p class="text-xs text-muted">Named objects can later be targeted by interactions such as stealing, carrying or removing them.</p>
          <div v-for="(o, i) in form.objects" :key="o.id" class="inset grid gap-2 rounded-md p-3 sm:grid-cols-[1fr_1fr_auto]">
            <label class="text-xs font-semibold text-muted">Object
              <select v-model="o.object" :class="field"><option v-for="x in objectData?.objects ?? []" :key="x.id" :value="x.id">{{ x.name }}</option></select>
            </label>
            <div class="grid grid-cols-3 gap-2"><label v-for="axis in ['x', 'y', 'z']" :key="axis" class="text-xs font-semibold text-muted">{{ axis }}<input v-model.number="o.at[['x','y','z'].indexOf(axis)]" type="number" step="any" :class="num" /></label></div>
            <button type="button" class="btn btn-secondary self-end text-red-ink" @click="form.objects.splice(i, 1)"><Trash2 :size="16" /> Remove</button>
          </div>
          <select v-if="objectData?.objects.length" class="btn btn-secondary" @change="($event.target as HTMLSelectElement).value && addObject(($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''">
            <option value="">Add World Object…</option><option v-for="x in objectData.objects" :key="x.id" :value="x.id">{{ x.name }}</option>
          </select>
          <p v-else class="text-xs text-muted">Create a reusable object on the World Objects page first.</p>
        </fieldset>

        <fieldset class="space-y-3">
          <legend class="font-display text-lg font-semibold">Pieces</legend>
          <p class="text-xs text-muted">World units (about metres). Actors stand on z 0 between x −2 and 2, about 1.6 tall. Anything across
            x −2.2…2.2 must sit behind z −1, and nothing may come forward of z 0.6: the preview says so if a piece breaks this.
            “at” is the piece's centre. Backdrop pieces are never hidden behind an actor.</p>
          <div v-for="(p, i) in form.pieces" :key="i" class="inset space-y-2 rounded-md p-3">
            <div class="grid items-end gap-2 sm:grid-cols-[8rem_1fr_auto]">
              <label class="block text-xs font-semibold text-muted">Shape
                <select :value="p.shape" :class="field" @change="changeShape(p, ($event.target as HTMLSelectElement).value as SetPiece['shape'])">
                  <option v-for="(s, k) in SHAPES" :key="k" :value="k">{{ s.label }}</option>
                </select>
              </label>
              <div class="grid grid-cols-3 gap-2">
                <label v-for="(axis, a) in ['x', 'y', 'z']" :key="axis" class="block text-xs font-semibold text-muted">{{ axis }}
                  <input v-model.number="p.at[a]" type="number" step="any" :class="num" />
                </label>
              </div>
              <div class="flex gap-1">
                <button type="button" class="btn btn-secondary size-11 justify-center p-0" :disabled="i === 0" :aria-label="`Move piece ${i + 1} up (drawn earlier)`" @click="move(i, -1)"><ArrowUp :size="16" aria-hidden="true" /></button>
                <button type="button" class="btn btn-secondary size-11 justify-center p-0" :disabled="i === form.pieces.length - 1" :aria-label="`Move piece ${i + 1} down (drawn later)`" @click="move(i, 1)"><ArrowDown :size="16" aria-hidden="true" /></button>
                <button type="button" class="btn btn-secondary size-11 justify-center p-0" :aria-label="`Remove piece ${i + 1}`" @click="form.pieces.splice(i, 1)"><Trash2 :size="16" aria-hidden="true" /></button>
              </div>
            </div>
            <div class="flex flex-wrap items-end gap-3">
              <label v-for="(what, k) in SHAPES[p.shape].size" :key="what" class="block w-28 text-xs font-semibold text-muted">{{ what }}
                <input v-model.number="p.size[k]" type="number" step="any" min="0" max="80" :class="num" />
              </label>
              <input v-model="p.color" type="color" :aria-label="`Colour of piece ${i + 1}`" class="h-11 w-14 cursor-pointer rounded-md" />
              <label class="flex h-11 items-center gap-2 text-sm"><input :checked="!!p.backdrop" type="checkbox" class="size-4"
                @change="p.backdrop = ($event.target as HTMLInputElement).checked" /> Backdrop</label>
              <label class="flex h-11 items-center gap-2 text-sm"><input :checked="p.outline !== false" type="checkbox" class="size-4"
                @change="p.outline = ($event.target as HTMLInputElement).checked" /> Outline</label>
            </div>
            <p v-if="badPiece(p)" class="text-xs text-red-ink" role="alert">numbers within −80…80, sizes not negative</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button v-for="(s, k) in SHAPES" :key="k" type="button" class="btn btn-secondary" :disabled="form.pieces.length >= 60" @click="addPiece(k)"><Plus :size="16" aria-hidden="true" /> {{ s.label }}</button>
          </div>
        </fieldset>

        <div class="flex flex-wrap justify-end gap-2">
          <button v-if="!isNew" type="button" class="btn btn-secondary mr-auto text-red-ink" @click="remove"><Trash2 :size="16" aria-hidden="true" /> Delete</button>
          <button class="btn btn-primary" :disabled="!valid || saving">{{ saving ? 'Saving…' : isNew ? 'Create set' : 'Save set' }}</button>
        </div>
      </div>

      <aside class="raised p-6 space-y-3 lg:sticky lg:top-0 lg:self-start">
        <SetPreview :id="draft.id" :custom="previewList" :weather="showWeather ? draft.default_weather : null"
          :label="`Preview of ${form.name || 'the set'}`" class="aspect-[9/16] w-full" />
        <label v-if="draft.default_weather" class="flex h-11 items-center justify-center gap-2 text-sm">
          <input v-model="showWeather" type="checkbox" class="size-4" /> Preview weather ({{ form.weather }}, {{ form.intensity }})
        </label>
        <p class="text-center text-xs text-muted">Built by the render engine through its wide camera. The grey figures show where actors stand.</p>
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
