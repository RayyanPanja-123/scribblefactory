<script setup lang="ts">
import { ArrowDown, ArrowLeft, ArrowUp, ClipboardPaste, Copy, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import SetPreview from '../components/SetPreview.vue'
import { act, confirm, toast } from '../composables/feedback'
import { useApi } from '../composables/useApi'
import { buildSetPrompt, importSet } from '../lib/setPrompt'
import { SHAPES, STARTER, type CustomSet, type SetKind, type SetPiece } from '../lib/sets'

// Create (/sets/new) or edit one custom set: floor, back wall or sky, and a list of primitive pieces in world units,
// previewed live by the engine's own set builder. The server (schema CustomSet) and the engine (stage clearance) have
// the final say.
const props = defineProps<{ id: string }>()
const router = useRouter()
const isNew = computed(() => props.id === 'new')
const { data, error, loading, reload } = useApi(() => api.sets())

const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
const copy = <T,>(v: T): T => JSON.parse(JSON.stringify(v))

const form = reactive({ id: '', name: '', idEdited: false, kind: 'indoor' as SetKind, floor: '', back: '', pieces: [] as SetPiece[] })
function load(s: CustomSet) {
  Object.assign(form, { id: s.id, name: s.name, kind: s.kind, floor: s.floor, back: s.back, pieces: copy(s.pieces ?? []) })
}
watch(data, (c) => {
  if (!c) return
  const s = c.custom.find((x) => x.id === props.id)
  if (s) { load(s); form.idEdited = true }
  else if (isNew.value) Object.assign(form, { id: '', name: '', idEdited: false, kind: 'indoor' }, copy(STARTER.indoor))
}, { immediate: true })
const missing = computed(() => !isNew.value && data.value && !data.value.custom.some((x) => x.id === props.id))
watch(() => form.name, (n) => { if (isNew.value && !form.idEdited) form.id = slugify(n) })

/** a new set: switching kind swaps in that kind's starter until you change a piece */
function setKind(k: SetKind) {
  const untouched = isNew.value && JSON.stringify(form.pieces) === JSON.stringify(STARTER[form.kind].pieces)
  form.kind = k
  if (untouched) Object.assign(form, copy(STARTER[k]))
}

const draft = computed<CustomSet>(() => ({ id: form.id || 'draft', name: form.name, kind: form.kind, floor: form.floor, back: form.back, pieces: form.pieces }))
const previewList = computed(() => [...(data.value?.custom ?? []).filter((s) => s.id !== draft.value.id), draft.value])
const taken = computed(() => data.value?.builtin.some((b) => b.id === form.id) || (isNew.value && data.value?.custom.some((s) => s.id === form.id)))
const badPiece = (p: SetPiece) => [...p.at, ...p.size].some((v) => typeof v !== 'number' || !Number.isFinite(v) || Math.abs(v) > 80)
  || p.size.some((v) => v < 0)
const valid = computed(() => form.name.trim() && /^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.id) && !taken.value && !form.pieces.some(badPiece))

const addPiece = (shape: SetPiece['shape']) => form.pieces.push(copy(SHAPES[shape].start))
const changeShape = (p: SetPiece, shape: SetPiece['shape']) => Object.assign(p, { shape, size: copy(SHAPES[shape].start.size) })
const move = (i: number, d: number) => form.pieces.splice(i + d, 0, ...form.pieces.splice(i, 1))

const saving = ref(false)
async function save() {
  saving.value = true
  const body = { ...draft.value, name: form.name.trim() }
  const c = await act(() => api.saveSet(body), `Set “${body.name}” saved`)
  saving.value = false
  if (!c) return
  data.value = c
  if (isNew.value) router.replace(`/sets/${body.id}`)
}
async function remove() {
  const ok = await confirm({ title: `Delete “${form.name}”?`, body: 'Only possible while no story uses it: change their @set lines first.', confirm: 'Delete set', danger: true })
  if (ok && (await act(() => api.deleteSet(props.id), 'Set deleted'))) router.push('/sets')
}

// ---- build with AI: a prompt to paste into any AI chat, then its JSON reply loads into the editor ----
const aiOpen = ref(useRoute().hash === '#ai')
const aiWhat = ref('')
const aiPrompt = ref('')
const aiReply = ref('')
const aiError = ref('')
const promptBox = ref<HTMLTextAreaElement>()
function makePrompt() {
  const c = data.value
  aiPrompt.value = buildSetPrompt(aiWhat.value, [...(c?.builtin ?? []).map((b) => b.id), ...(c?.custom ?? []).map((s) => s.id)].filter((x) => x !== props.id))
}
async function copyPrompt() {
  try {
    await navigator.clipboard.writeText(aiPrompt.value)
    toast('Prompt copied: paste it into your AI', 'ok')
  } catch {
    promptBox.value?.select()
    toast('Could not copy: the prompt is selected, press Ctrl+C', 'error')
  }
}
async function pasteReply() {
  try {
    aiReply.value = await navigator.clipboard.readText()
  } catch {
    document.getElementById('ai-reply')?.focus()
    toast('Could not read the clipboard: press Ctrl+V in the box', 'error')
  }
}
function loadReply() {
  const { set, error: err } = importSet(aiReply.value)
  aiError.value = err ?? ''
  if (!set) return
  const id = form.id
  load(set)
  if (isNew.value) form.idEdited = true
  else form.id = id // an existing set keeps its name
  aiReply.value = ''
  toast(`Loaded ${set.pieces?.length ?? 0} pieces: check the preview, then ${isNew.value ? 'create' : 'save'} the set`, 'ok')
}
const field = 'inset mt-1 block h-11 w-full rounded-full px-4 text-sm text-ink outline-none'
const num = 'inset mt-1 block h-11 w-full rounded-full px-3 text-sm text-ink outline-none num'
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-6">
    <RouterLink to="/sets" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> All sets</RouterLink>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading set" />
    <ErrorCard v-else-if="missing" :message="`No custom set “${id}”.`" @retry="reload" />
    <form v-else class="raised grid gap-6 p-6 lg:grid-cols-[1fr_300px]" @submit.prevent="save">
      <div class="min-w-0 space-y-5">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="font-display text-3xl font-semibold">{{ isNew ? 'New set' : form.name || id }}</h2>
          <button type="button" class="btn btn-secondary ml-auto" :aria-expanded="aiOpen" aria-controls="ai-build" @click="aiOpen = !aiOpen">
            <Sparkles :size="16" aria-hidden="true" /> Build with AI
          </button>
        </div>

        <section v-if="aiOpen" id="ai-build" class="inset rounded-md p-4" aria-label="Build with AI">
          <p class="pb-4 text-xs text-muted">Three steps. The result loads into this editor, so you check the preview before saving.</p>
          <ol class="divide-y divide-[#ebe6dc]">
            <li class="flex gap-3 pb-5">
              <span class="step-no" aria-hidden="true">1</span>
              <div class="min-w-0 flex-1 space-y-2">
                <h3 class="font-semibold">Say what to build</h3>
                <div class="flex flex-wrap items-end gap-2">
                  <label class="sr-only" for="ai-what">What should the set be?</label>
                  <input id="ai-what" v-model="aiWhat" placeholder="Kitchen, beach, classroom, forest…" :class="[field, 'mt-0 min-w-48 flex-1']"
                    @keydown.enter.prevent="aiWhat.trim() && makePrompt()" />
                  <button type="button" class="btn btn-primary" :disabled="!aiWhat.trim()" @click="makePrompt">Prompt for AI</button>
                </div>
              </div>
            </li>
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
                    class="block w-full resize-y rounded-md bg-[#ebe6dc] p-4 font-mono text-xs leading-5 text-muted outline-none" />
                </template>
              </div>
            </li>
            <li class="flex gap-3 pt-5">
              <span class="step-no" aria-hidden="true">3</span>
              <div class="min-w-0 flex-1 space-y-2">
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="font-semibold"><label for="ai-reply">Paste the AI's JSON reply here</label></h3>
                  <button type="button" class="btn btn-secondary ml-auto" @click="pasteReply"><ClipboardPaste :size="16" aria-hidden="true" /> Paste</button>
                </div>
                <p class="text-xs text-muted">The JSON block, or its whole message: the JSON is picked out of it.</p>
                <textarea id="ai-reply" v-model="aiReply" rows="6" spellcheck="false"
                  placeholder='Paste here, e.g.&#10;```json&#10;{"id": "kitchen", "name": "Kitchen", "kind": "indoor", ...}&#10;```'
                  class="paper block w-full resize-y rounded-md border-2 border-dashed p-4 font-mono text-xs leading-5 text-ink outline-none focus:border-solid"
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
            <input v-model="form.name" required maxlength="40" placeholder="Kitchen" :class="field" />
          </label>
          <label class="block text-xs font-semibold text-muted">Id (used in <code>@set</code>)
            <input v-model="form.id" required :readonly="!isNew" pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="kitchen"
              :class="[field, !isNew && 'opacity-70']" :aria-invalid="!!taken" @input="form.idEdited = true" />
            <span v-if="taken" class="mt-1 block text-red-ink" role="alert">“{{ form.id }}” is already a set</span>
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

      <aside class="space-y-3 lg:sticky lg:top-0 lg:self-start">
        <SetPreview :id="draft.id" :custom="previewList" :label="`Preview of ${form.name || 'the set'}`" class="aspect-[9/16] w-full" />
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
  border-radius: 9999px;
  background: var(--color-blue-ink);
  color: #fff;
  font-size: 0.8125rem;
  font-weight: 700;
}
</style>
