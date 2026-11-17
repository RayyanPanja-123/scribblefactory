<script setup lang="ts">
import { ArrowLeft, Check, ChevronRight, Clock, FileQuestion, ImageOff, Instagram, Mic, Palette, Plus, Youtube } from 'lucide-vue-next'
import { api, type CastMember, type PartSummary } from '../api/client'
import Card from '../components/Card.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import StageChips from '../components/StageChips.vue'
import Switch from '../components/Switch.vue'
import { act, zoom } from '../composables/feedback'
import { jobs, refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { expandFrom, label, statusChip } from '../composables/ui'

const props = defineProps<{ slug: string }>()
const { data, error, loading, reload, refresh } = useApi(() => api.seriesDetail(props.slug))
refetchOn(() => props.slug, () => null, refresh)

const castBusy = () => jobs.value.some((j) => j.slug === props.slug && j.status === 'running')
async function approveCast(c: CastMember) {
  if (await act(() => api.approveCast(props.slug, c.id), `${c.name} approved`)) refresh()
}
/** remember the clicked card's rect: the part page expands its header from it */
function expand(e: MouseEvent, p: PartSummary) {
  expandFrom.rect = (e.currentTarget as HTMLElement).closest('.raised')!.getBoundingClientRect()
  expandFrom.key = `${props.slug}/${p.id}`
}

const APPROVALS = ['stills', 'test_render', 'final'] as const

function approval(p: PartSummary, a: string): [string, string] {
  if (p.approvals[a]) return ['chip-green', 'approved']
  if (p.waiting.includes(a)) return ['chip-amber', 'waiting for you']
  return ['', 'not ready']
}
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />

  <div v-else-if="loading" class="space-y-6" aria-busy="true" aria-label="Loading series">
    <div class="skeleton h-48" />
    <div v-for="i in 2" :key="i" class="skeleton h-40" />
  </div>

  <div v-else-if="data" class="space-y-6">
    <RouterLink to="/series" class="btn btn-secondary">
      <ArrowLeft :size="16" aria-hidden="true" /> All series
    </RouterLink>

    <Card class="p-6">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="font-display text-3xl font-semibold">{{ data.series.title }}</h2>
        <span class="chip" :class="statusChip(data.series.status)">{{ data.series.status }}</span>
        <span class="text-sm text-muted">{{ data.series.slug }}</span>
      </div>

      <div class="mt-5 grid gap-4 md:grid-cols-[1fr_auto_auto_auto]">
        <div id="cast">
          <p class="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Cast</p>
          <ul class="flex flex-wrap gap-2">
            <li v-for="c in data.series.cast" :key="c.id" class="inset flex items-center gap-2 rounded-full py-1.5 pr-3 pl-1.5">
              <span class="size-6 shrink-0 rounded-full border-2 border-ink" :style="{ background: c.top.color }" aria-hidden="true" />
              <Switch :on="!!c.approved_at" :label="c.name"
                :reason="c.approved_at ? null : !data.cast_sheet ? 'render the cast sheet first' : castBusy() ? 'a job is running in this series' : null"
                @request="approveCast(c)">
                {{ c.name }}
                <span v-if="!c.approved_at" class="chip chip-amber ml-1">needs approval</span>
              </Switch>
            </li>
            <li v-if="!data.series.cast.length" class="text-sm text-muted">No cast yet.</li>
          </ul>
        </div>
        <button v-if="data.cast_sheet" class="inset group cursor-zoom-in p-2" aria-label="Zoom the cast sheet"
          @click="zoom(data.cast_sheet, 'Cast sheet')">
          <img :src="data.cast_sheet" alt="Cast sheet" class="h-24 rounded-sm transition-transform group-hover:scale-[1.03]" />
        </button>
        <div v-else class="inset grid place-items-center gap-1 px-4 text-xs text-muted">
          <ImageOff :size="18" class="text-faint" aria-hidden="true" />no cast sheet
        </div>
        <div class="inset px-4 py-3">
          <p class="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted uppercase"><Mic :size="14" aria-hidden="true" />Voice</p>
          <p class="mt-1 text-sm font-semibold">{{ data.series.voice.voice_name || 'not set' }}</p>
          <p class="text-xs text-muted">{{ data.series.voice.provider }}</p>
        </div>
        <div class="inset px-4 py-3">
          <p class="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted uppercase"><Palette :size="14" aria-hidden="true" />Style</p>
          <p class="mt-1 text-sm font-semibold">{{ data.series.style.preset }}</p>
          <p class="text-xs text-muted">
            {{ data.series.style.locked ? 'locked' : 'unlocked' }} · captions {{ data.series.style.captions ? 'on' : 'off' }}
          </p>
        </div>
      </div>
    </Card>

    <section class="space-y-4" aria-label="Parts">
      <div class="flex items-center gap-3">
        <h3 class="font-display text-xl font-semibold">Parts</h3>
        <RouterLink :to="`/series/${slug}/new-part`" class="btn btn-primary ml-auto"><Plus :size="16" aria-hidden="true" /> New part</RouterLink>
      </div>
      <EmptyState v-if="!data.parts.length" :icon="FileQuestion" title="No parts yet" text="Add one with the New part button." />
      <Card v-for="(p, i) in data.parts" :key="p.id" :index="i" :lift="!p.missing" :press="!p.missing">
        <p v-if="p.missing" class="p-5 text-sm text-muted">{{ p.id }}: part.json is missing</p>
        <RouterLink v-else :to="`/series/${slug}/${p.id}`" class="block p-5" @click="expand($event, p)">
          <div class="flex flex-wrap items-center gap-3">
            <span class="num text-2xl text-muted">{{ String(p.number).padStart(2, '0') }}</span>
            <h4 class="font-display text-lg font-semibold">{{ p.title }}</h4>
            <span class="ml-auto flex items-center gap-3 text-faint">
              <ChevronRight :size="18" class="order-last" aria-hidden="true" />
              <Youtube :size="18" :class="{ 'text-youtube': p.posted?.youtube }"
                :aria-label="p.posted?.youtube ? 'posted on YouTube' : 'not on YouTube'" />
              <Instagram :size="18" :class="{ 'text-instagram': p.posted?.instagram }"
                :aria-label="p.posted?.instagram ? 'posted on Instagram' : 'not on Instagram'" />
            </span>
          </div>

          <StageChips class="mt-4" :stages="p.stages" />

          <div class="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <span class="mr-1 text-muted">Approvals</span>
            <span v-for="a in APPROVALS" :key="a" class="chip" :class="approval(p, a)[0]" :title="approval(p, a)[1]">
              <Check v-if="p.approvals[a]" :size="14" aria-hidden="true" />
              <Clock v-else-if="p.waiting.includes(a)" :size="14" aria-hidden="true" />
              {{ label(a) }}<span class="sr-only">: {{ approval(p, a)[1] }}</span>
            </span>
          </div>
        </RouterLink>
      </Card>
    </section>
  </div>
</template>
