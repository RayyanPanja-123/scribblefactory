<script setup lang="ts">
// Series page: loads the series and lays it out. The cast workflow lives in CastPanel, each part in PartCard,
// and what to do next is lib/seriesNext (pure, tested).
import { ArrowLeft, ArrowRight, CircleCheck, FileQuestion, Plus } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import CastPanel from '../components/CastPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import PartCard from '../components/PartCard.vue'
import { castSheetJob, refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { statusChip } from '../composables/ui'
import { seriesNext } from '../lib/seriesNext'

const props = defineProps<{ slug: string }>()
const { data, error, loading, reload, refresh } = useApi(() => api.seriesDetail(props.slug))
refetchOn(() => props.slug, () => null, refresh)

const castPanel = ref<InstanceType<typeof CastPanel>>()
const series = computed(() => data.value?.series)

const next = computed(() => {
  const d = data.value
  if (!d) return null
  return seriesNext({
    cast: d.series.cast.length,
    castApproved: d.series.cast.filter((c) => c.approved_at).length,
    castSheet: !!d.cast_sheet,
    sheetRendering: !!castSheetJob(props.slug),
    parts: d.parts.filter((p) => !p.missing).map((p) => ({
      id: p.id, number: p.number ?? 0, waiting: p.waiting,
      finished: !!p.approvals.final, started: Object.values(p.stages).some((s) => s === 'done'),
    })),
  })
})

// the series facts, one compact line under the title
const facts = computed(() => {
  const s = series.value
  if (!s) return []
  return [
    { k: 'Slug', v: s.slug },
    { k: 'Parts', v: String(s.parts.length) },
    { k: 'Style', v: `${s.style.preset}${s.style.locked ? ' (locked)' : ''}`, hint: `captions ${s.style.captions ? 'on' : 'off'}` },
  ]
})
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />

  <div v-else-if="loading" class="space-y-6" aria-busy="true" aria-label="Loading series">
    <div class="skeleton h-40" />
    <div class="skeleton h-72" />
    <div class="skeleton h-40" />
  </div>

  <div v-else-if="data && series" class="space-y-8">
    <RouterLink to="/series" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> All series</RouterLink>

    <!-- who this series is, and the one thing to do next -->
    <header class="raised grid gap-6 p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)] lg:items-center">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="font-display text-3xl font-semibold text-balance">{{ series.title }}</h2>
          <span class="chip" :class="statusChip(series.status)">{{ series.status }}</span>
        </div>
        <dl class="mt-4 flex flex-wrap gap-x-6 gap-y-3 text-sm">
          <div v-for="f in facts" :key="f.k" class="min-w-0">
            <dt class="text-xs text-muted">{{ f.k }}</dt>
            <dd class="truncate font-semibold text-ink">
              {{ f.v }}<span v-if="f.hint" class="font-normal text-muted"> · {{ f.hint }}</span>
            </dd>
          </div>
        </dl>
      </div>

      <div v-if="next" class="inset flex items-start gap-3 p-4" role="status" aria-live="polite">
        <CircleCheck v-if="next.kind === 'done'" :size="20" class="mt-0.5 shrink-0 text-green-ink" aria-hidden="true" />
        <span v-else class="mt-1.5 size-2.5 shrink-0 rounded-full" :class="next.kind === 'wait' ? 'pulse bg-blue' : 'bg-amber'" aria-hidden="true" />
        <div class="min-w-0 flex-1">
          <p class="text-xs font-semibold text-muted">Next step</p>
          <p class="mt-0.5 text-sm text-ink">{{ next.text }}</p>
          <div class="mt-3 flex flex-wrap gap-2 whitespace-nowrap">
            <button v-if="next.kind === 'render-sheet'" class="btn btn-primary" @click="castPanel?.renderSheet()">
              Render cast sheet <ArrowRight :size="16" aria-hidden="true" />
            </button>
            <a v-else-if="next.kind === 'approve-cast'" href="#cast" class="btn btn-primary">
              Go to the cast <ArrowRight :size="16" aria-hidden="true" />
            </a>
            <RouterLink v-else-if="next.kind === 'add-part'" :to="`/series/${slug}/new-part`" class="btn btn-primary">
              <Plus :size="16" aria-hidden="true" /> New part
            </RouterLink>
            <RouterLink v-else-if="next.kind === 'open-part'" :to="`/series/${slug}/${next.part}`" class="btn btn-primary">
              {{ next.action }} <ArrowRight :size="16" aria-hidden="true" />
            </RouterLink>
          </div>
        </div>
      </div>
    </header>

    <CastPanel ref="castPanel" :series="series" :cast-sheet="data.cast_sheet" @changed="refresh" />

    <section class="space-y-4" aria-labelledby="parts-title">
      <div class="flex items-center gap-3">
        <h3 id="parts-title" class="font-display text-xl font-semibold">Parts</h3>
        <span v-if="data.parts.length" class="num text-sm text-muted">{{ data.parts.length }}</span>
        <RouterLink :to="`/series/${slug}/new-part`" class="btn btn-secondary ml-auto"><Plus :size="16" aria-hidden="true" /> New part</RouterLink>
      </div>
      <EmptyState v-if="!data.parts.length" :icon="FileQuestion" title="No parts yet"
        text="A part is one short: write its story, record the voice, and the factory does the rest." />
      <PartCard v-for="(p, i) in data.parts" :key="p.id" :slug="slug" :part="p" :index="i" />
    </section>
  </div>
</template>
