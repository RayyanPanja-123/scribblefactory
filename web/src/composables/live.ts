// One shared SSE connection (/api/events) and the job list it keeps current. Pages subscribe with onLive().
import { computed, onUnmounted, ref } from 'vue'
import { api, type Job } from '../api/client'
import { connectStream } from '../lib/events'
import { toast } from './feedback'

export type LiveEvent =
  | { type: 'part-changed'; slug: string; part: string }
  | { type: 'series-changed'; slug: string }
  | { type: 'resync' } // reconnected after a drop: anything may have changed

const TYPES = ['job-queued', 'job-started', 'job-step', 'job-output', 'job-finished', 'part-changed', 'series-changed']
const listeners = new Set<(e: LiveEvent) => void>()
const MAX_LINES = 200

export const jobs = ref<Job[]>([])
export const online = ref(false)
export const drawerOpen = ref(false)
/** index into job.output where the current step began (progress parses only the current step) */
export const stepStart = ref<Record<number, number>>({})

export const runningJob = computed(() => jobs.value.find((j) => j.status === 'running'))
export const queuedCount = computed(() => jobs.value.filter((j) => j.status === 'queued').length)
export const jobFor = (slug: string, part: string) =>
  jobs.value.find((j) => j.slug === slug && j.part === part && (j.status === 'running' || j.status === 'queued'))
/** a cast-sheet job queued or running for this series (it runs on any of its parts) */
export const castSheetJob = (slug: string) =>
  jobs.value.find((j) => j.slug === slug && j.steps.includes('cast-sheet') && (j.status === 'running' || j.status === 'queued'))
/** any job running in this series: cast approvals wait (a render reads series.json) */
export const seriesBusy = (slug: string) => jobs.value.some((j) => j.slug === slug && j.status === 'running')

/** Subscribe for the lifetime of the calling component. */
export function onLive(fn: (e: LiveEvent) => void) {
  listeners.add(fn)
  onUnmounted(() => listeners.delete(fn))
}
const emit = (e: LiveEvent) => listeners.forEach((fn) => fn(e))

async function loadJobs() {
  try {
    jobs.value = await api.jobs()
  } catch {
    /* API down: the stream reconnects and calls this again */
  }
}

function patch(id: number, fields: Partial<Job>) {
  const j = jobs.value.find((x) => x.id === id)
  if (j) Object.assign(j, fields)
}

function onEvent(type: string, d: any) {
  switch (type) {
    case 'job-queued':
      jobs.value.push(d)
      break
    case 'job-started':
      patch(d.id, { status: 'running', started_at: d.started_at ?? new Date().toISOString() })
      break
    case 'job-step': {
      const j = jobs.value.find((x) => x.id === d.id)
      if (j) {
        j.current_step = d.step
        stepStart.value[d.id] = j.output.length
      }
      break
    }
    case 'job-output': {
      const j = jobs.value.find((x) => x.id === d.id)
      if (j) {
        j.output.push(d.line)
        if (j.output.length > MAX_LINES) {
          const cut = j.output.length - MAX_LINES
          j.output.splice(0, cut)
          stepStart.value[d.id] = Math.max(0, (stepStart.value[d.id] ?? 0) - cut)
        }
      }
      break
    }
    case 'job-finished':
      patch(d.id, { status: d.status, finished_at: d.finished_at, returncode: d.returncode })
      if (d.status === 'done') toast(`Job ${d.id} done: ${d.slug} ${d.part}`, 'ok')
      else if (d.status === 'failed') toast(`Job ${d.id} failed: ${d.slug} ${d.part} (see the job drawer)`, 'error')
      break
    case 'part-changed':
      emit({ type: 'part-changed', slug: d.slug, part: d.part })
      break
    case 'series-changed':
      emit({ type: 'series-changed', slug: d.slug })
      break
  }
}

let stop: (() => void) | undefined
export function startLive() {
  if (stop) return
  loadJobs()
  stop = connectStream({
    url: '/api/events',
    types: TYPES,
    onEvent,
    onOpen: (reconnected) => {
      online.value = true
      if (reconnected) {
        loadJobs()
        emit({ type: 'resync' })
      }
    },
    onDown: () => (online.value = false),
  })
}

/** Refetch when this series (and part, if given) changes; also on resync. */
export function refetchOn(slug: () => string | null, part: () => string | null, refresh: () => void) {
  onLive((e) => {
    if (e.type === 'resync' || slug() === null) return refresh()
    if (e.slug !== slug()) return
    if (e.type === 'series-changed' || part() === null || e.part === part()) refresh()
  })
}
