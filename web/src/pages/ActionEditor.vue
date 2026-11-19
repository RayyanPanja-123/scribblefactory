<script setup lang="ts">
import { ArrowLeft, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, type CustomAction } from '../api/client'
import ActionPreview from '../components/ActionPreview.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { act, confirm } from '../composables/feedback'
import { useApi } from '../composables/useApi'


// Create (/actions/new) or edit one custom action: keyframes of arm, leg and lean angles the stickman blends between,
// previewed live by the engine's own code. Angles in degrees on the front view, from straight down, + toward screen
// right. The server (schema CustomAction) has the final say.
const props = defineProps<{ id: string }>()
const router = useRouter()
const isNew = computed(() => props.id === 'new')
const { data, error, loading, reload } = useApi(() => api.actions())

type Key = { t: number; arms: [[number, number], [number, number]] | null; legs: [number, number] | null; knees?: [number, number] | null; lean: number }
const REST = { arms: [[-16, 0], [16, 0]] as [[number, number], [number, number]], legs: [-6, 6] as [number, number] }
const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
const STARTER: Key[] = [ // a wave hello: rest, the right arm up, back down
  { t: 0, arms: null, legs: null, lean: 0 },
  { t: 0.4, arms: [[-16, 0], [140, 40]], legs: null, lean: 2 },
  { t: 1, arms: null, legs: null, lean: 0 },
]
const form = reactive({ id: '', name: '', use_for: '', idEdited: false, duration: 1.5, loop: true, facing: 'camera' as 'camera' | 'side', move: 0, keys: structuredClone(STARTER) })

watch(data, (cat) => {
  if (!cat || isNew.value) return
  const a = cat.custom.find((x) => x.id === props.id)
  if (a) Object.assign(form, { id: a.id, name: a.name, use_for: a.use_for ?? '', idEdited: true, duration: a.duration, loop: a.loop ?? true, facing: a.facing ?? 'camera', move: a.move ?? 0,
    keys: a.keys.map((k) => ({ t: k.t, arms: k.arms ?? null, legs: k.legs ?? null, knees: k.knees ?? (k.legs ? [0, 0] : null), lean: k.lean ?? 0 })) })
}, { immediate: true })
const missing = computed(() => !isNew.value && data.value && !data.value.custom.some((x) => x.id === props.id))
watch(() => form.name, (n) => { if (isNew.value && !form.idEdited) form.id = slugify(n) })

const sorted = computed(() => [...form.keys].sort((a, b) => a.t - b.t))
const draft = computed<CustomAction>(() => ({ id: form.id || 'draft', name: form.name || 'Draft', duration: form.duration,
  loop: form.loop, facing: form.facing, move: form.move, keys: sorted.value }))
const taken = computed(() => !!data.value && (data.value.builtin.includes(form.id) || (isNew.value && data.value.custom.some((a) => a.id === form.id))))
const valid = computed(() => form.name.trim() && /^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.id) && !taken.value && form.keys.length)

// preview: play it, or hold the moment the timeline slider picks
const scrub = ref<number | undefined>(undefined)
const color = ref('#3a7bd5')

function addKey() {
  const last = sorted.value.at(-1)
  form.keys.push({ t: Math.min(1, +((last?.t ?? 0) + 0.25).toFixed(2)), arms: last?.arms ? structuredClone(last.arms) : null,
    legs: last?.legs ? [...last.legs] as [number, number] : null, knees: last?.knees ? [...last.knees] as [number, number] : null, lean: last?.lean ?? 0 })
}
const toggle = (k: Key, part: 'arms' | 'legs') => {
  k[part] = (k[part] ? null : structuredClone(REST[part])) as never
  if (part === 'legs') k.knees = k.legs ? [0, 0] : null // knees come with the legs
}

const saving = ref(false)
async function save() {
  saving.value = true
  const body = { ...draft.value, name: form.name.trim(), use_for: form.use_for.trim() || null }
  const c = await act(() => api.saveAction(body), `Action “${body.name}” saved`)
  saving.value = false
  if (c && isNew.value) router.replace(`/actions/${body.id}`)
}
async function remove() {
  const ok = await confirm({ title: `Delete “${form.name}”?`, body: 'Only possible while no story uses it in @do.', confirm: 'Delete action', danger: true })
  if (ok && (await act(() => api.deleteAction(props.id), 'Action deleted'))) router.push('/actions')
}
const field = 'inset mt-1 block h-10 w-full rounded-md px-3 text-sm text-ink outline-none focus:border-blue'
const ARM_SLIDERS = [[0, 0, 'Left arm'], [0, 1, 'Left bend'], [1, 0, 'Right arm'], [1, 1, 'Right bend']] as const
</script>

<template>
  <div class="max-w-6xl space-y-6">
    <RouterLink to="/actions" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> All actions</RouterLink>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading action" />
    <ErrorCard v-else-if="missing" :message="`No custom action “${id}”.`" @retry="reload" />
    <form v-else class="raised grid gap-6 p-6 lg:grid-cols-[1fr_300px]" @submit.prevent="save">
      <div class="min-w-0 space-y-5">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="font-display text-3xl font-semibold">{{ isNew ? 'New action' : form.name || id }}</h2>
          <RouterLink :to="{ path: '/ai-creations', query: { type: 'action', name: form.name || undefined, id: form.id || undefined } }" class="btn btn-secondary ml-auto">
            <Sparkles :size="16" aria-hidden="true" /> Build with AI
          </RouterLink>
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block text-xs font-semibold text-muted">Name
            <input v-model="form.name" required maxlength="40" placeholder="Salute" :class="field" />
          </label>
          <label class="block text-xs font-semibold text-muted">Id (what @do uses)
            <input v-model="form.id" required :readonly="!isNew" pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="salute"
              :class="[field, !isNew && 'opacity-70']" :aria-invalid="taken" @input="form.idEdited = true" />
            <span v-if="taken" class="mt-1 block text-red-ink" role="alert">“{{ form.id }}” is already taken</span>
          </label>
          <label class="block text-xs font-semibold text-muted sm:col-span-2">Use for (tells the story AI when to use it)
            <input v-model="form.use_for" maxlength="200" placeholder="a god or king showing power, right before lightning" :class="field" />
          </label>
          <label class="block text-xs font-semibold text-muted">Duration (seconds for one pass)
            <input v-model.number="form.duration" type="number" min="0.2" max="10" step="0.1" required :class="field" />
          </label>
          <fieldset class="text-xs font-semibold text-muted">
            <legend>Timing</legend>
            <div class="mt-3 flex gap-4 text-sm font-normal text-ink">
              <label class="flex items-center gap-2"><input v-model="form.loop" type="radio" :value="true" /> Loop for the whole shot</label>
              <label class="flex items-center gap-2"><input v-model="form.loop" type="radio" :value="false" /> Play once, hold the end</label>
            </div>
          </fieldset>
          <fieldset class="text-xs font-semibold text-muted">
            <legend>Facing</legend>
            <div class="mt-3 flex flex-wrap gap-4 text-sm font-normal text-ink">
              <label class="flex items-center gap-2"><input v-model="form.facing" type="radio" value="camera" /> Face camera</label>
              <label class="flex items-center gap-2"><input v-model="form.facing" type="radio" value="side" /> Face sideways</label>
            </div>
          </fieldset>
          <label class="block text-xs font-semibold text-muted">Move speed (units/second)
            <input v-model.number="form.move" type="number" min="-2.5" max="2.5" step="0.1" :disabled="form.facing !== 'side'" :class="field" />
            <span class="mt-1 block font-normal">Positive moves forward; negative glides backward. Use 0 to stay in place.</span>
          </label>
        </div>

        <div class="flex items-center justify-between gap-2">
          <h3 class="font-display text-lg font-semibold">Keyframes</h3>
          <button type="button" class="btn btn-secondary" :disabled="form.keys.length >= 40" @click="addKey"><Plus :size="16" aria-hidden="true" /> Add key</button>
        </div>
        <p class="text-xs text-muted">Angles in degrees from straight down, + toward screen right: an arm at 0 hangs, 90 points
          right, 180 straight up (the left arm rests at −16, the right at +16). Bend turns the forearm (the elbow; facing sideways both bends are 0 or more, an elbow only bends forward). Legs rest at −6 / +6; the
          feet stay on the ground. Knee bends the shin back (0 straight, 90 a right angle); with bent knees, lean bends at the
          hips. Face sideways for these: a one-knee kneel is legs 0 / 90, knees 90 / 90; a deep squat is legs 85 / 85,
          knees 160 / 160, and with lean 40 the front hand reaches the ground. A key without arms or legs keeps them at rest. The engine eases between keys in time order.</p>
        <ol class="space-y-3">
          <li v-for="(k, i) in form.keys" :key="i" class="inset space-y-3 rounded-md p-4">
            <div class="flex flex-wrap items-end gap-3">
              <label class="block w-28 text-xs font-semibold text-muted">Time (0–1)
                <input v-model.number="k.t" type="number" min="0" max="1" step="0.05" :class="field" />
              </label>
              <label class="flex h-10 items-center gap-2 text-sm"><input type="checkbox" :checked="!!k.arms" @change="toggle(k, 'arms')" /> Arms</label>
              <label class="flex h-10 items-center gap-2 text-sm"><input type="checkbox" :checked="!!k.legs" @change="toggle(k, 'legs')" /> Legs</label>
              <button type="button" class="btn btn-secondary" @click="scrub = k.t">Show</button>
              <button type="button" class="btn btn-secondary ml-auto text-red-ink" :disabled="form.keys.length < 2" :aria-label="`Remove key ${i + 1}`" @click="form.keys.splice(i, 1)"><Trash2 :size="16" aria-hidden="true" /></button>
            </div>
            <div class="grid gap-x-4 gap-y-2 sm:grid-cols-2">
              <template v-if="k.arms">
                <label v-for="[s, j, label] in ARM_SLIDERS" :key="label" class="block text-xs font-semibold text-muted">
                  <span class="flex justify-between">{{ label }} <span class="font-mono font-normal">{{ k.arms[s][j] }}°</span></span>
                  <input v-model.number="k.arms[s][j]" type="range" min="-180" max="180" step="1" class="mt-1 block w-full" @input="scrub = k.t" />
                </label>
              </template>
              <template v-if="k.legs">
                <label v-for="(label, s) in ['Left leg', 'Right leg']" :key="label" class="block text-xs font-semibold text-muted">
                  <span class="flex justify-between">{{ label }} <span class="font-mono font-normal">{{ k.legs[s] }}°</span></span>
                  <input v-model.number="k.legs[s]" type="range" min="-90" max="90" step="1" class="mt-1 block w-full" @input="scrub = k.t" />
                </label>
                <label v-for="(label, s) in ['Left knee', 'Right knee']" :key="label" class="block text-xs font-semibold text-muted">
                  <span class="flex justify-between">{{ label }} <span class="font-mono font-normal">{{ k.knees?.[s] ?? 0 }}°</span></span>
                  <input :value="k.knees?.[s] ?? 0" type="range" min="0" max="170" step="1" class="mt-1 block w-full"
                    @input="(k.knees ??= [0, 0])[s] = +($event.target as HTMLInputElement).value; scrub = k.t" />
                </label>
              </template>
              <label class="block text-xs font-semibold text-muted">
                <span class="flex justify-between">Lean <span class="font-mono font-normal">{{ k.lean }}°</span></span>
                <input v-model.number="k.lean" type="range" min="-60" max="60" step="1" class="mt-1 block w-full" @input="scrub = k.t" />
              </label>
            </div>
          </li>
        </ol>

        <div class="flex flex-wrap justify-end gap-2">
          <button v-if="!isNew" type="button" class="btn btn-secondary mr-auto text-red-ink" @click="remove"><Trash2 :size="16" aria-hidden="true" /> Delete</button>
          <button class="btn btn-primary" :disabled="!valid || saving">{{ saving ? 'Saving…' : isNew ? 'Create action' : 'Save action' }}</button>
        </div>
      </div>

      <aside class="space-y-3 lg:sticky lg:top-0 lg:self-start">
        <div class="flex items-center justify-between gap-2">
          <h3 class="font-display text-lg font-semibold">Preview</h3>
          <label class="flex items-center gap-2 text-xs text-muted">Colour
            <input v-model="color" type="color" class="h-9 w-12 cursor-pointer rounded-md" aria-label="Preview colour" />
          </label>
        </div>
        <ActionPreview :action="draft" :at="scrub === undefined ? undefined : scrub * form.duration" :color="color"
          :label="`${form.name || 'Action'} preview`" class="h-80" />
        <label class="block text-xs font-semibold text-muted">
          <span class="flex justify-between">Timeline <span class="font-mono font-normal">{{ scrub === undefined ? 'playing' : scrub.toFixed(2) }}</span></span>
          <input type="range" min="0" max="1" step="0.01" :value="scrub ?? 0" class="mt-1 block w-full" @input="scrub = +($event.target as HTMLInputElement).value" />
        </label>
        <button type="button" class="btn btn-secondary w-full justify-center" :disabled="scrub === undefined" @click="scrub = undefined">Play</button>
        <p class="text-center text-xs text-muted">Drawn by the render engine: what you see is what renders.</p>
      </aside>
    </form>
  </div>
</template>

<style scoped>
/* step number: a small ink tab, like a numbered X-sheet column (as in PropEditor) */
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
