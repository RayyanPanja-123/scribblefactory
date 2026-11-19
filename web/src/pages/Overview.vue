<script setup lang="ts">
import { Check, Copy, Film, HardDrive, List, NotebookPen, Plus, X } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { api, type Overview } from '../api/client'
import GreaseCircle from '../components/GreaseCircle.vue'
import PencilTick from '../components/PencilTick.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { toast } from '../composables/feedback'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { bytes, label } from '../composables/ui'
import { needsYou } from '../lib/partSteps'
import { copyLibraryList, storyGuide } from '../lib/storyGuide'

const { data, error, loading, reload, refresh } = useApi(() => Promise.all([api.overview(), api.series()]))

// the story guide (lib/storyGuide); the AI asks for the library list separately
const copied = ref(false)
async function copyGuide() {
  try {
    await navigator.clipboard.writeText(await storyGuide())
    copied.value = true
    toast('Story guide copied: paste it into any AI and brainstorm. It asks for the library list when it needs it', 'ok')
    setTimeout(() => (copied.value = false), 2500)
  } catch {
    toast('Could not copy to the clipboard. Open docs/STORY_GUIDE.md and copy it from there.', 'error')
  }
}
// just what the library has (sets, props, creatures, actions, wardrobe, cast), without the rest of the guide
const listCopied = ref(false)
async function copyList() {
  if (!(await copyLibraryList())) return
  listCopied.value = true
  setTimeout(() => (listCopied.value = false), 2500)
}
refetchOn(() => null, () => null, refresh)

// ---- the title block: X-sheet header fields ----
const fields = computed(() => {
  if (!data.value) return []
  const [o, series] = data.value
  const months = o.posts_per_month
  const sum = (m?: { youtube: number; instagram: number }) => (m ? m.youtube + m.instagram : 0)
  const delta = sum(months.at(-1)) - sum(months.at(-2))
  return [
    { name: 'Series', value: o.kpi.series, note: `${series.filter((s) => s.status === 'active').length} active`, alert: false },
    { name: 'In production', value: o.kpi.parts_in_progress, note: 'parts not finished', alert: false },
    { name: 'Needs you', value: mine.value, note: mine.value ? 'circled below' : 'all clear', alert: mine.value > 0 },
    { name: 'Posted this month', value: o.kpi.posted_this_month, alert: false,
      note: delta > 0 ? `+${delta} on last month` : delta < 0 ? `${delta} on last month` : 'same as last month' },
  ]
})

// ---- the exposure sheet: unposted parts as rows, the part's journey as columns, grouped by series ----
type Row = Overview['sheet'][number]
const HREF = ['#story', '#voice', '#run', '#review', '#video', '#approvals', '#thumbnails', '#posting']
const NOTE: Record<string, string> = { current: 'up next', review: 'approve it', running: 'running', failed: 'failed', done: 'done', todo: 'to do' }
const groups = computed(() => {
  const out: { slug: string; title: string; rows: Row[] }[] = []
  for (const r of data.value?.[0].sheet ?? []) {
    const g = out.at(-1)
    if (g?.slug === r.slug) g.rows.push(r)
    else out.push({ slug: r.slug, title: r.series_title, rows: [r] })
  }
  return out
})
const KEYS = ['story', 'voice', 'plan', 'stills', 'test', 'final', 'thumbnail', 'post'] // lib/partSteps keys
const circled = (c: string, i: number) => needsYou({ key: KEYS[i], status: c as Parameters<typeof needsYou>[0]['status'] })
const castWaiting = computed(() => (data.value?.[0].waiting ?? []).filter((w) => !w.part))
// cells the creator owns right now, plus cast sheets waiting: the "Needs you" count
const mine = computed(() => (data.value?.[0].sheet ?? []).reduce((n, r) => n + r.cells.filter(circled).length, 0) + castWaiting.value.length)
const firstMine = (r: Row) => r.cells.findIndex(circled)
const partHref = (slug: string, part: string, i = -1) => `/series/${slug}/${part}${i >= 0 ? HREF[i] : ''}`

// ---- posting log: months as columns, platforms as rows ----
const monthName = (m: string) => new Date(`${m}-01T00:00:00Z`).toLocaleString('en-GB', { month: 'short', timeZone: 'UTC' })
const PLATFORMS = [{ key: 'youtube', name: 'YouTube', dot: 'bg-youtube' }, { key: 'instagram', name: 'Instagram', dot: 'bg-instagram' }] as const

// ---- disk: bars drawn to scale ----
const titles = computed(() => new Map(data.value?.[1].map((s) => [s.slug, s.title])))
const disk = computed(() => {
  const items = Object.entries(data.value?.[0].disk_usage ?? {}).map(([slug, value]) => ({ slug, label: titles.value.get(slug) ?? slug, value }))
  const max = Math.max(1, ...items.map((i) => i.value))
  return items.sort((a, b) => b.value - a.value).map((i) => ({ ...i, pct: (i.value / max) * 100 }))
})
const diskTotal = computed(() => disk.value.reduce((a, b) => a + b.value, 0))
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />

  <div v-else-if="loading" class="max-w-7xl space-y-6" aria-busy="true" aria-label="Loading overview">
    <div class="skeleton h-24" />
    <div class="skeleton h-96" />
  </div>

  <div v-else-if="data" class="flex max-w-7xl flex-col gap-6">
    <!-- title block (below the sheet on phones: the sheet is the first thing to see) -->
    <section class="raised grid max-sm:order-2 grid-cols-2 overflow-hidden xl:grid-cols-[repeat(4,minmax(0,1fr))_auto]" aria-label="Studio at a glance">
      <div v-for="f in fields" :key="f.name" class="border-r border-b border-rule px-4 py-2.5 even:border-r-0 sm:px-5 xl:border-b-0 xl:even:border-r">
        <p class="colhead">{{ f.name }}</p>
        <p class="flex flex-wrap items-baseline gap-x-2">
          <span class="font-display text-2xl font-semibold tabular-nums" :class="f.alert ? 'text-amber-ink' : 'text-ink'">{{ f.value }}</span>
          <span class="text-sm text-muted">{{ f.note }}</span>
        </p>
      </div>
      <div class="col-span-2 flex flex-wrap items-center gap-2 px-4 py-3 sm:px-5 sm:py-4 xl:col-span-1">
        <button class="btn btn-secondary w-full justify-center xl:w-auto" :aria-label="listCopied ? 'Library list copied' : 'Copy the library list'"
          title="Every set, prop, creature, action, wardrobe item and cast member you have, as a bullet list for any AI" @click="copyList">
          <component :is="listCopied ? Check : List" :size="16" aria-hidden="true" /> {{ listCopied ? 'Copied' : 'Copy library list' }}
        </button>
        <button class="btn btn-primary w-full justify-center xl:w-auto" :aria-label="copied ? 'Story guide copied' : 'Copy the story guide'" @click="copyGuide">
          <component :is="copied ? Check : Copy" :size="16" aria-hidden="true" /> {{ copied ? 'Copied' : 'Copy story guide' }}
        </button>
      </div>
    </section>

    <p class="flex max-w-3xl items-start gap-2 text-sm text-muted max-sm:order-3">
      <NotebookPen :size="16" class="mt-0.5 shrink-0" aria-hidden="true" />
      Write a part with any AI: copy the story guide, paste it into Claude, ChatGPT or another assistant, fill in your cast at the end and ask for a part.
    </p>

    <!-- cast sheets waiting (series level, not a part row) -->
    <section v-if="castWaiting.length" class="raised tint-amber flex flex-wrap items-center gap-3 px-5 py-3" aria-label="Cast sheets to approve">
      <p class="font-display font-semibold">Cast sheets to approve</p>
      <RouterLink v-for="w in castWaiting" :key="w.slug" :to="`/series/${w.slug}#cast`" class="chip chip-amber hover:underline">
        {{ titles.get(w.slug) ?? w.slug }} · {{ w.waiting.map((x) => label(x.slice(5))).join(', ') }}
      </RouterLink>
    </section>

    <!-- the exposure sheet -->
    <section class="raised overflow-hidden max-sm:order-1" aria-labelledby="sheet-title">
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-rule px-5 py-4">
        <h2 id="sheet-title" class="font-display text-xl font-semibold">Exposure sheet</h2>
        <p class="text-sm text-muted">Every part not posted yet. A circled cell needs you.</p>
        <RouterLink to="/new-series" class="btn btn-secondary ml-auto"><Plus :size="16" aria-hidden="true" /> New series</RouterLink>
      </div>

      <div v-if="groups.length" class="overflow-x-auto">
        <table class="w-full min-w-[880px] border-collapse text-sm">
          <thead>
            <tr class="border-b-2 border-rule-strong">
              <th scope="col" class="colhead sticky left-0 z-[1] w-40 bg-panel px-3 py-2.5 text-left sm:w-72 sm:px-5">Part</th>
              <th v-for="(st, i) in data[0].sheet_steps" :key="st" scope="col" class="colhead border-l border-rule px-2 py-2.5 text-center whitespace-nowrap">
                <span class="num text-muted" aria-hidden="true">{{ i + 1 }}</span> {{ st }}
              </th>
            </tr>
          </thead>
          <tbody v-for="g in groups" :key="g.slug">
            <tr class="border-b border-rule bg-well">
              <th colspan="9" scope="rowgroup" class="px-5 py-1.5 text-left">
                <RouterLink :to="`/series/${g.slug}`" class="sticky left-5 font-display font-semibold hover:underline">{{ g.title }}</RouterLink>
              </th>
            </tr>
            <tr v-for="r in g.rows" :key="r.part" class="group border-b border-rule last:border-b-0">
              <th scope="row" class="sticky left-0 z-[1] max-w-40 bg-panel px-3 py-2 text-left font-normal group-hover:bg-well sm:max-w-72 sm:px-5">
                <RouterLink :to="partHref(r.slug, r.part)" class="flex items-baseline gap-2 hover:underline">
                  <span class="num w-6 shrink-0 text-muted">{{ String(r.number).padStart(2, '0') }}</span>
                  <span class="truncate font-medium">{{ r.title || `Part ${r.number}` }}</span>
                </RouterLink>
                <!-- phones: the circled column may be off-screen, so name it here -->
                <RouterLink v-if="firstMine(r) >= 0" :to="partHref(r.slug, r.part, firstMine(r))"
                  class="mt-0.5 block font-display text-xs text-amber-ink sm:hidden">needs you: {{ data[0].sheet_steps[firstMine(r)] }}</RouterLink>
                <RouterLink v-else-if="r.cells.includes('failed')" :to="partHref(r.slug, r.part, r.cells.indexOf('failed'))"
                  class="mt-0.5 block font-display text-xs text-red-ink sm:hidden">failed: {{ data[0].sheet_steps[r.cells.indexOf('failed')] }}</RouterLink>
                <span v-else-if="r.cells.includes('running')" class="mt-0.5 block font-display text-xs text-blue-ink sm:hidden">running: {{ data[0].sheet_steps[r.cells.indexOf('running')] }}</span>
              </th>
              <td v-for="(c, i) in r.cells" :key="i" class="border-l border-rule p-0 text-center group-hover:bg-well/50">
                <span v-if="c === 'todo'" class="flex h-11 items-center justify-center" :title="`${data[0].sheet_steps[i]}: to do`">
                  <span class="sr-only">{{ data[0].sheet_steps[i] }}: to do</span>
                  <span class="size-1 rounded-full bg-rule-strong" aria-hidden="true" />
                </span>
                <RouterLink v-else :to="partHref(r.slug, r.part, i)" class="cell relative flex h-11 items-center justify-center gap-1 text-xs font-semibold"
                  :class="circled(c, i) ? 'cell-mine' : `cell-${c}`" :title="`${data[0].sheet_steps[i]}: ${circled(c, i) ? 'needs you' : NOTE[c]}`">
                  <span class="sr-only">{{ data[0].sheet_steps[i] }}: {{ circled(c, i) ? 'needs you' : NOTE[c] }}</span>
                  <PencilTick v-if="c === 'done'" class="text-ink" />
                  <template v-else-if="circled(c, i)">
                    <span class="font-display text-[13px] text-amber-ink" aria-hidden="true">{{ c === 'review' ? 'approve' : 'you' }}</span>
                    <GreaseCircle />
                  </template>
                  <template v-else-if="c === 'current'"><span class="size-1.5 rounded-full bg-blue" aria-hidden="true" /><span class="font-display text-[13px] text-blue-ink" aria-hidden="true">next</span></template>
                  <template v-else-if="c === 'running'"><Film :size="14" class="reel text-blue" aria-hidden="true" /><span class="font-display text-[13px] text-blue-ink" aria-hidden="true">running</span></template>
                  <template v-else><X :size="14" :stroke-width="3" class="text-red" aria-hidden="true" /><span class="font-display text-[13px] text-red-ink" aria-hidden="true">failed</span></template>
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

    <section class="grid items-start gap-6 max-sm:order-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(300px,1fr)]">
      <div class="raised overflow-hidden">
        <div class="border-b border-rule px-5 py-4">
          <h2 class="font-display text-lg font-semibold">Posting log</h2>
          <p class="text-sm text-muted">Parts posted per month, last 12 months</p>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr class="border-b-2 border-rule-strong">
                <th scope="col" class="colhead sticky left-0 bg-panel px-5 py-2 text-left">Platform</th>
                <th v-for="m in data[0].posts_per_month" :key="m.month" scope="col" class="colhead border-l border-rule px-1 py-2 text-center">{{ monthName(m.month) }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="pl in PLATFORMS" :key="pl.key" class="border-b border-rule last:border-b-0">
                <th scope="row" class="sticky left-0 bg-panel px-5 py-2.5 text-left font-medium">
                  <span class="flex items-center gap-2"><span class="size-2 rounded-full" :class="pl.dot" aria-hidden="true" />{{ pl.name }}</span>
                </th>
                <td v-for="m in data[0].posts_per_month" :key="m.month" class="border-l border-rule text-center">
                  <span v-if="m[pl.key]" class="font-display text-base font-semibold">{{ m[pl.key] }}</span>
                  <span v-else class="text-faint" aria-label="none">·</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="raised overflow-hidden">
        <div class="flex items-baseline justify-between gap-3 border-b border-rule px-5 py-4">
          <div>
            <h2 class="font-display text-lg font-semibold">Disk usage</h2>
            <p class="text-sm text-muted">Per series, frames included</p>
          </div>
          <span class="num shrink-0 text-sm text-muted">{{ bytes(diskTotal) }}</span>
        </div>
        <ul v-if="diskTotal" class="divide-y divide-rule">
          <li v-for="d in disk" :key="d.slug" class="px-5 py-2.5">
            <div class="flex items-baseline justify-between gap-3 text-sm">
              <RouterLink :to="`/series/${d.slug}`" class="truncate hover:underline">{{ d.label }}</RouterLink>
              <span class="num shrink-0 text-muted">{{ bytes(d.value) }}</span>
            </div>
            <!-- length is size, to scale -->
            <div class="mt-1.5 h-1.5 rounded-sm bg-well"><div class="h-full rounded-sm bg-blue" :style="{ width: `${d.pct}%` }" /></div>
          </li>
        </ul>
        <EmptyState v-else class="m-5" :icon="HardDrive" title="Nothing on disk" text="Create a series to start filling the library." />
      </div>
    </section>
  </div>
</template>

<style scoped>
.cell { transition: background-color 0.12s ease; }
.cell:hover { background: color-mix(in oklab, var(--color-blue) 9%, transparent); }
.cell-mine { background: color-mix(in oklab, var(--color-amber) 7%, transparent); }
.cell-failed { background: color-mix(in oklab, var(--color-red) 8%, transparent); }
</style>
