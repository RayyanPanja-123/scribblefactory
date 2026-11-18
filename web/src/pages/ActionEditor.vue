<script setup lang="ts">
import { ArrowLeft, ClipboardPaste, Copy, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CustomAction } from '../api/client'
import ActionPreview from '../components/ActionPreview.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { useAutoAi } from '../composables/autoAi'
import { act, confirm, toast } from '../composables/feedback'
import { useApi } from '../composables/useApi'
import { buildActionPrompt, importAction } from '../lib/actionPrompt'

// Create (/actions/new) or edit one custom action: keyframes of arm, leg and lean angles the stickman blends between,
// previewed live by the engine's own code. Angles in degrees on the front view, from straight down, + toward screen
// right. The server (schema CustomAction) has the final say.
const props = defineProps<{ id: string }>()
const router = useRouter()
const isNew = computed(() => props.id === 'new')
const { data, error, loading, reload } = useApi(() => api.actions())

type Key = { t: number; arms: [[number, number], [number, number]] | null; legs: [number, number] | null; lean: number }
const REST = { arms: [[-16, 0], [16, 0]] as [[number, number], [number, number]], legs: [-6, 6] as [number, number] }
const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
const STARTER: Key[] = [ // a wave hello: rest, the right arm up, back down
  { t: 0, arms: null, legs: null, lean: 0 },
  { t: 0.4, arms: [[-16, 0], [140, 40]], legs: null, lean: 2 },
  { t: 1, arms: null, legs: null, lean: 0 },
]
const form = reactive({ id: '', name: '', idEdited: false, duration: 1.5, loop: true, facing: 'camera' as 'camera' | 'side', move: 0, keys: structuredClone(STARTER) })

watch(data, (cat) => {
  if (!cat || isNew.value) return
  const a = cat.custom.find((x) => x.id === props.id)
  if (a) Object.assign(form, { id: a.id, name: a.name, idEdited: true, duration: a.duration, loop: a.loop ?? true, facing: a.facing ?? 'camera', move: a.move ?? 0,
    keys: a.keys.map((k) => ({ t: k.t, arms: k.arms ?? null, legs: k.legs ?? null, lean: k.lean ?? 0 })) })
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
    legs: last?.legs ? [...last.legs] as [number, number] : null, lean: last?.lean ?? 0 })
}
const toggle = (k: Key, part: 'arms' | 'legs') => { k[part] = (k[part] ? null : structuredClone(REST[part])) as never }

const saving = ref(false)
async function save() {
  saving.value = true
  const body = { ...draft.value, name: form.name.trim() }
  const c = await act(() => api.saveAction(body), `Action “${body.name}” saved`)
  saving.value = false
  if (c && isNew.value) router.replace(`/actions/${body.id}`)
}
async function remove() {
  const ok = await confirm({ title: `Delete “${form.name}”?`, body: 'Only possible while no story uses it in @do.', confirm: 'Delete action', danger: true })
  if (ok && (await act(() => api.deleteAction(props.id), 'Action deleted'))) router.push('/actions')
}
// ---- build with AI: a prompt to paste into any AI chat, then its JSON reply loads into the editor ----
const aiOpen = ref(useRoute().hash === '#ai')
const aiWhat = ref('')
const aiDetails = ref('')
// the id the AI must use: this one's own, or one typed in the id field (e.g. the id a story already uses)
const aiId = computed(() => (!isNew.value || form.idEdited ? form.id : '') || slugify(aiWhat.value))
const aiPrompt = ref('')
const aiReply = ref('')
const aiError = ref('')
const promptBox = ref<HTMLTextAreaElement>()
function makePrompt() {
  const c = data.value
  aiPrompt.value = buildActionPrompt(aiWhat.value, [...(c?.builtin ?? []), ...(c?.custom ?? []).map((a) => a.id)].filter((x) => x !== props.id),
    aiDetails.value, aiId.value)
}
async function copyPrompt() {
  try {
    await navigator.clipboard.writeText(aiPrompt.value)
    toast('Prompt copied: paste it into your AI', 'ok')
  } catch {
    promptBox.value?.select() // no clipboard access (plain http): select it for Ctrl+C
    toast('Could not copy: the prompt is selected, press Ctrl+C', 'error')
  }
}
async function pasteReply() {
  try {
    aiReply.value = await navigator.clipboard.readText()
  } catch {
    document.getElementById('ai-reply')?.focus() // no clipboard read access: paste with Ctrl+V
    toast('Could not read the clipboard: press Ctrl+V in the box', 'error')
  }
}
function loadReply() {
  const { action, error: err } = importAction(aiReply.value)
  aiError.value = err ?? ''
  if (!action) return
  Object.assign(form, { name: action.name, duration: action.duration, loop: action.loop ?? true, facing: action.facing ?? 'camera', move: action.move ?? 0, keys: action.keys as Key[] })
  if (isNew.value) Object.assign(form, { id: action.id, idEdited: true })
  aiReply.value = ''
  scrub.value = undefined
  toast(`Loaded ${action.keys.length} keys: watch the preview, then ${isNew.value ? 'create' : 'save'} the action`, 'ok')
}
// with an API key in Settings: prompt -> AI -> reply -> editor in one click; the reply stays in step 3 if it doesn't load
const { auto, busy, generate, label } = useAutoAi()
async function generateReply() {
  makePrompt()
  const text = await generate(aiPrompt.value)
  if (text === undefined) return
  aiReply.value = text
  loadReply()
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
          <button type="button" class="btn btn-secondary ml-auto" :aria-expanded="aiOpen" aria-controls="ai-build" @click="aiOpen = !aiOpen">
            <Sparkles :size="16" aria-hidden="true" /> Build with AI
          </button>
        </div>

        <section v-if="aiOpen" id="ai-build" class="inset rounded-md p-4" aria-label="Build with AI">
          <p class="pb-4 text-xs text-muted">Three steps. The result loads into this editor, so you watch the preview before saving.</p>
          <ol class="divide-y divide-rule">
            <!-- 1: what to build -->
            <li class="flex gap-3 pb-5">
              <span class="step-no" aria-hidden="true">1</span>
              <div class="min-w-0 flex-1 space-y-2">
                <h3 class="font-semibold">Say what to build</h3>
                <label class="block text-sm font-semibold" for="ai-what">Move
                  <input id="ai-what" v-model="aiWhat" placeholder="Salute, bow, facepalm, disco dance, clap…" maxlength="40" :class="field"
                    @keydown.enter.prevent="aiWhat.trim() && (auto ? generateReply() : makePrompt())" />
                </label>
                <p v-if="aiId" class="text-xs text-muted">Saved as <code>{{ aiId }}</code>. A story needs a different id? Set it in the id field below first.</p>
                <label class="block text-sm font-semibold" for="ai-details">Details <span class="font-normal text-muted">(optional)</span>
                  <textarea id="ai-details" v-model="aiDetails" rows="3" placeholder="Which arm, how fast, loops or plays once…"
                    class="inset mt-1 block w-full rounded-md px-4 py-2 text-sm text-ink outline-none focus:border-blue" />
                </label>
                <div class="flex flex-wrap items-center gap-2">
                  <template v-if="auto">
                    <button type="button" class="btn btn-primary" :disabled="!aiWhat.trim() || busy" :aria-busy="busy" @click="generateReply">
                      <Sparkles :size="16" aria-hidden="true" /> {{ label }}</button>
                    <button type="button" class="btn btn-secondary" :disabled="!aiWhat.trim() || busy" @click="makePrompt">Prompt only</button>
                  </template>
                  <template v-else>
                    <button type="button" class="btn btn-primary" :disabled="!aiWhat.trim()" @click="makePrompt">Prompt for AI</button>
                    <RouterLink to="/settings" class="text-xs text-muted underline">Add an API key in Settings to skip copy/paste</RouterLink>
                  </template>
                </div>
              </div>
            </li>
            <!-- 2: the prompt, read-only: goes OUT to the AI -->
            <li class="flex gap-3 py-5" :class="!aiPrompt && 'opacity-50'">
              <span class="step-no" aria-hidden="true">2</span>
              <div class="min-w-0 flex-1 space-y-2">
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="font-semibold">Copy the prompt into your AI</h3>
                  <button type="button" class="btn btn-secondary ml-auto" :disabled="!aiPrompt" @click="copyPrompt"><Copy :size="16" aria-hidden="true" /> Copy prompt</button>
                </div>
                <p class="text-xs text-muted">ChatGPT, Claude, Gemini, a CLI… any of them. Don't edit this: it's read-only.</p>
                <template v-if="aiPrompt">
                  <label class="sr-only" for="ai-prompt">Prompt for AI (read-only)</label>
                  <textarea id="ai-prompt" ref="promptBox" :value="aiPrompt" readonly rows="6" spellcheck="false"
                    class="block w-full resize-y rounded-md border border-rule bg-well p-4 font-mono text-xs leading-5 text-muted outline-none focus:border-blue" />
                </template>
              </div>
            </li>
            <!-- 3: the AI's reply: comes IN from the AI -->
            <li class="flex gap-3 pt-5">
              <span class="step-no" aria-hidden="true">3</span>
              <div class="min-w-0 flex-1 space-y-2">
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="font-semibold"><label for="ai-reply">Paste the AI's JSON reply here</label></h3>
                  <button type="button" class="btn btn-secondary ml-auto" @click="pasteReply"><ClipboardPaste :size="16" aria-hidden="true" /> Paste</button>
                </div>
                <p class="text-xs text-muted">The JSON block, or its whole message: the JSON is picked out of it.</p>
                <textarea id="ai-reply" v-model="aiReply" rows="6" spellcheck="false"
                  placeholder='Paste here, e.g.&#10;```json&#10;{"id": "bow", "name": "Bow", "duration": 1.5, "keys": [...]}&#10;```'
                  class="paper block w-full resize-y rounded-md border-2 border-dashed p-4 font-mono text-xs leading-5 text-ink outline-none focus:border-blue focus:border-solid"
                  :class="aiError ? 'border-red-ink' : 'border-blue-ink/60'" :aria-invalid="!!aiError" />
                <p v-if="aiError" class="text-sm text-red-ink" role="alert">{{ aiError }}</p>
                <div class="flex justify-end">
                  <button type="button" class="btn btn-primary" :disabled="!aiReply.trim()" @click="loadReply">Load into editor</button>
                </div>
              </div>
            </li>
          </ol>
        </section>
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block text-xs font-semibold text-muted">Name
            <input v-model="form.name" required maxlength="40" placeholder="Salute" :class="field" />
          </label>
          <label class="block text-xs font-semibold text-muted">Id (what @do uses)
            <input v-model="form.id" required :readonly="!isNew" pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="salute"
              :class="[field, !isNew && 'opacity-70']" :aria-invalid="taken" @input="form.idEdited = true" />
            <span v-if="taken" class="mt-1 block text-red-ink" role="alert">“{{ form.id }}” is already taken</span>
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
          right, 180 straight up (the left arm rests at −16, the right at +16). Bend turns the forearm. Legs rest at −6 / +6; the
          feet stay on the ground. A key without arms or legs keeps them at rest. The engine eases between keys in time order.</p>
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
                  <input v-model.number="k.legs[s]" type="range" min="-45" max="45" step="1" class="mt-1 block w-full" @input="scrub = k.t" />
                </label>
              </template>
              <label class="block text-xs font-semibold text-muted">
                <span class="flex justify-between">Lean <span class="font-mono font-normal">{{ k.lean }}°</span></span>
                <input v-model.number="k.lean" type="range" min="-30" max="30" step="1" class="mt-1 block w-full" @input="scrub = k.t" />
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
