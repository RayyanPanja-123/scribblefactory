<script setup lang="ts">
import { Stamp } from 'lucide-vue-next'
import PencilTick from './PencilTick.vue'

// An approval: an explicit Approve button that becomes an ink tick. One-way (the pipeline never removes one), so the
// approved state is not a control. Clicking emits `request` and the parent decides (confirm, API call).
// `reason` explains why it can't be approved yet.
const p = defineProps<{ on: boolean; label: string; reason?: string | null; busy?: boolean }>()
defineEmits<{ request: [] }>()
</script>

<template>
  <span v-if="p.on" class="inline-flex items-center gap-1.5 text-sm font-semibold text-ink">
    <PencilTick /> <slot>{{ p.label }}</slot><span class="font-normal text-muted">approved</span>
  </span>
  <span v-else class="inline-flex flex-wrap items-center gap-2">
    <button type="button" class="btn btn-secondary" :disabled="!!p.reason || p.busy" :title="p.reason ?? `Approve ${p.label}`"
      :aria-label="`Approve ${p.label}`" @click="$emit('request')">
      <Stamp :size="15" aria-hidden="true" /> Approve <span class="sr-only">{{ p.label }}</span>
    </button>
    <span class="text-sm font-semibold" :class="p.reason ? 'text-muted' : 'text-ink'"><slot>{{ p.label }}</slot></span>
  </span>
</template>
