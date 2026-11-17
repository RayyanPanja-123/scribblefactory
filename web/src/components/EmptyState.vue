<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{ icon: Component; title: string; text?: string }>()
</script>

<template>
  <div class="inset grid place-items-center gap-2 px-6 py-8 text-center">
    <span class="round-btn text-faint"><component :is="icon" :size="20" aria-hidden="true" /></span>
    <p class="font-display text-lg font-semibold">{{ title }}</p>
    <p v-if="text" class="max-w-xs text-sm text-muted">{{ text }}</p>
  </div>
</template>
