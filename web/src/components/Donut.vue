<script setup lang="ts">
import { motion } from 'motion-v'
import { computed } from 'vue'
import { bytes, PALETTE, reducedMotion } from '../composables/ui'

const p = defineProps<{ items: { label: string; value: number }[] }>()
const total = computed(() => p.items.reduce((a, b) => a + b.value, 0))
const R = 70, STROKE = 22, GAP = 0.006
const segments = computed(() => {
  let start = 0
  return p.items.map((it, i) => {
    const frac = total.value ? it.value / total.value : 0
    const seg = { ...it, color: PALETTE[i % PALETTE.length], start, len: Math.max(0, frac - (p.items.length > 1 ? GAP : 0)) }
    start += frac
    return seg
  })
})
const still = reducedMotion()
</script>

<template>
  <div class="flex flex-col items-center gap-5">
    <div class="relative shrink-0">
      <svg viewBox="0 0 180 180" class="size-44" role="img" :aria-label="`Disk usage, ${bytes(total)} total`">
        <circle cx="90" cy="90" :r="R" fill="none" stroke="#e4dfd5" :stroke-width="STROKE" />
        <motion.circle v-for="(s, i) in segments" :key="s.label" cx="90" cy="90" :r="R" fill="none"
          :stroke="s.color" :stroke-width="STROKE" stroke-linecap="butt"
          :transform="`rotate(${-90 + s.start * 360} 90 90)`"
          :initial="still ? false : { pathLength: 0 }" :animate="{ pathLength: s.len }"
          :transition="{ duration: 0.9, delay: 0.15 + i * 0.12, ease: [0.3, 0.7, 0.2, 1] }" />
      </svg>
      <div class="absolute inset-0 grid place-content-center text-center">
        <span class="num text-xl">{{ bytes(total) }}</span>
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
