<script setup lang="ts">
import { ArrowLeft, Check, Clock, FileQuestion, Instagram, Mic, Palette, Youtube } from 'lucide-vue-next'
import { api, type PartSummary } from '../api/client'
import Card from '../components/Card.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { useApi } from '../composables/useApi'
import { label, statusChip } from '../composables/ui'

const props = defineProps<{ slug: string }>()
const { data, error, loading, reload } = useApi(() => api.seriesDetail(props.slug))

const SHORT: Record<string, string> = { import_check: 'import', thumbnails: 'thumbs' }
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

      <div class="mt-5 grid gap-4 md:grid-cols-[1fr_auto_auto]">
        <div>
          <p class="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Cast</p>
          <ul class="flex flex-wrap gap-2">
            <li v-for="c in data.series.cast" :key="c.id" class="inset flex items-center gap-2 rounded-full py-1.5 pr-2 pl-1.5">
              <span class="size-6 rounded-full border-2 border-ink" :style="{ background: c.top.color }" aria-hidden="true" />
              <span class="text-sm font-semibold">{{ c.name }}</span>
              <span v-if="c.approved_at" class="chip chip-green px-1.5!" :title="`${c.name} approved`">
                <Check :size="14" aria-hidden="true" /><span class="sr-only">approved</span>
              </span>
              <span v-else class="chip chip-amber">needs approval</span>
            </li>
            <li v-if="!data.series.cast.length" class="text-sm text-muted">No cast yet.</li>
          </ul>
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
      <h3 class="font-display text-xl font-semibold">Parts</h3>
      <EmptyState v-if="!data.parts.length" :icon="FileQuestion" title="No parts yet"
        :text="`Add one with: new-part ${data.series.slug}`" />
      <Card v-for="(p, i) in data.parts" :key="p.id" :index="i" lift class="p-5">
        <p v-if="p.missing" class="text-sm text-muted">{{ p.id }}: part.json is missing</p>
        <template v-else>
          <div class="flex flex-wrap items-center gap-3">
            <span class="num text-2xl text-faint">{{ String(p.number).padStart(2, '0') }}</span>
            <h4 class="font-display text-lg font-semibold">{{ p.title }}</h4>
            <span class="ml-auto flex items-center gap-3 text-faint">
              <Youtube :size="18" :class="{ 'text-red': p.posted?.youtube }"
                :aria-label="p.posted?.youtube ? 'posted on YouTube' : 'not on YouTube'" />
              <Instagram :size="18" :class="{ 'text-[#9a6ff0]': p.posted?.instagram }"
                :aria-label="p.posted?.instagram ? 'posted on Instagram' : 'not on Instagram'" />
            </span>
          </div>

          <ol class="inset mt-4 flex flex-wrap gap-2 p-3" aria-label="Stages">
            <li v-for="(status, stage) in p.stages" :key="stage" class="chip" :class="statusChip(status)"
              :title="`${label(String(stage))}: ${status}`">
              <span class="size-1.5 rounded-full bg-current" :class="{ pulse: status === 'running' }" aria-hidden="true" />
              {{ SHORT[stage] ?? stage }}<span class="sr-only">: {{ status }}</span>
            </li>
          </ol>

          <div class="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <span class="mr-1 text-muted">Approvals</span>
            <span v-for="a in APPROVALS" :key="a" class="chip" :class="approval(p, a)[0]" :title="approval(p, a)[1]">
              <Check v-if="p.approvals[a]" :size="14" aria-hidden="true" />
              <Clock v-else-if="p.waiting.includes(a)" :size="14" aria-hidden="true" />
              {{ label(a) }}<span class="sr-only">: {{ approval(p, a)[1] }}</span>
            </span>
          </div>
        </template>
      </Card>
    </section>
  </div>
</template>
