<script setup lang="ts">
import { ChevronRight, Inbox } from 'lucide-vue-next'
import { computed } from 'vue'
import { api } from '../api/client'
import Card from '../components/Card.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { label } from '../composables/ui'

// Everything waiting for my approval, across all series; each row deep-links to the part's section.
const { data, error, loading, reload, refresh } = useApi(() => Promise.all([api.overview(), api.series()]))
refetchOn(() => null, () => null, refresh)

const SECTION: Record<string, string> = { stills: 'review', test_render: 'approvals', final: 'approvals' }
const rows = computed(() => {
  if (!data.value) return []
  const titles = new Map(data.value[1].map((s) => [s.slug, s.title]))
  return data.value[0].waiting.flatMap((w) =>
    w.waiting.map((what) => {
      const cast = what.startsWith('cast:')
      return {
        key: `${w.slug}/${w.part}/${what}`,
        series: titles.get(w.slug) ?? w.slug,
        where: w.part ? `Part ${Number(w.part.slice(5))}` : 'Cast',
        what: cast ? `cast: ${what.slice(5)}` : label(what),
        hint: cast ? 'check the cast sheet, then approve' : what === 'final' ? 'watch final.mp4 to the end' : `look at the ${label(what)}`,
        to: w.part ? `/series/${w.slug}/${w.part}#${SECTION[what] ?? 'approvals'}` : `/series/${w.slug}#cast`,
      }
    }))
})
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="space-y-4" aria-busy="true" aria-label="Loading review">
    <div v-for="i in 3" :key="i" class="skeleton h-20" />
  </div>
  <div v-else class="space-y-5">
    <div class="flex items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Review</h2>
      <span class="text-sm text-muted">{{ rows.length }} waiting for you</span>
    </div>
    <EmptyState v-if="!rows.length" :icon="Inbox" title="All caught up" text="Nothing needs your approval right now." />
    <Card v-for="(r, i) in rows" :key="r.key" :index="i" lift press>
      <RouterLink :to="r.to" class="flex items-center gap-4 px-6 py-4">
        <span class="chip chip-amber">{{ r.what }}</span>
        <span class="min-w-0">
          <span class="block font-semibold">{{ r.series }} <span class="font-normal text-muted">· {{ r.where }}</span></span>
          <span class="block text-sm text-muted">{{ r.hint }}</span>
        </span>
        <ChevronRight :size="20" class="ml-auto shrink-0 text-faint" aria-hidden="true" />
      </RouterLink>
    </Card>
  </div>
</template>
