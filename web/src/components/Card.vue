<script setup lang="ts">
import { motion } from 'motion-v'
import { reducedMotion, SPRING, STAGGER } from '../composables/ui'

// lift: hover lift + deeper shadow; press: sinks on press (clickable cards only); index: entrance stagger
const p = withDefaults(defineProps<{ lift?: boolean; press?: boolean; index?: number }>(), { index: 0 })
const still = reducedMotion() // MotionConfig makes transforms instant, but a hover jump is still movement
</script>

<template>
  <motion.div
    class="raised"
    :class="{ lift: p.lift }"
    :initial="{ opacity: 0, y: 16 }"
    :animate="{ opacity: 1, y: 0, transition: { ...SPRING, delay: p.index * STAGGER } }"
    :while-hover="p.lift && !still ? { y: -5 } : undefined"
    :while-press="p.press && !still ? { scale: 0.97 } : undefined"
    :transition="SPRING"
  >
    <slot />
  </motion.div>
</template>
