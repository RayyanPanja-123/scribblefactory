<script setup lang="ts">
// One set, built by the render engine's own code (engine/page/setPreview.js) through its wide camera, so the
// preview is what renders. A builder error (a piece on the stage) shows under the picture.
import { onMounted, ref, watch } from 'vue'
// @ts-expect-error plain JS module from the engine, no types
import { previewSet } from '../../../engine/page/setPreview.js'
import type { WorldObject } from '../lib/objects'
import type { CustomSet } from '../lib/sets'

const p = withDefaults(defineProps<{ id: string; custom: CustomSet[]; objects?: WorldObject[]; label: string; weather?: CustomSet['default_weather']; w?: number; h?: number }>(), { objects: () => [], w: 270, h: 480 })
const cv = ref<HTMLCanvasElement>()
const error = ref('')

function draw() {
  if (!cv.value) return
  try {
    previewSet(cv.value, p.id, p.custom, p.weather ?? null, p.objects)
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}
onMounted(draw)
watch(() => [p.id, p.custom, p.weather, p.objects], draw, { deep: true })
</script>

<template>
  <div class="relative overflow-hidden rounded-md bg-well">
    <canvas ref="cv" :width="w" :height="h" role="img" :aria-label="label" class="block h-full w-full object-contain" />
    <p v-if="error" class="absolute inset-x-0 bottom-0 bg-panel/95 p-2 text-xs text-red-ink" role="alert">{{ error }}</p>
  </div>
</template>
