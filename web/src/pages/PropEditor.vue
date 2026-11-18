<script setup lang="ts">
import { ArrowDown, ArrowLeft, ArrowUp, ClipboardPaste, Copy, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import PropPreview from '../components/PropPreview.vue'
import { act, confirm, toast } from '../composables/feedback'
import { useApi } from '../composables/useApi'
import { buildPrompt, importProp } from '../lib/propPrompt'
import { HANDS, type CustomProp, type Hand, type PropShape } from '../lib/props'

// Create (/props/new) or edit one custom prop: a list of shapes in hand space, previewed live in a stickman's hand
// by the engine's own drawing code. The server (schema PropShape) has the final say on every field.
const props = defineProps<{ id: string }>()
const router = useRouter()
const isNew = computed(() => props.id === 'new')
const { data, error, loading, reload } = useApi(() => api.props())

type Kind = PropShape['shape']
type Row = { shape: Kind; pts: string; r: number; fill: string; filled: boolean; width: number }
const SHAPES: Record<Kind, { label: string; pts: string; hint: string }> = {
  rect: { label: 'Rectangle', pts: '-10,-60 10,20', hint: 'two corners' },
  circle: { label: 'Circle', pts: '0,-30', hint: 'the centre' },
  line: { label: 'Line', pts: '0,30 0,-90', hint: '2 or more points' },
  poly: { label: 'Polygon', pts: '0,-90 30,-60 0,-30', hint: '3 or more points, closed' },
}
const STARTER: Row[] = [
  { shape: 'line', pts: '0,30 0,-80', r: 20, fill: '#8a5a2b', filled: false, width: 7 },
  { shape: 'circle', pts: '0,-100', r: 22, fill: '#e8b923', filled: true, width: 8 },
]
const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')

const form = reactive({ id: '', name: '', idEdited: false, rows: [] as Row[] })
const hand = ref<Hand>('right')
const toRow = (s: PropShape): Row => ({
  shape: s.shape, pts: s.pts.map(([x, y]) => `${x},${y}`).join(' '), r: s.r ?? 20,
  fill: s.fill ?? '#ffffff', filled: !!s.fill, width: s.width ?? 8,
})
watch(data, (c) => {
  if (!c) return
  const p = c.custom.find((x) => x.id === props.id)
  if (!isNew.value && !p) return
  Object.assign(form, p ? { id: p.id, name: p.name, idEdited: true, rows: p.shapes.map(toRow) } : { id: '', name: '', idEdited: false, rows: STARTER.map((r) => ({ ...r })) })
}, { immediate: true })
const missing = computed(() => !isNew.value && data.value && !data.value.custom.some((x) => x.id === props.id))
watch(() => form.name, (n) => { if (isNew.value && !form.idEdited) form.id = slugify(n) })

/** "x,y x,y" -> points, or an error for the row */
function parse(r: Row): { shape?: PropShape; err?: string } {
  const pts = r.pts.trim().split(/\s+/).filter(Boolean).map((t) => t.split(',').map(Number))
  if (!pts.length || pts.some((p) => p.length !== 2 || p.some((v) => !Number.isFinite(v)))) return { err: 'points as x,y x,y …' }
  const [lo, hi] = { rect: [2, 2], circle: [1, 1], line: [2, 24], poly: [3, 24] }[r.shape]
  if (pts.length < lo || pts.length > hi) return { err: `${SHAPES[r.shape].label.toLowerCase()}: ${SHAPES[r.shape].hint}` }
  if (pts.some((p) => p.some((v) => Math.abs(v) > 300))) return { err: 'keep points within 300 of the hand' }
  return { shape: { shape: r.shape, pts: pts as [number, number][], r: r.shape === 'circle' ? r.r : null, fill: r.shape !== 'line' && r.filled ? r.fill : null, width: r.width } }
}
const parsed = computed(() => form.rows.map(parse))
const draft = computed<CustomProp>(() => ({ id: form.id || 'draft', name: form.name, shapes: parsed.value.flatMap((p) => p.shape ?? []) }))
const previewList = computed(() => [...(data.value?.custom ?? []).filter((p) => p.id !== draft.value.id), draft.value])
const taken = computed(() => (data.value?.builtin as string[] | undefined)?.includes(form.id) || (isNew.value && data.value?.custom.some((p) => p.id === form.id)))
const valid = computed(() => form.name.trim() && /^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.id) && !taken.value && form.rows.length && parsed.value.every((p) => p.shape))

const addRow = (shape: Kind) => form.rows.push({ shape, pts: SHAPES[shape].pts, r: 20, fill: '#d84a3a', filled: true, width: 8 })
const move = (i: number, d: number) => form.rows.splice(i + d, 0, ...form.rows.splice(i, 1))

const saving = ref(false)
async function save() {
  saving.value = true
  const body = { ...draft.value, name: form.name.trim() }
  const c = await act(() => api.saveProp(body), `Prop “${body.name}” saved`)
  saving.value = false
  if (!c) return
  if (c.cleared.length) toast(`Drawing changed: approval cleared for ${c.cleared.join(', ')}. Re-run their cast sheets.`, 'info')
  data.value = c
  if (isNew.value) router.replace(`/props/${body.id}`)
}
async function remove() {
  const ok = await confirm({ title: `Delete “${form.name}”?`, body: 'Only possible while nobody holds it and no story uses it in @do.', confirm: 'Delete prop', danger: true })
  if (ok && (await act(() => api.deleteProp(props.id), 'Prop deleted'))) router.push('/props')
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
  aiPrompt.value = buildPrompt(aiWhat.value, [...(c?.builtin ?? []), ...(c?.custom ?? []).map((p) => p.id)].filter((x) => x !== props.id), aiDetails.value, aiId.value)
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
  const { prop, error: err } = importProp(aiReply.value)
  aiError.value = err ?? ''
  if (!prop) return
  Object.assign(form, { name: prop.name, rows: prop.shapes.map(toRow) })
  if (isNew.value) Object.assign(form, { id: prop.id, idEdited: true })
  aiReply.value = ''
  toast(`Loaded ${prop.shapes.length} shapes: check the preview, then ${isNew.value ? 'create' : 'save'} the prop`, 'ok')
}
const field = 'inset mt-1 block h-11 w-full rounded-full px-4 text-sm text-ink outline-none'
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6">
    <RouterLink to="/props" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> All props</RouterLink>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading prop" />
    <ErrorCard v-else-if="missing" :message="`No custom prop “${id}”.`" @retry="reload" />
    <form v-else class="raised grid gap-6 p-6 lg:grid-cols-[1fr_280px]" @submit.prevent="save">
      <div class="min-w-0 space-y-5">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="font-display text-3xl font-semibold">{{ isNew ? 'New prop' : form.name || id }}</h2>
          <button type="button" class="btn btn-secondary ml-auto" :aria-expanded="aiOpen" aria-controls="ai-build" @click="aiOpen = !aiOpen">
            <Sparkles :size="16" aria-hidden="true" /> Build with AI
          </button>
        </div>

        <section v-if="aiOpen" id="ai-build" class="inset rounded-md p-4" aria-label="Build with AI">
          <p class="pb-4 text-xs text-muted">Three steps. The result loads into this editor, so you check the preview before saving.</p>
          <ol class="divide-y divide-[#ebe6dc]">
            <!-- 1: what to build -->
            <li class="flex gap-3 pb-5">
              <span class="step-no" aria-hidden="true">1</span>
              <div class="min-w-0 flex-1 space-y-2">
                <h3 class="font-semibold">Say what to build</h3>
                <label class="block text-sm font-semibold" for="ai-what">Name
                  <input id="ai-what" v-model="aiWhat" placeholder="Gun, umbrella, trophy, newspaper…" maxlength="40" :class="field"
                    @keydown.enter.prevent="aiWhat.trim() && makePrompt()" />
                </label>
                <p v-if="aiId" class="text-xs text-muted">Saved as <code>{{ aiId }}</code>. A story needs a different id? Set it in the id field below first.</p>
                <label class="block text-sm font-semibold" for="ai-details">Details <span class="font-normal text-muted">(optional)</span>
                  <textarea id="ai-details" v-model="aiDetails" rows="3" placeholder="Shape, colours, which end is held…"
                    class="inset mt-1 block w-full rounded-md px-4 py-2 text-sm text-ink outline-none" />
                </label>
                <button type="button" class="btn btn-primary" :disabled="!aiWhat.trim()" @click="makePrompt">Prompt for AI</button>
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
                    class="block w-full resize-y rounded-md bg-[#ebe6dc] p-4 font-mono text-xs leading-5 text-muted outline-none" />
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
                  placeholder='Paste here, e.g.&#10;```json&#10;{"id": "gun", "name": "Gun", "shapes": [...]}&#10;```'
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
            <input v-model="form.name" required maxlength="40" placeholder="Torch" :class="field" />
          </label>
          <label class="block text-xs font-semibold text-muted">Id (used in cast props and @do)
            <input v-model="form.id" required :readonly="!isNew" pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="torch"
              :class="[field, !isNew && 'opacity-70']" :aria-invalid="!!taken" @input="form.idEdited = true" />
            <span v-if="taken" class="mt-1 block text-red-ink" role="alert">“{{ form.id }}” is already a prop</span>
          </label>
        </div>

        <fieldset class="space-y-3">
          <legend class="font-display text-lg font-semibold">Shapes</legend>
          <p class="text-xs text-muted">Hand space: the hand is at 0,0, y goes down, x goes away from the body. The built-in props
            fit in about −40…110. Later shapes draw on top.</p>
          <div v-for="(r, i) in form.rows" :key="i" class="inset space-y-2 rounded-md p-3">
            <div class="grid items-end gap-2 sm:grid-cols-[8rem_1fr_auto]">
              <label class="block text-xs font-semibold text-muted">Shape
                <select v-model="r.shape" :class="field">
                  <option v-for="(s, k) in SHAPES" :key="k" :value="k">{{ s.label }}</option>
                </select>
              </label>
              <label class="block text-xs font-semibold text-muted">Points ({{ SHAPES[r.shape].hint }})
                <input v-model="r.pts" spellcheck="false" :class="[field, 'font-mono']" :aria-invalid="!!parsed[i].err" />
              </label>
              <div class="flex gap-1">
                <button type="button" class="btn btn-secondary size-11 justify-center p-0" :disabled="i === 0" :aria-label="`Move shape ${i + 1} up the list (drawn earlier)`" @click="move(i, -1)"><ArrowUp :size="16" aria-hidden="true" /></button>
                <button type="button" class="btn btn-secondary size-11 justify-center p-0" :disabled="i === form.rows.length - 1" :aria-label="`Move shape ${i + 1} down the list (drawn later)`" @click="move(i, 1)"><ArrowDown :size="16" aria-hidden="true" /></button>
                <button type="button" class="btn btn-secondary size-11 justify-center p-0" :aria-label="`Remove shape ${i + 1}`" @click="form.rows.splice(i, 1)"><Trash2 :size="16" aria-hidden="true" /></button>
              </div>
            </div>
            <div class="flex flex-wrap items-end gap-3">
              <label v-if="r.shape === 'circle'" class="block w-28 text-xs font-semibold text-muted">Radius
                <input v-model.number="r.r" type="number" min="1" max="200" :class="field" />
              </label>
              <label class="block w-28 text-xs font-semibold text-muted">{{ r.shape === 'line' ? 'Line width' : 'Outline' }}
                <input v-model.number="r.width" type="number" min="0" max="24" :class="field" />
              </label>
              <template v-if="r.shape !== 'line'">
                <label class="flex h-11 items-center gap-2 text-sm"><input v-model="r.filled" type="checkbox" class="size-4" /> Fill</label>
                <input v-if="r.filled" v-model="r.fill" type="color" :aria-label="`Fill colour of shape ${i + 1}`" class="h-11 w-14 cursor-pointer rounded-md" />
              </template>
            </div>
            <p v-if="parsed[i].err" class="text-xs text-red-ink" role="alert">{{ parsed[i].err }}</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button v-for="(s, k) in SHAPES" :key="k" type="button" class="btn btn-secondary" @click="addRow(k)"><Plus :size="16" aria-hidden="true" /> {{ s.label }}</button>
          </div>
        </fieldset>

        <div class="flex flex-wrap justify-end gap-2">
          <button v-if="!isNew" type="button" class="btn btn-secondary mr-auto text-red-ink" @click="remove"><Trash2 :size="16" aria-hidden="true" /> Delete</button>
          <button class="btn btn-primary" :disabled="!valid || saving">{{ saving ? 'Saving…' : isNew ? 'Create prop' : 'Save prop' }}</button>
        </div>
      </div>

      <aside class="space-y-3 lg:sticky lg:top-0 lg:self-start">
        <PropPreview :kind="draft.id" :custom="previewList" :hand="hand" :label="`Preview: stickman holding ${form.name || 'the prop'}`" class="h-96" />
        <div class="flex justify-center gap-2" role="group" aria-label="Preview hand">
          <button v-for="h in HANDS" :key="h" type="button" class="btn" :class="hand === h ? 'btn-primary' : 'btn-secondary'" :aria-pressed="hand === h" @click="hand = h">{{ h }} hand</button>
        </div>
        <p class="text-center text-xs text-muted">Drawn by the render engine: what you see is what renders.</p>
      </aside>
    </form>
  </div>
</template>

<style scoped>
/* step number: a round badge in the accent ink */
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
