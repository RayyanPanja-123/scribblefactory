<script setup lang="ts">
import { ChevronDown, Copy, History, Trash2 } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { api, type Job } from '../api/client'
import EmptyState from '../components/EmptyState.vue'
import { act, confirm, toast } from '../composables/feedback'
import { jobs } from '../composables/live'
import { statusChip, today } from '../composables/ui'

// Every finished job (library/.jobs.json, the last 500 kept), newest first: filter by day and status, read a log,
// and clean up old history. Queued and running jobs live in the job drawer, not here.
const day = (j: Job) => (j.finished_at ?? j.queued_at).slice(0, 10)
const finished = computed(() => jobs.value.filter((j) => !['queued', 'running'].includes(j.status))
  .sort((a, b) => (b.finished_at ?? b.queued_at).localeCompare(a.finished_at ?? a.queued_at)))

const from = ref('')
const to = ref('')
const status = ref<'all' | 'done' | 'failed' | 'cancelled'>('all')
const shown = computed(() => finished.value.filter((j) => (!from.value || day(j) >= from.value)
  && (!to.value || day(j) <= to.value) && (status.value === 'all' || j.status === status.value)))
const days = computed(() => {
  const by = new Map<string, Job[]>()
  for (const j of shown.value) by.set(day(j), [...(by.get(day(j)) ?? []), j])
  return [...by]
})
const filtered = computed(() => !!(from.value || to.value || status.value !== 'all'))
function clearFilters() { from.value = ''; to.value = ''; status.value = 'all' }

const longDay = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
const clock = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '-')
function duration(j: Job) {
  if (!j.started_at || !j.finished_at) return '-'
  const s = Math.round((Date.parse(j.finished_at) - Date.parse(j.started_at)) / 1000)
  return s < 60 ? `${s} s` : s < 3600 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`
}
async function copyLog(j: Job) {
  try {
    await navigator.clipboard.writeText(j.output.join('\n'))
    toast('Log copied', 'ok')
  } catch {
    toast('Could not copy: clipboard not available', 'error')
  }
}

// ---- cleanup ----
const before = ref('')
const olderCount = computed(() => finished.value.filter((j) => before.value && day(j) < before.value).length)
async function cleanup(cut: string | null) {
  const n = cut ? olderCount.value : finished.value.length
  const ok = await confirm({
    title: cut ? `Delete ${n} job${n === 1 ? '' : 's'} from before ${longDay(cut)}?` : `Delete all ${n} jobs from the history?`,
    body: 'Their logs are gone for good. Queued and running jobs are not touched, and nothing in your series changes.',
    confirm: 'Delete history', danger: true,
  })
  if (!ok) return
  const left = await act(() => api.cleanupJobs(cut), `Deleted ${n} job${n === 1 ? '' : 's'} from the history`)
  if (left) jobs.value = left
}
const field = 'inset mt-1 block h-11 w-full rounded-full px-4 text-sm text-ink outline-none'
</script>

<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">History</h2>
      <span class="text-sm text-muted">{{ finished.length }} finished job{{ finished.length === 1 ? '' : 's' }} · the last 500 are kept</span>
    </div>

    <div class="grid items-start gap-5 lg:grid-cols-[1fr_300px]">
      <!-- filters + list -->
      <div class="min-w-0 space-y-4">
        <form class="raised flex flex-wrap items-end gap-3 p-4" aria-label="Filter history" @submit.prevent>
          <label class="min-w-36 flex-1 text-xs font-semibold text-muted">From
            <input v-model="from" type="date" :max="to || today()" :class="field" />
          </label>
          <label class="min-w-36 flex-1 text-xs font-semibold text-muted">To
            <input v-model="to" type="date" :min="from || undefined" :max="today()" :class="field" />
          </label>
          <label class="min-w-36 flex-1 text-xs font-semibold text-muted">Status
            <select v-model="status" :class="field">
              <option value="all">All</option>
              <option value="done">Done</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
          <button v-if="filtered" type="button" class="btn btn-secondary" @click="clearFilters">Clear</button>
        </form>

        <EmptyState v-if="!shown.length" :icon="History" :title="filtered ? 'Nothing matches' : 'No history yet'"
          :text="filtered ? 'No finished jobs in these dates with this status.' : 'Finished jobs show up here.'" />

        <section v-for="[d, list] in days" :key="d" class="raised p-4" :aria-label="longDay(d)">
          <h3 class="px-1 pb-2 text-sm font-semibold">{{ longDay(d) }} <span class="font-normal text-muted">· {{ list.length }}</span></h3>
          <ul class="divide-y divide-[#ebe6dc]">
            <li v-for="j in list" :key="j.id">
              <details class="group">
                <summary class="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 rounded-md px-1 py-2.5 hover:bg-panel [&::-webkit-details-marker]:hidden">
                  <span class="num w-12 text-sm text-muted">{{ clock(j.finished_at) }}</span>
                  <span class="chip" :class="statusChip(j.status)">{{ j.status }}</span>
                  <span class="order-last min-w-0 basis-full truncate text-sm sm:order-none sm:basis-0 sm:flex-1">
                    <span class="font-semibold">{{ j.slug }}</span> <span class="text-muted">{{ j.part }}</span>
                    <span class="text-muted"> · {{ j.steps.join(' → ') }}</span>
                  </span>
                  <span class="num ml-auto text-xs text-muted sm:ml-0">{{ duration(j) }}</span>
                  <ChevronDown :size="16" class="shrink-0 text-muted transition-transform group-open:rotate-180" aria-hidden="true" />
                </summary>
                <div class="space-y-2 px-1 pb-3">
                  <p v-if="j.error" class="rounded-sm bg-[#f8e6e1] px-2 py-1 text-xs text-red-ink">{{ j.error }}</p>
                  <pre v-if="j.output.length" class="inset max-h-72 overflow-auto p-3 font-mono text-xs leading-5 whitespace-pre-wrap">{{ j.output.join('\n') }}</pre>
                  <p v-else class="text-xs text-muted">No output.</p>
                  <div class="flex flex-wrap gap-2">
                    <RouterLink :to="`/series/${j.slug}/${j.part}`" class="btn btn-secondary text-xs">Open part</RouterLink>
                    <button v-if="j.output.length" type="button" class="btn btn-secondary text-xs" @click="copyLog(j)"><Copy :size="13" aria-hidden="true" /> Copy log</button>
                  </div>
                </div>
              </details>
            </li>
          </ul>
        </section>
      </div>

      <!-- cleanup -->
      <aside class="raised space-y-4 p-5 lg:sticky lg:top-0" aria-label="Clean up history">
        <h3 class="font-display text-lg font-semibold">Clean up</h3>
        <p class="text-xs text-muted">Deletes finished jobs and their logs. Queued and running jobs, and your series, are never touched.</p>
        <label class="block text-xs font-semibold text-muted">Delete everything before
          <input v-model="before" type="date" :max="today()" :class="field" />
        </label>
        <button type="button" class="btn btn-secondary w-full justify-center text-red-ink" :disabled="!olderCount" @click="cleanup(before)">
          <Trash2 :size="16" aria-hidden="true" /> {{ before ? `Delete ${olderCount} older job${olderCount === 1 ? '' : 's'}` : 'Pick a date' }}
        </button>
        <div class="border-t border-[#ebe6dc] pt-4">
          <button type="button" class="btn btn-secondary w-full justify-center text-red-ink" :disabled="!finished.length" @click="cleanup(null)">
            <Trash2 :size="16" aria-hidden="true" /> Delete all history
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>
