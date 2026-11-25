<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import { act } from '../composables/feedback'
import { parseVoiceReply, spokenWords, voicePrompt, voiceStory, type VoiceMode, type VoicePart } from '../lib/voicePrompt'
import AiBridge from './AiBridge.vue'

// Story step 1: title -> voice scripts. One small prompt, one paste, then one part per script (narration only;
// directives come later per part).
const props = defineProps<{ open: boolean; slug: string; title: string; cast: { id: string; name: string }[] }>()
const emit = defineEmits<{ close: []; done: [] }>()

const parts = ref(3)
const notes = ref('')
const reply = ref('')
const error = ref('')
const parsed = ref<VoicePart[]>([])
const saving = ref(false)
// asked first, never assumed: one narrator for everything, or the cast speaking their own lines in their own voices
const mode = ref<VoiceMode | null>(null)
const MODES: { id: VoiceMode; label: string; hint: string }[] = [
  { id: 'narration', label: 'Single narration', hint: 'One narrator reads everything. Best for history explainers.' },
  { id: 'cast', label: 'Cast voice acting', hint: 'A narrator plus the characters’ own lines, each in their own voice (TTS). Best for comedy and banter.' },
]
const prompt = computed(() => mode.value ? voicePrompt({ title: props.title, parts: parts.value, mode: mode.value, notes: notes.value, cast: props.cast }) : '')
const words = spokenWords

function close() {
  reply.value = ''; error.value = ''; parsed.value = []
  emit('close')
}
function load() {
  const r = parseVoiceReply(reply.value, parts.value, mode.value === 'cast' ? props.cast.map((c) => c.id) : null)
  error.value = r.error ?? ''
  parsed.value = r.parts ?? []
}
async function create() {
  saving.value = true
  const ids = props.cast.map((c) => c.id)
  for (const [i, p] of parsed.value.entries()) {
    const ok = await act(() => api.createPart(props.slug, { title: p.title, story: voiceStory(p, ids) }), `Part “${p.title}” created`)
    if (!ok) { parsed.value = parsed.value.slice(i); saving.value = false; return } // keep the rest to retry
  }
  saving.value = false
  emit('done')
  close()
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 grid place-items-center bg-[var(--scrim)] p-4" role="presentation" @keydown.esc="close">
      <section class="raised max-h-[calc(100vh-2rem)] w-full max-w-2xl overflow-y-auto p-6 shadow-[var(--shadow-pop)]" role="dialog" aria-modal="true" aria-labelledby="ai-voice-title">
        <div class="flex items-start gap-3">
          <div>
            <h2 id="ai-voice-title" class="font-display text-2xl font-semibold">Voice scripts with AI</h2>
            <p class="mt-1 text-sm text-muted">Step 1: the AI writes only the spoken lines for “{{ title }}”, real or made up. Staging comes later, part by part.</p>
          </div>
          <button type="button" class="round-btn ml-auto" aria-label="Close" @click="close"><X :size="18" /></button>
        </div>

        <div v-if="!parsed.length" class="mt-5 space-y-5">
          <div class="grid gap-4 sm:grid-cols-[8rem_1fr]">
            <label class="block text-xs font-semibold text-muted">Parts
              <input v-model.number="parts" type="number" min="1" max="20" class="inset mt-1 block h-10 w-full rounded-md px-4 text-sm text-ink outline-none focus:border-blue" />
            </label>
            <label class="block text-xs font-semibold text-muted">Tone, angle, things to avoid (optional)
              <input v-model="notes" placeholder="Funny, focus on the emperor's madness" class="inset mt-1 block h-10 w-full rounded-md px-4 text-sm text-ink outline-none focus:border-blue" />
            </label>
          </div>
          <fieldset>
            <legend class="text-xs font-semibold text-muted">Who speaks? Pick one first: the scripts are written for it.</legend>
            <div class="mt-1 grid gap-2 sm:grid-cols-2">
              <button v-for="m in MODES" :key="m.id" type="button" class="inset rounded-md p-3 text-left" :aria-pressed="mode === m.id"
                :class="mode === m.id ? 'border-ink ring-2 ring-ink' : 'hover:border-rule-strong'"
                :disabled="m.id === 'cast' && !cast.length" :title="m.id === 'cast' && !cast.length ? 'Add cast members first: only they can speak' : undefined"
                @click="mode = m.id">
                <span class="block text-sm font-semibold text-ink">{{ m.label }}</span>
                <span class="mt-0.5 block text-xs text-muted">{{ m.id === 'cast' && !cast.length ? 'Add cast members first: only they can speak.' : m.hint }}</span>
              </button>
            </div>
          </fieldset>
          <AiBridge v-if="mode" v-model="reply" :prompt="prompt" :error="error" load-label="Read scripts" reply-label="Paste the AI's scripts here"
            reply-hint="The <<<PART 1>>> … <<<END>>> block, or its whole message." @load="load" />
        </div>

        <div v-else class="mt-5 space-y-4">
          <ol class="space-y-3">
            <li v-for="(p, i) in parsed" :key="i" class="inset p-4">
              <p class="font-semibold">{{ p.title }} <span class="num text-xs text-muted">{{ words(p) }} words</span></p>
              <p class="mt-1 line-clamp-3 text-sm text-muted">{{ p.lines.join(' ') }}</p>
            </li>
          </ol>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn btn-secondary" :disabled="saving" @click="parsed = []">Back</button>
            <button type="button" class="btn btn-primary" :disabled="saving" @click="create">
              {{ saving ? 'Creating…' : `Create ${parsed.length} part${parsed.length === 1 ? '' : 's'}` }}</button>
          </div>
        </div>
      </section>
    </div>
  </Teleport>
</template>
