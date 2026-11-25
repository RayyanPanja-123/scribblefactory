<script setup lang="ts">
import { ArrowRight, Film, HardDrive, Plus, Send, X } from 'lucide-vue-next'
import { computed } from 'vue'
import { api, type Overview } from '../api/client'
import GreaseCircle from '../components/GreaseCircle.vue'
import PencilTick from '../components/PencilTick.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { queuedCount, refetchOn, runningJob } from '../composables/live'
import { useApi } from '../composables/useApi'
import { bytes, label } from '../composables/ui'
import { needsYou } from '../lib/partSteps'

// The studio wall: the exposure sheet is the page; the margin beside it holds what runs, what ships next and the log.
const { data, error, loading, reload, refresh } = useApi(() => Promise.all([api.overview(), api.series()]))
refetchOn(() => null, () => null, refresh)

// ---- the exposure sheet: unposted parts as rows, the part's journey as columns, grouped by series ----
type Row = Overview['sheet'][number]
const HREF = ['#story', '#voice', '#run', '#review', '#approvals', '#posting']
const NOTE: Record<string, string> = { current: 'up next', review: 'approve it', running: 'running', failed: 'failed', done: 'done', todo: 'to do' }
const KEYS = ['story', 'voice', 'plan', 'stills', 'final', 'post'] // lib/partSteps keys
// a cell that waits on the creator: their step, an approval, or a failed stage (only they can unblock it)
const owed = (c: string, i: number) => c === 'failed' || needsYou({ key: KEYS[i], status: c as Parameters<typeof needsYou>[0]['status'] })
const firstOwed = (r: Row) => r.cells.findIndex(owed)
// within a series: rows that need the creator first, then running, then the rest, each by part number
const rank = (r: Row) => (firstOwed(r) >= 0 ? 0 : r.cells.includes('running') ? 1 : 2)
const groups = computed(() => {
  const out: { slug: string; title: string; rows: Row[] }[] = []
  for (const r of data.value?.[0].sheet ?? []) {
    const g = out.at(-1)
    if (g?.slug === r.slug) g.rows.push(r)
    else out.push({ slug: r.slug, title: r.series_title, rows: [r] })
  }
  for (const g of out) g.rows.sort((a, b) => rank(a) - rank(b) || a.number - b.number)
  return out
})
const partHref = (slug: string, part: string, i = -1) => `/series/${slug}/${part}${i >= 0 ? HREF[i] : ''}`
const titles = computed(() => new Map(data.value?.[1].map((s) => [s.slug, s.title])))
const castWaiting = computed(() => (data.value?.[0].waiting ?? []).filter((w) => !w.part))
const owedCells = computed(() => groups.value.flatMap((g) => g.rows).reduce((n, r) => n + r.cells.filter(owed).length, 0))
const mine = computed(() => owedCells.value + castWaiting.value.length)
// "Needs you" goes straight to the first thing waiting, in sheet order (cast sheets when only those wait)
const firstHref = computed(() => {
  for (const g of groups.value) for (const r of g.rows) if (firstOwed(r) >= 0) return partHref(r.slug, r.part, firstOwed(r))
  const w = castWaiting.value[0]
  return w ? `/series/${w.slug}#cast` : null
})
const parts = computed(() => data.value?.[0].sheet.length ?? 0)

// ---- the margin ----
// next to post: final approved, not posted yet
const toPost = computed(() => (data.value?.[0].sheet ?? []).filter((r) => r.cells[4] === 'done' && r.cells[5] !== 'done'))
// posting log: the last six months, platforms as rows (the Posted page has every post)
const monthName = (m: string) => new Date(`${m}-01T00:00:00Z`).toLocaleString('en-GB', { month: 'short', timeZone: 'UTC' })
const PLATFORMS = [{ key: 'youtube', name: 'YouTube', dot: 'bg-youtube' }, { key: 'instagram', name: 'Instagram', dot: 'bg-instagram' }] as const
const months = computed(() => (data.value?.[0].posts_per_month ?? []).slice(-6))
const diskTotal = computed(() => Object.values(data.value?.[0].disk_usage ?? {}).reduce((a, b) => a + b, 0))
const runningStep = computed(() => {
  const j = runningJob.value
  return j && j.current_step != null ? j.steps[j.current_step] : null
})
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />

  <div v-else-if="loading" class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_19rem]" aria-busy="true" aria-label="Loading overview">
    <div class="skeleton h-[28rem]" />
    <div class="skeleton h-72" />
  </div>

  <div v-else-if="data" class="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_19rem]">
    <!-- the sheet: the page itself -->
    <section class="raised overflow-hidden" aria-labelledby="sheet-title">
      <header class="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-rule px-5 py-4">
        <div class="min-w-0">
          <h1 id="sheet-title" class="font-display text-2xl font-semibold">Exposure sheet</h1>
          <p class="text-sm text-muted">{{ parts ? `${parts} part${parts === 1 ? '' : 's'} not posted yet. A circled cell needs you.` : 'Every part not posted yet shows here.' }}</p>
        </div>
        <!-- the header's one field: what waits on the creator, and the way to it -->
        <RouterLink v-if="firstHref" :to="firstHref" class="needs relative flex items-center gap-3 rounded-md px-3 py-1.5 hover:bg-well"
          :aria-label="`${mine} thing${mine === 1 ? '' : 's'} need you: go to the first`">
          <span class="relative grid min-w-12 place-items-center px-2 py-1">
            <span class="font-display text-3xl font-semibold tabular-nums text-amber-ink">{{ mine }}</span>
            <GreaseCircle />
          </span>
          <span class="text-left">
            <span class="colhead block">Needs you</span>
            <span class="flex items-center gap-1 text-sm font-medium">Go to the first <ArrowRight :size="14" aria-hidden="true" /></span>
          </span>
        </RouterLink>
        <p v-else-if="parts" class="flex items-center gap-2 text-sm text-muted"><PencilTick class="text-ink" /> Nothing needs you</p>
        <RouterLink to="/new-series" class="btn btn-secondary ml-auto"><Plus :size="16" aria-hidden="true" /> New series</RouterLink>
      </header>

      <!-- cast sheets waiting (series level, not a part row) -->
      <div v-if="castWaiting.length" class="tint-amber flex flex-wrap items-center gap-3 border-b border-rule px-5 py-2.5">
        <p class="font-display font-semibold">Cast sheets to approve</p>
        <RouterLink v-for="w in castWaiting" :key="w.slug" :to="`/series/${w.slug}#cast`" class="chip chip-amber hover:underline">
          {{ titles.get(w.slug) ?? w.slug }} · {{ w.waiting.map((x) => label(x.slice(5))).join(', ') }}
        </RouterLink>
      </div>

      <div v-if="groups.length" class="overflow-x-auto">
        <table class="w-full min-w-[760px] border-collapse text-sm">
          <thead>
            <tr class="border-b-2 border-rule-strong">
              <th scope="col" class="colhead sticky left-0 z-[1] w-40 bg-panel px-3 py-2.5 text-left sm:w-64 sm:px-5">Part</th>
              <th v-for="(st, i) in data[0].sheet_steps" :key="st" scope="col" class="colhead border-l border-rule px-2 py-2.5 text-center whitespace-nowrap">
                <span class="num text-muted" aria-hidden="true">{{ i + 1 }}</span> {{ st }}
              </th>
            </tr>
          </thead>
          <tbody v-for="g in groups" :key="g.slug">
            <tr class="border-b border-rule bg-well">
              <th :colspan="data[0].sheet_steps.length + 1" scope="rowgroup" class="px-5 py-1.5 text-left">
                <RouterLink :to="`/series/${g.slug}`" class="sticky left-5 font-display font-semibold hover:underline">{{ g.title }}</RouterLink>
              </th>
            </tr>
            <tr v-for="r in g.rows" :key="r.part" class="group border-b border-rule last:border-b-0">
              <th scope="row" class="sticky left-0 z-[1] max-w-40 bg-panel px-3 py-2 text-left font-normal group-hover:bg-well sm:max-w-64 sm:px-5">
                <RouterLink :to="partHref(r.slug, r.part)" class="flex items-baseline gap-2 hover:underline">
                  <span class="num w-6 shrink-0 text-muted">{{ String(r.number).padStart(2, '0') }}</span>
                  <span class="truncate font-medium">{{ r.title || `Part ${r.number}` }}</span>
                </RouterLink>
                <!-- phones: the circled column may be off-screen, so name it here -->
                <RouterLink v-if="firstOwed(r) >= 0" :to="partHref(r.slug, r.part, firstOwed(r))" class="mt-0.5 block font-display text-xs sm:hidden"
                  :class="r.cells[firstOwed(r)] === 'failed' ? 'text-red-ink' : 'text-amber-ink'">
                  {{ r.cells[firstOwed(r)] === 'failed' ? 'failed' : 'needs you' }}: {{ data[0].sheet_steps[firstOwed(r)] }}</RouterLink>
                <span v-else-if="r.cells.includes('running')" class="mt-0.5 block font-display text-xs text-blue-ink sm:hidden">running: {{ data[0].sheet_steps[r.cells.indexOf('running')] }}</span>
              </th>
              <td v-for="(c, i) in r.cells" :key="i" class="border-l border-rule p-0 text-center group-hover:bg-well/50">
                <span v-if="c === 'todo'" class="flex h-11 items-center justify-center" :title="`${data[0].sheet_steps[i]}: to do`">
                  <span class="sr-only">{{ data[0].sheet_steps[i] }}: to do</span>
                  <span class="size-1 rounded-full bg-rule-strong" aria-hidden="true" />
                </span>
                <RouterLink v-else :to="partHref(r.slug, r.part, i)" class="cell relative flex h-11 items-center justify-center gap-1 text-xs font-semibold"
                  :class="c === 'failed' ? 'cell-failed' : owed(c, i) ? 'cell-mine' : `cell-${c}`"
                  :title="`${data[0].sheet_steps[i]}: ${c === 'failed' ? 'failed, needs you' : owed(c, i) ? 'needs you' : NOTE[c]}`">
                  <span class="sr-only">{{ data[0].sheet_steps[i] }}: {{ c === 'failed' ? 'failed, needs you' : owed(c, i) ? 'needs you' : NOTE[c] }}</span>
                  <PencilTick v-if="c === 'done'" class="text-ink" />
                  <template v-else-if="c === 'failed'">
                    <X :size="14" :stroke-width="3" class="text-red" aria-hidden="true" /><span class="font-display text-[13px] text-red-ink" aria-hidden="true">failed</span>
                    <GreaseCircle />
                  </template>
                  <template v-else-if="owed(c, i)">
                    <span class="font-display text-[13px] text-amber-ink" aria-hidden="true">{{ c === 'review' ? 'approve ?' : 'you ?' }}</span>
                    <GreaseCircle />
                  </template>
                  <template v-else-if="c === 'current'"><span class="size-1.5 rounded-full bg-blue" aria-hidden="true" /><span class="font-display text-[13px] text-blue-ink" aria-hidden="true">next</span></template>
                  <template v-else><Film :size="14" class="reel text-blue" aria-hidden="true" /><span class="font-display text-[13px] text-blue-ink" aria-hidden="true">running</span></template>
                </RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="grid place-items-center gap-3 px-6 py-14 text-center">
        <p class="font-display text-2xl font-semibold">The sheet is empty</p>
        <p class="max-w-sm text-sm text-muted">Every part is posted, or there are none yet. Start a series, then add its first part: it shows up here as a row.</p>
        <RouterLink to="/new-series" class="btn btn-primary"><Plus :size="16" aria-hidden="true" /> New series</RouterLink>
      </div>
    </section>

    <!-- the margin: what runs, what ships next, the log; beside the sheet on wide screens, under it otherwise -->
    <aside class="raised divide-y divide-rule overflow-hidden" aria-label="Studio margin">
      <section class="px-5 py-4" aria-labelledby="running-title">
        <h2 id="running-title" class="colhead">Running now</h2>
        <RouterLink v-if="runningJob" :to="partHref(runningJob.slug, runningJob.part)" class="mt-1.5 flex items-start gap-2 hover:underline">
          <Film :size="16" class="reel mt-0.5 shrink-0 text-blue" aria-hidden="true" />
          <span class="min-w-0">
            <span class="font-display font-semibold">{{ runningJob.tag }}</span>
            <span class="block truncate text-sm text-muted">{{ runningStep ?? 'starting' }}<template v-if="queuedCount"> · {{ queuedCount }} queued</template></span>
          </span>
        </RouterLink>
        <p v-else class="mt-1.5 text-sm text-muted">Nothing rendering{{ queuedCount ? ` · ${queuedCount} queued` : '' }}</p>
      </section>

      <section class="px-5 py-4" aria-labelledby="post-title">
        <h2 id="post-title" class="colhead">Next to post</h2>
        <ul v-if="toPost.length" class="mt-1.5 space-y-1.5">
          <li v-for="r in toPost.slice(0, 4)" :key="`${r.slug}/${r.part}`">
            <RouterLink :to="partHref(r.slug, r.part, 5)" class="flex items-baseline gap-2 text-sm hover:underline">
              <Send :size="14" class="shrink-0 self-center text-muted" aria-hidden="true" />
              <span class="min-w-0 truncate"><span class="font-medium">{{ r.title || `Part ${r.number}` }}</span> <span class="text-muted">· {{ r.series_title }}</span></span>
            </RouterLink>
          </li>
        </ul>
        <p v-else class="mt-1.5 text-sm text-muted">No finished part waiting to post.</p>
      </section>

      <section class="py-4" aria-labelledby="log-title">
        <div class="flex items-baseline justify-between gap-3 px-5">
          <h2 id="log-title" class="colhead">Posting log</h2>
          <RouterLink to="/posted" class="text-xs text-muted hover:underline">All posts</RouterLink>
        </div>
        <table class="mt-1.5 w-full border-collapse text-sm">
          <caption class="sr-only">Parts posted per month, last six months</caption>
          <thead>
            <tr class="border-b border-rule-strong">
              <th scope="col" class="sr-only">Platform</th>
              <th v-for="m in months" :key="m.month" scope="col" class="colhead px-1 pb-1 text-center">{{ monthName(m.month) }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="pl in PLATFORMS" :key="pl.key" class="border-b border-rule last:border-b-0">
              <th scope="row" class="w-px py-1.5 pr-1 pl-5 text-left font-normal">
                <span class="block size-2 rounded-full" :class="pl.dot" aria-hidden="true" /><span class="sr-only">{{ pl.name }}</span>
              </th>
              <td v-for="m in months" :key="m.month" class="text-center">
                <span v-if="m[pl.key]" class="font-display font-semibold">{{ m[pl.key] }}</span>
                <span v-else class="text-faint"><span aria-hidden="true">·</span><span class="sr-only">none</span></span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <RouterLink to="/storage" class="flex items-center gap-2 px-5 py-3 text-sm hover:bg-well">
        <HardDrive :size="16" class="shrink-0 text-muted" aria-hidden="true" />
        <span class="flex-1">Library on disk <span class="num text-muted">{{ bytes(diskTotal) }}</span></span>
        <ArrowRight :size="14" class="text-muted" aria-hidden="true" />
      </RouterLink>
    </aside>
  </div>
</template>

<style scoped>
.cell { transition: background-color 0.12s ease; }
.cell:hover { background: color-mix(in oklab, var(--color-blue) 9%, transparent); }
.cell-mine, .cell-mine:hover { background: color-mix(in oklab, var(--color-amber) 9%, transparent); }
.cell-failed, .cell-failed:hover { background: color-mix(in oklab, var(--color-red) 8%, transparent); }
.cell-failed :deep(.grease) { stroke: var(--color-red); }
</style>
