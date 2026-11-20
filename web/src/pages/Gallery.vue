<script setup lang="ts">
// The gallery: series posted everywhere and moved out of the working library (the series page's Move to gallery).
// Each series is a contact sheet: an X-sheet title block, then its parts as prints laid on ruled paper, each with its
// chosen thumbnail and its YouTube and Instagram posts. Everything else of the series was deleted to free the disk.
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
const file = (slug: string, path: string) => `/api/gallery/${encodeURIComponent(slug)}/${path.split('/').map(encodeURIComponent).join('/')}`
type Part = GalleryEntry['parts'][number]
const POSTS = [
  { key: 'youtube', name: 'YouTube', icon: Youtube, color: 'text-youtube' },
  { key: 'instagram', name: 'Instagram', icon: Instagram, color: 'text-instagram' },
] as const
// prints laid by hand: a slight, fixed tilt per position (never random: the sheet looks the same on every visit)
const TILT = ['-0.8deg', '0.6deg', '-0.3deg', '0.9deg', '-0.6deg', '0.4deg']
const two = (n: number) => String(n).padStart(2, '0')
const label = (p: Part) => `Part ${p.number}: ${p.title}`
</script>

<template>
  <div class="max-w-6xl space-y-6">
    <header class="flex flex-wrap items-end gap-x-8 gap-y-3">
      <div class="min-w-0 flex-1">
        <h2 class="font-display text-2xl font-semibold">Gallery</h2>
        <p class="mt-1 text-sm text-muted">Series posted everywhere: their thumbnails and links stay, the heavy files are gone.</p>
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
      text="Once every part of a series is posted to YouTube and Instagram, Move to gallery on the series page keeps its thumbnails and links here and frees the disk." />

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

      <!-- the prints -->
      <ol class="paper prints">
        <li v-for="(p, i) in e.parts" :key="p.id" class="print min-w-0" :style="{ '--tilt': TILT[i % TILT.length] }">
          <p class="caption">
            <span class="font-display text-lg leading-none text-blue-ink" aria-hidden="true">{{ two(p.number) }}</span>
            <span class="caption-title text-sm font-semibold" :title="p.title">{{ p.title }}</span>
          </p>
          <a :href="p.youtube.url" target="_blank" rel="noopener noreferrer" class="frame block rounded-md bg-panel p-1.5"
            :aria-label="`${label(p)}, watch on YouTube`">
            <img v-if="p.thumbnail" :src="file(e.slug, p.thumbnail)" alt="" loading="lazy" decoding="async"
              class="aspect-[9/16] w-full rounded-sm bg-well object-cover" />
            <span v-else class="grid aspect-[9/16] w-full place-items-center rounded-sm bg-well px-3 text-center text-xs text-muted">no thumbnail kept</span>
          </a>
          <ul class="posts" :aria-label="`Where ${label(p)} is posted`">
            <li v-for="s in POSTS" :key="s.key">
              <a :href="p[s.key].url" target="_blank" rel="noopener noreferrer" class="post"
                :aria-label="`${s.name}, posted ${shortDate(p[s.key].posted_at)} (opens in a new tab)`">
                <span class="post-circle" :class="s.color"><component :is="s.icon" :size="18" aria-hidden="true" /></span>
                <span class="post-date num" aria-hidden="true">{{ shortDate(p[s.key].posted_at) }}</span>
              </a>
            </li>
          </ul>
        </li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
/* the prints: small, fixed-width columns (a 9:16 frame at full row width is a wall, not a contact sheet); a series
   with few parts leaves the rest of the row as paper instead of stretching its prints */
.prints {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(10rem, 11.5rem));
  gap: 3rem 3rem;
  padding: 2rem 2rem 2.5rem;
}
/* each print: title, frame, posts. Subgrid shares those three rows across the prints of a row, so a long title
   pushes every frame in that row down together and the frames stay level */
.print { display: grid; grid-row: span 3; grid-template-rows: subgrid; row-gap: 0; }
.caption { display: flex; align-items: baseline; align-self: end; gap: 0.5rem; margin-bottom: 0.75rem; }
.caption-title { min-width: 0; line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* where it's posted: one round icon button per site, its date centred under it */
.posts { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1.25rem; }
.post { display: flex; flex-direction: column; align-items: center; gap: 0.375rem; border-radius: var(--radius-md); padding: 0.25rem 0; }
.post-circle {
  display: grid; place-items: center; width: 2.5rem; height: 2.5rem; border-radius: 9999px;
  background: var(--color-panel); border: 1px solid var(--color-rule-strong);
  transition: border-color 0.15s ease, background-color 0.15s ease, transform 0.15s ease;
}
.post:hover .post-circle, .post:focus-visible .post-circle { border-color: currentColor; background: var(--color-well); transform: translateY(-1px); }
.post:focus-visible { outline: 2px solid var(--color-blue); outline-offset: 2px; }
.post-date { font-size: 11px; line-height: 1.2; white-space: nowrap; color: var(--color-muted); }
.post:hover .post-date { color: var(--color-ink); }
/* a print laid on the sheet: a slight tilt and a paper shadow; picked up (straightened, lifted) on hover or focus */
.frame {
  border: 1px solid var(--color-rule);
  box-shadow: var(--shadow-sheet);
  transform: rotate(var(--tilt, 0deg));
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.25s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.25s ease;
}
.frame:hover, .frame:focus-visible {
  transform: rotate(0deg) translateY(-3px);
  box-shadow: var(--shadow-pop);
  border-color: var(--color-rule-strong);
}
@media (prefers-reduced-motion: reduce) {
  .frame { transition: none; }
  .frame:hover, .frame:focus-visible { transform: rotate(0deg); }
}
</style>
