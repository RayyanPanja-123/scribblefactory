<script setup lang="ts">
import { motion } from 'motion-v'
import { computed, ref } from 'vue'
import { SPRING } from '../composables/ui'

type Month = { month: string; youtube: number; instagram: number }
const p = defineProps<{ months: Month[] }>()

const SERIES = [
  { key: 'youtube', name: 'YouTube', color: '#4f7cf7' },
  { key: 'instagram', name: 'Instagram', color: '#9a6ff0' },
] as const
const W = 640, H = 220, L = 32, R = 12, T = 14, B = 28

const top = computed(() => {
  const m = Math.max(0, ...p.months.flatMap((d) => [d.youtube, d.instagram]))
  return m <= 4 ? 4 : Math.ceil(m / 4) * 4
})
const empty = computed(() => p.months.every((d) => d.youtube + d.instagram === 0))
const x = (i: number) => L + (i * (W - L - R)) / Math.max(1, p.months.length - 1)
const y = (v: number) => H - B - (v / top.value) * (H - B - T)
const ticks = computed(() => [0, 1, 2, 3, 4].map((i) => (top.value * i) / 4))
const monthName = (m: string) => new Date(`${m}-01T00:00:00Z`).toLocaleString('en-GB', { month: 'short', timeZone: 'UTC' })

/** Catmull-Rom -> cubic Bézier, control points clamped to the plot so curves never dip below zero. */
function smooth(pts: [number, number][]): string {
  const c = (v: number) => Math.min(H - B, Math.max(T, v))
  let d = `M${pts[0][0]},${pts[0][1]}`
  for (let i = 0; i < pts.length - 1; i++) {
    const [p0, p1, p2, p3] = [pts[i - 1] ?? pts[i], pts[i], pts[i + 1], pts[i + 2] ?? pts[i + 1]]
    d += ` C${p1[0] + (p2[0] - p0[0]) / 6},${c(p1[1] + (p2[1] - p0[1]) / 6)} ${p2[0] - (p3[0] - p1[0]) / 6},${c(p2[1] - (p3[1] - p1[1]) / 6)} ${p2[0]},${p2[1]}`
  }
  return d
}
const paths = computed(() =>
  SERIES.map((s) => {
    const line = smooth(p.months.map((d, i) => [x(i), y(d[s.key])]))
    return { ...s, line, area: `${line} L${x(p.months.length - 1)},${H - B} L${x(0)},${H - B} Z` }
  }),
)

const hover = ref<number | null>(null)
function onMove(e: PointerEvent) {
  const r = (e.currentTarget as SVGElement).getBoundingClientRect()
  const px = ((e.clientX - r.left) / r.width) * W
  hover.value = Math.max(0, Math.min(p.months.length - 1, Math.round(((px - L) / (W - L - R)) * (p.months.length - 1))))
}
</script>

<template>
  <div class="relative">
    <svg :viewBox="`0 0 ${W} ${H}`" class="block w-full" role="img"
      :aria-label="`Posts per month, last ${months.length} months, YouTube and Instagram`"
      @pointermove="onMove" @pointerleave="hover = null">
      <defs>
        <linearGradient v-for="s in SERIES" :id="`fill-${s.key}`" :key="s.key" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" :stop-color="s.color" stop-opacity="0.32" />
          <stop offset="1" :stop-color="s.color" stop-opacity="0" />
        </linearGradient>
        <clipPath id="reveal">
          <motion.rect x="0" y="0" :width="W" :height="H" :style="{ originX: 0 }"
            :initial="{ scaleX: 0 }" :animate="{ scaleX: 1 }" :transition="{ duration: 1.1, ease: [0.3, 0.7, 0.2, 1] }" />
        </clipPath>
      </defs>
      <g class="text-[10px]" fill="#6b665d">
        <template v-for="t in ticks" :key="t">
          <line :x1="L" :x2="W - R" :y1="y(t)" :y2="y(t)" stroke="#d9d3c8" stroke-dasharray="3 5" />
          <text :x="L - 8" :y="y(t) + 3" text-anchor="end">{{ t }}</text>
        </template>
        <text v-for="(d, i) in months" :key="d.month" :x="x(i)" :y="H - 8" text-anchor="middle"
          :font-weight="hover === i ? 700 : 400">{{ monthName(d.month) }}</text>
      </g>
      <g clip-path="url(#reveal)">
        <g v-for="s in paths" :key="s.key">
          <path :d="s.area" :fill="`url(#fill-${s.key})`" />
          <path :d="s.line" fill="none" :stroke="s.color" stroke-width="2.5" stroke-linecap="round" />
        </g>
      </g>
      <g v-if="hover !== null">
        <line :x1="x(hover)" :x2="x(hover)" :y1="T" :y2="H - B" stroke="#8a857c" stroke-dasharray="2 4" />
        <circle v-for="s in SERIES" :key="s.key" :cx="x(hover)" :cy="y(months[hover][s.key])" r="4.5"
          :fill="s.color" stroke="#f8f6f1" stroke-width="2" />
      </g>
    </svg>

    <motion.div v-if="hover !== null" :key="hover"
      class="raised pointer-events-none absolute top-0 z-10 min-w-36 -translate-x-1/2 px-3 py-2 text-xs"
      :style="{ left: `${(x(hover) / W) * 100}%` }" :initial="{ opacity: 0 }" :animate="{ opacity: 1 }" :transition="SPRING">
      <p class="font-semibold">{{ monthName(months[hover].month) }} {{ months[hover].month.slice(0, 4) }}</p>
      <p v-for="s in SERIES" :key="s.key" class="mt-1 flex items-center gap-2 text-muted">
        <span class="size-2 rounded-full" :style="{ background: s.color }" />{{ s.name }}
        <span class="num ml-auto text-ink">{{ months[hover][s.key] }}</span>
      </p>
    </motion.div>

    <div v-if="empty" class="pointer-events-none absolute inset-0 grid place-items-center pb-6">
      <p class="raised px-4 py-2 text-sm text-muted">No posts yet. Mark a part posted and it shows up here.</p>
    </div>

    <div class="mt-2 flex gap-4 text-xs text-muted">
      <span v-for="s in SERIES" :key="s.key" class="flex items-center gap-1.5">
        <span class="h-1 w-4 rounded-full" :style="{ background: s.color }" />{{ s.name }}
      </span>
    </div>
  </div>
</template>
