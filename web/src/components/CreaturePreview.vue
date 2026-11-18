<script setup lang="ts">
// One creature in one pose, drawn by the render engine's own code (engine/page/creatures.js), so the preview is what
// renders. Cropped to the creature's own size. A drawing error (a bad part or joint) shows under the picture.
import { onMounted, ref, watch } from 'vue'
// @ts-expect-error plain JS module from the engine, no types
import { CRW, GX, drawCreature, measure } from '../../../engine/page/creatures.js'
import type { CustomCreature } from '../lib/creatures'

const p = defineProps<{ creature: CustomCreature; action?: string; headless?: boolean; color?: string; label: string }>()
const cv = ref<HTMLCanvasElement>()
const error = ref('')
const FEET = 1000, PAD = 40

function draw() {
  const out = cv.value
  if (!out) return
  const g = out.getContext('2d')!
  g.clearRect(0, 0, out.width, out.height)
  const card = Object.assign(document.createElement('canvas'), { width: CRW, height: 1024 })
  try {
    const def = structuredClone(p.creature) // a fresh object: measure() caches per definition
    const a = p.action ?? 'idle'
    drawCreature(card, def, {
      seed: `preview:${def.id}`, boil: 0, t: 0.15, action: a, phase: a === 'walk' || a === 'run' ? 0.25 : 0, lid: 0,
      mouth: a === 'talk' ? 0.8 : 0, breath: 0, facing: 'right', headless: p.headless, top: { color: p.color ?? '#c98a4b' },
      mood: { k: 1, bounce: 0, shake: 0.5 }, eat: { k: 1, chew: 0.5 }, props: [],
    })
    const m = measure(def), w = Math.min(CRW, 2 * (m.half + PAD)), h = Math.min(1024, m.top + 2 * PAD)
    const s = Math.min(out.width / w, out.height / h)
    g.drawImage(card, GX - w / 2, FEET - m.top - PAD, w, h, (out.width - w * s) / 2, (out.height - h * s) / 2, w * s, h * s)
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}
onMounted(draw)
watch(() => [p.creature, p.action, p.headless, p.color], draw, { deep: true })
</script>

<template>
  <div class="drawing relative grid place-items-center overflow-hidden rounded-md">
    <canvas ref="cv" width="320" height="240" role="img" :aria-label="label" class="h-full w-auto max-w-full" />
    <p v-if="error" class="absolute inset-x-2 bottom-2 text-xs text-red-ink" role="alert">{{ error }}</p>
  </div>
</template>
