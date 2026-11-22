<script setup lang="ts">
// A creature's model sheet, opened from its card on the Creatures page: the standing drawing large, then every pose
// the renderer can put it in (and the headless stump when it has one), all drawn by the engine in one colour the
// viewer can change. Inline under the group, not a modal: nothing here needs protected focus.
import { X } from 'lucide-vue-next'
import { onMounted, ref, watch } from 'vue'
import { RIG_NOTES, posesFor, type CustomCreature } from '../lib/creatures'
import CreaturePreview from './CreaturePreview.vue'

const p = defineProps<{ creature: CustomCreature; color?: string; tag: string }>()
defineEmits<{ close: [] }>()
const FALLBACK = '#c98a4b' // the editor's preview colour when nobody wears the creature yet
const color = ref(p.color ?? FALLBACK)
watch(() => p.creature.id, () => { color.value = p.color ?? FALLBACK })

const root = ref<HTMLElement>()
const heading = ref<HTMLElement>()
onMounted(() => {
  const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  root.value?.scrollIntoView({ block: 'nearest', behavior: still ? 'auto' : 'smooth' })
  heading.value?.focus({ preventScroll: true })
})
</script>

<template>
  <section :id="`sheet-${creature.id}`" ref="root" class="inset mt-4 p-4 sm:p-5" :aria-labelledby="`sheet-title-${creature.id}`"
    @keydown.esc="$emit('close')">
    <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
      <h4 :id="`sheet-title-${creature.id}`" ref="heading" tabindex="-1" class="font-display text-xl font-semibold outline-none">{{ creature.name }}</h4>
      <span class="text-xs text-muted"><code>{{ creature.id }}</code> · {{ creature.rig }} · {{ tag }}</span>
      <label class="ml-auto flex items-center gap-2 text-xs text-muted">Colour
        <input v-model="color" type="color" class="h-9 w-12 cursor-pointer rounded-md" :aria-label="`Preview colour for ${creature.name}`" />
      </label>
      <button type="button" class="round-btn" :aria-label="`Close ${creature.name}'s model sheet`" title="Close" @click="$emit('close')"><X :size="18" aria-hidden="true" /></button>
    </div>

    <div class="mt-4 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <figure>
        <CreaturePreview :creature="creature" :color="color" hi :label="`${creature.name}, standing`" class="h-80 lg:h-[26rem]" />
        <figcaption class="mt-1 text-center font-display text-sm text-muted">standing</figcaption>
      </figure>
      <ul class="grid content-start gap-3 grid-cols-2 sm:grid-cols-3" :aria-label="`${creature.name} poses`">
        <li v-for="a in posesFor(creature.rig).filter((x) => x !== 'idle')" :key="a">
          <CreaturePreview :creature="creature" :action="a" :color="color" :label="`${creature.name}: ${a}`" class="h-36" />
          <p class="mt-1 text-center font-display text-sm text-muted">{{ a }}</p>
        </li>
        <li v-if="creature.parts?.stump">
          <CreaturePreview :creature="creature" headless :color="color" :label="`${creature.name}: headless`" class="h-36" />
          <p class="mt-1 text-center font-display text-sm text-muted">headless</p>
        </li>
      </ul>
    </div>
    <p class="mt-4 text-xs text-muted">{{ creature.rig[0].toUpperCase() + creature.rig.slice(1) }}: {{ RIG_NOTES[creature.rig] }}. Drawn by the render engine: what you see is what renders.</p>
  </section>
</template>
