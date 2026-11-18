<script setup lang="ts">
import { Pause, Play } from 'lucide-vue-next'
import { motion } from 'motion-v'
import { computed, ref, watch } from 'vue'
import { SPRING } from '../composables/ui'

// Custom player over /api/media (Range requests make seeking work). Space plays, arrows seek 5 s.
const p = defineProps<{ sources: { key: string; label: string; src: string }[] }>()
const current = ref(p.sources.at(-1)?.key)
const src = computed(() => p.sources.find((s) => s.key === current.value)?.src)
watch(() => p.sources.map((s) => s.key).join(), () => {
  if (!p.sources.some((s) => s.key === current.value)) current.value = p.sources.at(-1)?.key
})

const video = ref<HTMLVideoElement>()
const playing = ref(false)
const time = ref(0)
const duration = ref(0)
const mediaError = ref(false)
const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

function toggle() {
  const v = video.value
  if (!v) return
  v.paused ? v.play() : v.pause()
}
function seek(to: number) {
  if (video.value) video.value.currentTime = Math.max(0, Math.min(duration.value || 0, to))
}
function onKey(e: KeyboardEvent) {
  if (e.target instanceof HTMLInputElement && e.key !== ' ') return // the range input handles its own arrows
  if (e.key === ' ') toggle()
  else if (e.key === 'ArrowLeft') seek(time.value - 5)
  else if (e.key === 'ArrowRight') seek(time.value + 5)
  else return
  e.preventDefault()
}
function choose(key: string) {
  current.value = key
  mediaError.value = false
}
</script>

<template>
  <div class="space-y-4 outline-none focus:border-blue" tabindex="0" aria-label="Video player: space plays, arrow keys seek 5 seconds"
    @keydown="onKey">
    <div v-if="p.sources.length > 1" class="inset relative flex p-1" role="tablist" aria-label="Source">
      <button v-for="s in p.sources" :key="s.key" type="button" role="tab" :aria-selected="current === s.key"
        :aria-controls="`video-panel-${s.key}`" :tabindex="current === s.key ? 0 : -1"
        class="relative flex-1 rounded-sm px-3 py-1.5 text-sm font-semibold" @click="choose(s.key)">
        <motion.span v-if="current === s.key" layout-id="player-src" class="absolute inset-0 rounded-sm bg-panel shadow-[var(--shadow-sheet)]"
          :transition="SPRING" />
        <span class="relative">{{ s.label }}</span>
      </button>
    </div>

    <div class="inset overflow-hidden p-2">
      <video :id="`video-panel-${current}`" ref="video" :key="src" :src="src" class="aspect-[9/16] w-full rounded-[10px] bg-ink" preload="metadata"
        playsinline @click="toggle" @play="playing = true" @pause="playing = false" @ended="playing = false"
        @timeupdate="time = video!.currentTime" @loadedmetadata="duration = video!.duration; time = 0; mediaError = false" @error="mediaError = true" />
    </div>

    <p v-if="mediaError" class="text-sm text-red-ink" role="alert">This video could not be loaded. Try another source or refresh the part.</p>

    <div class="flex items-center gap-3">
      <button class="round-btn size-12! shrink-0 text-ink" :aria-label="playing ? 'Pause' : 'Play'" @click="toggle">
        <Pause v-if="playing" :size="20" aria-hidden="true" />
        <Play v-else :size="20" class="translate-x-px" aria-hidden="true" />
      </button>
      <input class="scrub min-w-0 flex-1" type="range" min="0" :max="duration || 0" step="0.1" :value="time"
        aria-label="Seek" :aria-valuetext="`${fmt(time)} of ${fmt(duration)}`"
        :style="{ '--pct': `${duration ? (time / duration) * 100 : 0}%` }"
        @input="seek(+($event.target as HTMLInputElement).value)" />
      <span class="num shrink-0 text-sm text-muted">{{ fmt(time) }} / {{ fmt(duration) }}</span>
    </div>
  </div>
</template>

<style scoped>
.scrub {
  appearance: none;
  height: 12px;
  border-radius: 999px;
  background: linear-gradient(90deg, #8a857c var(--pct), transparent var(--pct)), var(--color-well);
  box-shadow: var(--shadow-inset);
  cursor: pointer;
}
.scrub::-webkit-slider-thumb {
  appearance: none;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: var(--color-panel);
  box-shadow: var(--shadow-raised);
}
.scrub::-moz-range-thumb {
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: 999px;
  background: var(--color-panel);
  box-shadow: var(--shadow-raised);
}
</style>
