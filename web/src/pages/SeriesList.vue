<script setup lang="ts">
import { Clapperboard, HardDrive, ImageOff, Instagram, SearchX, Youtube } from 'lucide-vue-next'
import { computed } from 'vue'
import { api } from '../api/client'
import Card from '../components/Card.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { useApi } from '../composables/useApi'
import { bytes, search, statusChip } from '../composables/ui'

const { data, error, loading, reload } = useApi(api.series)
const shown = computed(() => {
  const q = search.value.trim().toLowerCase()
  return (data.value ?? []).filter((s) => !q || s.title.toLowerCase().includes(q) || s.slug.includes(q))
})
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />

  <div v-else-if="loading" class="grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-6" aria-busy="true" aria-label="Loading series">
    <div v-for="i in 4" :key="i" class="skeleton h-[520px]" />
  </div>

  <template v-else-if="data">
    <div class="mb-5 flex items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Series</h2>
      <span class="text-sm text-muted">{{ shown.length }} of {{ data.length }}</span>
    </div>
    <EmptyState v-if="!data.length" :icon="Clapperboard" title="No series yet"
      text="Create one with: python -m pipeline.scribble.cli new-series <slug> --title ..." />
    <EmptyState v-else-if="!shown.length" :icon="SearchX" title="No match" :text="`Nothing matches “${search}”.`" />
    <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-6">
      <Card v-for="(s, i) in shown" :key="s.slug" :index="i" lift press class="p-3">
        <RouterLink :to="`/series/${s.slug}`" class="block rounded-[inherit]">
          <div class="inset aspect-[9/16] overflow-hidden p-1.5">
            <img v-if="s.cover" :src="s.cover" :alt="`${s.title} cover`" loading="lazy"
              class="size-full rounded-[10px] object-cover" />
            <div v-else class="grid size-full place-items-center text-faint"><ImageOff :size="28" aria-hidden="true" /></div>
          </div>
          <div class="px-2 pt-4 pb-2">
            <div class="flex items-start gap-2">
              <h3 class="min-w-0 flex-1 font-display text-lg leading-tight font-semibold">{{ s.title }}</h3>
              <span class="chip" :class="statusChip(s.status)">{{ s.status }}</span>
            </div>
            <div class="mt-3 flex items-center gap-3 text-sm text-muted">
              <span>{{ s.part_count }} {{ s.part_count === 1 ? 'part' : 'parts' }}</span>
              <span class="flex items-center gap-1" :title="`${s.posted.youtube} on YouTube`">
                <Youtube :size="16" :class="s.posted.youtube ? 'text-red' : 'text-faint'" aria-hidden="true" />
                <span class="sr-only">YouTube</span>{{ s.posted.youtube }}
              </span>
              <span class="flex items-center gap-1" :title="`${s.posted.instagram} on Instagram`">
                <Instagram :size="16" :class="s.posted.instagram ? 'text-[#9a6ff0]' : 'text-faint'" aria-hidden="true" />
                <span class="sr-only">Instagram</span>{{ s.posted.instagram }}
              </span>
              <span class="ml-auto flex items-center gap-1"><HardDrive :size="14" aria-hidden="true" />{{ bytes(s.disk_usage) }}</span>
            </div>
          </div>
        </RouterLink>
      </Card>
    </div>
  </template>
</template>
