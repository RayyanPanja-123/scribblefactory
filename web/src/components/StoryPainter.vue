<script setup lang="ts">
import { ArrowDown, ArrowUp, CircleAlert, CornerDownLeft, Plus, Trash2, X } from 'lucide-vue-next'
import { computed, nextTick, onMounted, ref, toRaw, watch } from 'vue'
import { api } from '../api/client'
import { useApi } from '../composables/useApi'
import { propOptions } from '../lib/props'
import { addRow, KINDS, lintBeat, parseStory, writeStory, type Beat, type Ctx, type Field, type Row } from '../lib/storyPaint'

// The Story tab's typewriter view of story.md: the page (every line typed so far) above, the carriage (the line being
// typed, with its directions) below. "Add to page" feeds the line onto the page, which rolls up like typewriter paper.
// The page is written straight back into the text (the same story.md the Text view shows), so Save works as before.
// It fills the whole screen (teleported to body); the #actions slot holds the page's Save / Create button.
defineOptions({ inheritAttrs: false }) // the parent's listeners (Ctrl+S) go on the full-screen sheet
const props = defineProps<{ cast: Ctx['cast']; noTitle?: boolean }>() // noTitle: the page has its own title field
const emit = defineEmits<{ close: [] }>()
const text = defineModel<string>({ required: true })

const { data } = useApi(() => Promise.all([api.sets(), api.actions(), api.props(), api.sfx()]))
const ctx = computed<Ctx>(() => {
  const [sets, actions, ps, sfx] = data.value ?? []
  return {
    sets: [...(sets?.builtin ?? []).map((s) => s.id), ...(sets?.custom ?? []).map((s) => s.id)],
    actions: [...(actions?.do ?? []), ...(actions?.custom ?? []).map((a) => a.id)],
    props: propOptions(ps).map((p) => p.id),
    sounds: (sfx?.sfx ?? []).map((s) => s.id),
    cast: props.cast,
  }
})

const paint = ref(parseStory(text.value))
watch(text, (v) => { if (writeStory(parseStory(v)) !== writeStory(paint.value)) paint.value = parseStory(v) })
// only a real change rewrites the text: opening the painter never reformats a hand-written story
watch(paint, (p) => { if (writeStory(p) !== writeStory(parseStory(text.value))) text.value = writeStory(p) }, { deep: true })

// the keys, grouped by how long they last (see the tips): scene ones stay until changed, line ones only touch their line
const GROUPS: [string, string[]][] = [
  ['Scene · stays', ['set', 'cast', 'weather', 'look', 'hold', 'ride', 'background-music']],
  ['This line only', ['do', 'face', 'cam', 'fx', 'sfx']],
  ['Extras', ['car', 'dogs', 'runners', 'crowd', 'crowd-look', 'crowd-weapon']],
]

const blank = (): Beat => ({ rows: [], text: '', twist: false })
const draft = ref<Beat>(blank())
const editing = ref<number | null>(null) // the page line in the carriage, or null for a new line at the end
const typed = (b: Beat) => !!(b.text.trim() || b.rows.length)

// every line's problems, the carriage's checked where it would land
const issues = computed(() => paint.value.beats.map((_, i) => lintBeat(paint.value.beats, i, ctx.value)))
const draftIssues = computed(() => {
  const beats = [...paint.value.beats]
  const at = editing.value ?? beats.length
  beats.splice(at, editing.value === null ? 0 : 1, draft.value)
  return lintBeat(beats, at, ctx.value)
})

const page = ref<HTMLElement>()
const carriage = ref<HTMLTextAreaElement>()
onMounted(() => carriage.value?.focus())
async function feed() {
  if (!typed(draft.value)) return
  const b = { ...draft.value, text: draft.value.text.replace(/\s*\n\s*/g, ' ').trim() } // one spoken line is one line of story.md
  if (editing.value === null) paint.value.beats.push(b)
  else paint.value.beats.splice(editing.value, 1, b)
  const end = editing.value === null
  draft.value = blank()
  editing.value = null
  await nextTick()
  if (end && page.value) page.value.scrollTo({ top: page.value.scrollHeight, behavior: 'smooth' })
  carriage.value?.focus()
}
function edit(i: number) {
  if (typed(draft.value) && !confirm('Drop the line in the typewriter?')) return
  editing.value = i
  draft.value = structuredClone(toRaw(paint.value.beats[i]))
  carriage.value?.focus()
}
function cancel() {
  draft.value = blank()
  editing.value = null
}
function remove(i: number) {
  paint.value.beats.splice(i, 1)
  if (editing.value === i) cancel()
  else if (editing.value !== null && editing.value > i) editing.value--
}
function move(i: number, by: number) {
  const b = paint.value.beats
  b.splice(i + by, 0, ...b.splice(i, 1))
  if (editing.value === i) editing.value = i + by
  else if (editing.value === i + by) editing.value = i
}
// the text changed underneath (Text view, an issue fix): a line being edited may be gone
watch(() => paint.value.beats.length, (n) => { if (editing.value !== null && editing.value >= n) cancel() })

const castName = (id: string) => props.cast.find((c) => c.id === id)?.name ?? id
const rec = (r: Row) => KINDS[r.name]?.parse(r.arg) ?? null
const fields = (r: Row): Field[] => KINDS[r.name].fields(ctx.value, rec(r)!)
// a select always offers the current value, also one the library does not know (the line check flags it)
const opts = (f: Field, v: string) => (f.options?.includes(v) || !v ? f.options ?? [] : [v, ...(f.options ?? [])])
function set(r: Row, key: string, v: string) {
  r.arg = KINDS[r.name].build({ ...rec(r)!, [key]: v })
}
function toggleCast(r: Row, id: string) {
  const on = rec(r)!.cast.split(',').map((x) => x.trim()).filter(Boolean)
  set(r, 'cast', (on.includes(id) ? on.filter((x) => x !== id) : [...on, id]).join(', '))
}
const onStage = (r: Row, id: string) => rec(r)!.cast.split(',').map((x) => x.trim()).includes(id)
const field = 'inset mt-1 block h-9 w-full rounded-md px-2 text-sm text-ink outline-none focus:border-blue'
</script>

<template>
  <Teleport to="body">
  <div v-bind="$attrs" class="fixed inset-0 z-50 flex flex-col gap-3 bg-page p-4 sm:p-6" role="dialog" aria-modal="true" aria-label="Typewriter"
    @keydown.esc="emit('close')">
    <header class="flex flex-wrap items-end gap-3">
      <h2 class="font-display text-2xl font-semibold">Typewriter</h2>
      <label v-if="!noTitle" class="min-w-48 flex-1 text-xs font-semibold text-muted">Title
        <input v-model="paint.title" :class="field" placeholder="Part title" />
      </label>
      <div class="ml-auto flex items-center gap-2">
        <slot name="actions" />
        <button type="button" class="btn btn-secondary" aria-label="Close typewriter" @click="emit('close')"><X :size="16" /> Close</button>
      </div>
    </header>

    <!-- the page: what is typed so far; click a line to put it back in the typewriter -->
    <div ref="page" class="paper inset min-h-0 flex-1 overflow-y-auto px-5 py-4 font-mono text-sm" aria-label="Story so far">
      <p v-if="!paint.beats.length" class="py-10 text-center text-muted">The page is blank. Type the first line below.</p>
      <TransitionGroup tag="ol" name="feed" class="space-y-2">
        <li v-for="(b, i) in paint.beats" :key="`${i}:${b.text}`" class="group rounded-md px-2 py-1.5"
          :class="editing === i ? 'bg-blue/10 ring-1 ring-blue' : 'hover:bg-well'">
          <div class="flex items-start gap-2">
            <span class="num w-6 shrink-0 pt-0.5 text-right text-xs text-muted">{{ i + 1 }}</span>
            <button type="button" class="min-w-0 flex-1 text-left" :aria-label="`Edit line ${i + 1}`" @click="edit(i)">
              <span v-if="b.rows.length" class="mb-1 flex flex-wrap gap-1">
                <span v-for="(r, j) in b.rows" :key="j" class="chip font-sans text-xs">{{ KINDS[r.name]?.label ?? `@${r.name}` }}: {{ r.arg }}</span>
              </span>
              <span class="block leading-6 text-ink"><b v-if="b.twist" class="text-red-ink">!! </b>{{ b.text || '—' }}</span>
            </button>
            <span class="flex shrink-0 gap-1 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
              <button type="button" class="btn btn-secondary px-1.5" :disabled="i === 0" aria-label="Move up" @click="move(i, -1)"><ArrowUp :size="12" /></button>
              <button type="button" class="btn btn-secondary px-1.5" :disabled="i === paint.beats.length - 1" aria-label="Move down" @click="move(i, 1)"><ArrowDown :size="12" /></button>
              <button type="button" class="btn btn-secondary px-1.5" aria-label="Delete line" @click="remove(i)"><Trash2 :size="12" /></button>
            </span>
          </div>
          <ul v-if="issues[i].length" class="mt-1 ml-8 space-y-0.5 font-sans text-xs text-red-ink">
            <li v-for="m in issues[i]" :key="m" class="flex items-start gap-1"><CircleAlert :size="12" class="mt-0.5 shrink-0" aria-hidden="true" />{{ m }}</li>
          </ul>
        </li>
      </TransitionGroup>
    </div>

    <!-- the carriage: the line being typed -->
    <div class="raised max-h-[55vh] shrink-0 overflow-y-auto p-4">
      <div class="flex items-center gap-2 text-xs text-muted">
        <span class="font-semibold">{{ editing === null ? `Line ${paint.beats.length + 1}` : `Editing line ${editing + 1}` }}</span>
        <label class="ml-auto flex items-center gap-1"><input v-model="draft.twist" type="checkbox" /> Twist (last line)</label>
      </div>

      <div v-for="(r, j) in draft.rows" :key="j" class="mt-2 flex flex-wrap items-end gap-2 border-l-2 border-rule pl-3">
        <span class="chip w-28 shrink-0 justify-center">{{ KINDS[r.name]?.label ?? `@${r.name}` }}</span>
        <template v-if="KINDS[r.name] && rec(r)">
          <template v-for="f in fields(r)" :key="f.key">
            <div v-if="f.type === 'cast'" class="flex flex-wrap gap-1">
              <button v-for="c in cast" :key="c.id" type="button" class="chip" :class="onStage(r, c.id) ? 'chip-green' : 'opacity-60'"
                :aria-pressed="onStage(r, c.id)" @click="toggleCast(r, c.id)">{{ c.name }}</button>
            </div>
            <label v-else class="min-w-28 flex-1 text-xs text-muted">{{ f.label }}
              <select v-if="f.type === 'select'" :value="rec(r)![f.key]" :class="field" @change="set(r, f.key, ($event.target as HTMLSelectElement).value)">
                <option v-for="o in opts(f, rec(r)![f.key])" :key="o" :value="o">{{ f.names?.[o] ?? (f.key === 'who' ? castName(o) : o || '—') }}</option>
              </select>
              <input v-else :value="rec(r)![f.key]" :type="f.type" :step="f.type === 'number' ? 'any' : undefined" :class="field"
                @change="set(r, f.key, ($event.target as HTMLInputElement).value)" />
            </label>
          </template>
        </template>
        <label v-else class="min-w-40 flex-1 text-xs text-muted">@{{ r.name }}
          <input v-model="r.arg" :class="field" class="font-mono" />
        </label>
        <button type="button" class="btn btn-secondary px-2" aria-label="Remove" @click="draft.rows.splice(j, 1)"><X :size="14" /></button>
      </div>

      <label class="sr-only" for="carriage">What the narrator says</label>
      <textarea id="carriage" ref="carriage" v-model="draft.text" rows="2" placeholder="What the narrator says…"
        class="paper inset mt-3 block w-full resize-none rounded-md p-4 font-mono text-lg leading-7 outline-none focus:border-blue"
        @keydown.enter.exact.prevent="feed" />
      <ul v-if="draftIssues.length" class="mt-2 space-y-0.5 text-xs text-red-ink" aria-live="polite">
        <li v-for="m in draftIssues" :key="m" class="flex items-start gap-1"><CircleAlert :size="12" class="mt-0.5 shrink-0" aria-hidden="true" />{{ m }}</li>
      </ul>

      <div class="mt-3 flex flex-wrap items-center justify-end gap-2">
        <span class="mr-auto text-xs text-muted">Enter adds the line. Not on the page yet = not saved.</span>
        <button v-if="editing !== null || typed(draft)" type="button" class="btn btn-secondary" @click="cancel">{{ editing === null ? 'Clear' : 'Cancel' }}</button>
        <button type="button" class="btn btn-primary" :disabled="!typed(draft)" @click="feed">
          <CornerDownLeft :size="16" aria-hidden="true" /> {{ editing === null ? 'Add to page' : 'Put back' }}</button>
      </div>

      <!-- the keys -->
      <div class="mt-4 grid gap-3 border-t border-rule pt-3 sm:grid-cols-3">
        <div v-for="[label, names] in GROUPS" :key="label">
          <p class="text-xs font-semibold text-muted">{{ label }}</p>
          <div class="mt-1 flex flex-wrap gap-1">
            <button v-for="name in names" :key="name" type="button" class="btn btn-secondary px-2 py-1 text-xs" @click="addRow(draft, name, ctx)">
              <Plus :size="12" /> {{ KINDS[name].label }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
  </Teleport>
</template>

<style scoped>
@media (prefers-reduced-motion: no-preference) {
  .feed-enter-active { transition: transform 0.35s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.35s; }
  .feed-enter-from { transform: translateY(3rem); opacity: 0; }
  .feed-move { transition: transform 0.3s ease; }
}
</style>
