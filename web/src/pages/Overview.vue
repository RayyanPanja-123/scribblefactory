<script setup lang="ts">
import { Clapperboard, Clock, HardDrive, Inbox, Layers, Sparkles } from 'lucide-vue-next'
import { computed } from 'vue'
import { api } from '../api/client'
import AreaChart from '../components/AreaChart.vue'
import Card from '../components/Card.vue'
import CountUp from '../components/CountUp.vue'
import Donut from '../components/Donut.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { label } from '../composables/ui'

const { data, error, loading, reload, refresh } = useApi(() => Promise.all([api.overview(), api.series()]))
refetchOn(() => null, () => null, refresh)

const kpis = computed(() => {
  if (!data.value) return []
  const [o, series] = data.value
  const k = o.kpi
  const months = o.posts_per_month
  const sum = (m?: { youtube: number; instagram: number }) => (m ? m.youtube + m.instagram : 0)
  const delta = sum(months.at(-1)) - sum(months.at(-2))
  const active = series.filter((s) => s.status === 'active').length
  return [
    { name: 'Series', value: k.series, icon: Layers, accent: ACCENTS.indigo,
      badge: `${active} active` },
    { name: 'Parts in progress', value: k.parts_in_progress, icon: Clapperboard, accent: ACCENTS.blue,
      badge: k.parts_in_progress ? 'in the works' : 'all finished' },
    { name: 'Waiting for you', value: k.waiting_for_approval, icon: Clock, accent: ACCENTS.amber,
      badge: k.waiting_for_approval ? 'needs you' : 'all clear' },
    { name: 'Posted this month', value: k.posted_this_month, icon: Sparkles, accent: ACCENTS.green,
      badge: delta > 0 ? `+${delta} vs last month` : delta < 0 ? `${delta} vs last month` : 'same as last month',
      tint: delta > 0 ? ACCENTS.green : delta < 0 ? DOWN : NEUTRAL }, // this badge follows the sign
  ]
})

// per-card identity: icon gradient a1 -> a2, badge = 12% tint + AA ink (docs/design.md)
const ACCENTS = {
  indigo: { a1: '#5b6cf0', a2: '#4453d6', bg: '#e8e8f4', ink: '#3a47c4' },
  blue: { a1: '#4f9cf7', a2: '#2f7be0', bg: '#e6eef5', ink: '#1d5fb5' },
  amber: { a1: '#f5b544', a2: '#c97a0a', bg: '#faf1e0', ink: '#875400' }, // white icon 3.35:1 on the dark stop
  green: { a1: '#3fbf7f', a2: '#23a063', bg: '#e4f2e7', ink: '#147045' },
}

const DOWN = { bg: '#f9e7df', ink: '#a8401f' } // red-orange #e8603c at 12%, ink 5.1:1
const NEUTRAL = { bg: '#edebe6', ink: '#5c584f' }

const titles = computed(() => new Map(data.value?.[1].map((s) => [s.slug, s.title])))
const disk = computed(() =>
  Object.entries(data.value?.[0].disk_usage ?? {}).map(([slug, value]) => ({ label: titles.value.get(slug) ?? slug, value })),
)
const waitLabel = (w: string) => (w.startsWith('cast:') ? `cast: ${w.slice(5)}` : label(w))
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />

  <div v-else-if="loading" class="space-y-6" aria-busy="true" aria-label="Loading overview">
    <div class="grid grid-cols-2 gap-6 xl:grid-cols-4"><div v-for="i in 4" :key="i" class="skeleton h-36" /></div>
    <div class="grid gap-6 xl:grid-cols-3"><div class="skeleton h-80 xl:col-span-2" /><div class="skeleton h-80" /></div>
    <div class="skeleton h-48" />
  </div>

  <div v-else-if="data" class="space-y-6">
    <section class="grid grid-cols-2 gap-6 xl:grid-cols-4" aria-label="Key numbers">
      <Card v-for="(k, i) in kpis" :key="k.name" :index="i" lift class="p-5">
        <div class="flex items-start justify-between">
          <p class="text-sm font-medium text-muted">{{ k.name }}</p>
          <span class="accent-icon" :style="{ '--a1': k.accent.a1, '--a2': k.accent.a2 }">
            <component :is="k.icon" :size="18" :stroke-width="2.25" aria-hidden="true" />
          </span>
        </div>
        <p class="mt-1 text-5xl"><CountUp :value="k.value" /></p>
        <span class="chip mt-3" :style="{ background: (k.tint ?? k.accent).bg, color: (k.tint ?? k.accent).ink }">{{ k.badge }}</span>
      </Card>
    </section>

    <section class="grid gap-6 xl:grid-cols-3">
      <Card :index="4" class="p-6 xl:col-span-2">
        <h2 class="font-display text-lg font-semibold">Posts per month</h2>
        <p class="text-sm text-muted">Last 12 months, YouTube and Instagram</p>
        <div class="inset mt-4 p-4"><AreaChart :months="data[0].posts_per_month" /></div>
      </Card>
      <Card :index="5" class="p-6">
        <h2 class="font-display text-lg font-semibold">Disk usage</h2>
        <p class="text-sm text-muted">Per series, frames included</p>
        <div class="inset mt-4 p-4">
          <Donut v-if="disk.some((d) => d.value)" :items="disk" />
          <EmptyState v-else :icon="HardDrive" title="Nothing on disk" text="Create a series to start filling the library." />
        </div>
      </Card>
    </section>

    <Card :index="6" class="p-6">
      <h2 class="font-display text-lg font-semibold">Waiting for you</h2>
      <p class="text-sm text-muted">Approvals with something ready to look at</p>
      <ul v-if="data[0].waiting.length" class="mt-4 space-y-3">
        <li v-for="w in data[0].waiting" :key="`${w.slug}/${w.part}`">
          <RouterLink :to="`/series/${w.slug}`" class="inset flex items-center gap-4 px-4 py-3 transition-colors hover:bg-[#e9e4da]">
            <span class="font-semibold">{{ titles.get(w.slug) ?? w.slug }}</span>
            <span class="text-sm text-muted">{{ w.part ? `Part ${Number(w.part.slice(5))}` : 'Cast' }}</span>
            <span class="ml-auto flex flex-wrap justify-end gap-2">
              <span v-for="x in w.waiting" :key="x" class="chip chip-amber">{{ waitLabel(x) }}</span>
            </span>
          </RouterLink>
        </li>
      </ul>
      <EmptyState v-else class="mt-4" :icon="Inbox" title="All caught up" text="Nothing needs your approval right now." />
    </Card>
  </div>
</template>
