<script setup lang="ts">
import { ArrowDown, ArrowUp, Plus, Trash2, X } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { api } from '../api/client'
import { useApi } from '../composables/useApi'
import { propOptions } from '../lib/props'
import { addRow, KINDS, parseStory, writeStory, type Beat, type Ctx, type Field, type Row } from '../lib/storyPaint'

// The Story tab's form view of story.md: one card per spoken line with the directives above it as fields.
// Edits are written straight back into the text (the same story.md the Text view shows), so Save works as before.
const props = defineProps<{ cast: Ctx['cast']; noTitle?: boolean }>() // noTitle: the page has its own title field
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

const common = Object.entries(KINDS).filter(([, k]) => k.common)
const rare = Object.entries(KINDS).filter(([, k]) => !k.common)
const more = ref<number | null>(null) // the card whose More is open

const castName = (id: string) => props.cast.find((c) => c.id === id)?.name ?? id
const rec = (r: Row) => KINDS[r.name]?.parse(r.arg) ?? null
const fields = (r: Row): Field[] => KINDS[r.name].fields(ctx.value, rec(r)!)
// a select always offers the current value, also one the library does not know (the story check flags it)
const opts = (f: Field, v: string) => (f.options?.includes(v) || !v ? f.options ?? [] : [v, ...(f.options ?? [])])
function set(r: Row, key: string, v: string) {
  r.arg = KINDS[r.name].build({ ...rec(r)!, [key]: v })
}
function toggleCast(r: Row, id: string) {
  const on = rec(r)!.cast.split(',').map((x) => x.trim()).filter(Boolean)
  set(r, 'cast', (on.includes(id) ? on.filter((x) => x !== id) : [...on, id]).join(', '))
}
const onStage = (r: Row, id: string) => rec(r)!.cast.split(',').map((x) => x.trim()).includes(id)

const blank = (): Beat => ({ rows: [], text: '', twist: false })
function move(i: number, by: number) {
  const b = paint.value.beats
  b.splice(i + by, 0, ...b.splice(i, 1))
}
const field = 'inset mt-1 block h-9 w-full rounded-md px-2 text-sm text-ink outline-none focus:border-blue'
</script>

<template>
  <div class="space-y-3">
    <label v-if="!noTitle" class="block text-xs font-semibold text-muted">Title
      <input v-model="paint.title" :class="field" placeholder="Part title" />
    </label>

    <ol class="space-y-3">
      <li v-for="(b, i) in paint.beats" :key="i" class="inset rounded-md p-4">
        <div class="flex items-center gap-2 text-xs text-muted">
          <span class="num font-semibold">Line {{ i + 1 }}</span>
          <label class="ml-auto flex items-center gap-1"><input v-model="b.twist" type="checkbox" /> Twist (last line)</label>
          <button type="button" class="btn btn-secondary px-2" :disabled="i === 0" aria-label="Move up" @click="move(i, -1)"><ArrowUp :size="14" /></button>
          <button type="button" class="btn btn-secondary px-2" :disabled="i === paint.beats.length - 1" aria-label="Move down" @click="move(i, 1)"><ArrowDown :size="14" /></button>
          <button type="button" class="btn btn-secondary px-2" aria-label="Delete line" @click="paint.beats.splice(i, 1)"><Trash2 :size="14" /></button>
        </div>

        <div v-for="(r, j) in b.rows" :key="j" class="mt-2 flex flex-wrap items-end gap-2 border-l-2 border-rule pl-3">
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
          <button type="button" class="btn btn-secondary px-2" aria-label="Remove" @click="b.rows.splice(j, 1)"><X :size="14" /></button>
        </div>

        <label class="sr-only" :for="`beat-${i}`">Spoken line {{ i + 1 }}</label>
        <textarea :id="`beat-${i}`" v-model="b.text" rows="2" placeholder="What the narrator says"
          class="paper inset mt-3 block w-full resize-y rounded-md p-3 text-sm outline-none focus:border-blue" />

        <div class="mt-2 flex flex-wrap gap-1">
          <button v-for="[name, k] in common" :key="name" type="button" class="btn btn-secondary px-2 py-1 text-xs" @click="addRow(b, name, ctx)">
            <Plus :size="12" /> {{ k.label }}</button>
          <button type="button" class="btn btn-secondary px-2 py-1 text-xs" :aria-expanded="more === i" @click="more = more === i ? null : i">
            More {{ more === i ? '▾' : '▸' }}</button>
        </div>
        <div v-if="more === i" class="mt-1 flex flex-wrap gap-1">
          <button v-for="[name, k] in rare" :key="name" type="button" class="btn btn-secondary px-2 py-1 text-xs" @click="addRow(b, name, ctx)">
            <Plus :size="12" /> {{ k.label }}</button>
        </div>
        <button type="button" class="mt-2 text-xs font-semibold text-blue-ink underline underline-offset-2" @click="paint.beats.splice(i + 1, 0, blank())">
          + line below</button>
      </li>
    </ol>
    <button type="button" class="btn btn-secondary" @click="paint.beats.push(blank())"><Plus :size="16" /> Add line</button>
  </div>
</template>
