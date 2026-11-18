<script setup lang="ts">
// One group of a library page (a wardrobe slot, a creature rig, built-in vs custom...): a ruled panel with its title,
// count and a grid of LibraryCards. `empty` shows when the group has nothing yet.
defineProps<{ id: string; title: string; count: number; note?: string; empty?: string }>()
</script>

<template>
  <section class="raised p-4" :aria-labelledby="`group-${id}`">
    <h3 :id="`group-${id}`" class="font-display text-lg font-semibold">{{ title }}
      <span class="text-sm font-normal text-muted">· {{ count || 'nothing yet' }}</span></h3>
    <p v-if="note" class="mt-1 text-xs text-muted">{{ note }}</p>
    <ul v-if="count" class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><slot /></ul>
    <p v-else-if="empty" class="mt-3 text-sm text-muted">{{ empty }}</p>
  </section>
</template>
