<script setup lang="ts">
import { ClipboardPaste, Copy, Sparkles, X } from 'lucide-vue-next'
import { nextTick, ref } from 'vue'
import { toast } from '../composables/feedback'

type Parsed = { data?: unknown; error?: string }
const props = defineProps<{
  open: boolean
  title: string
  descriptionHint: string
  promptBuilder: (description: string, choice?: string) => string
  parser: (text: string, choice?: string) => Parsed
  save: (data: unknown) => Promise<unknown>
  choiceLabel?: string
  choiceOptions?: { value: string; label: string }[]
}>()
const emit = defineEmits<{ close: []; done: [] }>()
const description = ref('')
const choice = defineModel<string>('choice', { default: '' })
const prompt = ref('')
const direct = ref(false)
const reply = ref('')
const error = ref('')
const saving = ref(false)
const replyBox = ref<HTMLTextAreaElement>()

function reset() {
  description.value = ''
  prompt.value = ''
  direct.value = false
  reply.value = ''
  error.value = ''
  saving.value = false
}
function close() { reset(); emit('close') }
function next() {
  if (!description.value.trim()) { error.value = 'Describe what you want to create first.'; return }
  prompt.value = props.promptBuilder(description.value.trim(), choice.value)
  error.value = ''
}
async function copyPrompt() {
  try { await navigator.clipboard.writeText(prompt.value); toast('Prompt copied: paste it into your AI', 'ok') }
  catch { error.value = 'Could not copy the prompt. Select it and press Ctrl+C.' }
}
async function pasteReply() {
  try { reply.value = await navigator.clipboard.readText() }
  catch { await nextTick(); replyBox.value?.focus(); toast('Could not read the clipboard. Press Ctrl+V here.', 'error') }
}
async function done() {
  const parsed = props.parser(reply.value, choice.value)
  if (!parsed.data) { error.value = parsed.error ?? 'The AI response could not be read as valid JSON.'; return }
  saving.value = true
  error.value = ''
  try { await props.save(parsed.data); toast('Library item imported', 'ok'); emit('done'); close() }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { saving.value = false }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 grid place-items-center bg-[var(--scrim)] p-4" role="presentation" @keydown.esc="close">
      <section class="raised max-h-[calc(100vh-2rem)] w-full max-w-2xl overflow-y-auto p-6 shadow-[var(--shadow-pop)]" role="dialog" aria-modal="true" :aria-labelledby="'ai-generate-title'">
        <div class="flex items-start gap-3">
          <div><h2 id="ai-generate-title" class="font-display text-2xl font-semibold">{{ title }}</h2><p class="mt-1 text-sm text-muted">Describe it, copy the prompt into any AI, then paste the JSON reply back here.</p></div>
          <button type="button" class="round-btn ml-auto" aria-label="Close" @click="close"><X :size="18" /></button>
        </div>
        <div class="mt-5 space-y-5">
          <template v-if="!prompt && !direct">
            <label class="block text-sm font-semibold">Description
              <textarea v-model="description" rows="6" :placeholder="descriptionHint" class="mt-1 block w-full rounded-md border border-rule bg-well p-3 text-sm outline-none focus:border-blue" autofocus />
            </label>
            <label v-if="choiceOptions?.length" class="block text-sm font-semibold">{{ choiceLabel }}
              <select v-model="choice" class="mt-1 block w-full rounded-md border border-rule bg-well p-3 text-sm"><option v-for="o in choiceOptions" :key="o.value" :value="o.value">{{ o.label }}</option></select>
            </label>
            <div class="flex flex-wrap justify-end gap-2"><button type="button" class="btn btn-secondary" @click="direct = true"><ClipboardPaste :size="16" aria-hidden="true" /> Paste JSON directly</button><button type="button" class="btn btn-primary" @click="next"><Sparkles :size="16" aria-hidden="true" /> Next</button></div>
          </template>
          <template v-else>
            <div v-if="prompt" class="flex flex-wrap items-center gap-2"><span class="chip chip-green">1. Prompt ready</span><button type="button" class="btn btn-secondary ml-auto" @click="prompt = ''; error = ''">Edit description</button></div>
            <div v-if="prompt" class="flex items-center gap-3 rounded-md border border-rule bg-well p-4 text-sm text-muted">
              <Copy :size="18" class="shrink-0" aria-hidden="true" />
              <span>Prompt available to copy. Paste it into ChatGPT, Claude, Gemini, or another AI.</span>
              <button type="button" class="btn btn-secondary ml-auto shrink-0" @click="copyPrompt"><Copy :size="16" aria-hidden="true" /> Copy prompt</button>
            </div>
            <div class="border-t border-rule pt-5">
              <div class="flex flex-wrap items-center gap-2"><h3 class="font-semibold">2. Paste the JSON reply</h3><button type="button" class="btn btn-secondary ml-auto" @click="pasteReply"><ClipboardPaste :size="16" aria-hidden="true" /> Paste</button></div>
              <textarea ref="replyBox" v-model="reply" rows="9" placeholder="Paste the AI's JSON here" class="mt-2 block w-full rounded-md border-2 border-dashed border-blue-ink/60 bg-well p-3 font-mono text-xs leading-5 text-ink outline-none focus:border-blue" />
            </div>
            <div class="flex justify-end"><button type="button" class="btn btn-primary" :disabled="!reply.trim() || saving" @click="done">{{ saving ? 'Importing…' : 'Done — import item' }}</button></div>
          </template>
          <p v-if="error" class="text-sm text-red-ink" role="alert">{{ error }}</p>
        </div>
      </section>
    </div>
  </Teleport>
</template>
