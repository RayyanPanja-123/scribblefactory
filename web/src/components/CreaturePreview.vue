<script setup lang="ts">
// One creature in one pose, drawn by the render engine's own code (engine/page/creatures.js), so the preview is what
// renders. Cropped to the creature's own size. A drawing error (a bad part or joint) shows under the picture.
// A humanoid is a stickman with its build (engine/page/stickman.js), shown facing the camera.
import { onMounted, ref, watch } from 'vue'
// @ts-expect-error plain JS module from the engine, no types
import { CRW, FLAME, GX, drawCreature, measure } from '../../../engine/page/creatures.js'
// @ts-expect-error plain JS module from the engine, no types
import { CW, drawStickman, figurePx } from '../../../engine/page/stickman.js'
// @ts-expect-error plain JS module from the engine, no types
import { setLibrary } from '../../../engine/page/library.js'
import type { CustomCreature } from '../lib/creatures'

// hi: a sharper canvas for drawings shown large (model sheet)
// flame / flameColor: the cast's flame (creatures only). wear: a cast entry whose headwear / face / accessory / back
// a creature wears (custom items, from library.wardrobe)
const p = defineProps<{ creature: CustomCreature; action?: string; headless?: boolean; color?: string; label: string; hi?: boolean
  flame?: string; flameColor?: string | null; wear?: Record<string, unknown>; library?: Record<string, unknown[]> }>()
const cv = ref<HTMLCanvasElement>()
const error = ref('')
const FEET = 1000, PAD = 40

function draw() {
  const out = cv.value
  if (!out) return
  const g = out.getContext('2d')!
  g.clearRect(0, 0, out.width, out.height)
  const humanoid = p.creature.rig === 'humanoid'
  const card = Object.assign(document.createElement('canvas'), { width: humanoid ? CW : CRW, height: 1024 })
  try {
    if (p.library) setLibrary(p.library)
    const def = structuredClone(p.creature) // a fresh object: measure() caches per definition
    const a = p.action ?? 'idle'
    const o = {
      seed: `preview:${def.id}`, boil: 0, t: 0.15, action: a, phase: a === 'walk' || a === 'run' ? 0.25 : 0, lid: 0,
      mouth: a === 'talk' ? 0.8 : 0, breath: 0, facing: humanoid ? 'camera' : 'right', headless: p.headless,
      top: { color: p.color ?? '#c98a4b' }, flame: p.flame, flame_color: p.flameColor, mood: { k: 1, bounce: 0, shake: 0.5 }, eat: { k: 1, chew: 0.5 }, props: [],
      ...(humanoid ? {} : { headwear: p.wear?.headwear, face: p.wear?.face, accessory: p.wear?.accessory, back: p.wear?.back }),
    }
    if (humanoid) drawStickman(card, { ...o, color: o.top.color, eyes: 'dots', expression: 'neutral', build: def.build })
    else drawCreature(card, def, o)
    // humanoid: the card is CW wide around its middle; reach = the card's half width
    const m0 = humanoid ? { half: CW / 2 - PAD, top: figurePx(def.build) } : measure(def)
    const m = { ...m0, top: Math.min(FEET, m0.top * (!humanoid && FLAME[p.flame ?? ''] ? 1.15 : 1)) } // headroom for the mane's flames
    const cx = humanoid ? CW / 2 : GX, w = Math.min(card.width, 2 * (m.half + PAD)), h = Math.min(1024, m.top + 2 * PAD)
    const s = Math.min(out.width / w, out.height / h)
    g.drawImage(card, cx - w / 2, FEET - m.top - PAD, w, h, (out.width - w * s) / 2, (out.height - h * s) / 2, w * s, h * s)
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}
onMounted(draw)
watch(() => [p.creature, p.action, p.headless, p.color, p.flame, p.flameColor, p.wear, p.library], draw, { deep: true })
</script>

<template>
  <div class="drawing relative grid place-items-center overflow-hidden rounded-md">
    <canvas ref="cv" :width="hi ? 720 : 320" :height="hi ? 540 : 240" role="img" :aria-label="label" class="h-full w-auto max-w-full" />
    <p v-if="error" class="absolute inset-x-2 bottom-2 text-xs text-red-ink" role="alert">{{ error }}</p>
  </div>
</template>
