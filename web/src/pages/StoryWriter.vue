<script setup lang="ts">
import { CircleAlert, CircleX, Copy, List, Sparkles } from 'lucide-vue-next'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, type PackageResult } from '../api/client'
import AiBridge from '../components/AiBridge.vue'
import IssueFix from '../components/IssueFix.vue'
import { toast } from '../composables/feedback'
import { packageText as reply } from '../composables/storyDraft'
import { copyLibraryList, fixPrompt, storyGuide } from '../lib/storyGuide'

// Story Writer: brainstorm a series with any chat AI (it gets the story guide), paste back its one Story Package
// (docs/story-package.md), see what it creates, fix what the check finds right where it is reported (or have the AI
// fix it), then review it (StoryReview page: every item and part approved on its own) and import it all in one go.
// The API checks and writes; nothing is written until Import, which is all or nothing.
const router = useRouter()
const prompt = ref('')
const result = ref<PackageResult | null>(null)
const checkError = ref('')
const checking = ref(false)

onMounted(async () => {
  prompt.value = await storyGuide()
  check() // a package kept from earlier (back from the review page)
})

let seq = 0
async function check() {
  const text = reply.value
  if (!text.trim()) {
    result.value = null
    checkError.value = ''
    return
  }
  const mine = ++seq
  checking.value = true
  try {
    const r = await api.validatePackage(text)
    if (mine === seq) [result.value, checkError.value] = [r, '']
  } catch (e) {
    if (mine === seq) [result.value, checkError.value] = [null, e instanceof Error ? e.message : String(e)]
  } finally {
    if (mine === seq) checking.value = false
  }
}
let timer: ReturnType<typeof setTimeout> | undefined
watch(reply, () => {
  clearTimeout(timer)
  timer = setTimeout(check, 400) // paste -> validate, without a request per keystroke while editing
})

const KINDS = [['props', 'Prop'], ['sets', 'Set'], ['creatures', 'Creature'], ['actions', 'Action'], ['cast', 'Cast']] as const
const newItems = computed(() => {
  const r = result.value
  if (!r) return []
  return KINDS.flatMap(([k, label]) => r[k].map((x) => {
    const was = k === 'cast' ? undefined : Object.entries(r.renames[k] ?? {}).find(([, v]) => v === x.id)?.[0]
    return { key: `${k}:${x.id}`, label, id: x.id, name: x.name, was }
  }))
})

type Issue = PackageResult['errors'][number]
const STAGING = 'staging: '
/** issues by section, in package order (the order the checker reports them) */
const bySection = (xs: Issue[]) => {
  const m = new Map<string, Issue[]>()
  for (const x of xs) m.set(x.section, [...(m.get(x.section) ?? []), x])
  return [...m]
}
const groups = computed(() => {
  const r = result.value
  if (!r) return []
  const staging = r.warnings.filter((w) => w.message.startsWith(STAGING)).map((w) => ({ ...w, message: w.message.slice(STAGING.length) }))
  return [
    { key: 'errors', title: 'Errors: nothing can be imported until these are fixed', tone: 'error', items: bySection(r.errors) },
    { key: 'warnings', title: 'Warnings', tone: 'warn', items: bySection(r.warnings.filter((w) => !w.message.startsWith(STAGING))) },
    { key: 'staging', title: 'Staging: make it more watchable', tone: 'warn', items: bySection(staging) },
  ].filter((g) => g.items.length)
})
const issueCount = computed(() => (result.value ? result.value.errors.length + result.value.warnings.length : 0))
const partIssues = (n: number) => result.value ? [...result.value.errors, ...result.value.warnings].filter((x) => x.section.startsWith(`PART ${n} `)).length : 0
const wordsOk = (w: number) => w >= 110 && w <= 175 // the package checker's WORDS range
const anchor = (section: string) => `sw-${section.toLowerCase().replace(/\s+/g, '-')}`
function jumpToPart(n: number) {
  document.querySelector(`[id^="${anchor(`PART ${n}`)}-"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

/** a line-less issue: select its section in the paste box (PART 2 SCRIPT -> the <<<SCRIPT>>> after <<<PART 2>>>) */
function showSection(section: string) {
  const lines = reply.value.split('\n')
  const at = (marker: string, from = 0) => lines.findIndex((l, i) => i >= from && l.trim() === `<<<${marker}>>>`)
  const m = /^PART (\d+) (SCRIPT|VOICE)$/.exec(section)
  const start = m ? at(m[2], at(`PART ${m[1]}`)) : at(section)
  if (start < 0) return
  const end = lines.findIndex((l, i) => i > start && l.trim().startsWith('<<<'))
  const offset = (i: number) => lines.slice(0, i).reduce((n, l) => n + l.length + 1, 0)
  const box = document.getElementById('ai-reply') as HTMLTextAreaElement | null
  if (!box) return
  box.focus()
  box.setSelectionRange(offset(start + 1), offset(end < 0 ? lines.length : end))
  box.scrollTop = start * 20 // leading-5: 20px a line
  box.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

async function copyFix() {
  const r = result.value
  if (!r) return
  try {
    await navigator.clipboard.writeText(fixPrompt([...r.errors, ...r.warnings]))
    toast('Fix request copied: paste it into the same chat, then paste the new package here', 'ok')
  } catch {
    toast('Could not copy to the clipboard', 'error')
  }
}

</script>

<template>
  <div class="max-w-4xl space-y-6">
    <div>
      <h2 class="font-display text-2xl font-semibold">Story Writer</h2>
      <p class="text-sm text-muted">Brainstorm a series with any chat AI, then paste its Story Package: every new prop, set, creature and
        action, the cast, and each part's script and voice text, imported in one go.</p>
    </div>

    <section class="raised space-y-4 p-6" aria-labelledby="sw-ai">
      <h3 id="sw-ai" class="font-display text-xl font-semibold">Write it with your AI</h3>
      <p class="text-sm text-muted">Copy the story guide into your AI and tell it your idea. Brainstorm until you agree and say “approved”.
        It then asks for your library list: copy it with the button below and paste it in. It answers with one Story Package: paste
        that below. It is checked as you paste.</p>
      <button type="button" class="btn btn-secondary" title="Every set, prop, creature, action, wardrobe item, sound and cast member you have, by id" @click="copyLibraryList">
        <List :size="16" aria-hidden="true" /> Copy library list</button>
      <AiBridge v-model="reply" :prompt="prompt" :error="checkError" load-label="Check again"
        reply-label="Paste the Story Package here"
        reply-hint="The text block, or the AI's whole message: only what is between <<<SCRIBBLE_PACKAGE v1>>> and <<<END>>> is read."
        @load="check" />
    </section>

    <section v-if="result" class="raised p-6" aria-labelledby="sw-preview" :aria-busy="checking">
      <!-- status bar: stays in view while working through the issues -->
      <div class="sticky top-0 z-10 -mx-6 -mt-6 mb-4 flex flex-wrap items-center gap-2 rounded-t-[inherit] border-b border-rule bg-panel px-6 py-3">
        <h3 id="sw-preview" class="font-display text-xl font-semibold">Preview</h3>
        <span class="chip" :class="result.ok ? 'chip-green' : 'chip-red'">{{ result.ok ? 'ready to review' : `${result.errors.length} error${result.errors.length === 1 ? '' : 's'}` }}</span>
        <span v-if="result.warnings.length" class="chip chip-amber">{{ result.warnings.length }} warning{{ result.warnings.length === 1 ? '' : 's' }}</span>
        <span v-if="checking" class="text-xs text-muted" role="status">checking…</span>
        <div class="ml-auto flex flex-wrap gap-2">
          <button v-if="issueCount" type="button" class="btn btn-secondary" title="A prompt with every issue, for the chat the package came from" @click="copyFix">
            <Sparkles :size="16" aria-hidden="true" /> Copy fix request</button>
          <button type="button" class="btn btn-primary" :disabled="!result.ok || checking" title="See every new item and part, approve each, then import"
            @click="router.push('/story-writer/review')">Review</button>
        </div>
      </div>

      <div class="space-y-6">
        <template v-if="result.series">
          <p class="text-sm">Series <strong>{{ result.series.title }}</strong> <code class="text-xs text-muted">{{ result.series.slug }}</code>
            <span v-if="result.series.was" class="text-xs text-muted"> (“{{ result.series.was }}” is taken)</span></p>

          <div>
            <h4 class="font-semibold">Parts ({{ result.parts.length }})</h4>
            <ul class="divide-y divide-rule">
              <li v-for="p in result.parts" :key="p.number">
                <button type="button" class="flex w-full flex-wrap items-center gap-2 py-1.5 text-left text-sm hover:bg-well disabled:hover:bg-transparent"
                  :disabled="!partIssues(p.number)" @click="jumpToPart(p.number)">
                  <span class="chip">Part {{ p.number }}</span><strong>{{ p.title }}</strong>
                  <span class="chip" :class="wordsOk(p.words) ? 'chip-green' : 'chip-amber'" :title="'Aim for 110 to 175 words'">{{ p.words }} words</span>
                  <span v-if="partIssues(p.number)" class="ml-auto text-xs text-muted underline underline-offset-2">{{ partIssues(p.number) }} issue{{ partIssues(p.number) === 1 ? '' : 's' }}</span>
                </button>
              </li>
            </ul>
          </div>

          <component :is="newItems.length > 8 ? 'details' : 'div'">
            <component :is="newItems.length > 8 ? 'summary' : 'h4'" class="font-semibold" :class="newItems.length > 8 && 'cursor-pointer'">
              New in the library and cast ({{ newItems.length }})</component>
            <ul class="divide-y divide-rule">
              <li v-for="i in newItems" :key="i.key" class="flex flex-wrap items-center gap-2 py-1.5 text-sm">
                <span class="chip">{{ i.label }}</span><strong>{{ i.name }}</strong><code class="text-xs text-muted">{{ i.id }}</code>
                <span v-if="i.was" class="text-xs text-red-ink">“{{ i.was }}” is taken: saved as {{ i.id }}</span>
              </li>
            </ul>
          </component>
        </template>

        <div v-for="g in groups" :key="g.key" :role="g.tone === 'error' ? 'alert' : undefined">
          <h4 class="font-semibold" :class="g.tone === 'error' && 'text-red-ink'">{{ g.title }}</h4>
          <div v-for="[section, xs] in g.items" :id="`${anchor(section)}-${g.key}`" :key="section" class="mt-3 scroll-mt-20">
            <h5 class="text-xs font-semibold uppercase tracking-wide text-muted">{{ section }}</h5>
            <ul class="mt-1 space-y-2">
              <li v-for="(x, n) in xs" :key="`${x.line}-${n}-${x.message}`" class="flex items-start gap-2 text-sm">
                <CircleX v-if="g.tone === 'error'" :size="16" class="mt-0.5 shrink-0 text-red-ink" aria-label="error" />
                <CircleAlert v-else :size="16" class="mt-0.5 shrink-0 text-amber-ink" aria-label="warning" />
                <div class="min-w-0 flex-1">
                  <p><span v-if="x.line" class="num font-semibold">line {{ x.line }}</span> {{ x.message }}</p>
                  <IssueFix v-if="x.line" v-model="reply" :line="x.line" />
                  <button v-else type="button" class="text-xs font-semibold text-blue-ink underline underline-offset-2" @click="showSection(section)">Show in package</button>
                </div>
              </li>
            </ul>
          </div>
        </div>

        <p class="text-xs text-muted">Review shows every new item and part to approve one by one; Import then writes it all or nothing and never overwrites. Each part starts at the story step: approve the cast,
          then record the voice from its TTS script and upload the mp3, as before.
          <template v-if="issueCount"> <Copy :size="12" class="inline" aria-hidden="true" /> Copy fix request hands every issue back to your AI.</template></p>
      </div>
    </section>
  </div>
</template>
