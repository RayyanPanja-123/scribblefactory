<script setup lang="ts">
// The series cast: one card per character with its idle pose. Each one renders, is edited (CastEditor page) and is
// approved on its own, so changing one character never means re-rendering the rest. Approving needs a render of the
// character's current look (renders[id].current); live job state comes from live.ts.
import { CheckCheck, Download, FileJson, ImageOff, Pencil, RefreshCw, TriangleAlert, ZoomIn } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { api, type CastMember, type SeriesModel } from '../api/client'
import type { components } from '../api/types'
import { act, confirm, toast, zoom } from '../composables/feedback'
import { castSheetJob, seriesBusy } from '../composables/live'
import { shortDate } from '../composables/ui'
import Switch from './Switch.vue'

type CastRender = components['schemas']['CastRender']
const p = defineProps<{ series: SeriesModel; renders: Record<string, CastRender> }>()
const emit = defineEmits<{ changed: [] }>()

const cast = computed(() => p.series.cast)
const render = (c: CastMember): CastRender => p.renders[c.id] ?? { sheet: null, idle: null, current: false }
const rendering = (c: CastMember) => !!castSheetJob(p.series.slug, c.id)
const busy = computed(() => seriesBusy(p.series.slug))
const outdated = computed(() => cast.value.filter((c) => !render(c).current))
const waiting = computed(() => cast.value.filter((c) => !c.approved_at))
const ready = computed(() => waiting.value.filter((c) => !approveReason(c)))

// why a character can't be rendered now (null: it can)
const renderReason = (c?: CastMember) => !p.series.parts.length ? 'add a part first: the cast renders through a part'
  : c && rendering(c) ? `${c.name} is rendering` : busy.value ? 'a job is running in this series' : null
// why a character can't be approved now
const approveReason = (c: CastMember) => {
  const r = render(c)
  return !r.sheet ? 'render it first' : !r.current ? 'changed since its render: re-render it first'
    : rendering(c) ? 'wait for the new render' : busy.value ? 'a job is running in this series' : null
}

async function renderCast(members: CastMember[], what: string) {
  if (!members.length || renderReason()) return
  await act(() => api.submitJob(p.series.slug, p.series.parts[0], [`cast-sheet ${members.map((c) => c.id).join(' ')}`]),
    `${what} queued`)
}
/** the series page's next-step button: whatever is new or changed, else everyone */
const renderSheet = () => renderCast(outdated.value.length ? outdated.value : cast.value, 'Cast render')

async function approve(c: CastMember) {
  if (await act(() => api.approveCast(p.series.slug, c.id), `${c.name} approved`)) emit('changed')
}
async function approveAll() {
  const n = ready.value.length
  const ok = await confirm({
    title: `Approve ${n} cast members?`,
    body: 'Only after checking every pose of each one. An approval stays until that character’s look changes.',
    confirm: `Approve ${n}`,
  })
  if (!ok) return
  for (const c of ready.value) {
    if (!(await act(() => api.approveCast(p.series.slug, c.id), `${c.name} approved`))) break
  }
  emit('changed')
}

// ---- JSON round trip for mass edits: export everyone, change the file, import it back ----
function exportJson() {
  const entries = cast.value.map(({ approved_at: _, ...c }) => c)
  const url = URL.createObjectURL(new Blob([JSON.stringify({ cast: entries }, null, 2) + '\n'], { type: 'application/json' }))
  Object.assign(document.createElement('a'), { href: url, download: `${p.series.slug}-cast.json` }).click()
  URL.revokeObjectURL(url)
}
const importOpen = ref(false)
const importText = ref('')
const importError = ref('')
async function loadFile(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = ''
  if (f) importText.value = await f.text()
}
async function runImport() {
  importError.value = ''
  let entries: unknown
  try {
    const j = JSON.parse(importText.value)
    entries = Array.isArray(j) ? j : j?.cast // an array, {"cast": [...]}, or a whole series.json
  } catch (e) {
    importError.value = `Not valid JSON: ${(e as Error).message}`
    return
  }
  if (!Array.isArray(entries) || !entries.length) {
    importError.value = 'Expected a non-empty array of cast entries, or an object with a "cast" array.'
    return
  }
  const before = new Map(cast.value.map((c) => [c.id, c]))
  let s: SeriesModel
  try {
    s = await api.importCast(p.series.slug, entries as Record<string, unknown>[])
  } catch (e) {
    importError.value = e instanceof Error ? e.message : String(e) // shown by the textarea: fix it and import again
    return
  }
  const ids = (entries as { id?: string }[]).map((x) => x.id)
  const added = ids.filter((id) => id && !before.has(id)).length
  const cleared = s.cast.filter((c) => before.get(c.id)?.approved_at && !c.approved_at).map((c) => c.name)
  toast(`${ids.length - added} updated, ${added} added` + (cleared.length ? `. New look, approval cleared: ${cleared.join(', ')}` : ''), 'ok')
  importOpen.value = false
  importText.value = ''
  emit('changed')
}
defineExpose({ renderSheet })
</script>

<template>
  <section id="cast" class="raised p-6" aria-labelledby="cast-title">
    <div class="flex flex-wrap items-center gap-3">
      <h3 id="cast-title" class="font-display text-xl font-semibold">Cast</h3>
      <span v-if="cast.length" class="chip" :class="waiting.length ? 'chip-amber' : 'chip-green'">
        <span class="num">{{ cast.length - waiting.length }}/{{ cast.length }}</span> approved
      </span>
      <div class="ml-auto flex flex-wrap gap-2">
        <button v-if="cast.length" class="btn btn-secondary" @click="exportJson">
          <Download :size="16" aria-hidden="true" /> Export JSON
        </button>
        <button class="btn btn-secondary" :aria-expanded="importOpen" aria-controls="cast-import" @click="importOpen = !importOpen">
          <FileJson :size="16" aria-hidden="true" /> Import JSON
        </button>
        <button v-if="outdated.length" class="btn btn-secondary" :disabled="!!renderReason()" :title="renderReason() ?? undefined"
          @click="renderCast(outdated, 'Cast render')">
          <RefreshCw :size="16" aria-hidden="true" />
          Render {{ outdated.length === cast.length ? 'all' : `${outdated.length} new or changed` }}
        </button>
        <button v-if="ready.length > 1" class="btn btn-primary" @click="approveAll">
          <CheckCheck :size="16" aria-hidden="true" /> Approve {{ ready.length }}
        </button>
      </div>
    </div>

    <div v-if="importOpen" id="cast-import" class="inset mt-4 space-y-3 p-4">
      <div class="flex flex-wrap items-center gap-2">
        <label class="btn btn-secondary cursor-pointer">Choose file
          <input type="file" accept=".json,application/json" class="sr-only" @change="loadFile" />
        </label>
        <a href="/cast-reference.json" download class="btn btn-secondary ml-auto"><Download :size="16" aria-hidden="true" /> Reference JSON</a>
      </div>
      <label class="sr-only" for="cast-json">Cast JSON</label>
      <textarea id="cast-json" v-model="importText" rows="10" spellcheck="false" placeholder='{ "cast": [ ... ] } from Export JSON'
        class="paper block w-full resize-y rounded-md p-4 font-mono text-xs leading-6 text-ink outline-none focus:border-blue" />
      <p v-if="importError" class="text-sm text-red-ink" role="alert">{{ importError }}</p>
      <p class="text-xs text-muted">An entry with an existing id replaces that character; a new id is added. Characters not in the file stay as
        they are (nothing is deleted). All or nothing: one bad entry and nothing changes. A new look clears that approval and needs a re-render.</p>
      <div class="flex justify-end gap-2">
        <button type="button" class="btn btn-secondary" @click="importOpen = false">Cancel</button>
        <button type="button" class="btn btn-primary" :disabled="!importText.trim() || busy" :title="busy ? 'a job is running in this series' : undefined"
          @click="runImport">Import</button>
      </div>
    </div>

    <p v-if="!cast.length" class="mt-3 text-sm text-muted">
      No cast yet. Add characters with <code>cast-add</code>, or import cast JSON when creating a series.
    </p>

    <ul v-else class="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" aria-label="Cast members">
      <li v-for="c in cast" :key="c.id" class="inset flex flex-col p-3">
        <div class="relative">
          <button v-if="render(c).idle" class="group relative block w-full cursor-zoom-in overflow-hidden rounded-sm bg-white"
            :aria-label="`Zoom every pose of ${c.name}`" @click="zoom(render(c).sheet!, `${c.name}: every pose`)">
            <img :src="render(c).idle!" :alt="`${c.name}, idle`" loading="lazy" class="aspect-[3/4] w-full object-cover object-bottom"
              :class="{ 'opacity-40': rendering(c) || !render(c).current }" />
            <span class="absolute right-2 bottom-2 grid size-8 place-items-center rounded-full bg-panel text-ink opacity-0 shadow-[var(--shadow-sheet)] transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
              <ZoomIn :size="14" aria-hidden="true" />
            </span>
          </button>
          <div v-else class="grid aspect-[3/4] place-items-center gap-2 rounded-sm border-2 border-dashed border-rule-strong p-4 text-center">
            <ImageOff :size="22" class="text-faint" aria-hidden="true" />
            <span class="text-xs text-muted">{{ rendering(c) ? 'Rendering…' : 'Not rendered yet' }}</span>
          </div>
          <span v-if="render(c).idle && !render(c).current && !rendering(c)" class="chip chip-amber absolute top-2 left-2">
            <TriangleAlert :size="12" aria-hidden="true" /> Changed: re-render
          </span>
          <span v-else-if="render(c).idle && rendering(c)" class="chip absolute top-2 left-2">Rendering…</span>
        </div>

        <div class="mt-3 flex items-center gap-2">
          <span class="size-4 shrink-0 rounded-full border-2 border-ink" :style="{ background: c.top.color }" aria-hidden="true" />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-semibold">{{ c.name }}</span>
            <span class="block truncate text-xs text-muted">{{ c.id }}<template v-if="c.approved_at"> · approved {{ shortDate(c.approved_at) }}</template></span>
          </span>
        </div>

        <div class="mt-3 flex flex-wrap items-center gap-2">
          <RouterLink :to="`/series/${series.slug}/cast/${c.id}`" class="btn btn-secondary" :aria-label="`Edit ${c.name}`">
            <Pencil :size="14" aria-hidden="true" /> Edit
          </RouterLink>
          <button class="btn btn-secondary" :disabled="!!renderReason(c)" :title="renderReason(c) ?? undefined"
            :aria-label="`Re-render ${c.name}`" @click="renderCast([c], `${c.name} render`)">
            <RefreshCw :size="14" :class="{ 'animate-spin': rendering(c) }" aria-hidden="true" /> {{ render(c).sheet ? 'Re-render' : 'Render' }}
          </button>
          <Switch v-if="!c.approved_at" :on="false" :label="c.name" :reason="approveReason(c)" @request="approve(c)">
            <span class="sr-only">{{ c.name }}</span>
          </Switch>
        </div>
      </li>
    </ul>
  </section>
</template>
