<script setup lang="ts">
import { motion } from 'motion-v'
import { SPRING } from '../composables/ui'

// Approvals are one-way (the pipeline never removes one), so an "on" switch is locked; turning it on emits
// `request` and the parent decides (confirm, API call). `reason` explains a disabled switch.
const p = defineProps<{ on: boolean; label: string; reason?: string | null; busy?: boolean }>()
defineEmits<{ request: [] }>()
</script>

<template>
  <button
    type="button" role="switch" :aria-checked="p.on" :aria-label="p.label"
    :disabled="p.on || !!p.reason || p.busy" :title="p.reason ?? (p.on ? `${p.label}: approved` : `Approve ${p.label}`)"
    class="group inline-flex items-center gap-3 disabled:cursor-not-allowed" @click="$emit('request')"
  >
    <span class="relative h-8 w-14 shrink-0 rounded-full shadow-[var(--shadow-inset)] transition-colors"
      :class="p.on ? 'bg-[#cfe8d6]' : 'bg-well'">
      <motion.span
        class="absolute top-1 left-1 grid size-6 place-items-center rounded-full bg-panel shadow-[var(--shadow-raised)]"
        :animate="{ x: p.on ? 24 : 0 }" :transition="SPRING">
        <span class="size-2 rounded-full" :class="p.on ? 'bg-green' : p.reason ? 'bg-[#d9d3c8]' : 'bg-faint'" />
      </motion.span>
    </span>
    <span class="text-sm font-semibold" :class="p.reason && !p.on ? 'text-muted' : 'text-ink'">
      <slot>{{ p.label }}</slot>
    </span>
  </button>
</template>
