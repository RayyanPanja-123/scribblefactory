<script setup lang="ts">
// The series cast workflow in one place: the cast sheet to check against, one approval per character, and the
// cast-sheet render. The page passes the data in and refreshes on `changed`; live job state comes from live.ts.
import { Check, CheckCheck, ImageOff, RefreshCw, ZoomIn } from 'lucide-vue-next'
import { computed } from 'vue'
import { api, type CastMember, type SeriesModel } from '../api/client'
import { act, confirm, zoom } from '../composables/feedback'
import { castSheetJob, seriesBusy } from '../composables/live'
import { shortDate } from '../composables/ui'
import Switch from './Switch.vue'

const p = defineProps<{ series: SeriesModel; castSheet: string | null }>()
const emit = defineEmits<{ changed: [] }>()

const cast = computed(() => p.series.cast)
const waiting = computed(() => cast.value.filter((c) => !c.approved_at))
const rendering = computed(() => !!castSheetJob(p.series.slug))
const busy = computed(() => seriesBusy(p.series.slug))

// why the sheet can't be rendered now (null: it can)
const renderReason = computed(() => !cast.value.length ? 'add cast first'
  : !p.series.parts.length ? 'add a part first: the cast sheet renders through a part'
  : rendering.value ? 'the cast sheet is rendering' : busy.value ? 'a job is running in this series' : null)
// why a character can't be approved now
const approveReason = computed(() => !p.castSheet ? 'render the cast sheet first'
  : rendering.value ? 'wait for the new cast sheet' : busy.value ? 'a job is running in this series' : null)

async function renderSheet() {
  if (renderReason.value) return
  await act(() => api.submitJob(p.series.slug, p.series.parts[0], ['cast-sheet']), 'Cast sheet queued')
}
async function approve(c: CastMember) {
  if (await act(() => api.approveCast(p.series.slug, c.id), `${c.name} approved`)) emit('changed')
}
async function approveAll() {
  const n = waiting.value.length
  const ok = await confirm({
    title: `Approve all ${n} cast members?`,
    body: 'Only after checking every row of the cast sheet. An approval stays until that character’s look changes.',
    confirm: `Approve ${n}`,
  })
  if (!ok) return
  for (const c of waiting.value) {
    if (!(await act(() => api.approveCast(p.series.slug, c.id), `${c.name} approved`))) break
  }
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
        <button v-if="cast.length" class="btn btn-secondary" :disabled="!!renderReason" :title="renderReason ?? undefined" @click="renderSheet">
          <RefreshCw :size="16" :class="{ 'animate-spin': rendering }" aria-hidden="true" />
          {{ rendering ? 'Rendering…' : castSheet ? 'Re-render sheet' : 'Render cast sheet' }}
        </button>
        <button v-if="waiting.length > 1" class="btn btn-primary" :disabled="!!approveReason" :title="approveReason ?? undefined" @click="approveAll">
          <CheckCheck :size="16" aria-hidden="true" /> Approve all
        </button>
      </div>
    </div>

    <p v-if="!cast.length" class="mt-3 text-sm text-muted">
      No cast yet. Add characters with <code>cast-add</code>, or import cast JSON when creating a series.
    </p>

    <div v-else class="mt-5 grid items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <!-- the sheet is what approvals are judged on: it gets the room -->
      <figure class="min-w-0">
        <button v-if="castSheet" class="inset group relative block w-full cursor-zoom-in overflow-hidden p-3"
          aria-label="Zoom the cast sheet" @click="zoom(castSheet, 'Cast sheet')">
          <img :src="castSheet" alt="Cast sheet: one row per character, in the order listed" class="w-full rounded-sm"
            :class="{ 'opacity-50': rendering }" />
          <span class="absolute right-5 bottom-5 grid size-9 place-items-center rounded-full bg-panel text-ink opacity-0 shadow-[var(--shadow-raised)] transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
            <ZoomIn :size="16" aria-hidden="true" />
          </span>
        </button>
        <div v-else class="inset grid min-h-48 place-items-center gap-3 p-6 text-center">
          <ImageOff :size="24" class="text-faint" aria-hidden="true" />
          <p class="max-w-xs text-sm text-muted">
            {{ rendering ? 'Rendering the cast sheet: every character in every pose.' : 'No cast sheet yet. It shows every character in every pose, so you can approve their looks.' }}
          </p>
        </div>
        <figcaption v-if="castSheet" class="mt-2 text-xs text-muted">One row per character, top to bottom in the order listed. Click to zoom.</figcaption>
      </figure>

      <ol class="divide-y divide-[#e7e1d6]" aria-label="Cast approvals">
        <li v-for="(c, i) in cast" :key="c.id" class="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
          <span class="num w-5 shrink-0 text-right text-xs text-muted" :title="`row ${i + 1} of the cast sheet`">{{ i + 1 }}</span>
          <span class="size-5 shrink-0 rounded-full border-2 border-ink" :style="{ background: c.top.color }" aria-hidden="true" />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-semibold">{{ c.name }}</span>
            <span class="block truncate text-xs text-muted">{{ c.id }}</span>
          </span>
          <span v-if="c.approved_at" class="flex shrink-0 items-center gap-1 text-xs font-semibold text-green-ink">
            <Check :size="14" aria-hidden="true" /> {{ shortDate(c.approved_at) }}
          </span>
          <Switch class="shrink-0" :on="!!c.approved_at" :label="`Approve ${c.name}`" :reason="c.approved_at ? null : approveReason"
            @request="approve(c)"><span class="sr-only">{{ c.name }}</span></Switch>
        </li>
      </ol>
    </div>
  </section>
</template>
