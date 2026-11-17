<script setup lang="ts">
import { ExternalLink, Instagram, Send, Youtube } from 'lucide-vue-next'
import { computed } from 'vue'
import { api, type PartSummary, type Platform } from '../api/client'
import Card from '../components/Card.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { shortDate } from '../composables/ui'

// Every part with its YouTube / Instagram links. A finished part without a link is flagged "missing".
const { data, error, loading, reload, refresh } = useApi(async () => {
  const list = await api.series()
  return Promise.all(list.map((s) => api.seriesDetail(s.slug)))
})
refetchOn(() => null, () => null, refresh)

const rows = computed(() =>
  (data.value ?? []).flatMap((s) => s.parts.filter((p) => !p.missing).map((p) => ({ s: s.series, p }))))
const counts = computed(() => ({
  youtube: rows.value.filter((r) => r.p.posted?.youtube).length,
  instagram: rows.value.filter((r) => r.p.posted?.instagram).length,
}))
const finished = (p: PartSummary) => p.stages.finish === 'done'
const PLATFORMS: { key: Platform; name: string; icon: typeof Youtube; color: string }[] = [
  { key: 'youtube', name: 'YouTube', icon: Youtube, color: 'text-youtube' },
  { key: 'instagram', name: 'Instagram', icon: Instagram, color: 'text-instagram' },
]
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading posted" />
  <div v-else class="space-y-5">
    <div class="flex items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Posted</h2>
      <span class="text-sm text-muted">{{ counts.youtube }} on YouTube · {{ counts.instagram }} on Instagram · {{ rows.length }} parts</span>
    </div>
    <EmptyState v-if="!rows.length" :icon="Send" title="No parts yet" text="Parts show up here once a series has some." />
    <Card v-else class="overflow-hidden p-2">
      <table class="w-full text-left text-sm">
        <thead>
          <tr class="text-xs tracking-wide text-muted uppercase">
            <th class="px-4 py-3 font-semibold">Series</th>
            <th class="px-4 py-3 font-semibold">Part</th>
            <th v-for="pl in PLATFORMS" :key="pl.key" class="px-4 py-3 font-semibold">
              <span class="flex items-center gap-1.5"><component :is="pl.icon" :size="14" :class="pl.color" aria-hidden="true" />{{ pl.name }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="`${r.s.slug}/${r.p.id}`" class="border-t border-[#ebe6dc]">
            <td class="px-4 py-3 font-semibold">{{ r.s.title }}</td>
            <td class="px-4 py-3">
              <RouterLink :to="`/series/${r.s.slug}/${r.p.id}#posting`" class="hover:underline">
                {{ String(r.p.number).padStart(2, '0') }} <span class="text-muted">{{ r.p.title }}</span>
              </RouterLink>
            </td>
            <td v-for="pl in PLATFORMS" :key="pl.key" class="px-4 py-3">
              <template v-if="r.p.posted?.[pl.key]">
                <a :href="r.p.posted[pl.key]!.url" target="_blank" rel="noopener noreferrer"
                  class="inline-flex items-center gap-1 font-semibold text-blue-ink hover:underline">
                  {{ shortDate(r.p.posted[pl.key]!.posted_at) }} <ExternalLink :size="12" aria-hidden="true" />
                  <span class="sr-only">open on {{ pl.name }}</span>
                </a>
              </template>
              <span v-else-if="finished(r.p)" class="chip chip-amber">missing</span>
              <span v-else class="chip">not finished</span>
            </td>
          </tr>
        </tbody>
      </table>
    </Card>
  </div>
</template>
