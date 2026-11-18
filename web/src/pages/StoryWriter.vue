<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, type PackageResult } from '../api/client'
import AiBridge from '../components/AiBridge.vue'
import { toast } from '../composables/feedback'
import { storyGuide } from '../lib/storyGuide'

// Story Writer: brainstorm a series with any chat AI (it gets the story guide), paste back its one Story Package
// (docs/story-package.md), see what it creates, import it all in one go. The API checks and writes; nothing is
// written until Import, and Import is all or nothing.
const router = useRouter()
const prompt = ref('')
const reply = ref('')
const result = ref<PackageResult | null>(null)
const checkError = ref('')
const checking = ref(false)
const importing = ref(false)

async function makeGuide() {
  prompt.value = await storyGuide()
}

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
const where = (i: { section: string; line?: number | null }) => `${i.section}${i.line ? `, line ${i.line}` : ''}`

async function runImport() {
  importing.value = true
  try {
    const r = await api.importPackage(reply.value)
    toast(`Imported “${r.series!.title}”: ${r.parts.length} part${r.parts.length === 1 ? '' : 's'}`, 'ok')
    reply.value = ''
    router.push(`/series/${r.series!.slug}`)
  } catch (e) {
    checkError.value = e instanceof Error ? e.message : String(e)
  } finally {
    importing.value = false
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
      <ol class="list-decimal space-y-1 pl-5 text-sm text-muted">
        <li>Make the guide and paste it into your AI, then tell it your idea.</li>
        <li>Brainstorm until you agree on the story.</li>
        <li>It answers with one Story Package in one text block: paste that below.</li>
      </ol>
      <button type="button" class="btn btn-primary" @click="makeGuide">Make story guide</button>
      <AiBridge v-model="reply" :prompt="prompt" :error="checkError" load-label="Check again"
        reply-label="Paste the Story Package here"
        reply-hint="The text block, or the AI's whole message: only what is between <<<SCRIBBLE_PACKAGE v1>>> and <<<END>>> is read."
        @load="check" />
    </section>

    <section v-if="result" class="raised space-y-4 p-6" aria-labelledby="sw-preview" :aria-busy="checking">
      <div class="flex flex-wrap items-baseline gap-2">
        <h3 id="sw-preview" class="font-display text-xl font-semibold">Preview</h3>
        <span class="chip" :class="result.ok ? 'text-green-ink' : 'text-red-ink'">{{ result.ok ? 'ready to import' : `${result.errors.length} error${result.errors.length === 1 ? '' : 's'}` }}</span>
        <span v-if="checking" class="text-xs text-muted">checking…</span>
      </div>

      <div v-if="result.errors.length">
        <h4 class="font-semibold text-red-ink">Errors: nothing can be imported until these are fixed</h4>
        <ul class="mt-1 list-disc space-y-0.5 pl-5 text-sm" role="alert">
          <li v-for="(e, n) in result.errors" :key="n"><strong>{{ where(e) }}:</strong> {{ e.message }}</li>
        </ul>
      </div>

      <template v-if="result.series">
        <p class="text-sm">Series <strong>{{ result.series.title }}</strong> <code class="text-xs text-muted">{{ result.series.slug }}</code>
          <span v-if="result.series.was" class="text-xs text-muted"> (“{{ result.series.was }}” is taken)</span></p>
        <div>
          <h4 class="font-semibold">New in the library and cast ({{ newItems.length }})</h4>
          <ul class="divide-y divide-rule">
            <li v-for="i in newItems" :key="i.key" class="flex flex-wrap items-center gap-2 py-1.5 text-sm">
              <span class="chip">{{ i.label }}</span><strong>{{ i.name }}</strong><code class="text-xs text-muted">{{ i.id }}</code>
              <span v-if="i.was" class="text-xs text-red-ink">“{{ i.was }}” is taken: saved as {{ i.id }}</span>
            </li>
          </ul>
        </div>
        <div>
          <h4 class="font-semibold">Parts ({{ result.parts.length }})</h4>
          <ul class="divide-y divide-rule">
            <li v-for="p in result.parts" :key="p.number" class="flex flex-wrap items-center gap-2 py-1.5 text-sm">
              <span class="chip">Part {{ p.number }}</span><strong>{{ p.title }}</strong><span class="text-xs text-muted">{{ p.words }} words</span>
            </li>
          </ul>
        </div>
      </template>

      <div v-if="result.warnings.length">
        <h4 class="font-semibold">Warnings</h4>
        <ul class="mt-1 list-disc space-y-0.5 pl-5 text-sm text-muted">
          <li v-for="(w, n) in result.warnings" :key="n"><strong>{{ where(w) }}:</strong> {{ w.message }}</li>
        </ul>
      </div>

      <p class="text-xs text-muted">Import writes it all or nothing and never overwrites. Each part starts at the story step: approve the cast,
        then record the voice from its TTS script and upload the mp3, as before.</p>
      <button type="button" class="btn btn-primary" :disabled="!result.ok || checking || importing" :aria-busy="importing" @click="runImport">
        {{ importing ? 'Importing…' : 'Import' }}</button>
    </section>
  </div>
</template>
