<script setup lang="ts">
// A TTS voice (the Kokoro server): which one, how fast, and a sample of it. null: `none` (the narrator's / the default).
import { Pause, Play } from 'lucide-vue-next'
import { computed, onBeforeUnmount, ref } from 'vue'
import { api, type TtsVoice, type TtsVoices, type VoiceFx } from '../api/client'
import { toast } from '../composables/feedback'

const p = defineProps<{ modelValue: TtsVoice | null; voices: TtsVoices | null; none: string; sample?: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [v: TtsVoice | null] }>()

const id = computed({
  get: () => p.modelValue?.id ?? '',
  set: (v: string) => emit('update:modelValue', v ? { id: v, speed: p.modelValue?.speed ?? 1 } : null),
})
const speed = computed({
  get: () => p.modelValue?.speed ?? 1,
  set: (s: number) => p.modelValue && emit('update:modelValue', { ...p.modelValue, speed: Math.min(2, Math.max(0.5, s || 1)) }),
})
// The "In This Town" effect: processed after the TTS, tuned here (defaults = the preset)
const FX: VoiceFx = { preset: 'in_this_town', enabled: true, pitch: -1.5, speed: 0.94, warmth: 0.5, intensity: 1 }
const fx = computed<VoiceFx | null>(() => p.modelValue?.fx ?? null)
function setFx(v: VoiceFx | null) {
  if (p.modelValue) emit('update:modelValue', { ...p.modelValue, fx: v })
}
const sliders = [
  { key: 'pitch', label: 'Pitch (semitones)', min: -6, max: 6, step: 0.1 },
  { key: 'speed', label: 'Speed', min: 0.7, max: 1.3, step: 0.01 },
  { key: 'warmth', label: 'Warmth', min: 0, max: 1, step: 0.05 },
  { key: 'intensity', label: 'Intensity', min: 0, max: 1, step: 0.05 },
] as const
// English first (US, then UK), then the rest by language; offline: the saved ids, ungrouped
const LANG: Record<string, string> = { 'en-us': 'English (US)', 'en-gb': 'English (UK)' }
const groups = computed(() => {
  const by = new Map<string, TtsVoices['voices']>()
  for (const v of p.voices?.voices ?? []) {
    const g = v.lang ? (LANG[v.lang] ?? `Other (${v.lang})`) : 'Voices'
    by.set(g, [...(by.get(g) ?? []), v])
  }
  return [...by.entries()].sort(([a], [b]) => Number(!a.startsWith('English')) - Number(!b.startsWith('English')) || a.localeCompare(b))
})
const known = computed(() => !id.value || (p.voices?.voices ?? []).some((v) => v.id === id.value))

const playing = ref<HTMLAudioElement | null>(null)
const fetching = ref(false)
function stop() {
  playing.value?.pause()
  if (playing.value) URL.revokeObjectURL(playing.value.src)
  playing.value = null
}
async function preview() {
  if (playing.value) return stop()
  fetching.value = true
  try {
    const a = new Audio(await api.ttsPreview(id.value || p.voices?.default || '', speed.value, p.sample ?? '', fx.value))
    a.onended = stop
    playing.value = a
    await a.play()
  } catch (e) {
    toast(`Preview failed: ${(e as Error).message}`, 'error')
    stop()
  } finally {
    fetching.value = false
  }
}
onBeforeUnmount(stop)
const field = 'inset mt-1 block h-10 w-full rounded-md px-3 text-sm text-ink outline-none focus:border-blue'
</script>

<template>
  <div class="grid gap-2 sm:grid-cols-[1fr_6rem_auto] sm:items-end">
    <label class="block text-xs font-semibold text-muted">Voice
      <select v-model="id" :disabled="disabled" :class="field">
        <option value="">{{ none }}</option>
        <optgroup v-for="[g, vs] in groups" :key="g" :label="g">
          <option v-for="v in vs" :key="v.id" :value="v.id">{{ v.label }}</option>
        </optgroup>
        <option v-if="!known" :value="id">{{ id }} (not on the server)</option>
      </select>
    </label>
    <label class="block text-xs font-semibold text-muted">Speed
      <input v-model.number="speed" type="number" min="0.5" max="2" step="0.05" :disabled="disabled || !modelValue" :class="field" />
    </label>
    <button type="button" class="btn btn-secondary h-10" :disabled="fetching" :aria-pressed="!!playing" @click="preview">
      <component :is="playing ? Pause : Play" :size="14" aria-hidden="true" /> {{ fetching ? 'Making…' : playing ? 'Stop' : 'Preview' }}
    </button>
    <div class="space-y-2 sm:col-span-3">
      <label class="flex items-center gap-2 text-xs font-semibold text-muted">
        <input type="checkbox" :checked="!!fx" :disabled="disabled || !modelValue" @change="setFx(($event.target as HTMLInputElement).checked ? { ...FX } : null)" />
        "In This Town" effect <span class="font-normal">calm, low, warm narration; applied after the TTS</span>
      </label>
      <div v-if="fx" class="grid gap-2 sm:grid-cols-4">
        <label class="flex items-center gap-2 text-xs font-semibold text-muted sm:col-span-4">
          <input type="checkbox" :checked="fx.enabled" :disabled="disabled" @change="setFx({ ...fx, enabled: ($event.target as HTMLInputElement).checked })" /> On
          <button type="button" class="btn btn-secondary ml-auto" :disabled="disabled" @click="setFx({ ...FX })">Reset</button>
        </label>
        <label v-for="s in sliders" :key="s.key" class="block text-xs font-semibold text-muted">
          {{ s.label }} <span class="num font-normal">{{ fx[s.key] }}</span>
          <input type="range" class="mt-1 block w-full" :min="s.min" :max="s.max" :step="s.step" :value="fx[s.key]" :disabled="disabled || !fx.enabled"
            @input="setFx({ ...fx, [s.key]: Number(($event.target as HTMLInputElement).value) })" />
        </label>
      </div>
    </div>
    <p v-if="voices && !voices.online" class="text-xs text-muted sm:col-span-3">The TTS server is not answering: these are the voices it had last time.</p>
  </div>
</template>
