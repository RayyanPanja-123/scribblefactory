<script setup lang="ts">
// The gallery: series posted everywhere and moved out of the working library (the series page's Move to gallery).
// Each series is an X-sheet title block, then its parts as ruled rows: number, title and its YouTube and Instagram
// posts. Everything else of the series was deleted to free the disk.
import { Images, Instagram, Youtube } from 'lucide-vue-next'
import { computed } from 'vue'
import { api, type GalleryEntry } from '../api/client'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { useApi } from '../composables/useApi'
import { bytes, shortDate } from '../composables/ui'

const { data, error, loading, reload } = useApi(() => api.gallery())
const totals = computed(() => {
  const list = data.value ?? []
  return { series: list.length, parts: list.reduce((n, e) => n + e.parts.length, 0), freed: list.reduce((n, e) => n + e.freed_bytes, 0) }
})
type Part = GalleryEntry['parts'][number]
const POSTS = [
  { key: 'youtube', name: 'YouTube', icon: Youtube, color: 'text-youtube' },
  { key: 'instagram', name: 'Instagram', icon: Instagram, color: 'text-instagram' },
] as const
const two = (n: number) => String(n).padStart(2, '0')
const label = (p: Part) => `Part ${p.number}: ${p.title}`
</script>

<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-end gap-x-8 gap-y-3">
      <div class="min-w-0 flex-1">
        <h2 class="font-display text-2xl font-semibold">Gallery</h2>
        <p class="mt-1 text-sm text-muted">Series posted everywhere: their titles and links stay, the heavy files are gone.</p>
      </div>
      <dl v-if="totals.series" class="flex divide-x divide-rule rounded-md border border-rule bg-panel text-sm">
        <div class="px-4 py-2"><dt class="colhead">Series</dt><dd class="num">{{ totals.series }}</dd></div>
        <div class="px-4 py-2"><dt class="colhead">Parts</dt><dd class="num">{{ totals.parts }}</dd></div>
        <div class="px-4 py-2"><dt class="colhead">Disk freed</dt><dd class="num">{{ bytes(totals.freed) }}</dd></div>
      </dl>
    </header>

    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading the gallery" />
    <EmptyState v-else-if="!data?.length" :icon="Images" title="Nothing in the gallery yet"
      text="Once every part of a series is posted to YouTube or Instagram, Move to gallery on the series page keeps its titles and links here and frees the disk." />

    <section v-for="e in data" v-else :key="e.slug" class="raised overflow-hidden" :aria-labelledby="`gallery-${e.slug}`">
      <!-- the title block: the sheet's header fields -->
      <div class="flex flex-wrap items-stretch border-b border-rule">
        <h3 :id="`gallery-${e.slug}`" class="min-w-0 flex-1 basis-64 px-6 py-4 font-display text-xl leading-snug font-semibold text-balance">
          {{ e.title }}
        </h3>
        <dl class="flex divide-x divide-rule border-rule text-sm max-sm:w-full max-sm:border-t sm:border-l">
          <div class="flex-1 px-5 py-3"><dt class="colhead">Parts</dt><dd class="num">{{ e.parts.length }}</dd></div>
          <div class="flex-1 px-5 py-3"><dt class="colhead">Moved</dt><dd class="num whitespace-nowrap">{{ shortDate(e.moved_at) }}</dd></div>
          <div class="flex-1 px-5 py-3"><dt class="colhead">Freed</dt><dd class="num whitespace-nowrap">{{ bytes(e.freed_bytes) }}</dd></div>
        </dl>
      </div>

      <!-- the parts -->
      <ol class="divide-y divide-rule">
        <li v-for="p in e.parts" :key="p.id" class="flex flex-wrap items-center gap-x-4 gap-y-2 px-6 py-3">
          <p class="flex min-w-0 flex-1 basis-56 items-baseline gap-3">
            <span class="font-display text-lg leading-none text-blue-ink" aria-hidden="true">{{ two(p.number) }}</span>
            <span class="truncate text-sm font-semibold" :title="p.title">{{ p.title }}</span>
          </p>
          <ul class="posts" :aria-label="`Where ${label(p)} is posted`">
            <li v-for="s in POSTS.filter((x) => p[x.key])" :key="s.key">
              <a :href="p[s.key]!.url" target="_blank" rel="noopener noreferrer" class="post"
                :aria-label="`${s.name}, posted ${shortDate(p[s.key]!.posted_at)} (opens in a new tab)`">
                <span class="post-circle" :class="s.color"><component :is="s.icon" :size="16" aria-hidden="true" /></span>
                <span class="post-date num" aria-hidden="true">{{ shortDate(p[s.key]!.posted_at) }}</span>
              </a>
            </li>
          </ul>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
/* where it's posted: one round icon button per site, its date beside it */
.posts { display: flex; gap: 1.5rem; }
.post { display: flex; align-items: center; gap: 0.5rem; border-radius: var(--radius-md); padding: 0.25rem; }
.post-circle {
  display: grid; place-items: center; width: 2rem; height: 2rem; border-radius: 9999px;
  background: var(--color-panel); border: 1px solid var(--color-rule-strong);
  transition: border-color 0.15s ease, background-color 0.15s ease;
}
.post:hover .post-circle, .post:focus-visible .post-circle { border-color: currentColor; background: var(--color-well); }
.post:focus-visible { outline: 2px solid var(--color-blue); outline-offset: 2px; }
.post-date { font-size: 12px; white-space: nowrap; color: var(--color-muted); }
.post:hover .post-date { color: var(--color-ink); }
</style>
