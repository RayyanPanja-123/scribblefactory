<script setup lang="ts">
// A card World Item drawn by the render engine's own drawers (engine/page/items.js previewItem), playing its
// animations in the chosen state. A bad item (unknown drawing) shows its error under the picture.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
// @ts-expect-error plain JS module from the engine, no types
import { previewItem } from '../../../engine/page/items.js'
import type { WorldObject } from '../lib/objects'

const p = withDefaults(defineProps<{ item: WorldObject; state?: string | null; label: string; w?: number; h?: number }>(), { state: null, w: 380, h: 240 })
const cv = ref<HTMLCanvasElement>()
const error = ref('')
let raf = 0, t0 = 0
const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function frame(now: number) {
  if (!cv.value) return
  try {
    previewItem(cv.value, p.item, { t: still ? 0 : (now - t0) / 1000, state: p.state })
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
    return
  }
  if (!still) raf = requestAnimationFrame(frame)
}
function start() { cancelAnimationFrame(raf); t0 = performance.now(); raf = requestAnimationFrame(frame) }
onMounted(start)
onBeforeUnmount(() => cancelAnimationFrame(raf))
watch(() => [p.item, p.state], start, { deep: true })
</script>

<template>
  <div class="relative overflow-hidden rounded-md bg-well">
    <canvas ref="cv" :width="w" :height="h" role="img" :aria-label="label" class="block h-full w-full object-contain" />
    <p v-if="error" class="absolute inset-x-0 bottom-0 bg-panel/95 p-2 text-xs text-red-ink" role="alert">{{ error }}</p>
  </div>
</template>
