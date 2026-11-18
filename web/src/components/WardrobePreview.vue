<script setup lang="ts">
// A humanoid wearing one wardrobe item (or nothing: a pose preview), drawn by the render engine's own code (engine/page/stickman.js), so the preview
// is what renders: any build, pose, expression and facing. Cropped to the figure. A drawing error shows under it.
import { onMounted, ref, watch } from 'vue'
// @ts-expect-error plain JS module from the engine, no types
import { CW, drawStickman, figurePx } from '../../../engine/page/stickman.js'
// @ts-expect-error plain JS module from the engine, no types
import { setLibrary } from '../../../engine/page/library.js'
import { LIST_SLOTS, PREVIEW_POSES, type Build, type Slot, type WardrobeItem } from '../lib/wardrobe'

const p = defineProps<{
  id?: string; slot?: Slot; custom?: WardrobeItem[]; color?: string; build?: Build | null; pose?: string;
  expression?: string; facing?: 'camera' | 'left' | 'right'; label: string
}>()
const cv = ref<HTMLCanvasElement>()
const error = ref('')
const FEET = 1000, PAD = 30

function draw() {
  const out = cv.value
  if (!out) return
  const g = out.getContext('2d')!
  g.clearRect(0, 0, out.width, out.height)
  const card = Object.assign(document.createElement('canvas'), { width: CW, height: 1024 })
  const color = p.color ?? '#6b4f3a', body = p.slot === 'top' ? color : '#c9c2b4'
  const worn = !p.id || !p.slot ? {} : p.slot === 'top' ? { top: { style: p.id, color } }
    : LIST_SLOTS.includes(p.slot) ? { [p.slot]: [{ id: p.id, color }] } : { [p.slot]: { id: p.id, color } }
  const pose = p.pose ?? 'idle'
  try {
    if (p.custom) setLibrary({ wardrobe: p.custom })
    drawStickman(card, {
      seed: 'preview:wardrobe', boil: 0, t: 0.3, action: pose, phase: 0, lid: 0, mouth: 0, breath: 0,
      facing: p.facing ?? 'camera', eyes: 'dots', expression: p.expression ?? 'neutral', props: [], color: body,
      top: { style: 'plain', color: body }, build: p.build ?? undefined, ...(PREVIEW_POSES[pose] ?? {}), ...worn,
    })
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
  const top = figurePx(p.build ?? undefined) + 60, w = CW, h = Math.min(1024, top + 2 * PAD)
  const s = Math.min(out.width / w, out.height / h)
  g.drawImage(card, 0, FEET - top - PAD, w, h, (out.width - w * s) / 2, (out.height - h * s) / 2, w * s, h * s)
}
onMounted(draw)
watch(() => [p.id, p.slot, p.custom, p.color, p.build, p.pose, p.expression, p.facing], draw, { deep: true })
</script>

<template>
  <div class="drawing relative grid place-items-center overflow-hidden rounded-md">
    <canvas ref="cv" width="240" height="420" role="img" :aria-label="label" class="h-full w-auto max-w-full" />
    <p v-if="error" class="absolute inset-x-2 bottom-2 text-xs text-red-ink" role="alert">{{ error }}</p>
  </div>
</template>
