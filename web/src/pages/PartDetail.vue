<script setup lang="ts">
import { ArrowLeft, ArrowRight, Check, CircleAlert, CircleCheck, CircleX, Copy, ExternalLink, HardDrive, Instagram, Minus, Play, Plus, RefreshCw, Save, Trash2, Upload, Youtube } from 'lucide-vue-next'
import { animate, motion } from 'motion-v'
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, media, type Approval, type Platform, type StoryCheck } from '../api/client'
import PartStepper from '../components/PartStepper.vue'
import ErrorCard from '../components/ErrorCard.vue'
import StageChips from '../components/StageChips.vue'
import Switch from '../components/Switch.vue'
import VideoPlayer from '../components/VideoPlayer.vue'
import VuMeter from '../components/VuMeter.vue'
import { act, confirm, toast, zoom } from '../composables/feedback'
import { jobFor, refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { bytes, expandFrom, label, reducedMotion, shortDate, SPRING, today } from '../composables/ui'
import { partNext, type PartState } from '../lib/partNext'
import { partSteps } from '../lib/partSteps'

const props = defineProps<{ slug: string; part: string }>()
const route = useRoute()
const router = useRouter()
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
// script-for-tts.txt: what the voice reads (written by prep, or by a Story Package import)
async function copyTts() {
  try {
    await navigator.clipboard.writeText(d.value?.tts_script ?? '')
    toast('TTS script copied: paste it into freetts.ai', 'ok')
  } catch {
    toast('Could not copy: select the script on the Voice tab and press Ctrl+C', 'error')
  }
}

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

const failedStage = computed(() => {
  const st = Object.keys(stages.value).find((k) => stages.value[k] === 'failed')
  return st ? { stage: st, error: errors.value[st] } : null
})
const state = computed<PartState>(() => ({
  stages: stages.value as never,
  approvals: { stills: approved('stills'), test_render: approved('test_render'), final: approved('final') },
  files: { voice: has('voice.mp3'), stillsSheet: has('stills-sheet.png'), testRender: has('test-render.mp4') },
  castApproved: !unapprovedCast.value.length,
  busy: busy.value,
  failed: failedStage.value,
  thumbs: !!d.value?.thumbs.length,
  thumbnailPicked: !!p.value?.thumbnail_choice,
  posted: { youtube: !!p.value?.posted.youtube, instagram: !!p.value?.posted.instagram },
}))
const next = computed(() => partNext(state.value))
const steps = computed(() => partSteps(state.value))
// the section the next step happens in, outlined so the eye lands on it
const focus = computed(() => {
  const n = next.value
  if (n.kind === 'approve') return n.approval === 'stills' ? 'review' : 'approvals'
  return ({ voice: 'voice', thumbnail: 'thumbnails', post: 'posting' } as Record<string, string>)[n.kind] ?? null
})
const approvalOf = (key: Approval) => APPROVALS.find((a) => a.key === key)!
const workers = ref(2)
api.settings().then((v) => { workers.value = v.workers_now }).catch(() => {}) // start from Settings; 2 if unreachable

async function run(steps: string[]) {
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

// ---- check story (story.md against the series: no voice or timing needed) ----
const story = ref<StoryCheck | null>(null)
const checking = ref(false)
async function checkStory() {
  checking.value = true
  try {
    const r = await act(() => api.checkStory(props.slug, props.part), 'Story checked')
    if (r) {
      story.value = r
      goTo('story') // the result shows in the Story tab, next to the text its line numbers point at
    }
  } finally {
    checking.value = false
  }
}
watch(() => props.part, () => { story.value = null })
const at = (line: number | null) => (line ? `line ${line}` : 'story')

// ---- story.md (the voice is read from it: a changed story after recording means recording again) ----
const storyText = ref('')
const storySaved = ref('')
const storyDirty = computed(() => storyText.value !== storySaved.value)
watch(() => d.value?.story_md, (md) => {
  if (!storyDirty.value) storyText.value = storySaved.value = md ?? '' // never clobber unsaved edits on a live refresh
}, { immediate: true })
async function saveStory() {
  if (!storyDirty.value) return
  const body = storyText.value
  if (await act(() => api.saveStory(props.slug, props.part, body), 'story.md saved')) {
    storySaved.value = body
    story.value = null // an old check result no longer applies
  }
}
function onStoryKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    e.stopPropagation() // not the page-wide Ctrl+S, which saves upload.md
    saveStory()
  }
}

// ---- voice ----
const uploading = ref(false)
async function uploadVoice(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // same file can be picked again
  if (!file) return
  const replace = has('voice.mp3')
  if (replace && !await confirm({ title: 'Replace voice.mp3?', body: 'The current recording is overwritten. Stages after it will need re-running.', confirm: 'Replace', danger: true })) return
  uploading.value = true
  try {
    if (await act(() => api.uploadVoice(props.slug, props.part, file, replace), 'voice.mp3 uploaded')) {
      refresh()
      await run([`run --stage import_check${replace ? ' --force' : ''}`])
    }
  } finally {
    uploading.value = false
  }
}

// ---- what is on screen: each section shows up once it has something to do or show ----
const anyApproval = computed(() => APPROVALS.some((a) => approved(a.key) || has(a.file)))
const show = computed(() => ({
  video: sources.value.length > 0,
  review: has('stills-sheet.png') || !!d.value?.thumbs.length,
  approvals: anyApproval.value,
  qa: !!qa.value,
  upload: has('final.mp4') || approved('final'),
  posting: approved('final') || !!p.value?.posted.youtube || !!p.value?.posted.instagram,
}))
// ---- tabs: Story, Voice, Review, Publish, Tools. Review and Publish show up once they have something in them ----
type Tab = 'story' | 'voice' | 'review' | 'publish' | 'tools'
const tabs = computed(() => [
  { id: 'story', label: 'Story' },
  { id: 'voice', label: 'Voice' },
  ...(show.value.video || show.value.review || show.value.approvals || show.value.qa ? [{ id: 'review', label: 'Review' }] : []),
  ...(show.value.upload || show.value.posting ? [{ id: 'publish', label: 'Publish' }] : []),
  { id: 'tools', label: 'Tools' },
] as { id: Tab; label: string }[])
// the tab where the current step (lib/partSteps) happens
const STEP_TAB: Record<string, Tab> = { story: 'story', voice: 'voice', plan: 'story', stills: 'review', test: 'review', final: 'review', thumbnail: 'review', post: 'publish' }
const stepTab = computed<Tab>(() => STEP_TAB[steps.value.find((x) => x.status !== 'done')?.key ?? 'post'])
const chosen = ref<Tab | null>(null)
const tab = computed<Tab>(() => {
  const want = chosen.value ?? stepTab.value
  return tabs.value.some((t) => t.id === want) ? want : 'story'
})
// every in-page link (#voice, #posting, ...) opens its tab, then scrolls to that section
const TAB_OF: Record<string, Tab> = { story: 'story', voice: 'voice', video: 'review', review: 'review', approvals: 'review', qa: 'review',
  thumbnails: 'review', upload: 'publish', posting: 'publish', run: 'tools', disk: 'tools', publish: 'publish', tools: 'tools' }
async function goTo(id: string) {
  if (!TAB_OF[id]) return
  chosen.value = TAB_OF[id]
  await nextTick()
  document.getElementById(id)?.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'nearest' })
}
function onAnchor(e: MouseEvent) {
  const a = (e.target as HTMLElement).closest<HTMLAnchorElement>('a[href^="#"]')
  if (!a || !TAB_OF[a.hash.slice(1)]) return
  e.preventDefault()
  goTo(a.hash.slice(1))
}
function onTabKey(e: KeyboardEvent) { // arrow keys move between tabs (WAI-ARIA tabs pattern)
  const k = ({ ArrowRight: 1, ArrowLeft: -1 } as Record<string, number>)[e.key]
  if (!k) return
  e.preventDefault()
  const ids = tabs.value.map((t) => t.id)
  const next = ids[(ids.indexOf(tab.value) + k + ids.length) % ids.length]
  chosen.value = next
  nextTick(() => document.getElementById(`tab-${next}`)?.focus())
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
    const ok = await confirm({ title: 'Approve the final video?', body: 'Approvals are kept for good: only approve after watching final.mp4 to the end. Approving also deletes what only made it (frames, audio stems, preview, test render) to free space: changing the video later means rendering it again. final.mp4, voice, story and thumbnails are kept.', confirm: 'Approve final' })
    if (!ok) return
  }
  if (await act(() => api.approve(props.slug, props.part, a.key), `${a.label} approved`)) refresh()
}

// ---- reject: render a waiting item again (approvals are kept for good, so only before approving) ----
// stills re-plan the shots first, so planner fixes and changed sets / props / cast show up on the new sheet
const REDO: Record<Approval, { steps: string[]; body: string }> = {
  stills: { steps: ['run --stage shots --force', 'run --stage validate --force', 'render-stills'],
    body: 'Plans the shots again from story.md, then renders a new stills sheet. Change the story, cast, sets or props first if something in it was wrong.' },
  test_render: { steps: ['test-render'], body: 'Renders the 5 s test again. Takes a minute or two.' },
  // the story stages first, without --force: they skip themselves unless story.md or voice.mp3 changed
  final: { steps: ['run --stage prep', 'run --stage import_check', 'run --stage timing', 'run --stage shots', 'run --stage validate',
    'render --force', 'run --stage audio --force', 'run --stage finish --force', 'run --stage thumbnails --force'],
    body: 'Picks up a changed story.md and voice.mp3 (save the new story and upload the new voice first), deletes every frame and renders the whole video again, then the sound, final.mp4 and thumbnails. This is the slow one.' },
}
const canReject = (a: (typeof APPROVALS)[number]) => !approved(a.key) && has(a.file)
async function reject(a: (typeof APPROVALS)[number]) {
  const ok = await confirm({ title: `Reject the ${a.label.toLowerCase()} and render again?`, body: REDO[a.key].body,
    confirm: 'Render again', danger: a.key === 'final' })
  if (ok) await run(REDO[a.key].steps)
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
const qa = computed(() => d.value?.qa as { ok: boolean; checks: Record<string, Check>; warnings?: string[] } | null | undefined)
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

async function deletePart() {
  const posted = p.value?.posted.youtube || p.value?.posted.instagram
  const ok = await confirm({
    title: `Delete part ${p.value?.number}: ${p.value?.title}?`,
    body: `Deletes the whole part folder for good: story.md, voice.mp3, every video, the frames and the thumbnails `
      + `(${bytes(d.value!.part_bytes)}). Other parts keep their numbers.${posted ? ' It is marked posted: the posted links are lost too.' : ''}`,
    confirm: 'Delete part', danger: true,
  })
  if (ok && (await act(() => api.deletePart(props.slug, props.part), `Part ${p.value?.number} deleted`))) router.push(`/series/${props.slug}`)
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
watch(data, (v, old) => {
  if (v && !old && route.hash) goTo(route.hash.slice(1))
})
watch(() => props.part, () => { chosen.value = null })
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />

  <div v-else-if="loading" class="space-y-6" aria-busy="true" aria-label="Loading part">
    <div class="skeleton h-44" />
    <div class="grid grid-cols-[360px_1fr] gap-6"><div class="skeleton h-[720px]" /><div class="skeleton h-[720px]" /></div>
  </div>

  <div v-else-if="d && p && series" class="space-y-6" @click="onAnchor">
    <RouterLink :to="`/series/${slug}`" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> {{ series.title }}</RouterLink>

    <!-- header (the part card expands into this) -->
    <div ref="header" class="raised grid origin-top-left gap-6 p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)] lg:items-start">
     <div class="min-w-0">
      <div class="flex flex-wrap items-center gap-3">
        <span class="num text-3xl text-muted">{{ String(p.number).padStart(2, '0') }}</span>
        <h2 class="font-display text-3xl font-semibold">{{ p.title }}</h2>
        <span v-if="busy" class="chip chip-blue"><span class="pulse size-1.5 rounded-full bg-current" />{{ busy }}</span>
      </div>
      <PartStepper class="mt-5" :steps="steps" />
      <details class="mt-3 text-sm">
        <summary class="cursor-pointer text-xs font-semibold text-muted">Pipeline stages (re-run one)</summary>
        <StageChips class="mt-2" :stages="stages" :errors="errors" menu :disabled="busy" @rerun="rerun" />
      </details>
     </div>

      <!-- the one thing to do next (lib/partNext) -->
      <div class="inset flex items-start gap-3 p-4" role="status" aria-live="polite">
        <CircleCheck v-if="next.kind === 'done'" :size="20" class="mt-0.5 shrink-0 text-green-ink" aria-hidden="true" />
        <CircleX v-else-if="failedStage && next.kind === 'run'" :size="20" class="mt-0.5 shrink-0 text-red-ink" aria-hidden="true" />
        <span v-else class="mt-1.5 size-2.5 shrink-0 rounded-full" :class="next.kind === 'wait' ? 'pulse bg-blue' : 'bg-amber'" aria-hidden="true" />
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium text-ink">{{ next.text }}</p>
          <details v-if="next.kind === 'run'" class="mt-2 text-xs text-muted">
            <summary class="cursor-pointer">Show the {{ next.steps.length }} step{{ next.steps.length === 1 ? '' : 's' }}</summary>
            <ol class="mt-1 list-decimal space-y-0.5 pl-5"><li v-for="s in next.steps" :key="s"><code>{{ s }}</code></li></ol>
          </details>
          <div class="mt-3 flex flex-wrap gap-2 whitespace-nowrap">
            <button v-if="next.kind === 'run'" class="btn btn-primary" @click="run(next.steps)">
              <Play :size="16" aria-hidden="true" /> {{ failedStage ? 'Run again' : 'Run' }}
            </button>
            <template v-else-if="next.kind === 'voice'">
              <label class="btn btn-primary" :class="{ 'pointer-events-none opacity-50': uploading }">
                <Upload :size="16" aria-hidden="true" /> {{ uploading ? 'Uploading…' : 'Upload mp3' }}
                <input type="file" accept=".mp3,audio/mpeg" class="sr-only" :disabled="uploading" @change="uploadVoice" />
              </label>
              <button v-if="d?.tts_script" type="button" class="btn btn-secondary" @click="copyTts">
                <Copy :size="14" aria-hidden="true" /> Copy TTS script
              </button>
            </template>
            <RouterLink v-else-if="next.kind === 'cast'" :to="`/series/${slug}`" class="btn btn-primary">
              Go to the cast <ArrowRight :size="16" aria-hidden="true" />
            </RouterLink>
            <template v-else-if="next.kind === 'approve'">
              <button v-if="next.approval === 'stills'" class="btn btn-secondary" @click="zoom(src('stills-sheet.png'), 'Stills sheet')">
                View stills sheet
              </button>
              <a v-else href="#video" class="btn btn-secondary">Watch <ArrowRight :size="16" aria-hidden="true" /></a>
              <button class="btn btn-primary" @click="approve(approvalOf(next.approval))">
                <Check :size="16" aria-hidden="true" /> Approve {{ approvalOf(next.approval).label.toLowerCase() }}
              </button>
              <button class="btn btn-secondary text-red-ink" @click="reject(approvalOf(next.approval))">
                <RefreshCw :size="16" aria-hidden="true" /> Reject and render again
              </button>
            </template>
            <a v-else-if="next.kind === 'thumbnail'" href="#thumbnails" class="btn btn-primary">Pick a thumbnail <ArrowRight :size="16" aria-hidden="true" /></a>
            <a v-else-if="next.kind === 'post'" href="#posting" class="btn btn-primary">Add the links <ArrowRight :size="16" aria-hidden="true" /></a>
          </div>
        </div>
      </div>
    </div>

    <!-- tabs: one area of work at a time; it opens where the current step happens -->
    <div class="sticky top-0 z-10 -mx-1 flex gap-1 overflow-x-auto border-b border-rule bg-page/90 px-1 backdrop-blur-md"
      role="tablist" aria-label="Part sections">
      <button v-for="t in tabs" :id="`tab-${t.id}`" :key="t.id" type="button" role="tab" :aria-selected="tab === t.id" :aria-controls="`panel-${t.id}`"
        :tabindex="tab === t.id ? 0 : -1" class="relative shrink-0 px-4 py-3 text-sm font-semibold"
        :class="tab === t.id ? 'text-ink' : 'text-muted hover:text-ink'" @click="goTo(t.id)" @keydown="onTabKey">
        <motion.span v-if="tab === t.id" layout-id="part-tab-pill" class="absolute inset-x-2 -bottom-px h-[3px] rounded-t-sm bg-ink"
          :transition="SPRING" aria-hidden="true" />
        <span class="relative">{{ t.label }}</span>
        <span v-if="t.id === stepTab && tab !== t.id" class="relative ml-1.5 inline-block size-2 rounded-full bg-amber align-middle" aria-label="current step" />
      </button>
    </div>

    <div v-show="tab === 'story'" id="panel-story" role="tabpanel" aria-labelledby="tab-story">
      <section id="story" class="raised p-6">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="font-display text-lg font-semibold">Story</h3>
          <span class="text-xs text-muted">story.md</span>
          <span v-if="storyDirty" class="size-2.5 rounded-full bg-amber" title="Unsaved changes" aria-label="Unsaved changes" />
        </div>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <button class="btn btn-secondary" :disabled="checking || storyDirty" :title="storyDirty ? 'Save first: the check reads the saved file' : undefined" @click="checkStory">
            <CircleCheck :size="16" aria-hidden="true" /> Check
          </button>
          <button class="btn btn-primary" :disabled="!storyDirty || !!busy" :title="busy ?? undefined" @click="saveStory"><Save :size="16" aria-hidden="true" /> Save</button>
        </div>
        <p class="mt-1 text-xs text-muted">
          Ctrl+S saves. Later stages pick up the change on their next run.<template v-if="has('voice.mp3')"> The voice is already recorded: if the narration changes, record and upload it again.</template>
        </p>
        <div v-if="story" class="inset mt-4 p-4 text-sm" role="status" aria-label="Story check">
          <div class="flex flex-wrap items-center gap-2">
            <span class="chip" :class="story.ok ? 'chip-green' : 'chip-red'">
              {{ story.ok ? 'story ready' : `${story.problems.length} problem${story.problems.length === 1 ? '' : 's'}` }}
            </span>
            <span class="text-muted">{{ story.words }} words · about {{ story.seconds }} s of video</span>
            <button class="btn btn-secondary ml-auto" @click="story = null">Close</button>
          </div>
          <ul v-if="story.problems.length || story.warnings.length" class="mt-3 space-y-1.5">
            <li v-for="(x, i) in story.problems" :key="`p${i}`" class="flex items-start gap-2">
              <CircleX :size="16" class="mt-0.5 shrink-0 text-red-ink" aria-label="problem" />
              <span><span class="num font-semibold">{{ at(x.line) }}</span> {{ x.message }}</span>
            </li>
            <li v-for="(x, i) in story.warnings" :key="`w${i}`" class="flex items-start gap-2">
              <CircleAlert :size="16" class="mt-0.5 shrink-0 text-amber-ink" aria-label="warning" />
              <span><span class="num font-semibold">{{ at(x.line) }}</span> {{ x.message }}</span>
            </li>
          </ul>
        </div>
        <label class="sr-only" for="story-md">story.md</label>
        <textarea id="story-md" v-model="storyText" class="paper inset mt-4 block max-h-[32rem] min-h-48 w-full resize-y overflow-auto p-5 font-mono text-sm leading-7 outline-none focus:border-blue"
          spellcheck="true" @keydown="onStoryKey" />
      </section>
    </div>

    <div v-show="tab === 'voice'" id="panel-voice" role="tabpanel" aria-labelledby="tab-voice">
      <section id="voice" :class="{ 'next-target': focus === 'voice' }" class="raised p-6">
        <div class="flex items-center gap-2">
          <h3 class="font-display text-lg font-semibold">Voice</h3>
          <span class="text-xs text-muted">{{ has('voice.mp3') ? `voice.mp3 · ${d?.voice_duration?.toFixed(1) ?? '?'} s` : 'no voice.mp3 yet' }}</span>
          <label class="btn btn-secondary ml-auto" :class="{ 'pointer-events-none opacity-50': !!busy || uploading }" :title="busy ?? undefined">
            <Upload :size="16" aria-hidden="true" /> {{ uploading ? 'Uploading…' : has('voice.mp3') ? 'Replace' : 'Upload mp3' }}
            <input type="file" accept=".mp3,audio/mpeg" class="sr-only" :disabled="!!busy || uploading" @change="uploadVoice" />
          </label>
        </div>
        <audio v-if="has('voice.mp3')" :key="d?.voice_duration ?? 0" :src="src('voice.mp3')" controls class="mt-4 w-full" />
        <p class="mt-1 text-xs text-muted">An import check runs after each upload.</p>
        <div class="mt-4">
          <div class="flex items-center gap-2">
            <h4 class="text-sm font-semibold">TTS script</h4>
            <span class="text-xs text-muted">script-for-tts.txt: paste it into freetts.ai, word for word</span>
            <button v-if="d?.tts_script" type="button" class="btn btn-secondary ml-auto" @click="copyTts"><Copy :size="14" aria-hidden="true" /> Copy</button>
          </div>
          <pre v-if="d?.tts_script" class="inset mt-2 max-h-80 overflow-auto rounded-md p-4 font-mono text-xs leading-5 whitespace-pre-wrap text-ink">{{ d.tts_script }}</pre>
          <p v-else class="mt-1 text-xs text-muted">None yet: running the story step (prep) writes it from story.md.</p>
        </div>
      </section>
    </div>

    <div v-show="tab === 'review'" id="panel-review" role="tabpanel" aria-labelledby="tab-review" class="space-y-6">
      <div class="grid items-start gap-6" :class="show.video && (show.approvals || show.qa) && 'xl:grid-cols-[360px_1fr]'">
        <!-- player -->
        <section v-if="show.video" id="video" class="raised p-5" aria-label="Video">
          <VideoPlayer :sources="sources" />
        </section>
        <div v-if="show.approvals || show.qa" class="space-y-6">
          <!-- approvals -->
          <section v-if="show.approvals" id="approvals" :class="{ 'next-target': focus === 'approvals' }" class="raised p-6">
            <h3 class="font-display text-lg font-semibold">Approvals</h3>
            <div class="mt-4 flex flex-wrap gap-x-8 gap-y-4">
              <div v-for="a in APPROVALS" :key="a.key">
                <Switch :on="approved(a.key)" :label="a.label" :reason="approved(a.key) ? null : approvalReason(a)" @request="approve(a)" />
                <p class="mt-1 text-xs text-muted">
                  {{ approved(a.key) ? shortDate(p.approvals[a.key].approved_at) : approvalReason(a) ?? 'ready to approve' }}
                </p>
                <button v-if="canReject(a)" class="btn btn-secondary mt-2 text-red-ink" :disabled="!!busy" :title="busy ?? undefined" @click="reject(a)">
                  <RefreshCw :size="14" aria-hidden="true" /> Reject and render again
                </button>
              </div>
            </div>
          </section>

          <!-- QA -->
          <section v-if="show.qa" id="qa" class="raised p-6">
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
            <ul v-if="qa?.warnings?.length" class="mt-4 space-y-1.5 text-sm">
              <li v-for="(w, i) in qa.warnings" :key="i" class="flex items-start gap-2">
                <CircleAlert :size="16" class="mt-0.5 shrink-0 text-amber-ink" aria-label="warning" />
                <span>{{ w }}</span>
              </li>
            </ul>
          </section>
        </div>
      </div>

      <!-- light table: sheets + thumbnail polaroids -->
      <section v-if="show.review" id="review" :class="{ 'next-target': focus === 'review' }" class="raised p-6">
        <h3 class="font-display text-lg font-semibold">Light table</h3>
        <p class="text-sm text-muted">Click a sheet to zoom. Click a polaroid to pick the thumbnail.</p>
        <div class="lighttable inset mt-4 grid gap-8 p-8 lg:grid-cols-[1fr_auto]">
          <div class="flex flex-wrap items-start gap-6">
            <figure v-for="sh in [{ f: 'stills-sheet.png', t: 'Stills sheet', url: has('stills-sheet.png') ? src('stills-sheet.png') : null }]"
              :key="sh.f" class="w-60">
              <button v-if="sh.url" class="block w-full cursor-zoom-in rounded-md bg-white p-2 shadow-[var(--shadow-sheet)] transition-transform hover:-translate-y-1"
                :aria-label="`Zoom ${sh.t}`" @click="zoom(sh.url!, sh.t)">
                <img :src="sh.url" :alt="sh.t" loading="lazy" class="w-full rounded-sm" />
              </button>
              <div v-else class="grid h-40 place-items-center rounded-md border-2 border-dashed border-rule-strong text-sm text-muted">not rendered yet</div>
              <figcaption class="mt-2 text-center text-sm font-semibold">{{ sh.t }}</figcaption>
            </figure>
          </div>
          <div id="thumbnails" class="rounded-md" :class="{ 'next-target': focus === 'thumbnails' }">
            <p class="mb-8 text-center text-sm font-semibold">Thumbnail</p>
            <div v-if="d.thumbs.length" class="flex gap-5">
              <motion.button v-for="(t, i) in d.thumbs" :key="t" class="relative w-32 bg-white p-2 pb-8 shadow-[var(--shadow-sheet)]"
                :animate="picked === `thumbs/${t}` ? { rotate: 0, y: -12, scale: 1.06 } : { rotate: TILT[i % 3], y: 0, scale: 1 }"
                :while-hover="picked === `thumbs/${t}` ? undefined : { y: -4 }" :transition="SPRING"
                :aria-pressed="picked === `thumbs/${t}`" :aria-label="`Pick thumbnail ${i + 1}`" :disabled="!!busy"
                @click="pick(Number(t.match(/\d+/)![0]))">
                <img :src="src(`thumbs/${t}`)" :alt="`Thumbnail candidate ${i + 1}`" loading="lazy" class="aspect-[9/16] w-full object-cover" />
                <span class="absolute bottom-2 left-0 w-full text-center font-display text-sm text-muted">#{{ i + 1 }}</span>
                <span v-if="picked === `thumbs/${t}`" class="absolute -top-2 left-1/2 grid size-6 -translate-x-1/2 place-items-center rounded-full bg-ink text-[var(--on-ink)] shadow-[var(--shadow-sheet)]">
                  <Check :size="14" :stroke-width="3" aria-hidden="true" />
                </span>
              </motion.button>
            </div>
            <p v-else class="text-sm text-muted">No candidates yet (thumbnails stage).</p>
          </div>
        </div>
      </section>
    </div>

    <div v-show="tab === 'publish'" id="panel-publish" role="tabpanel" aria-labelledby="tab-publish"
      class="grid items-start gap-6" :class="show.upload && show.posting && 'xl:grid-cols-2'">
      <!-- upload.md -->
      <section v-if="show.upload" id="upload" class="raised p-6">
        <div class="flex items-center gap-2">
          <h3 class="font-display text-lg font-semibold">upload.md</h3>
          <span v-if="dirty" class="size-2.5 rounded-full bg-amber" title="Unsaved changes" aria-label="Unsaved changes" />
          <button class="btn btn-primary ml-auto" :disabled="!dirty" @click="save"><Save :size="16" aria-hidden="true" /> Save</button>
        </div>
        <p class="mt-1 text-xs text-muted">Ctrl+S saves. Written atomically; nothing else in the part is touched.</p>
        <label class="sr-only" for="upload-md">upload.md</label>
        <textarea id="upload-md" v-model="text" class="paper inset mt-4 block min-h-64 w-full resize-y p-5 font-mono text-sm leading-7 outline-none focus:border-blue"
          spellcheck="true" @keydown="onKey" />
      </section>

      <!-- posting -->
      <section v-if="show.posting" id="posting" :class="{ 'next-target': focus === 'posting' }" class="grid gap-6 sm:grid-cols-2">
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
                class="inset mt-1 block w-full rounded-md px-4 py-2 text-sm text-ink outline-none focus:border-blue" />
            </label>
            <label class="block text-xs font-semibold text-muted">Date
              <input v-model="form[pl.key].date" type="date" class="inset mt-1 block w-full rounded-md px-4 py-2 text-sm text-ink outline-none focus:border-blue" />
            </label>
            <div class="flex gap-2">
              <button class="btn btn-primary" :disabled="!form[pl.key].url.trim()">Mark posted</button>
              <button v-if="form[pl.key].replacing" type="button" class="btn btn-secondary" @click="form[pl.key].replacing = false">Cancel</button>
            </div>
          </form>
        </div>
      </section>
    </div>

    <div v-show="tab === 'tools'" id="panel-tools" role="tabpanel" aria-labelledby="tab-tools" class="grid items-start gap-6 xl:grid-cols-2">
      <!-- run controls -->
      <section id="run" class="raised p-6">
        <h3 class="font-display text-lg font-semibold">Manual controls</h3>
        <p class="text-xs text-muted">The Next step card runs these for you; use them to redo one step by hand.</p>
        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <div v-for="c in [{ cmd: 'render-stills', label: 'Render stills' }, { cmd: 'test-render', label: 'Test render (5 s)' }, { cmd: 'cast-sheet', label: 'Render whole cast' }]"
            :key="c.cmd" class="flex flex-col">
            <button class="btn btn-secondary justify-center" :disabled="!!why(c.cmd)" :title="why(c.cmd) ?? undefined"
              @click="run([c.cmd])">{{ c.label }}</button>
            <span v-if="why(c.cmd)" class="mt-1 text-xs text-muted">{{ why(c.cmd) }}</span>
          </div>
          <div class="flex flex-col">
            <div class="flex gap-2">
              <button class="btn btn-secondary flex-1 justify-center" :disabled="!!why('render')" :title="why('render') ?? undefined"
                @click="run([`render --workers ${workers}`])">Full render</button>
              <div class="inset flex items-center px-1" role="group" aria-label="Render workers">
                <button class="grid size-7 place-items-center rounded-sm hover:bg-panel disabled:opacity-40" aria-label="Fewer workers"
                  :disabled="workers <= 1" @click="workers--"><Minus :size="14" /></button>
                <span class="num w-5 text-center" :aria-label="`${workers} workers`">{{ workers }}</span>
                <button class="grid size-7 place-items-center rounded-sm hover:bg-panel disabled:opacity-40" aria-label="More workers"
                  :disabled="workers >= 16" @click="workers++"><Plus :size="14" /></button>
              </div>
            </div>
            <span class="mt-1 text-xs text-muted">{{ why('render') ?? `${workers} parallel browser${workers > 1 ? 's' : ''}` }}</span>
          </div>
        </div>
      </section>

      <!-- disk + danger zone -->
      <section id="disk" class="raised p-6">
        <h3 class="font-display text-lg font-semibold">Disk</h3>
        <dl class="mt-3 grid grid-cols-2 gap-4">
          <div class="inset px-4 py-3"><dt class="text-xs font-semibold text-muted">Frames</dt><dd class="num text-xl">{{ bytes(d.frames_bytes) }}</dd></div>
          <div class="inset px-4 py-3"><dt class="text-xs font-semibold text-muted">Whole part</dt><dd class="num text-xl">{{ bytes(d.part_bytes) }}</dd></div>
        </dl>
        <div class="mt-5 rounded-md border tint-red p-4">
          <p class="flex items-center gap-2 text-sm font-semibold text-red-ink"><HardDrive :size="16" aria-hidden="true" /> Danger zone</p>
          <p class="mt-1 text-xs text-muted">Delete frames/ once final.mp4 is finished. Frees {{ bytes(d.frames_bytes) }}.</p>
          <button class="btn btn-secondary mt-3 text-red-ink" :disabled="!!cleanReason" :title="cleanReason ?? undefined" @click="clean">
            <Trash2 :size="16" aria-hidden="true" /> Clean frames
          </button>
          <p v-if="cleanReason" class="mt-1 text-xs text-muted">{{ cleanReason }}</p>
          <div class="mt-4 border-t border-red/30 pt-4">
            <p class="text-xs text-muted">Delete this part: story, voice, videos, everything. Cannot be undone.</p>
            <button class="btn btn-secondary mt-3 text-red-ink" :disabled="!!busy" :title="busy ?? undefined" @click="deletePart">
              <Trash2 :size="16" aria-hidden="true" /> Delete part
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* a lightbox: the glow is the sheet colour brightening toward the centre */
.lighttable { background: radial-gradient(ellipse at 50% 40%, color-mix(in oklab, var(--color-panel) 70%, #fff8e6) 0%, var(--color-well) 75%); }
.paper {
  field-sizing: content; /* autosize, native */
  background-color: var(--color-panel);
  background-image: repeating-linear-gradient(transparent 0 27px, var(--color-rule) 27px 28px);
  background-position: 0 19px;
}
button:disabled { cursor: not-allowed; opacity: 0.55; }
.next-target { outline: 2px solid var(--color-amber); outline-offset: 4px; scroll-margin-top: 1.5rem; }
:where(section[id], div[id]) { scroll-margin-top: 4.5rem; }
</style>
