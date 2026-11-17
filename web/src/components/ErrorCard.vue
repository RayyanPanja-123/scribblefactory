<script setup lang="ts">
import { CircleAlert, RotateCw } from 'lucide-vue-next'
import Card from './Card.vue'

defineProps<{ message: string }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <Card class="mx-auto mt-12 flex max-w-md flex-col items-center gap-4 p-8 text-center" role="alert">
    <span class="round-btn text-red"><CircleAlert :size="22" aria-hidden="true" /></span>
    <div>
      <p class="font-display text-xl font-semibold">Couldn't load this</p>
      <p class="mt-1 text-sm text-muted">{{ message }}</p>
    </div>
    <button class="btn btn-primary" @click="$emit('retry')"><RotateCw :size="16" aria-hidden="true" /> Retry</button>
  </Card>
</template>
