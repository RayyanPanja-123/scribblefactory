<script setup lang="ts">
import { motion } from 'motion-v'
import { computed } from 'vue'
import { bytes, PALETTE, reducedMotion } from '../composables/ui'

const p = defineProps<{ items: { label: string; value: number }[] }>()
const total = computed(() => p.items.reduce((a, b) => a + b.value, 0))
const R = 70, STROKE = 20
const CAP = STROKE / (2 * Math.PI * R) // a round cap adds half the stroke at each end, in pathLength units
const GAP = 0.012
const segments = computed(() => {
  // one series (or one at >= 99.5%): a single seamless ring, no caps, no gap
  const whole = p.items.findIndex((i) => total.value > 0 && i.value / total.value >= 0.995)
  if (whole >= 0) return [{ ...p.items[whole], color: PALETTE[whole % PALETTE.length], offset: 0, len: 1, cap: 'butt' as const }]
  let start = 0
  const many = p.items.filter((i) => i.value > 0).length > 1
  return p.items.map((it, i) => {
    const frac = total.value ? it.value / total.value : 0
    const trim = many ? CAP + GAP : 0 // keep rounded caps from overlapping the next segment
    const seg = { ...it, color: PALETTE[i % PALETTE.length], offset: start + trim / 2, len: Math.max(0.001, frac - trim), cap: 'round' as const }
    start += frac
    return seg
  })
})
const still = reducedMotion()
</script>

<template>
  <div class="flex flex-col items-center gap-5">
    <div class="relative size-44 shrink-0">
      <!-- pressed-in track (ring outer r = R + STROKE/2 of the 180 box) -->
      <div class="absolute inset-[5%] rounded-full bg-well shadow-[var(--shadow-inset)]" aria-hidden="true" />
      <svg viewBox="0 0 180 180" class="relative size-full" role="img" :aria-label="`Disk usage, ${bytes(total)} total`">
        <motion.circle v-for="(s, i) in segments" :key="s.label" cx="90" cy="90" :r="R" fill="none"
          :stroke="s.color" :stroke-width="STROKE" :stroke-linecap="s.cap"
          :transform="`rotate(${-90 + s.offset * 360} 90 90)`"
          :initial="still ? false : { pathLength: 0 }" :animate="{ pathLength: s.len }"
          :transition="{ duration: 0.9, delay: 0.15 + i * 0.12, ease: [0.3, 0.7, 0.2, 1] }" />
      </svg>
      <!-- raised centre disc with the total -->
      <div class="raised absolute inset-[24%] grid place-content-center rounded-full! text-center">
        <span class="num text-lg leading-tight">{{ bytes(total) }}</span>
        <span class="text-xs text-muted">total</span>
      </div>
    </div>
    <ul class="w-full space-y-2 text-sm">
      <li v-for="s in segments" :key="s.label" class="flex items-center gap-2">
        <span class="size-3 shrink-0 rounded-full shadow-[var(--shadow-chip)]" :style="{ background: s.color }" />
        <span class="truncate">{{ s.label }}</span>
        <span class="num ml-auto text-muted">{{ bytes(s.value) }}</span>
      </li>
    </ul>
  </div>
</template>
