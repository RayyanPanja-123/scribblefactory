<!-- stickman head (assets/brand-mark.svg) on an ink tile -->
<script setup lang="ts">
import mark from '../assets/brand-mark.svg'
</script>

<template>
  <span class="grid size-11 place-items-center rounded-lg bg-[#1b2531] ring-1 ring-rule" role="img" aria-label="Scribble Factory">
    <img :src="mark" alt="" class="size-[70%]" aria-hidden="true" />
  </span>
</template>
