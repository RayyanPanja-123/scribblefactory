<script setup lang="ts">
import { ArrowDown, ArrowLeft, ArrowUp, Plus, Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import PropPreview from '../components/PropPreview.vue'
import { useLibraryEditor } from '../composables/libraryEditor'
import { useApi } from '../composables/useApi'
import { HANDS, type CustomProp, type Hand, type PropShape } from '../lib/props'

// Create (/props/new) or edit one custom prop: a list of shapes in hand space, previewed live in a stickman's hand
// by the engine's own drawing code. The server (schema PropShape) has the final say on every field.
const props = defineProps<{ id: string }>()
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

const form = reactive({ id: '', name: '', use_for: '', idEdited: false, rows: [] as Row[], angle: 0, grip: '' })
const hand = ref<Hand>('right')
const toRow = (s: PropShape): Row => ({
  shape: s.shape, pts: s.pts.map(([x, y]) => `${x},${y}`).join(' '), r: s.r ?? 20,
  fill: s.fill ?? '#ffffff', filled: !!s.fill, width: s.width ?? 8,
})
const { isNew, missing, saving, save: saveItem, remove: removeItem } = useLibraryEditor({
  id: () => props.id, base: '/props', form, custom: () => data.value?.custom })
watch(data, (c) => {
  if (!c) return
  const p = c.custom.find((x) => x.id === props.id)
  if (!isNew.value && !p) return
  Object.assign(form, p ? { id: p.id, name: p.name, use_for: p.use_for ?? '', idEdited: true, rows: p.shapes.map(toRow), angle: p.angle ?? 0, grip: p.grip ? p.grip.join(',') : '' }
    : { id: '', name: '', use_for: '', idEdited: false, rows: STARTER.map((r) => ({ ...r })), angle: 0, grip: '' })
}, { immediate: true })

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
// grip: "x,y" (the point of the shapes the hand holds) or empty for 0,0
const grip = computed<{ v: [number, number] | null; err?: string }>(() => {
  if (!form.grip.trim()) return { v: null }
  const xy = form.grip.split(',').map((t) => Number(t.trim()))
  return xy.length === 2 && xy.every((v) => Number.isFinite(v) && Math.abs(v) <= 300) ? { v: xy as [number, number] } : { v: null, err: 'x,y within 300 of the hand' }
})
/** an angle as a clock reading in the right hand: 75 -> "2:30" */
const clock = (deg: number) => {
  const m = Math.round((((deg % 360) + 360) % 360) * 2) % 720 // minutes on a 12 h dial: 30 deg = 60 min
  return `${Math.floor(m / 60) || 12}:${String(m % 60).padStart(2, '0')}`
}
const draft = computed<CustomProp>(() => ({ id: form.id || 'draft', name: form.name, shapes: parsed.value.flatMap((p) => p.shape ?? []),
  angle: form.angle, grip: grip.value.v }))
const previewList = computed(() => [...(data.value?.custom ?? []).filter((p) => p.id !== draft.value.id), draft.value])
const taken = computed(() => (data.value?.builtin as string[] | undefined)?.includes(form.id) || (isNew.value && data.value?.custom.some((p) => p.id === form.id)))
const valid = computed(() => form.name.trim() && /^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.id) && !taken.value && form.rows.length && parsed.value.every((p) => p.shape) && !grip.value.err)

const addRow = (shape: Kind) => form.rows.push({ shape, pts: SHAPES[shape].pts, r: 20, fill: '#d84a3a', filled: true, width: 8 })
const move = (i: number, d: number) => form.rows.splice(i + d, 0, ...form.rows.splice(i, 1))

function save() {
  const body = { ...draft.value, name: form.name.trim(), use_for: form.use_for.trim() || null }
  return saveItem(() => api.saveProp(body), `Prop “${body.name}” saved`, body.id, (c) => { data.value = c })
}
const remove = () => removeItem(() => api.deleteProp(props.id), 'prop', 'Only possible while nobody holds it and no story uses it in @do.', 'Prop deleted')
const field = 'inset mt-1 block h-10 w-full rounded-md px-4 text-sm text-ink outline-none focus:border-blue'
</script>

<template>
  <div class="space-y-6">
    <RouterLink to="/props" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> All props</RouterLink>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading prop" />
    <ErrorCard v-else-if="missing" :message="`No custom prop “${id}”.`" @retry="reload" />
    <form v-else class="grid items-start gap-6 lg:grid-cols-[1fr_280px]" @submit.prevent="save">
      <div class="raised min-w-0 space-y-5 p-6">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="font-display text-3xl font-semibold">{{ isNew ? 'New prop' : form.name || id }}</h2>
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block text-xs font-semibold text-muted">Name
            <input v-model="form.name" required maxlength="40" placeholder="Torch" :class="field" />
          </label>
          <label class="block text-xs font-semibold text-muted">Id (used in cast props and @do)
            <input v-model="form.id" required :readonly="!isNew" pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="torch"
              :class="[field, !isNew && 'opacity-70']" :aria-invalid="!!taken" @input="form.idEdited = true" />
            <span v-if="taken" class="mt-1 block text-red-ink" role="alert">“{{ form.id }}” is already a prop</span>
          </label>
          <label class="block text-xs font-semibold text-muted sm:col-span-2">Use for (tells the story AI when to use it)
            <input v-model="form.use_for" maxlength="200" placeholder="Neptune's weapon: lightning, commanding the sea" :class="field" />
          </label>
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block text-xs font-semibold text-muted">Angle when held: {{ form.angle }}° · {{ clock(form.angle) }} on a clock
            <input v-model.number="form.angle" type="range" min="-180" max="180" step="5" class="mt-3 block w-full" />
            <span class="mt-1 block font-normal">Leans like a clock hand, top away from the body: 0 upright, 75 = half past two, 90 level. A character can override it in its cast JSON (<code>"angle"</code>).</span>
          </label>
          <label class="block text-xs font-semibold text-muted">Grip (the point the hand holds)
            <input v-model="form.grip" spellcheck="false" placeholder="0,0" :class="[field, 'font-mono']" :aria-invalid="!!grip.err" />
            <span v-if="grip.err" class="mt-1 block text-red-ink" role="alert">{{ grip.err }}</span>
            <span v-else class="mt-1 block font-normal">In the shapes' own coordinates, e.g. the middle of a staff's shaft.</span>
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

      <aside class="raised p-6 space-y-3 lg:sticky lg:top-0 lg:self-start">
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
/* step number: a small ink tab, like a numbered X-sheet column */
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
