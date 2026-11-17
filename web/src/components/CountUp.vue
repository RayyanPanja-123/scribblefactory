<script setup lang="ts">
import { animate } from 'motion-v'
import { onMounted, onUnmounted, ref } from 'vue'
import { reducedMotion } from '../composables/ui'

const p = defineProps<{ value: number }>()
const shown = ref(reducedMotion() ? p.value : 0)
let stop: (() => void) | undefined

onMounted(() => {
  if (shown.value === p.value) return
  const a = animate(0, p.value, { duration: 0.9, ease: [0.2, 0.8, 0.2, 1], onUpdate: (v) => (shown.value = Math.round(v)) })
  stop = () => a.stop()
})
onUnmounted(() => stop?.())
</script>

<template>
  <span class="num" :aria-label="String(p.value)">{{ shown }}</span>
</template>
