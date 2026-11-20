<script setup lang="ts">
import { BatteryFull, Minus, Signal, Smartphone, Wifi } from 'lucide-vue-next'
import { onBeforeUnmount, ref, watch } from 'vue'
import VideoPlayer from './VideoPlayer.vue'

// The part's videos on a modern phone (thin titanium frame, island cutout, side buttons) floating bottom right,
// left of the utilities button, on every tab. Minimized it is one button; the video unmounts, so nothing keeps
// playing out of sight.
defineProps<{ sources: { key: string; label: string; src: string }[]; wide?: boolean }>() // wide: a 16:9 series, the phone on its side
const KEY = 'floating-player-open'
const read = () => { try { return localStorage.getItem(KEY) !== '0' } catch { return true } }
const open = ref(read())
watch(open, (v) => { try { localStorage.setItem(KEY, v ? '1' : '0') } catch { /* private window: not remembered */ } })
defineExpose({ show: () => { open.value = true } }) // "Watch" and #video links

const clock = () => new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }).replace(/\s?[AP]M$/i, '')
const now = ref(clock())
const tick = setInterval(() => { now.value = clock() }, 20_000)
onBeforeUnmount(() => clearInterval(tick))
</script>

<template>
  <div class="fixed right-24 bottom-5 z-20 sm:right-28 sm:bottom-8">
    <button v-if="!open" type="button" class="btn btn-primary shadow-[var(--shadow-pop)]" aria-label="Show video" @click="open = true">
      <Smartphone :size="16" aria-hidden="true" /> Video
    </button>

    <section v-else id="video" aria-label="Video" class="phone relative rounded-[3.1rem] p-[2px]"
      :class="wide ? 'w-[min(30rem,calc(100vw-9rem))]' : 'w-[min(17rem,calc((100vh-6rem)*9/16))]'">
      <!-- side buttons: action + volume on the left, power and camera control on the right -->
      <template v-if="!wide">
        <span class="key -left-[3px] top-24 h-7" aria-hidden="true" />
        <span class="key -left-[3px] top-36 h-12" aria-hidden="true" />
        <span class="key -left-[3px] top-[12.5rem] h-12" aria-hidden="true" />
        <span class="key -right-[3px] top-32 h-16" aria-hidden="true" />
        <span class="key -right-[3px] top-[15rem] h-9" aria-hidden="true" />
      </template>

      <!-- off the phone's corner, in amber: never lost against the video or the page -->
      <button type="button" class="absolute top-1 -right-12 z-10 grid size-9 place-items-center rounded-full bg-amber text-black shadow-[var(--shadow-pop)] ring-2 ring-white/70 hover:brightness-110"
        aria-label="Minimize video" title="Minimize" @click="open = false">
        <Minus :size="18" stroke-width="3" aria-hidden="true" />
      </button>

      <!-- the screen: the reel edge to edge, status bar and home bar drawn over it -->
      <div class="relative overflow-hidden rounded-[2.95rem] bg-black" :class="wide ? 'aspect-video' : 'aspect-[9/16]'">
        <VideoPlayer :sources="sources" :top="wide ? 'pt-3' : 'pt-11'" />
        <div v-if="!wide" class="pointer-events-none absolute inset-x-0 top-0 flex h-10 items-center justify-between px-7 pt-1 text-[13px] font-semibold text-white drop-shadow" aria-hidden="true">
          <span class="num">{{ now }}</span>
          <span class="absolute top-2 left-1/2 h-[1.4rem] w-[5.5rem] -translate-x-1/2 rounded-full bg-black" />
          <span class="flex items-center gap-1"><Signal :size="13" /><Wifi :size="13" /><BatteryFull :size="16" /></span>
        </div>
        <span v-if="!wide" class="pointer-events-none absolute bottom-1.5 left-1/2 h-1 w-24 -translate-x-1/2 rounded-full bg-white/80" aria-hidden="true" />
      </div>
    </section>
  </div>
</template>

<style scoped>
/* brushed titanium: a cool metal edge with a highlight, deep drop shadow */
.phone {
  background: linear-gradient(145deg, #c9ccd1 0%, #8d9198 22%, #e4e6ea 48%, #7d8188 74%, #b5b8be 100%);
  box-shadow: 0 0 0 1px rgb(0 0 0 / 0.35), 0 24px 48px -12px rgb(0 0 0 / 0.55), inset 0 0 1px rgb(255 255 255 / 0.6);
}
.key {
  position: absolute;
  width: 3px;
  border-radius: 2px;
  background: linear-gradient(90deg, #6f737a, #c4c7cc);
}
</style>
