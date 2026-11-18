<script setup lang="ts">
// A stickman holding one prop, drawn by the render engine's own code (engine/page/stickman.js), so the preview is
// exactly what renders. The upper body only: the canvas is cropped to where hands and props are.
import { onMounted, ref, watch } from 'vue'
// @ts-expect-error plain JS module from the engine, no types
import { drawStickman, setCustomProps } from '../../../engine/page/stickman.js'
import type { CustomProp, Hand } from '../lib/props'

const p = defineProps<{ kind: string; custom: CustomProp[]; hand?: Hand; color?: string; label: string }>()
const cv = ref<HTMLCanvasElement>()
const error = ref('')
const TOP = 160, H = 760 // crop of the 512 x 1024 figure canvas: head top to just below the hands

function draw() {
  const out = cv.value
  if (!out) return
  const fig = document.createElement('canvas')
  fig.width = 512
  fig.height = 1024
  try {
    setCustomProps(p.custom)
    drawStickman(fig, {
      seed: 'preview:prop', boil: 0, color: p.color ?? '#3a7bd5', eyes: 'dots', expression: 'happy', action: 'idle',
      phase: 0, lid: 0, mouth: 0, breath: 0, facing: 'camera', t: 0, props: [{ kind: p.kind, hand: p.hand ?? 'right' }],
    })
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
  const g = out.getContext('2d')!
  g.clearRect(0, 0, out.width, out.height)
  g.drawImage(fig, 0, TOP, 512, H, 0, 0, out.width, out.height)
}
onMounted(draw)
watch(() => [p.kind, p.custom, p.hand, p.color], draw, { deep: true })
</script>

<template>
  <div class="drawing relative grid place-items-center overflow-hidden rounded-md">
    <canvas ref="cv" width="256" height="380" role="img" :aria-label="label" class="h-full w-auto max-w-full" />
    <p v-if="error" class="absolute inset-x-2 bottom-2 text-xs text-red-ink" role="alert">{{ error }}</p>
  </div>
</template>
