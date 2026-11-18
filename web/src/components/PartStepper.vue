<script setup lang="ts">
import { Check, X } from 'lucide-vue-next'
import { nextTick, ref, watch } from 'vue'
import type { PartStepView, StepStatus } from '../lib/partSteps'

// The part's journey (lib/partSteps) as a row of numbered steps joined by a line. Each step links to the section
// where it happens; the current one is marked aria-current="step".
const p = defineProps<{ steps: PartStepView[] }>()

// on a narrow screen the row scrolls sideways: keep the current step in view (horizontal only, never the page)
const nav = ref<HTMLElement>()
watch([nav, () => p.steps.findIndex((s) => s.status !== 'done')], async ([el]) => {
  await nextTick()
  const cur = el?.querySelector<HTMLElement>('[aria-current=step]')
  if (el && cur) el.scrollLeft = cur.offsetLeft - (el.clientWidth - cur.offsetWidth) / 2
}, { immediate: true })
const DOT: Record<StepStatus, string> = {
  done: 'bg-green text-white',
  current: 'bg-amber text-ink ring-4 ring-amber/30',
  review: 'bg-amber text-ink ring-4 ring-amber/30',
  running: 'pulse bg-blue text-white ring-4 ring-blue/25',
  failed: 'bg-red text-white ring-4 ring-red/25',
  todo: 'inset text-muted',
}
const NOTE: Record<StepStatus, string> = {
  done: 'text-green-ink', current: 'text-amber-ink', review: 'text-amber-ink font-semibold', running: 'text-blue-ink', failed: 'text-red-ink font-semibold', todo: 'text-muted',
}
</script>

<template>
  <nav ref="nav" aria-label="Part progress" class="relative overflow-x-auto">
    <ol class="flex w-full min-w-max">
      <li v-for="(s, i) in steps" :key="s.key" class="relative flex min-w-[4.5rem] flex-1 flex-col items-center text-center"
        :aria-current="['current', 'review', 'running', 'failed'].includes(s.status) ? 'step' : undefined">
        <span v-if="i" class="absolute top-4 right-1/2 h-0.5 w-full" :class="s.status === 'todo' ? 'bg-[#e2dccf]' : 'bg-green'" aria-hidden="true" />
        <component :is="s.href ? 'a' : 'span'" :href="s.href || undefined"
          class="relative z-[1] flex flex-col items-center gap-1 rounded-md px-1 py-0.5" :class="s.href && 'hover:bg-panel'">
          <span class="grid size-8 place-items-center rounded-full text-sm font-semibold" :class="DOT[s.status]" aria-hidden="true">
            <Check v-if="s.status === 'done'" :size="16" :stroke-width="3" />
            <X v-else-if="s.status === 'failed'" :size="16" :stroke-width="3" />
            <template v-else>{{ i + 1 }}</template>
          </span>
          <span class="text-xs font-semibold" :class="s.status === 'todo' ? 'text-muted' : 'text-ink'">{{ s.label }}</span>
          <span class="text-[11px] leading-tight" :class="NOTE[s.status]">{{ s.note || ' ' }}<span v-if="!s.note" class="sr-only">to do</span></span>
        </component>
      </li>
    </ol>
  </nav>
</template>
