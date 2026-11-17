<script setup lang="ts">
import { motion } from 'motion-v'
import { computed } from 'vue'
import { SPRING } from '../composables/ui'

// Analogue loudness meter: -30..0 LUFS over a 100° arc; the needle springs to the value, -14 is the target.
const p = defineProps<{ lufs: number; target?: number }>()
const target = computed(() => p.target ?? -14)
const MIN = -30, MAX = 0, SWEEP = 100
const angle = (v: number) => ((Math.min(MAX, Math.max(MIN, v)) - MIN) / (MAX - MIN)) * SWEEP - SWEEP / 2
const ticks = [-30, -24, -18, -14, -9, -6, 0]
const R = 82, CX = 100, CY = 104
const at = (deg: number, r: number) => {
  const a = ((deg - 90) * Math.PI) / 180
  return [CX + r * Math.cos(a), CY + r * Math.sin(a)]
}
const arc = (from: number, to: number, r: number) => {
  const [x1, y1] = at(from, r), [x2, y2] = at(to, r)
  return `M${x1},${y1} A${r},${r} 0 0 1 ${x2},${y2}`
}
</script>

<template>
  <div class="inset relative mx-auto w-full max-w-[260px] overflow-hidden px-3 pt-3 pb-2"
    :aria-label="`Loudness ${lufs} LUFS, target ${target}`" role="img">
    <svg viewBox="0 0 200 118" class="block w-full">
      <path :d="arc(-SWEEP / 2, SWEEP / 2, R)" fill="none" stroke="#d9d3c8" stroke-width="6" stroke-linecap="round" />
      <path :d="arc(angle(target - 1), angle(target + 1), R)" fill="none" stroke="#2fa36b" stroke-width="6" />
      <path :d="arc(angle(-6), SWEEP / 2, R)" fill="none" stroke="#e8603c" stroke-width="6" stroke-linecap="round" />
      <g v-for="t in ticks" :key="t">
        <line :x1="at(angle(t), R - 10)[0]" :y1="at(angle(t), R - 10)[1]" :x2="at(angle(t), R - 18)[0]" :y2="at(angle(t), R - 18)[1]"
          :stroke="t === target ? '#1b6b45' : '#8a857c'" :stroke-width="t === target ? 2.5 : 1.5" />
        <text :x="at(angle(t), R - 28)[0]" :y="at(angle(t), R - 28)[1] + 3" text-anchor="middle" font-size="9"
          :font-weight="t === target ? 700 : 500" :fill="t === target ? '#1b6b45' : '#5f5a51'">{{ t }}</text>
      </g>
      <text x="100" y="112" text-anchor="middle" font-size="9" fill="#5f5a51">LUFS</text>
    </svg>
    <!-- needle: rotates about its foot -->
    <motion.div class="absolute left-1/2 h-[72%] w-[3px] -translate-x-1/2 rounded-full bg-ink"
      :style="{ bottom: '10%', transformOrigin: '50% 100%' }"
      :initial="{ rotate: -SWEEP / 2 }" :animate="{ rotate: angle(lufs) }" :transition="{ ...SPRING, delay: 0.2 }" />
    <span class="absolute bottom-[7%] left-1/2 size-4 -translate-x-1/2 rounded-full bg-ink shadow-[var(--shadow-dark)]" />
  </div>
</template>
