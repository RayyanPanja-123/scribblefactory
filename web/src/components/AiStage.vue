<script setup lang="ts">
import { CircleAlert, X } from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { api } from '../api/client'
import { parseStageReply, stagePrompt } from '../lib/stagePrompt'
import { libraryRecords } from '../lib/storyGuide'
import AiBridge from './AiBridge.vue'

// Story step "stage": this part's narration -> a staged story.md, put into the story box unsaved (the writer checks
// it, then saves).
// The cast is read fresh on every open: the page's copy of the series goes stale when the cast changes elsewhere.
const props = defineProps<{ open: boolean; slug: string; title: string; story: string }>()
const emit = defineEmits<{ close: []; apply: [md: string] }>()

const prompt = ref('')
const reply = ref('')
const error = ref('')
const result = ref<ReturnType<typeof parseStageReply> | null>(null)

watch(() => props.open, async (o) => {
  if (!o) return
  prompt.value = ''
  const [inventory, { series }] = await Promise.all([libraryRecords(true), api.seriesDetail(props.slug)])
  prompt.value = stagePrompt({ series: series.title, title: props.title, story: props.story, cast: series.cast, inventory })
}, { immediate: true })

function close() {
  reply.value = ''; error.value = ''; result.value = null
  emit('close')
}
function load() {
  const r = parseStageReply(reply.value, props.story)
  error.value = r.error ?? ''
  result.value = r.md ? r : null
}
function apply() {
  emit('apply', result.value!.md!)
  close()
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 grid place-items-center bg-[var(--scrim)] p-4" role="presentation" @keydown.esc="close">
      <section class="raised max-h-[calc(100vh-2rem)] w-full max-w-2xl overflow-y-auto p-6 shadow-[var(--shadow-pop)]" role="dialog" aria-modal="true" aria-labelledby="ai-stage-title">
        <div class="flex items-start gap-3">
          <div>
            <h2 id="ai-stage-title" class="font-display text-2xl font-semibold">Stage with AI</h2>
            <p class="mt-1 text-sm text-muted">The AI adds directives to this part's narration, using only your cast and library.</p>
          </div>
          <button type="button" class="round-btn ml-auto" aria-label="Close" @click="close"><X :size="18" /></button>
        </div>

        <div v-if="!result" class="mt-5">
          <AiBridge v-model="reply" :prompt="prompt" :error="error" load-label="Read script" reply-label="Paste the AI's script here"
            reply-hint="The ```md block, or its whole message." @load="load" />
        </div>

        <div v-else class="mt-5 space-y-4">
          <p class="text-sm">Script ready: {{ result.md!.split('\n').filter((l) => l.trim().startsWith('@')).length }} directives.</p>
          <p v-if="result.changed" class="flex items-start gap-2 text-sm text-amber-ink">
            <CircleAlert :size="16" class="mt-0.5 shrink-0" aria-hidden="true" /> The AI changed narration words. Check them: a recorded voice must match.</p>
          <div v-if="result.missing.length" class="inset p-4 text-sm">
            <p class="font-semibold">Missing from the library (make these, then Check again)</p>
            <ul class="mt-2 list-disc space-y-1 pl-5 text-muted"><li v-for="m in result.missing" :key="m">{{ m }}</li></ul>
          </div>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn btn-secondary" @click="result = null">Back</button>
            <button type="button" class="btn btn-primary" @click="apply">Put in story box</button>
          </div>
        </div>
      </section>
    </div>
  </Teleport>
</template>
