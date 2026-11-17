<script setup lang="ts">
import { Square, X } from 'lucide-vue-next'
import { AnimatePresence, motion } from 'motion-v'
import { computed, nextTick, ref, watch } from 'vue'
import { api, type Job } from '../api/client'
import { act, confirm } from '../composables/feedback'
import { drawerOpen, jobs, runningJob, stepStart } from '../composables/live'
import { SPRING, statusChip } from '../composables/ui'
import { jobFraction, parseProgress } from '../lib/progress'

const selectedId = ref<number | null>(null)
const recent = computed(() => [...jobs.value].filter((j) => !['queued', 'running'].includes(j.status)).reverse())
const queued = computed(() => jobs.value.filter((j) => j.status === 'queued'))
// the running job, else the one picked from the list, else the latest finished one
const shown = computed<Job | undefined>(() =>
  (selectedId.value !== null ? jobs.value.find((j) => j.id === selectedId.value) : undefined) ?? runningJob.value ?? recent.value[0])

const stepFrac = computed(() => {
  const j = shown.value
  if (!j || j.status !== 'running') return null
  return parseProgress(j.output.slice(stepStart.value[j.id] ?? 0))
})
const frac = computed(() => {
  const j = shown.value
  if (!j) return 0
  if (j.status === 'done') return 1
  return jobFraction(j.current_step, j.steps.length, stepFrac.value)
})
const indeterminate = computed(() => shown.value?.status === 'running' && stepFrac.value === null)

const log = ref<HTMLElement>()
watch(() => [shown.value?.id, shown.value?.output.length, drawerOpen.value], async () => {
  await nextTick()
  if (log.value) log.value.scrollTop = log.value.scrollHeight
})

function duration(j: Job) {
  if (!j.started_at) return '-'
  const s = Math.round(((j.finished_at ? Date.parse(j.finished_at) : Date.now()) - Date.parse(j.started_at)) / 1000)
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} m ${s % 60} s`
}

async function cancel(j: Job) {
  const ok = await confirm({
    title: `Cancel job ${j.id}?`,
    body: `${j.slug} ${j.part}: stops "${j.steps[j.current_step ?? 0]}" and kills its processes. Finished steps stay done.`,
    confirm: 'Cancel job', danger: true,
  })
  if (ok) await act(() => api.cancelJob(j.id), `Job ${j.id} cancelled`)
}
</script>

<template>
  <AnimatePresence>
    <motion.div v-if="drawerOpen" key="scrim" class="fixed inset-0 z-30 bg-ink/25" :initial="{ opacity: 0 }"
      :animate="{ opacity: 1 }" :exit="{ opacity: 0 }" @click="drawerOpen = false" />
    <motion.aside v-if="drawerOpen" key="drawer" class="raised fixed top-4 right-4 bottom-4 z-30 flex w-[460px] flex-col rounded-frame! p-6"
      :initial="{ x: 500 }" :animate="{ x: 0 }" :exit="{ x: 500 }" :transition="SPRING" aria-label="Jobs" role="dialog">
      <header class="flex items-center justify-between">
        <h2 class="font-display text-xl font-semibold">Jobs</h2>
        <button class="round-btn size-9!" aria-label="Close jobs" @click="drawerOpen = false"><X :size="18" /></button>
      </header>

      <p v-if="!shown" class="inset mt-6 px-4 py-8 text-center text-sm text-muted">
        No jobs yet. Start one from a part's run controls.
      </p>
      <section v-else class="mt-5 flex min-h-0 flex-1 flex-col">
        <div class="flex items-center gap-2">
          <span class="chip" :class="statusChip(shown.status === 'cancelled' ? '' : shown.status)">{{ shown.status }}</span>
          <RouterLink :to="`/series/${shown.slug}/${shown.part}`" class="truncate font-semibold hover:underline" @click="drawerOpen = false">
            {{ shown.slug }} · {{ shown.part }}
          </RouterLink>
          <span class="ml-auto shrink-0 text-xs text-muted">#{{ shown.id }} · {{ duration(shown) }}</span>
        </div>
        <p class="mt-2 text-sm text-muted">
          Step {{ (shown.current_step ?? 0) + 1 }} of {{ shown.steps.length }}:
          <code class="text-ink">{{ shown.steps[shown.current_step ?? 0] }}</code>
        </p>
        <!-- progress: the fill is scaled (transform only); unknown progress shimmers -->
        <div class="mt-3 h-3 overflow-hidden rounded-full bg-well shadow-[var(--shadow-inset)]" role="progressbar"
          :aria-valuenow="indeterminate ? undefined : Math.round(frac * 100)" aria-valuemin="0" aria-valuemax="100">
          <motion.div v-if="!indeterminate" class="h-full origin-left rounded-full"
            :class="shown.status === 'failed' ? 'bg-red' : shown.status === 'cancelled' ? 'bg-faint' : 'bg-blue'"
            :animate="{ scaleX: frac }" :transition="SPRING" />
          <div v-else class="indeterminate h-full w-1/3 rounded-full bg-blue" />
        </div>
        <pre ref="log" class="inset scroll scrolling mt-4 min-h-0 flex-1 overflow-auto p-3 font-mono text-xs leading-5 whitespace-pre-wrap text-ink"
          aria-label="Job output" tabindex="0">{{ shown.output.join('\n') || '(no output yet)' }}</pre>
        <button v-if="shown.status === 'running' || shown.status === 'queued'" class="btn btn-secondary mt-3 self-start"
          @click="cancel(shown)"><Square :size="14" aria-hidden="true" /> Cancel</button>
      </section>

      <section v-if="queued.length" class="mt-4">
        <h3 class="text-xs font-semibold tracking-wide text-muted uppercase">Queued</h3>
        <ul class="mt-2 space-y-1 text-sm">
          <li v-for="j in queued" :key="j.id" class="flex justify-between gap-2">
            <span class="truncate">#{{ j.id }} {{ j.slug }} · {{ j.part }}</span><span class="text-muted">{{ j.steps.length }} steps</span>
          </li>
        </ul>
      </section>
      <section v-if="recent.length" class="mt-4">
        <h3 class="text-xs font-semibold tracking-wide text-muted uppercase">Recent</h3>
        <ul class="scroll scrolling mt-2 max-h-40 space-y-1 overflow-y-auto pr-1 text-sm">
          <li v-for="j in recent" :key="j.id">
            <button class="flex w-full items-center gap-2 rounded-sm px-2 py-1 text-left hover:bg-well"
              :class="{ 'bg-well': shown?.id === j.id }" @click="selectedId = j.id">
              <span class="chip" :class="statusChip(j.status === 'cancelled' ? '' : j.status)">{{ j.status }}</span>
              <span class="min-w-0 flex-1 truncate">#{{ j.id }} {{ j.slug }} · {{ j.part }}</span>
              <span class="num shrink-0 text-muted">{{ duration(j) }}</span>
            </button>
          </li>
        </ul>
      </section>
    </motion.aside>
  </AnimatePresence>
</template>

<style scoped>
.indeterminate { animation: slide 1.2s ease-in-out infinite; }
@keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(300%); } }
@media (prefers-reduced-motion: reduce) {
  .indeterminate { width: 100%; animation: fade 1.4s ease-in-out infinite; }
}
</style>
