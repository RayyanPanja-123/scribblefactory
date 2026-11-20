<script setup lang="ts">
import { ArrowRight, Clapperboard, HardDrive, ImageOff, Instagram, Plus, SearchX, Youtube } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import Card from '../components/Card.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { bytes, search, statusChip } from '../composables/ui'

const { data, error, loading, reload, refresh } = useApi(api.series)
refetchOn(() => null, () => null, refresh)
const status = ref<'all' | 'draft' | 'active' | 'complete' | 'archived'>('all')
const shown = computed(() => {
  const q = search.value.trim().toLowerCase()
  return [...(data.value ?? [])]
    .filter((s) => (status.value === 'all' || s.status === status.value)
      && (!q || s.title.toLowerCase().includes(q) || s.slug.includes(q)))
    .sort((a, b) => b.created_at.localeCompare(a.created_at) || a.slug.localeCompare(b.slug))
})
const filtered = computed(() => !!search.value.trim() || status.value !== 'all')
function clearFilters() { search.value = ''; status.value = 'all' }
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />

  <div v-else-if="loading" class="space-y-6" aria-busy="true" aria-label="Loading series">
    <div v-for="i in 3" :key="i" class="skeleton h-44" />
  </div>

  <template v-else-if="data">
    <div class="mb-5 flex flex-wrap items-center gap-3">
      <h2 class="font-display text-2xl font-semibold">Series</h2>
      <span class="text-sm text-muted">{{ shown.length }} of {{ data.length }}</span>
      <RouterLink to="/new-series" class="btn btn-primary ml-auto"><Plus :size="16" aria-hidden="true" /> New series</RouterLink>
    </div>
    <form class="raised mb-5 flex flex-wrap items-end gap-3 p-4" aria-label="Filter series" @submit.prevent>
      <label class="min-w-48 flex-1 text-xs font-semibold text-muted">Search
        <input v-model="search" type="search" placeholder="Title or slug" class="inset mt-1 block h-10 w-full rounded-md px-4 text-sm font-normal text-ink outline-none focus:border-blue" />
      </label>
      <label class="min-w-40 text-xs font-semibold text-muted">Status
        <select v-model="status" class="inset mt-1 block h-10 w-full rounded-md px-4 text-sm font-normal text-ink outline-none focus:border-blue">
          <option value="all">All statuses</option>
          <option value="draft">Draft</option>
          <option value="active">Active</option>
          <option value="complete">Complete</option>
          <option value="archived">Archived</option>
        </select>
      </label>
      <button v-if="filtered" type="button" class="btn btn-secondary" @click="clearFilters">Clear</button>
    </form>
    <EmptyState v-if="!data.length" :icon="Clapperboard" title="No series yet"
      text="Start one with the New series button." />
    <EmptyState v-else-if="!shown.length" :icon="SearchX" title="No match" :text="`Nothing matches “${search}”.`" />
    <div v-else class="space-y-4" role="list">
      <Card v-for="(s, i) in shown" :key="s.slug" role="listitem" :index="i" lift
        class="relative flex items-center gap-4 p-3 sm:gap-6">
        <div class="flex min-w-0 flex-1 items-center gap-4 sm:gap-6">
          <div class="inset aspect-[9/16] w-20 shrink-0 overflow-hidden p-1.5 sm:w-24">
            <img v-if="s.cover" :src="s.cover" alt="" loading="lazy" class="size-full rounded-[10px] object-cover" />
            <div v-else class="grid size-full place-items-center text-faint"><ImageOff :size="24" aria-hidden="true" /></div>
          </div>
  
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
              <!-- the title link covers the whole row (after:inset-0); the actions sit above it -->
              <RouterLink :to="`/series/${s.slug}`"
                class="font-display text-xl leading-tight font-semibold text-balance after:absolute after:inset-0 after:rounded-[inherit] after:content-['']">
                {{ s.title }}
              </RouterLink>
              <span class="chip" :class="statusChip(s.status)">{{ s.status }}</span>
            </div>
            <p class="mt-0.5 text-sm text-muted">{{ s.slug }}</p>
            <dl class="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm whitespace-nowrap text-muted">
              <div class="flex items-baseline gap-1.5"><dt class="sr-only">Parts</dt>
                <dd class="num font-display text-lg font-semibold text-ink">{{ s.part_count }}</dd>{{ s.part_count === 1 ? 'part' : 'parts' }}</div>
              <div class="flex items-center gap-1.5" :title="`${s.posted.youtube} posted on YouTube`"><dt class="sr-only">YouTube</dt>
                <Youtube :size="16" :class="s.posted.youtube ? 'text-youtube' : 'text-faint'" aria-hidden="true" /><dd class="num">{{ s.posted.youtube }}</dd></div>
              <div class="flex items-center gap-1.5" :title="`${s.posted.instagram} posted on Instagram`"><dt class="sr-only">Instagram</dt>
                <Instagram :size="16" :class="s.posted.instagram ? 'text-instagram' : 'text-faint'" aria-hidden="true" /><dd class="num">{{ s.posted.instagram }}</dd></div>
              <div class="flex items-center gap-1.5"><dt class="sr-only">Disk</dt>
                <HardDrive :size="14" class="text-faint" aria-hidden="true" /><dd class="num">{{ bytes(s.disk_usage) }}</dd></div>
            </dl>
          </div>
        </div>

        <div class="relative z-10 flex shrink-0 flex-col items-end justify-between gap-3 self-stretch py-1 pr-1 sm:pr-3">
          <RouterLink :to="`/series/${s.slug}/new-part`" class="btn btn-secondary">
            <Plus :size="16" aria-hidden="true" /> New part
          </RouterLink>
          <RouterLink :to="`/series/${s.slug}`" class="btn btn-primary" aria-label="Open series">
            Open <ArrowRight :size="16" aria-hidden="true" />
          </RouterLink>
        </div>
      </Card>
    </div>
  </template>
</template>
