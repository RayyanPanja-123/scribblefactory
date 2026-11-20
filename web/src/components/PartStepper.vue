<script setup lang="ts">
import { Film, X } from 'lucide-vue-next'
import { nextTick, ref, watch } from 'vue'
import { needsYou, type PartStepView } from '../lib/partSteps'
import GreaseCircle from './GreaseCircle.vue'
import PencilTick from './PencilTick.vue'

// The part's journey (lib/partSteps) as one row of the exposure sheet: the same columns and marks as the Overview.
// Each cell links to the section where the step happens; the current one is aria-current="step".
const p = defineProps<{ steps: PartStepView[] }>()

// on a narrow screen the row scrolls sideways: keep the current cell in view (horizontal only, never the page)
const nav = ref<HTMLElement>()
watch([nav, () => p.steps.findIndex((s) => s.status !== 'done')], async ([el]) => {
  await nextTick()
  const cur = el?.querySelector<HTMLElement>('[aria-current=step]')
  if (el && cur) el.scrollLeft = cur.offsetLeft - (el.clientWidth - cur.offsetWidth) / 2
}, { immediate: true })
const live = (s: PartStepView) => ['current', 'review', 'running', 'failed'].includes(s.status)
</script>

<template>
  <nav ref="nav" aria-label="Part progress" class="overflow-x-auto rounded-md border border-rule">
    <ol class="grid min-w-[640px] grid-cols-8">
      <li v-for="(s, i) in steps" :key="s.key" class="border-rule text-center" :class="{ 'border-l': i > 0 }" :aria-current="live(s) ? 'step' : undefined">
        <p class="colhead flex h-14 flex-col items-center justify-center border-b-2 border-rule-strong px-1 py-1.5 leading-tight">
          <span class="num text-muted" aria-hidden="true">{{ i + 1 }}</span><span>{{ s.label }}</span>
        </p>
        <component :is="s.href ? 'a' : 'span'" :href="s.href || undefined"
          class="relative flex h-12 items-center justify-center gap-1 text-xs font-semibold" :class="s.href && 'hover:bg-blue/10'">
          <span class="sr-only">{{ s.label }}: {{ s.note || 'to do' }}</span>
          <PencilTick v-if="s.status === 'done'" class="text-ink" />
          <template v-else-if="needsYou(s)">
            <span class="font-display text-[13px] text-amber-ink" aria-hidden="true">{{ s.status === 'review' ? 'approve ?' : 'you ?' }}</span>
            <GreaseCircle />
          </template>
          <template v-else-if="s.status === 'current'"><span class="size-1.5 rounded-full bg-blue" aria-hidden="true" /><span class="font-display text-[13px] text-blue-ink" aria-hidden="true">next</span></template>
          <template v-else-if="s.status === 'running'"><Film :size="14" class="reel text-blue" aria-hidden="true" /><span class="font-display text-[13px] text-blue-ink" aria-hidden="true">running</span></template>
          <template v-else-if="s.status === 'failed'"><X :size="14" :stroke-width="3" class="text-red" aria-hidden="true" /><span class="font-display text-[13px] text-red-ink" aria-hidden="true">failed</span></template>
          <span v-else class="size-1 rounded-full bg-rule-strong" aria-hidden="true" />
        </component>
      </li>
    </ol>
  </nav>
</template>
