<script setup lang="ts">
import { Check, CircleDashed, Copy, Film, LoaderCircle, Square, X } from 'lucide-vue-next'
import { AnimatePresence, LayoutGroup, motion } from 'motion-v'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { api, type Job } from '../api/client'
import { act, confirm, confirmState, toast, zoomed } from '../composables/feedback'
import { drawerOpen, jobs, runningJob, stepStart } from '../composables/live'
import { reducedMotion, SPRING } from '../composables/ui'
import { shortPaths } from '../lib/paths'
import { jobFraction, parseProgress } from '../lib/progress'
import asleepReel from '../assets/asleep-reel.svg'

// A sheet sliding in from the right over a scrim.
const tab = ref<'now' | 'history'>('now')
const expanded = ref<number | null>(null)
const still = reducedMotion() // MotionConfig stills transforms; the clip-path reveal needs its own opt-out
const queued = computed(() => jobs.value.filter((j) => j.status === 'queued'))
const history = computed(() => jobs.value.filter((j) => !['queued', 'running'].includes(j.status)).reverse())
const run = computed(() => runningJob.value)

// content rows enter 30 ms apart
const row = (i: number) => ({
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { ...SPRING, delay: 0.08 + i * 0.03 } },
})

// ---- running job ----
const stepFrac = computed(() => (run.value ? parseProgress(run.value.output.slice(stepStart.value[run.value.id] ?? 0)) : null))
const frac = computed(() => (run.value ? jobFraction(run.value.current_step, run.value.steps.length, stepFrac.value) : 0))
const now = ref(Date.now())
const tick = setInterval(() => (now.value = Date.now()), 1000)
onBeforeUnmount(() => clearInterval(tick))
const clock = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
const elapsed = computed(() => (run.value?.started_at ? clock(now.value - Date.parse(run.value.started_at)) : '0:00'))

const log = ref<HTMLElement>()
watch(() => [run.value?.id, run.value?.output.length, drawerOpen.value, tab.value], async () => {
  await nextTick()
  if (log.value) log.value.scrollTop = log.value.scrollHeight
})
async function copyLog(j: Job) {
  try {
    await navigator.clipboard.writeText(j.output.join('\n'))
    toast('Log copied', 'ok')
  } catch {
    toast('Could not copy: clipboard not available', 'error')
  }
}

async function cancel(j: Job) {
  const queuedOnly = j.status === 'queued'
  const ok = await confirm({
    title: queuedOnly ? `Remove ${j.tag} from the queue?` : `Cancel ${j.tag}?`,
    body: queuedOnly ? `${j.slug} ${j.part}: it has not started; nothing is touched.`
      : `${j.slug} ${j.part}: stops "${j.steps[j.current_step ?? 0]}" and kills its processes. Finished steps stay done.`,
    confirm: queuedOnly ? 'Remove' : 'Cancel job', danger: true,
  })
  if (ok) await act(() => api.cancelJob(j.id), queuedOnly ? `${j.tag} removed` : `${j.tag} cancelled`)
}
async function retry(j: Job) {
  await act(() => api.submitJob(j.slug, j.part, j.steps), `${j.tag} queued again`)
}

// ---- history ----
const duration = (j: Job) =>
  j.started_at ? clock((j.finished_at ? Date.parse(j.finished_at) : now.value) - Date.parse(j.started_at)) : '-'
const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
function ago(iso: string | null) {
  if (!iso) return ''
  const s = (Date.parse(iso) - now.value) / 1000
  for (const [unit, size] of [['day', 86400], ['hour', 3600], ['minute', 60]] as const)
    if (Math.abs(s) >= size) return rtf.format(Math.round(s / size), unit)
  return 'just now'
}
const summary = (j: Job) => (j.steps.length === 1 ? j.steps[0] : `${j.steps[0]} + ${j.steps.length - 1} more`)
const DOT: Record<string, string> = { done: 'bg-green', failed: 'bg-red', cancelled: 'bg-faint' }

function onKey(e: KeyboardEvent) {
  // a dialog or zoom on top takes the first Esc (Overlays.vue also stops that event); the next one closes the drawer
  if (e.key === 'Escape' && drawerOpen.value && !confirmState.value && !zoomed.value) drawerOpen.value = false
}
window.addEventListener('keydown', onKey)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <AnimatePresence>
    <motion.div v-if="drawerOpen" key="scrim" class="fixed inset-0 z-30 bg-[var(--scrim)]"
      :initial="{ opacity: 0 }" :animate="{ opacity: 1 }" :exit="{ opacity: 0 }" @click="drawerOpen = false" />
    <motion.aside v-if="drawerOpen" key="drawer" role="dialog" aria-label="Jobs"
      class="raised fixed top-2 right-2 bottom-2 z-40 flex w-[calc(100%-16px)] max-w-[440px] flex-col p-4 shadow-[var(--shadow-pop)]! sm:top-3 sm:right-3 sm:bottom-3 sm:p-5"
      :initial="{ opacity: 0, x: 40, scale: 0.98 }" :animate="{ opacity: 1, x: 0, scale: 1 }"
      :exit="{ opacity: 0, x: 40, scale: 0.98 }" :transition="SPRING">
      <header class="flex items-center gap-3">
        <span class="round-btn shrink-0 text-ink">
          <Film :size="18" :class="{ reel: run }" aria-hidden="true" />
        </span>
        <h2 class="font-display text-xl font-semibold">Jobs</h2>
        <span v-if="run" class="chip chip-blue">1 running</span>
        <span v-if="queued.length" class="chip chip-amber">{{ queued.length }} queued</span>
        <button class="round-btn ml-auto size-10!" aria-label="Close jobs" @click="drawerOpen = false"><X :size="18" /></button>
      </header>

      <div class="inset relative mt-4 flex p-1" role="tablist" aria-label="Jobs view">
        <button v-for="t in (['now', 'history'] as const)" :key="t" role="tab" :aria-selected="tab === t"
          class="relative flex-1 rounded-sm py-1.5 text-sm font-semibold" @click="tab = t">
          <motion.span v-if="tab === t" layout-id="drawer-tab" class="absolute inset-0 rounded-sm bg-panel shadow-[var(--shadow-sheet)]"
            :transition="SPRING" />
          <span class="relative">{{ t === 'now' ? 'Now' : `History${history.length ? ` (${history.length})` : ''}` }}</span>
        </button>
      </div>

      <!-- NOW -->
      <div v-if="tab === 'now'" class="scroll scrolling -mx-1 mt-4 min-h-0 flex-1 overflow-y-auto px-1 pb-1">
        <template v-if="run">
          <motion.section class="console rounded-lg p-4 text-[#e9eef3]" v-bind="row(0)" aria-label="Running job">
            <div class="flex items-center gap-2">
              <span class="led size-2.5 rounded-full bg-[#3dbb7a]" aria-hidden="true" />
              <span class="text-xs font-semibold tracking-wide text-[#9fb0c0] uppercase">Running · {{ run.tag }}</span>
              <span class="num ml-auto text-lg" :aria-label="`elapsed ${elapsed}`">{{ elapsed }}</span>
            </div>
            <RouterLink :to="`/series/${run.slug}/${run.part}`" class="mt-1 block font-display text-lg font-semibold hover:underline"
              @click="drawerOpen = false">{{ run.slug }} · {{ run.part }}</RouterLink>
            <ol class="mt-3 space-y-1.5" aria-label="Steps">
              <li v-for="(s, i) in run.steps" :key="i" class="flex items-center gap-2 font-mono text-xs"
                :class="i < (run.current_step ?? 0) ? 'text-[#7fd8a6]' : i === run.current_step ? 'text-[#e9eef3]' : 'text-[#8496a8]'">
                <Check v-if="i < (run.current_step ?? 0)" :size="14" :stroke-width="3" aria-label="done" />
                <LoaderCircle v-else-if="i === run.current_step" :size="14" class="spin" aria-label="running" />
                <CircleDashed v-else :size="14" aria-label="upcoming" />
                <span class="truncate">{{ s }}</span>
              </li>
            </ol>
            <div class="track mt-4 h-2.5 overflow-hidden rounded-full" role="progressbar" aria-valuemin="0" aria-valuemax="100"
              :aria-valuenow="stepFrac === null ? undefined : Math.round(frac * 100)">
              <motion.div v-if="stepFrac !== null" class="fill h-full origin-left rounded-full" :animate="{ scaleX: frac }" :transition="SPRING" />
              <div v-else class="sheen h-full w-full rounded-full" />
            </div>
            <p class="mt-2 text-xs text-[#9fb0c0]">
              Step {{ (run.current_step ?? 0) + 1 }} of {{ run.steps.length }} · {{ stepFrac === null ? 'working' : `${Math.round(frac * 100)}%` }}
            </p>
          </motion.section>

          <motion.div class="relative mt-3" v-bind="row(1)">
            <pre ref="log" class="terminal scroll scrolling h-56 overflow-auto rounded-md p-3 pt-7 font-mono text-[12px] leading-5 whitespace-pre-wrap text-[#dfe6ed]"
              tabindex="0" aria-label="Live log">{{ run.output.map(shortPaths).join('\n') || 'waiting for output' }}</pre>
            <button class="absolute top-2 right-2 grid size-8 place-items-center rounded-sm bg-[#1e2730] text-[#dfe6ed] hover:bg-[#2a3541]"
              aria-label="Copy log" title="Copy log" @click="copyLog(run)"><Copy :size="14" /></button>
          </motion.div>

          <motion.div v-bind="row(2)">
            <button class="btn btn-secondary mt-3" @click="cancel(run)">
              <Square :size="14" class="text-red" fill="currentColor" aria-hidden="true" /> Cancel job
            </button>
          </motion.div>
        </template>

        <section v-if="queued.length" :class="run ? 'mt-5' : ''" aria-label="Queued">
          <h3 class="text-xs font-semibold tracking-wide text-muted uppercase">Up next</h3>
          <motion.div v-for="(j, i) in queued" :key="j.id" v-bind="row(i + 3)"
            class="raised mt-2 flex items-center gap-3 py-2 pr-2 pl-3 text-sm shadow-none!">
            <span class="num grid size-7 shrink-0 place-items-center rounded-sm bg-well text-muted">{{ i + 1 }}</span>
            <span class="min-w-0 flex-1">
              <span class="block truncate font-semibold">{{ j.slug }} · {{ j.part }}</span>
              <span class="block truncate font-mono text-xs text-muted">{{ j.tag }} · {{ summary(j) }}</span>
            </span>
            <button class="grid size-8 shrink-0 place-items-center rounded-sm text-muted hover:bg-well hover:text-red-ink"
              :aria-label="`Remove ${j.tag} from the queue`" @click="cancel(j)"><X :size="16" /></button>
          </motion.div>
        </section>

        <motion.div v-if="!run && !queued.length" class="flex h-full flex-col items-center justify-center px-6 text-center" v-bind="row(0)">
          <!-- a stickman asleep against a film reel (marker style, like the brand mark) -->
          <img :src="asleepReel" alt="" class="w-44 dark:invert dark:hue-rotate-180" aria-hidden="true" />
          <p class="mt-4 font-display text-lg font-semibold">Nothing running.</p>
          <p class="mt-1 max-w-60 text-sm text-muted">Start a job from a part's Run panel.</p>
        </motion.div>
      </div>

      <!-- HISTORY -->
      <div v-else class="scroll scrolling -mx-1 mt-4 min-h-0 flex-1 overflow-y-auto px-1 pb-1">
        <p v-if="!history.length" class="mt-10 text-center text-sm text-muted">No finished jobs yet.</p>
        <LayoutGroup>
          <!-- rows slide by transform (layout="position"); an opened log is revealed with clip-path -->
          <motion.div v-for="(j, i) in history" :key="j.id" layout="position" v-bind="row(i)" :transition="SPRING"
            class="raised mb-2 overflow-hidden shadow-none!">
            <button class="flex w-full items-center gap-3 px-4 py-3 text-left" :aria-expanded="expanded === j.id"
              @click="expanded = expanded === j.id ? null : j.id">
              <span class="size-2.5 shrink-0 rounded-full" :class="DOT[j.status] ?? 'bg-faint'" aria-hidden="true" />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-semibold">{{ j.slug }} · {{ j.part }}<span class="sr-only">: {{ j.status }}</span></span>
                <span class="block truncate font-mono text-xs text-muted">{{ j.tag }} · {{ summary(j) }}</span>
              </span>
              <span class="shrink-0 text-right text-xs text-muted">
                <span class="num block text-sm text-ink">{{ duration(j) }}</span>{{ ago(j.finished_at) }}
              </span>
            </button>
              <motion.div v-if="expanded === j.id" class="px-3 pb-3"
              :initial="still ? { opacity: 0 } : { clipPath: 'inset(0 0 100% 0)', opacity: 0 }"
              :animate="still ? { opacity: 1 } : { clipPath: 'inset(0 0 0% 0)', opacity: 1 }" :transition="SPRING">
              <div class="relative">
                <pre class="terminal scroll scrolling max-h-52 overflow-auto rounded-md p-3 pt-6 font-mono text-[12px] leading-5 whitespace-pre-wrap text-[#dfe6ed]"
                  tabindex="0" :aria-label="`Log of ${j.tag}`">{{ j.output.map(shortPaths).join('\n') || '(no output)' }}</pre>
                <button class="absolute top-2 right-2 grid size-7 place-items-center rounded-sm bg-[#1e2730] text-[#dfe6ed] hover:bg-[#2a3541]"
                  :aria-label="`Copy log of ${j.tag}`" @click="copyLog(j)"><Copy :size="13" /></button>
              </div>
              <div class="mt-2 flex flex-wrap gap-2">
                <RouterLink :to="`/series/${j.slug}/${j.part}`" class="btn btn-secondary text-xs" @click="drawerOpen = false">Open part</RouterLink>
                <button v-if="j.status === 'failed'" class="btn btn-primary text-xs" @click="retry(j)">Run again</button>
              </div>
            </motion.div>
          </motion.div>
        </LayoutGroup>
      </div>
    </motion.aside>
  </AnimatePresence>
</template>

<style scoped>
/* the console and logs stay dark in both themes: they are a terminal */
.console { background: #121920; box-shadow: inset 0 0 0 1px #24303c; }
.track { background: #0a0f14; box-shadow: inset 0 0 0 1px #24303c; }
.fill { background: #6aa6ec; }
.sheen {
  background: linear-gradient(90deg, transparent 0%, rgb(106 166 236 / 0.85) 50%, transparent 100%);
  animation: sheen 1.4s ease-in-out infinite;
}
.terminal {
  background: #0d1318;
  box-shadow: inset 0 0 0 1px #22303b;
  mask-image: linear-gradient(to bottom, transparent 0, #000 22px); /* fade at the top edge */
}
.led { box-shadow: 0 0 6px #3dbb7a; animation: led 2s ease-in-out infinite; }
.spin { animation: spin 1s linear infinite; }
@keyframes sheen { from { transform: translateX(-100%); } to { transform: translateX(100%); } }
@keyframes led { 50% { opacity: 0.45; } }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .sheen { animation: fade 1.6s ease-in-out infinite; transform: none; }
  .spin { animation: none; }
}
</style>
