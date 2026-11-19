<script setup lang="ts">
// One part on the series page: number, title, stages, approvals, posts. The whole card opens the part.
import { Check, ChevronRight, Clock, Instagram, Youtube } from 'lucide-vue-next'
import type { PartSummary } from '../api/client'
import { expandFrom, label } from '../composables/ui'
import Card from './Card.vue'
import StageChips from './StageChips.vue'

const p = defineProps<{ slug: string; part: PartSummary; index: number }>()

const APPROVALS = ['stills', 'final'] as const // the test render is optional
function approval(a: string): [string, string] {
  if (p.part.approvals[a]) return ['chip-green', 'approved']
  if (p.part.waiting.includes(a)) return ['chip-amber', 'waiting for you']
  return ['', 'not ready']
}
/** remember the clicked card's rect: the part page expands its header from it */
function expand(e: MouseEvent) {
  expandFrom.rect = (e.currentTarget as HTMLElement).closest('.raised')!.getBoundingClientRect()
  expandFrom.key = `${p.slug}/${p.part.id}`
}
</script>

<template>
  <Card :index="index" :lift="!part.missing" :press="!part.missing">
    <p v-if="part.missing" class="p-5 text-sm text-muted">{{ part.id }}: part.json is missing</p>
    <RouterLink v-else :to="`/series/${slug}/${part.id}`" class="block rounded-lg p-5" @click="expand">
      <div class="flex flex-wrap items-center gap-3">
        <span class="num text-2xl text-muted">{{ String(part.number).padStart(2, '0') }}</span>
        <h4 class="font-display text-lg font-semibold">{{ part.title }}</h4>
        <span v-if="part.waiting.length" class="chip chip-amber"><Clock :size="14" aria-hidden="true" />waiting for you</span>
        <span class="ml-auto flex items-center gap-3 text-faint">
          <Youtube :size="18" :class="{ 'text-youtube': part.posted?.youtube }"
            :aria-label="part.posted?.youtube ? 'posted on YouTube' : 'not on YouTube'" />
          <Instagram :size="18" :class="{ 'text-instagram': part.posted?.instagram }"
            :aria-label="part.posted?.instagram ? 'posted on Instagram' : 'not on Instagram'" />
          <ChevronRight :size="18" aria-hidden="true" />
        </span>
      </div>

      <StageChips class="mt-4" :stages="part.stages" />

      <div class="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <span class="mr-1 text-muted">Approvals</span>
        <span v-for="a in APPROVALS" :key="a" class="chip" :class="approval(a)[0]" :title="approval(a)[1]">
          <Check v-if="part.approvals[a]" :size="14" aria-hidden="true" />
          <Clock v-else-if="part.waiting.includes(a)" :size="14" aria-hidden="true" />
          {{ label(a) }}<span class="sr-only">: {{ approval(a)[1] }}</span>
        </span>
      </div>
    </RouterLink>
  </Card>
</template>
