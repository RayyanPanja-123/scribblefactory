<script setup lang="ts">
import { Pause, Play } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

// Reel-style player over /api/media (Range requests make seeking work): the video fills its box, tap or Space
// plays/pauses (big button in the centre while paused), arrows seek 5 s, a thin bar at the bottom scrubs.
// Sources are tabs over the top. Fills its parent: the parent sets the size.
const p = defineProps<{ sources: { key: string; label: string; src: string }[]; top?: string }>()
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
  <div class="group relative size-full overflow-hidden bg-black text-white outline-none" tabindex="0"
    aria-label="Video player: space plays, arrow keys seek 5 seconds" @keydown="onKey">
    <video :id="`video-panel-${current}`" ref="video" :key="src" :src="src" class="size-full object-cover" preload="metadata" playsinline
      @click="toggle" @play="playing = true" @pause="playing = false" @ended="playing = false"
      @timeupdate="time = video!.currentTime" @loadedmetadata="duration = video!.duration; time = 0; mediaError = false" @error="mediaError = true" />

    <!-- sources, over the top like a reels header -->
    <div v-if="p.sources.length > 1" class="absolute inset-x-0 top-0 flex justify-center gap-4 bg-gradient-to-b from-black/55 to-transparent pb-6"
      :class="top ?? 'pt-3'" role="tablist" aria-label="Source">
      <button v-for="s in p.sources" :key="s.key" type="button" role="tab" :aria-selected="current === s.key"
        :aria-controls="`video-panel-${s.key}`" :tabindex="current === s.key ? 0 : -1"
        class="border-b-2 pb-0.5 text-[13px] font-semibold drop-shadow" :class="current === s.key ? 'border-white text-white' : 'border-transparent text-white/60 hover:text-white'"
        @click="choose(s.key)">{{ s.label }}</button>
    </div>

    <!-- play / pause in the centre: always while paused, on hover while playing -->
    <button type="button" class="absolute top-1/2 left-1/2 grid size-16 -translate-1/2 place-items-center rounded-full bg-black/5 transition-opacity"
      :class="playing ? 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100' : 'opacity-100'" :aria-label="playing ? 'Pause' : 'Play'" @click="toggle">
      <Pause v-if="playing" :size="28" fill="currentColor" aria-hidden="true" />
      <Play v-else :size="28" fill="currentColor" class="translate-x-0.5" aria-hidden="true" />
    </button>

    <p v-if="mediaError" class="absolute inset-x-4 top-1/3 rounded-md bg-black/70 p-3 text-center text-sm" role="alert">
      This video could not be loaded. Try another source or refresh the part.</p>

    <!-- time + thin scrub bar at the bottom -->
    <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/55 to-transparent px-4 pt-8 pb-5">
      <span class="num block text-right text-[11px] text-white/80">{{ fmt(time) }} / {{ fmt(duration) }}</span>
      <input class="scrub mt-1 block w-full" type="range" min="0" :max="duration || 0" step="0.1" :value="time"
        aria-label="Seek" :aria-valuetext="`${fmt(time)} of ${fmt(duration)}`"
        :style="{ '--pct': `${duration ? (time / duration) * 100 : 0}%` }"
        @input="seek(+($event.target as HTMLInputElement).value)" />
    </div>
  </div>
</template>

<style scoped>
.scrub {
  appearance: none;
  height: 3px;
  border-radius: 999px;
  background: linear-gradient(90deg, #fff var(--pct), rgb(255 255 255 / 0.3) var(--pct));
  cursor: pointer;
}
.scrub:hover, .scrub:focus-visible { height: 5px; }
.scrub::-webkit-slider-thumb {
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #fff;
  opacity: 0;
}
.scrub:hover::-webkit-slider-thumb, .scrub:focus-visible::-webkit-slider-thumb { opacity: 1; }
.scrub::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border: 0;
  border-radius: 999px;
  background: #fff;
}
</style>
