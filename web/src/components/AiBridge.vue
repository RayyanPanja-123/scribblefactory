<script setup lang="ts">
import { ClipboardPaste, Copy } from 'lucide-vue-next'
import { ref } from 'vue'
import { toast } from '../composables/feedback'

// The copy/paste bridge to any chat AI (web or CLI, works offline): the prompt goes out read-only, the reply comes
// back in. The parent turns the reply into something (emit "load") and passes back any error.
defineProps<{ prompt: string; error?: string; loadLabel?: string }>()
const reply = defineModel<string>({ default: '' })
const emit = defineEmits<{ load: [] }>()
const promptBox = ref<HTMLTextAreaElement>()
const replyBox = ref<HTMLTextAreaElement>()

async function copyPrompt() {
  try {
    await navigator.clipboard.writeText(promptBox.value?.value ?? '')
    toast('Prompt copied: paste it into your AI', 'ok')
  } catch {
    promptBox.value?.select() // no clipboard access (plain http): select it for Ctrl+C
    toast('Could not copy: the prompt is selected, press Ctrl+C', 'error')
  }
}
async function pasteReply() {
  try {
    reply.value = await navigator.clipboard.readText()
  } catch {
    replyBox.value?.focus() // no clipboard read access: paste with Ctrl+V
    toast('Could not read the clipboard: press Ctrl+V in the box', 'error')
  }
}
</script>

<template>
  <ol class="divide-y divide-rule">
    <!-- the prompt, read-only: goes OUT to the AI -->
    <li class="flex gap-3 pb-5" :class="!prompt && 'opacity-50'">
      <span class="step-no" aria-hidden="true">1</span>
      <div class="min-w-0 flex-1 space-y-2">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="font-semibold">Copy the prompt into your AI</h3>
          <button type="button" class="btn btn-secondary ml-auto" :disabled="!prompt" @click="copyPrompt"><Copy :size="16" aria-hidden="true" /> Copy prompt</button>
        </div>
        <p class="text-xs text-muted">ChatGPT, Claude, Gemini, a CLI… any of them. Don't edit this: it's read-only.</p>
        <template v-if="prompt">
          <label class="sr-only" for="ai-prompt">Prompt for AI (read-only)</label>
          <textarea id="ai-prompt" ref="promptBox" :value="prompt" readonly rows="6" spellcheck="false"
            class="block w-full resize-y rounded-md border border-rule bg-well p-4 font-mono text-xs leading-5 text-muted outline-none focus:border-blue" />
        </template>
      </div>
    </li>
    <!-- the AI's reply: comes IN from the AI -->
    <li class="flex gap-3 pt-5">
      <span class="step-no" aria-hidden="true">2</span>
      <div class="min-w-0 flex-1 space-y-2">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="font-semibold"><label for="ai-reply">Paste the AI's JSON reply here</label></h3>
          <button type="button" class="btn btn-secondary ml-auto" @click="pasteReply"><ClipboardPaste :size="16" aria-hidden="true" /> Paste</button>
        </div>
        <p class="text-xs text-muted">The JSON block, or its whole message: the JSON is picked out of it.</p>
        <textarea id="ai-reply" ref="replyBox" v-model="reply" rows="6" spellcheck="false" placeholder="Paste here, e.g.&#10;```json&#10;{ … }&#10;```"
          class="paper block w-full resize-y rounded-md border-2 border-dashed p-4 font-mono text-xs leading-5 text-ink outline-none focus:border-blue focus:border-solid"
          :class="error ? 'border-red-ink' : 'border-blue-ink/60'" :aria-invalid="!!error" />
        <p v-if="error" class="text-sm text-red-ink" role="alert">{{ error }}</p>
        <div class="flex justify-end">
          <button type="button" class="btn btn-primary" :disabled="!reply.trim()" @click="emit('load')">{{ loadLabel ?? 'Load reply' }}</button>
        </div>
      </div>
    </li>
  </ol>
</template>

<style scoped>
/* step number: a small ink tab, like a numbered X-sheet column */
.step-no {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: var(--radius-sm);
  background: var(--color-ink);
  color: var(--on-ink);
  font-size: 0.8125rem;
  font-weight: 700;
}
</style>
