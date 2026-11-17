<script setup lang="ts">
import { ArrowLeft, Check, CircleCheck, CircleX, Clock, ExternalLink, HardDrive, Instagram, Minus, Play, Plus, Save, Trash2, Youtube } from 'lucide-vue-next'
import { animate, motion } from 'motion-v'
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, media, type Approval, type Platform } from '../api/client'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import StageChips from '../components/StageChips.vue'
import Switch from '../components/Switch.vue'
import VideoPlayer from '../components/VideoPlayer.vue'
import VuMeter from '../components/VuMeter.vue'
import { act, confirm, zoom } from '../composables/feedback'
import { jobFor, refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { bytes, expandFrom, label, reducedMotion, shortDate, SPRING, today } from '../composables/ui'
import { nextSteps } from '../lib/nextSteps'

const props = defineProps<{ slug: string; part: string }>()
const route = useRoute()
const { data, error, loading, reload, refresh } = useApi(() =>
  Promise.all([api.part(props.slug, props.part), api.seriesDetail(props.slug)]))
refetchOn(() => props.slug, () => props.part, refresh)

const d = computed(() => data.value?.[0])
const series = computed(() => data.value?.[1].series)
const p = computed(() => d.value?.part)
const stages = computed<Record<string, string>>(() => Object.fromEntries(Object.entries(p.value?.stages ?? {}).map(([k, v]) => [k, v.status])))
const errors = computed(() => Object.fromEntries(Object.entries(p.value?.stages ?? {}).map(([k, v]) => [k, v.error ?? null])))
const approved = (a: Approval) => !!p.value?.approvals[a].approved_at
const has = (f: string) => !!d.value?.files[f]

// ---- gates (client mirror of the CLI's, for the disabled reasons; the API stays the judge) ----
const job = computed(() => jobFor(props.slug, props.part))
const busy = computed(() => d.value?.busy ?? (job.value ? `job ${job.value.id} is ${job.value.status} on this part` : null))
const unapprovedCast = computed(() => (series.value?.cast ?? []).filter((c) => !c.approved_at).map((c) => c.name))
const gate = computed<Record<string, string | null>>(() => ({
  'cast-sheet': series.value?.cast.length ? null : 'no cast yet: add some with cast-add',
  'render-stills': stages.value.shots !== 'done' ? 'shot plan not done yet'
    : unapprovedCast.value.length ? `cast not approved: ${unapprovedCast.value.join(', ')}` : null,
  'test-render': approved('stills') ? null : 'stills not approved yet',
  render: !approved('stills') ? 'stills not approved yet' : !approved('test_render') ? 'test render not approved yet' : null,
}))
const why = (cmd: string) => busy.value ?? gate.value[cmd]

const plan = computed(() => nextSteps({
  stages: stages.value as never,
  approvals: { stills: approved('stills'), test_render: approved('test_render'), final: approved('final') },
  files: { voice: has('voice.mp3'), stillsSheet: has('stills-sheet.png'), testRender: has('test-render.mp4') },
  castApproved: !unapprovedCast.value.length,
}))
const planOpen = ref(false)
const workers = ref(2)

async function run(steps: string[]) {
  planOpen.value = false
  await act(() => api.submitJob(props.slug, props.part, steps), `Job queued: ${steps.join(' → ')}`)
}
async function rerun(stage: string) {
  if (stage === 'render') {
    const ok = await confirm({ title: 'Re-render everything?', body: 'render --force deletes all frames of this part and renders them again.', confirm: 'Re-render', danger: true })
    if (!ok) return
    return run(['render --force'])
  }
  return run([`run --stage ${stage} --force`])
}

// ---- approvals ----
const APPROVALS: { key: Approval; label: string; file: string }[] = [
  { key: 'stills', label: 'Stills', file: 'stills-sheet.png' },
  { key: 'test_render', label: 'Test render', file: 'test-render.mp4' },
  { key: 'final', label: 'Final', file: 'final.mp4' },
]
function approvalReason(a: (typeof APPROVALS)[number]): string | null {
  if (!has(a.file)) return `no ${a.file} yet`
  if (a.key === 'final' && stages.value.finish !== 'done') return 'finish not done yet'
  return busy.value
}
async function approve(a: (typeof APPROVALS)[number]) {
  if (a.key === 'final') {
    const ok = await confirm({ title: 'Approve the final video?', body: 'Approvals are kept for good: only approve after watching final.mp4 to the end.', confirm: 'Approve final' })
    if (!ok) return
  }
  if (await act(() => api.approve(props.slug, props.part, a.key), `${a.label} approved`)) refresh()
}

// ---- media ----
const src = (rel: string) => media(props.slug, `${props.part}/${rel}`)
const sources = computed(() => [
  { key: 'test', label: 'Test render', file: 'test-render.mp4' },
  { key: 'preview', label: 'Preview', file: 'preview.mp4' },
  { key: 'final', label: 'Final', file: 'final.mp4' },
].filter((s) => has(s.file)).map((s) => ({ ...s, src: src(s.file) })))

const TILT = [-5, 3, -2]
const picked = computed(() => p.value?.thumbnail_choice)
async function pick(n: number) {
  if (await act(() => api.pickThumbnail(props.slug, props.part, n as 1 | 2 | 3), `Thumbnail ${n} picked`)) refresh()
}

// ---- QA ----
type Check = { ok: boolean; value: unknown; want: unknown }
const qa = computed(() => d.value?.qa as { ok: boolean; checks: Record<string, Check> } | null | undefined)
const lufs = computed(() => {
  const v = qa.value?.checks.loudness?.value
  return typeof v === 'number' ? v : null
})

// ---- upload.md ----
const text = ref('')
const saved = ref('')
const dirty = computed(() => text.value !== saved.value)
watch(() => d.value?.upload_md, (md) => {
  if (!dirty.value) text.value = saved.value = md ?? '' // never clobber unsaved edits on a live refresh
}, { immediate: true })
async function save() {
  if (!dirty.value) return
  const body = text.value
  if (await act(() => api.saveUpload(props.slug, props.part, body), 'upload.md saved')) saved.value = body
}
function onKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    save()
  }
}
window.addEventListener('keydown', onKey)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

// ---- posting ----
const PLATFORMS: { key: Platform; name: string; icon: typeof Youtube; color: string }[] = [
  { key: 'youtube', name: 'YouTube', icon: Youtube, color: 'text-youtube' },
  { key: 'instagram', name: 'Instagram', icon: Instagram, color: 'text-instagram' },
]
const form = reactive<Record<Platform, { url: string; date: string; replacing: boolean }>>({
  youtube: { url: '', date: today(), replacing: false },
  instagram: { url: '', date: today(), replacing: false },
})
async function replace(pl: Platform) {
  const ok = await confirm({ title: `Replace the ${pl} link?`, body: 'The current link and date are overwritten.', confirm: 'Replace', danger: true })
  if (ok) form[pl].replacing = true
}
async function post(pl: Platform) {
  const f = form[pl]
  const r = await act(() => api.markPosted(props.slug, props.part, { platform: pl, url: f.url.trim(), date: f.date || undefined, force: f.replacing }),
    `Marked posted on ${pl}`)
  if (r) {
    Object.assign(f, { url: '', replacing: false })
    refresh()
  }
}

// ---- danger zone ----
const cleanReason = computed(() =>
  !has('final.mp4') || stages.value.finish !== 'done' ? 'finish not done yet: frames are still needed'
    : !d.value?.frames_bytes ? 'no frames to clean' : busy.value)
async function clean() {
  const ok = await confirm({ title: 'Delete the frames?', body: `Frees ${bytes(d.value!.frames_bytes)}. final.mp4 is kept; re-rendering needs the frames again.`, confirm: 'Delete frames', danger: true })
  if (ok && (await act(() => api.cleanFrames(props.slug, props.part), 'Frames deleted'))) refresh()
}

// ---- shared-element expand from the part card (FLIP: transforms only) + #section deep links ----
const header = ref<HTMLElement>()
watch(header, (el) => {
  const from = expandFrom.rect
  if (!el || !from || expandFrom.key !== `${props.slug}/${props.part}`) return
  expandFrom.rect = null
  if (reducedMotion()) return
  const to = el.getBoundingClientRect()
  animate(el, { x: [from.left - to.left, 0], y: [from.top - to.top, 0], scaleX: [from.width / to.width, 1], scaleY: [from.height / to.height, 1] }, SPRING)
})
watch(data, async (v, old) => {
  if (!v || old || !route.hash) return
  await nextTick()
  document.querySelector(route.hash)?.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start' })
})
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />

  <div v-else-if="loading" class="space-y-6" aria-busy="true" aria-label="Loading part">
    <div class="skeleton h-44" />
    <div class="grid grid-cols-[360px_1fr] gap-6"><div class="skeleton h-[720px]" /><div class="skeleton h-[720px]" /></div>
  </div>

  <div v-else-if="d && p && series" class="space-y-6">
    <RouterLink :to="`/series/${slug}`" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> {{ series.title }}</RouterLink>

    <!-- header (the part card expands into this) -->
    <div ref="header" class="raised origin-top-left p-6">
      <div class="flex flex-wrap items-center gap-3">
        <span class="num text-3xl text-muted">{{ String(p.number).padStart(2, '0') }}</span>
        <h2 class="font-display text-3xl font-semibold">{{ p.title }}</h2>
        <span v-if="busy" class="chip chip-blue"><span class="pulse size-1.5 rounded-full bg-current" />{{ busy }}</span>
        <div class="relative ml-auto">
          <button class="btn btn-primary" :aria-expanded="planOpen" @click="planOpen = !planOpen">
            <Play :size="16" aria-hidden="true" /> Run next
          </button>
          <div v-if="planOpen" class="raised absolute top-full right-0 z-20 mt-3 w-80 p-4 text-sm" role="dialog" aria-label="Planned steps">
            <p class="font-semibold">Planned steps</p>
            <ol v-if="plan.steps.length" class="mt-2 list-decimal space-y-1 pl-5">
              <li v-for="s in plan.steps" :key="s"><code>{{ s }}</code></li>
            </ol>
            <p v-else class="mt-2 text-muted">Nothing to run yet.</p>
            <p v-if="plan.stop" class="mt-3 flex items-start gap-2 text-amber-ink">
              <Clock :size="16" class="mt-0.5 shrink-0" aria-hidden="true" /> Stops before: {{ plan.stop }}
            </p>
            <p v-else class="mt-3 text-green-ink">All stages done and approved.</p>
            <div class="mt-4 flex justify-end gap-2">
              <button class="btn btn-secondary" @click="planOpen = false">Close</button>
              <button class="btn btn-primary" :disabled="!plan.steps.length || !!busy" :title="busy ?? undefined"
                @click="run(plan.steps)">Start</button>
            </div>
          </div>
        </div>
      </div>
      <StageChips class="mt-4" :stages="stages" :errors="errors" menu :disabled="busy" @rerun="rerun" />
      <div class="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <span class="mr-1 text-muted">Approvals</span>
        <span v-for="a in APPROVALS" :key="a.key" class="chip" :class="approved(a.key) ? 'chip-green' : d.files[a.file] ? 'chip-amber' : ''">
          <Check v-if="approved(a.key)" :size="14" aria-hidden="true" />{{ a.label.toLowerCase() }}
          <span class="sr-only">: {{ approved(a.key) ? 'approved' : d.files[a.file] ? 'waiting' : 'not ready' }}</span>
        </span>
      </div>
    </div>

    <div class="grid items-start gap-6 xl:grid-cols-[360px_1fr]">
      <!-- player -->
      <section class="raised p-5" aria-label="Video">
        <VideoPlayer v-if="sources.length" :sources="sources" />
        <EmptyState v-else :icon="Play" title="No video yet" text="A test render, preview or final shows up here." />
      </section>

      <div class="space-y-6">
        <!-- run controls -->
        <section id="run" class="raised p-6">
          <h3 class="font-display text-lg font-semibold">Run</h3>
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <div v-for="c in [{ cmd: 'render-stills', label: 'Render stills' }, { cmd: 'test-render', label: 'Test render (5 s)' }, { cmd: 'cast-sheet', label: 'Cast sheet' }]"
              :key="c.cmd" class="flex flex-col">
              <button class="btn btn-secondary justify-center" :disabled="!!why(c.cmd)" :title="why(c.cmd) ?? undefined"
                @click="run([c.cmd])">{{ c.label }}</button>
              <span v-if="why(c.cmd)" class="mt-1 text-xs text-muted">{{ why(c.cmd) }}</span>
            </div>
            <div class="flex flex-col">
              <div class="flex gap-2">
                <button class="btn btn-secondary flex-1 justify-center" :disabled="!!why('render')" :title="why('render') ?? undefined"
                  @click="run([`render --workers ${workers}`])">Full render</button>
                <div class="inset flex items-center rounded-full px-1" role="group" aria-label="Render workers">
                  <button class="grid size-7 place-items-center rounded-full disabled:opacity-40" aria-label="Fewer workers"
                    :disabled="workers <= 1" @click="workers--"><Minus :size="14" /></button>
                  <span class="num w-5 text-center" :aria-label="`${workers} workers`">{{ workers }}</span>
                  <button class="grid size-7 place-items-center rounded-full disabled:opacity-40" aria-label="More workers"
                    :disabled="workers >= 3" @click="workers++"><Plus :size="14" /></button>
                </div>
              </div>
              <span class="mt-1 text-xs text-muted">{{ why('render') ?? `${workers} parallel browser${workers > 1 ? 's' : ''}` }}</span>
            </div>
          </div>
        </section>

        <!-- approvals -->
        <section id="approvals" class="raised p-6">
          <h3 class="font-display text-lg font-semibold">Approvals</h3>
          <div class="mt-4 flex flex-wrap gap-x-8 gap-y-4">
            <div v-for="a in APPROVALS" :key="a.key">
              <Switch :on="approved(a.key)" :label="a.label" :reason="approved(a.key) ? null : approvalReason(a)" @request="approve(a)" />
              <p class="mt-1 pl-[68px] text-xs text-muted">
                {{ approved(a.key) ? shortDate(p.approvals[a.key].approved_at) : approvalReason(a) ?? 'ready to approve' }}
              </p>
            </div>
          </div>
        </section>

        <!-- QA -->
        <section id="qa" class="raised p-6">
          <div class="flex items-center gap-3">
            <h3 class="font-display text-lg font-semibold">QA</h3>
            <span v-if="qa" class="chip" :class="qa.ok ? 'chip-green' : 'chip-red'">{{ qa.ok ? 'all checks pass' : 'checks failed' }}</span>
          </div>
          <div v-if="qa" class="mt-4 grid items-center gap-6 lg:grid-cols-[1fr_260px]">
            <ul class="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              <li v-for="(c, name) in qa.checks" :key="name" class="flex items-start gap-2">
                <CircleCheck v-if="c.ok" :size="18" class="mt-px shrink-0 text-green-ink" aria-label="pass" />
                <CircleX v-else :size="18" class="mt-px shrink-0 text-red-ink" aria-label="fail" />
                <span class="min-w-0">
                  <span class="font-semibold">{{ label(String(name)) }}</span>
                  <span class="block text-xs text-muted">{{ c.value }} · want {{ c.want }}</span>
                </span>
              </li>
            </ul>
            <VuMeter v-if="lufs !== null" :lufs="lufs" />
          </div>
          <EmptyState v-else class="mt-4" :icon="CircleCheck" title="No QA yet" text="Runs with the finish stage (qa.json)." />
        </section>
      </div>
    </div>

    <!-- light table: sheets + thumbnail polaroids -->
    <section id="review" class="raised p-6">
      <h3 class="font-display text-lg font-semibold">Light table</h3>
      <p class="text-sm text-muted">Click a sheet to zoom. Click a polaroid to pick the thumbnail.</p>
      <div class="lighttable inset mt-4 grid gap-8 p-8 lg:grid-cols-[1fr_auto]">
        <div class="flex flex-wrap items-start gap-6">
          <figure v-for="sh in [{ f: 'stills-sheet.png', t: 'Stills sheet', url: has('stills-sheet.png') ? src('stills-sheet.png') : null }, { f: 'cast-sheet.png', t: 'Cast sheet', url: data?.[1].cast_sheet ?? null }]"
            :key="sh.f" class="w-60">
            <button v-if="sh.url" class="block w-full cursor-zoom-in rounded-md bg-white p-2 shadow-[var(--shadow-raised)] transition-transform hover:-translate-y-1"
              :aria-label="`Zoom ${sh.t}`" @click="zoom(sh.url!, sh.t)">
              <img :src="sh.url" :alt="sh.t" loading="lazy" class="w-full rounded-sm" />
            </button>
            <div v-else class="grid h-40 place-items-center rounded-md border-2 border-dashed border-[#cfc8bb] text-sm text-muted">not rendered yet</div>
            <figcaption class="mt-2 text-center text-sm font-semibold">{{ sh.t }}</figcaption>
          </figure>
        </div>
        <div id="thumbnails">
          <p class="mb-8 text-center text-sm font-semibold">Thumbnail</p>
          <div v-if="d.thumbs.length" class="flex gap-5">
            <motion.button v-for="(t, i) in d.thumbs" :key="t" class="relative w-32 bg-white p-2 pb-8 shadow-[var(--shadow-raised)]"
              :animate="picked === `thumbs/${t}` ? { rotate: 0, y: -12, scale: 1.06 } : { rotate: TILT[i % 3], y: 0, scale: 1 }"
              :while-hover="picked === `thumbs/${t}` ? undefined : { y: -4 }" :transition="SPRING"
              :aria-pressed="picked === `thumbs/${t}`" :aria-label="`Pick thumbnail ${i + 1}`" :disabled="!!busy"
              @click="pick(Number(t.match(/\d+/)![0]))">
              <img :src="src(`thumbs/${t}`)" :alt="`Thumbnail candidate ${i + 1}`" loading="lazy" class="aspect-[9/16] w-full object-cover" />
              <span class="absolute bottom-2 left-0 w-full text-center font-display text-sm text-muted">#{{ i + 1 }}</span>
              <span v-if="picked === `thumbs/${t}`" class="absolute -top-2 left-1/2 grid size-6 -translate-x-1/2 place-items-center rounded-full bg-green text-white shadow-[var(--shadow-dark)]">
                <Check :size="14" :stroke-width="3" aria-hidden="true" />
              </span>
            </motion.button>
          </div>
          <p v-else class="text-sm text-muted">No candidates yet (thumbnails stage).</p>
        </div>
      </div>
    </section>

    <div class="grid items-start gap-6 xl:grid-cols-2">
      <!-- upload.md -->
      <section id="upload" class="raised p-6">
        <div class="flex items-center gap-2">
          <h3 class="font-display text-lg font-semibold">upload.md</h3>
          <span v-if="dirty" class="size-2.5 rounded-full bg-amber" title="Unsaved changes" aria-label="Unsaved changes" />
          <button class="btn btn-primary ml-auto" :disabled="!dirty" @click="save"><Save :size="16" aria-hidden="true" /> Save</button>
        </div>
        <p class="mt-1 text-xs text-muted">Ctrl+S saves. Written atomically; nothing else in the part is touched.</p>
        <label class="sr-only" for="upload-md">upload.md</label>
        <textarea id="upload-md" v-model="text" class="paper inset mt-4 block min-h-64 w-full resize-y p-5 font-mono text-sm leading-7 outline-none"
          spellcheck="true" @keydown="onKey" />
      </section>

      <div class="space-y-6">
        <!-- posting -->
        <section id="posting" class="grid gap-6 sm:grid-cols-2">
          <div v-for="pl in PLATFORMS" :key="pl.key" class="raised p-5">
            <p class="flex items-center gap-2 font-display text-lg font-semibold">
              <component :is="pl.icon" :size="20" :class="pl.color" aria-hidden="true" />{{ pl.name }}
            </p>
            <template v-if="p.posted[pl.key] && !form[pl.key].replacing">
              <a :href="p.posted[pl.key]!.url" target="_blank" rel="noopener noreferrer"
                class="mt-3 flex items-center gap-1 text-sm font-semibold break-all text-blue-ink hover:underline">
                {{ p.posted[pl.key]!.url }} <ExternalLink :size="14" class="shrink-0" aria-hidden="true" />
              </a>
              <p class="mt-1 text-sm text-muted">posted {{ shortDate(p.posted[pl.key]!.posted_at) }}</p>
              <button class="btn btn-secondary mt-4" @click="replace(pl.key)">Replace</button>
            </template>
            <form v-else class="mt-3 space-y-3" @submit.prevent="post(pl.key)">
              <label class="block text-xs font-semibold text-muted">Link
                <input v-model="form[pl.key].url" type="url" required placeholder="https://"
                  class="inset mt-1 block w-full rounded-full px-4 py-2 text-sm text-ink outline-none" />
              </label>
              <label class="block text-xs font-semibold text-muted">Date
                <input v-model="form[pl.key].date" type="date" class="inset mt-1 block w-full rounded-full px-4 py-2 text-sm text-ink outline-none" />
              </label>
              <div class="flex gap-2">
                <button class="btn btn-primary" :disabled="!form[pl.key].url.trim()">Mark posted</button>
                <button v-if="form[pl.key].replacing" type="button" class="btn btn-secondary" @click="form[pl.key].replacing = false">Cancel</button>
              </div>
            </form>
          </div>
        </section>

        <!-- disk + danger zone -->
        <section id="disk" class="raised p-6">
          <h3 class="font-display text-lg font-semibold">Disk</h3>
          <dl class="mt-3 grid grid-cols-2 gap-4">
            <div class="inset px-4 py-3"><dt class="text-xs font-semibold text-muted">Frames</dt><dd class="num text-xl">{{ bytes(d.frames_bytes) }}</dd></div>
            <div class="inset px-4 py-3"><dt class="text-xs font-semibold text-muted">Whole part</dt><dd class="num text-xl">{{ bytes(d.part_bytes) }}</dd></div>
          </dl>
          <div class="mt-5 rounded-md border border-[#f0c9bd] bg-[#fbeee9] p-4">
            <p class="flex items-center gap-2 text-sm font-semibold text-red-ink"><HardDrive :size="16" aria-hidden="true" /> Danger zone</p>
            <p class="mt-1 text-xs text-muted">Delete frames/ once final.mp4 is finished. Frees {{ bytes(d.frames_bytes) }}.</p>
            <button class="btn btn-secondary mt-3 text-red-ink" :disabled="!!cleanReason" :title="cleanReason ?? undefined" @click="clean">
              <Trash2 :size="16" aria-hidden="true" /> Clean frames
            </button>
            <p v-if="cleanReason" class="mt-1 text-xs text-muted">{{ cleanReason }}</p>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lighttable { background: radial-gradient(ellipse at 50% 40%, #fffdf7 0%, #f3eee3 70%, #ebe5d8 100%); }
.paper {
  field-sizing: content; /* autosize, native */
  background-color: #fbf8f1;
  background-image: var(--grain), repeating-linear-gradient(transparent 0 27px, rgb(96 78 52 / 0.08) 27px 28px);
  background-position: 0 0, 0 19px;
}
button:disabled { cursor: not-allowed; opacity: 0.55; }
</style>
