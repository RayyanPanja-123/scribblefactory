<script setup lang="ts">
// A stickman playing one custom action, drawn by the render engine's own code (engine/page/actions.js customPose +
// stickman.js), so the preview is what renders. Animates in real time; with reduced motion, or `at` given, it holds
// one moment instead. A bad action (the editor's draft) shows its error under the picture. `action` is a custom
// action, or a built-in's id (walk, wave, cheer...), driven by the engine's own motion helpers.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
// @ts-expect-error plain JS module from the engine, no types
import { customPose, gaitPhase, staggerAt } from '../../../engine/page/actions.js'
// @ts-expect-error plain JS module from the engine, no types
import { MOOD_EXPRESSION, moodAt } from '../../../engine/page/extras.js'
// @ts-expect-error plain JS module from the engine, no types
import { waveAmount } from '../../../engine/page/motion.js'
// @ts-expect-error plain JS module from the engine, no types
import { CW, drawStickman } from '../../../engine/page/stickman.js'
import type { CustomAction } from '../api/client'

const p = defineProps<{ action: CustomAction | string; at?: number; color?: string; label: string }>()
const cv = ref<HTMLCanvasElement>()
const error = ref('')
const TOP = 120, H = 900, W = 760 // crop of the CW x 1024 figure card: head (and raised hands) to the feet, room to lean
const fig = document.createElement('canvas')
fig.width = CW
fig.height = 1024
const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
const SPEED: Record<string, number> = { walk: 1.2, run: 2.5, stagger: 0.6 } // units/s (pipeline shots.py MOVE_SPEED)
const REACT_FACE: Record<string, string> = { react: 'surprised', point: 'neutral' }

/** drawStickman options for one moment of the action: a custom pose, or a built-in looped like the render plays it */
function pose(ts: number): Record<string, unknown> {
  const a = p.action
  if (typeof a !== 'string') return { action: a.id, facing: a.facing === 'side' ? 'right' : 'camera', custom: customPose(a, ts) }
  const o: Record<string, unknown> = { action: a, facing: 'camera', expression: MOOD_EXPRESSION[a] ?? REACT_FACE[a] ?? 'neutral' }
  if (SPEED[a]) {
    o.facing = 'right'
    o.phase = gaitPhase(a, SPEED[a] * ts, ts)
    if (a === 'stagger') o.stagger = staggerAt('preview', o.phase)
  }
  if (a === 'wave') o.wave = waveAmount(ts % 2.4)
  if (a === 'talk') o.mouth = Math.abs(Math.sin(ts * 9))
  if (MOOD_EXPRESSION[a]) o.mood = moodAt(a, ts, 'preview')
  return o
}

function draw(ts: number) {
  const out = cv.value
  if (!out) return
  try {
    drawStickman(fig, {
      seed: 'preview:action', boil: Math.floor(ts * 8), color: p.color ?? '#3a7bd5', eyes: 'dots', expression: 'neutral',
      phase: 0, lid: 0, mouth: 0, breath: 0, t: ts, props: [], ...pose(ts),
    })
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
  const g = out.getContext('2d')!
  g.clearRect(0, 0, out.width, out.height)
  const s = out.height / H
  const ahead = typeof p.action !== 'string' && p.action.facing === 'side' ? 100 : 0 // side-on: room for a forward lean
  g.drawImage(fig, (CW - W) / 2 + ahead, TOP, W, H, (out.width - W * s) / 2, 0, W * s, H * s)
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
  if (p.at !== undefined || still) draw(p.at ?? (typeof p.action === 'string' ? 0.6 : p.action.duration * 0.5))
  else raf = requestAnimationFrame(frame)
}
onMounted(restart)
onBeforeUnmount(() => cancelAnimationFrame(raf))
watch(() => [p.action, p.at, p.color], restart, { deep: true })
</script>

<template>
  <div class="drawing relative grid place-items-center overflow-hidden rounded-md">
    <canvas ref="cv" width="270" height="320" role="img" :aria-label="label" class="h-full w-auto max-w-full" />
    <p v-if="error" class="absolute inset-x-2 bottom-2 text-xs text-red-ink" role="alert">{{ error }}</p>
  </div>
</template>
