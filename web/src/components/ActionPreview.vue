<script setup lang="ts">
// A stickman playing one custom action, drawn by the render engine's own code (engine/page/actions.js customPose +
// stickman.js), so the preview is what renders. Animates in real time; with reduced motion, or `at` given, it holds
// one moment instead. A bad action (the editor's draft) shows its error under the picture.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
// @ts-expect-error plain JS module from the engine, no types
import { customPose } from '../../../engine/page/actions.js'
// @ts-expect-error plain JS module from the engine, no types
import { drawStickman } from '../../../engine/page/stickman.js'
import type { CustomAction } from '../api/client'

const p = defineProps<{ action: CustomAction; at?: number; color?: string; label: string }>()
const cv = ref<HTMLCanvasElement>()
const error = ref('')
const TOP = 120, H = 900 // crop of the 512 x 1024 figure canvas: head (and raised hands) to the feet
const fig = document.createElement('canvas')
fig.width = 512
fig.height = 1024
const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function draw(ts: number) {
  const out = cv.value
  if (!out) return
  try {
    drawStickman(fig, {
      seed: 'preview:action', boil: Math.floor(ts * 8), color: p.color ?? '#3a7bd5', eyes: 'dots', expression: 'neutral',
      action: p.action.id, phase: 0, lid: 0, mouth: 0, breath: 0, facing: 'camera', t: ts, props: [],
      custom: customPose(p.action, ts),
    })
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
  const g = out.getContext('2d')!
  g.clearRect(0, 0, out.width, out.height)
  const s = out.height / H
  g.drawImage(fig, 0, TOP, 512, H, (out.width - 512 * s) / 2, 0, 512 * s, H * s)
}

let raf = 0, t0 = 0
const frame = (now: number) => {
  t0 ||= now
  draw((now - t0) / 1000)
  raf = requestAnimationFrame(frame)
}
const restart = () => {
  cancelAnimationFrame(raf)
  t0 = 0
  if (p.at !== undefined || still) draw(p.at ?? p.action.duration * 0.5)
  else raf = requestAnimationFrame(frame)
}
onMounted(restart)
onBeforeUnmount(() => cancelAnimationFrame(raf))
watch(() => [p.action, p.at, p.color], restart, { deep: true })
</script>

<template>
  <div class="drawing relative grid place-items-center overflow-hidden rounded-md">
    <canvas ref="cv" width="240" height="320" role="img" :aria-label="label" class="h-full w-auto max-w-full" />
    <p v-if="error" class="absolute inset-x-2 bottom-2 text-xs text-red-ink" role="alert">{{ error }}</p>
  </div>
</template>
