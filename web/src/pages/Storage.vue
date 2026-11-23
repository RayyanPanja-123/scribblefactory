<script setup lang="ts">
import { HardDrive, RotateCw } from 'lucide-vue-next'
import { computed } from 'vue'
import { api } from '../api/client'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { onLive } from '../composables/live'
import { useApi } from '../composables/useApi'
import { bytes } from '../composables/ui'
import { KINDS, biggest, byKind, duration, kindOf } from '../lib/storage'

// What the library holds on disk: per series, the stored files by kind (GET /api/storage syncs them first) and the
// rest of the series folder (rendered frames, work files) from the overview's disk usage. Ruled tables, no gauges.
const { data, error, loading, reload, refresh } = useApi(() => Promise.all([api.overview(), api.series(), api.storage()]))
onLive((e) => { if (e.type === 'series-changed') refresh() })

const titles = computed(() => new Map(data.value?.[1].map((s) => [s.slug, s.title])))
const rows = computed(() => {
  if (!data.value) return []
  const [overview, , files] = data.value
  return Object.entries(overview.disk_usage)
    .map(([slug, onDisk]) => {
      const kinds = byKind(files.filter((f) => f.slug === slug))
      const stored = kinds.reduce((a, k) => a + k.bytes, 0)
      return { slug, title: titles.value.get(slug) ?? slug, kinds, other: Math.max(0, onDisk - stored), onDisk }
    })
    .sort((a, b) => b.onDisk - a.onDisk)
})
const totals = computed(() => ({
  kinds: byKind(data.value?.[2] ?? []),
  other: rows.value.reduce((a, r) => a + r.other, 0),
  onDisk: rows.value.reduce((a, r) => a + r.onDisk, 0),
}))
const top = computed(() => biggest(data.value?.[2] ?? [], 10))
const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.key, k.label]))
</script>

<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-end gap-x-4 gap-y-2">
      <div>
        <h1 class="font-display text-2xl font-semibold">Storage</h1>
        <p class="text-sm text-muted">What each series keeps on disk, from library/database/storage.</p>
      </div>
      <button class="btn btn-secondary ml-auto" :disabled="loading" @click="reload"><RotateCw :size="16" aria-hidden="true" /> Check again</button>
    </header>

    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-72" aria-busy="true" aria-label="Loading storage" />

    <template v-else-if="data">
      <EmptyState v-if="!rows.length" :icon="HardDrive" title="Nothing on disk" text="Create a series: its story, voice and renders show here as they are made." />
      <template v-else>
        <section class="raised overflow-hidden" aria-labelledby="by-series">
          <div class="border-b border-rule px-5 py-4">
            <h2 id="by-series" class="font-display text-lg font-semibold">By series</h2>
            <p class="text-sm text-muted">Stored files by kind, then rendered frames and work files, then the whole folder.</p>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[760px] border-collapse text-sm">
              <thead>
                <tr class="border-b-2 border-rule-strong">
                  <th scope="col" class="colhead px-5 py-2.5 text-left">Series</th>
                  <th v-for="k in KINDS" :key="k.key" scope="col" class="colhead border-l border-rule px-3 py-2.5 text-right">{{ k.label }}</th>
                  <th scope="col" class="colhead border-l border-rule px-3 py-2.5 text-right">Frames and work files</th>
                  <th scope="col" class="colhead border-l-2 border-rule-strong px-5 py-2.5 text-right">On disk</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in rows" :key="r.slug" class="border-b border-rule">
                  <th scope="row" class="px-5 py-2.5 text-left font-medium">
                    <RouterLink :to="`/series/${r.slug}`" class="hover:underline">{{ r.title }}</RouterLink>
                  </th>
                  <td v-for="k in r.kinds" :key="k.key" class="border-l border-rule px-3 py-2.5 text-right align-top">
                    <span class="num block">{{ k.files ? bytes(k.bytes) : '·' }}</span>
                    <span v-if="k.files" class="block text-xs text-muted">{{ k.files }} file{{ k.files === 1 ? '' : 's' }}<template v-if="k.seconds"> · {{ duration(k.seconds) }}</template></span>
                  </td>
                  <td class="num border-l border-rule px-3 py-2.5 text-right align-top">{{ bytes(r.other) }}</td>
                  <td class="num border-l-2 border-rule-strong px-5 py-2.5 text-right align-top font-semibold">{{ bytes(r.onDisk) }}</td>
                </tr>
              </tbody>
              <tfoot>
                <tr class="border-t-2 border-rule-strong bg-well">
                  <th scope="row" class="px-5 py-2.5 text-left font-display font-semibold">Library</th>
                  <td v-for="k in totals.kinds" :key="k.key" class="num border-l border-rule px-3 py-2.5 text-right">{{ k.files ? bytes(k.bytes) : '·' }}</td>
                  <td class="num border-l border-rule px-3 py-2.5 text-right">{{ bytes(totals.other) }}</td>
                  <td class="num border-l-2 border-rule-strong px-5 py-2.5 text-right font-semibold">{{ bytes(totals.onDisk) }}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </section>

        <section class="raised overflow-hidden" aria-labelledby="biggest">
          <div class="border-b border-rule px-5 py-4">
            <h2 id="biggest" class="font-display text-lg font-semibold">Biggest files</h2>
            <p class="text-sm text-muted">Rendered frames aside. A part's frames go once its final is approved.</p>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr class="border-b-2 border-rule-strong">
                  <th scope="col" class="colhead px-5 py-2.5 text-left">File</th>
                  <th scope="col" class="colhead border-l border-rule px-3 py-2.5 text-left">Where</th>
                  <th scope="col" class="colhead border-l border-rule px-3 py-2.5 text-left">Kind</th>
                  <th scope="col" class="colhead border-l border-rule px-3 py-2.5 text-right">Length</th>
                  <th scope="col" class="colhead border-l border-rule px-5 py-2.5 text-right">Size</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="f in top" :key="`${f.path}/${f.filename}`" class="border-b border-rule last:border-b-0">
                  <th scope="row" class="px-5 py-2 text-left font-medium">{{ f.filename }}</th>
                  <td class="border-l border-rule px-3 py-2">
                    <RouterLink :to="f.part ? `/series/${f.slug}/${f.part}` : `/series/${f.slug}`" class="hover:underline">
                      {{ titles.get(f.slug) ?? f.slug }}<span v-if="f.part" class="text-muted"> · {{ f.part }}</span>
                    </RouterLink>
                  </td>
                  <td class="border-l border-rule px-3 py-2 text-muted">{{ KIND_LABEL[kindOf(f.content_type)] }}</td>
                  <td class="num border-l border-rule px-3 py-2 text-right text-muted">{{ f.duration_s ? duration(f.duration_s) : '·' }}</td>
                  <td class="num border-l border-rule px-5 py-2 text-right">{{ bytes(f.size_bytes) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </template>
  </div>
</template>
