<!-- stickman head (assets/brand-mark.svg) in a raised dark disc -->
<script setup lang="ts">
import mark from '../assets/brand-mark.svg'
</script>

<template>
  <span class="grid size-11 place-items-center rounded-full bg-ink shadow-[var(--shadow-dark)]" role="img" aria-label="Scribble Factory">
    <img :src="mark" alt="" class="size-8" aria-hidden="true" />
  </span>
</template>
