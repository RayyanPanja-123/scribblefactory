<script setup lang="ts">
// Suggested @sfx for a part (rule-based, never applied silently): accept writes "@sfx <id>" into story.md above the
// line, reject hides it for good. Shown at the stills stage, before the final render.
import { Check, Play, Volume2, X } from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { api, sfxAudio } from '../api/client'
import { act } from '../composables/feedback'
import type { SfxSuggestion, SfxSuggestions } from '../lib/sfx'

const props = defineProps<{ slug: string; part: string; storyMd?: string | null; busy?: string | null }>()
const emit = defineEmits<{ changed: [] }>()
const data = ref<SfxSuggestions | null>(null)
const load = () => api.sfxSuggestions(props.slug, props.part).then((r) => { data.value = r }, () => { data.value = null })
watch(() => [props.slug, props.part, props.storyMd], load, { immediate: true }) // story.md edited: suggest again

async function decide(s: SfxSuggestion, accept: boolean) {
  const r = await act(() => api.decideSfx(props.slug, props.part, s, accept), accept ? `@sfx ${s.id} added to story.md` : 'Suggestion dismissed')
  if (r) {
    data.value = r
    if (accept) emit('changed')
  }
}
const play = (id: string) => new Audio(sfxAudio(id)).play().catch(() => {})
</script>

<template>
  <section v-if="data && (data.suggestions.length || data.written)" id="sfx" class="raised p-6" aria-labelledby="sfx-title">
    <div class="flex flex-wrap items-baseline gap-2">
      <h3 id="sfx-title" class="font-display text-lg font-semibold">Sound effects</h3>
      <span class="text-xs text-muted">{{ data.written }} of {{ data.max }} in story.md · {{ data.timed ? 'timed from the voice' : 'times estimated' }}</span>
    </div>
    <p class="mt-1 text-sm text-muted">Suggestions only: accepting writes the <code>@sfx</code> line into story.md (the final picks it up).</p>
    <ul v-if="data.suggestions.length" class="mt-4 space-y-2">
      <li v-for="s in data.suggestions" :key="`${s.line}-${s.id}`" class="inset flex flex-wrap items-center gap-3 rounded-md p-3 text-sm">
        <button type="button" class="round-btn size-8!" :aria-label="`Preview ${s.id}`" @click="play(s.id)"><Play :size="14" aria-hidden="true" /></button>
        <span class="min-w-0 flex-1">
          <code class="font-semibold">@sfx {{ s.id }}</code> <span class="text-muted">· {{ s.reason }} · {{ s.at.toFixed(1) }} s</span>
          <span class="block truncate text-xs text-muted">line {{ s.line }}: {{ s.text }}</span>
        </span>
        <button type="button" class="btn btn-primary" :disabled="!!busy" :title="busy ?? undefined" @click="decide(s, true)"><Check :size="14" aria-hidden="true" /> Accept</button>
        <button type="button" class="btn btn-secondary" :disabled="!!busy" @click="decide(s, false)"><X :size="14" aria-hidden="true" /> Reject</button>
      </li>
    </ul>
    <p v-else class="mt-3 flex items-center gap-2 text-sm text-muted"><Volume2 :size="16" aria-hidden="true" /> No more suggestions.</p>
  </section>
</template>
