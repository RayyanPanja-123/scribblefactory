<script setup lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { ref } from 'vue'
// Story writing tips, shown beside the story editor (Text and Painter views)
const TIPS: [string, string][] = [
  ['Sticky stuff', 'Place, On stage and Weather stay until you change them. Set them once, and they hang around for later lines until you swap them.'],
  ['One-line stuff', 'Action, Face, Effect and Sound only happen on that line. Poof, gone after that line.'],
  ['Sound in the middle of a sentence', 'Cut the sentence in two right where the sound happens. Put the second half on the line below it, and put the Sound on that second half. It plays right when the second half starts talking.'],
  ['Sound right after a line', 'Put the Sound on the next line down.'],
  ['Leave room for a sound', 'Put ... at the end of the first half so the speaker pauses. If you don\'t, the sound talks right over their voice.'],
  ['Someone walks in', 'Put On stage with their name on the line right above the line where they show up.'],
  ['Two people doing stuff at the same time', 'Switch to Text and type one line like this: @do ava: wave, ben: cheer.'],
  ['The twist', 'Put only one on the very last line. The camera zooms in, the music cuts out, and a deep thud hits.'],
  ['Don\'t overdo it', 'Use 5 sounds max (never two lines in a row) and 3 lightning bolts max. Use Pop when something suddenly shows up, and Shake when something hits or crashes.'],
  ['Numbers', 'Spell them out. Write "eighteen million", not "18 million".'],
  ['Changed any words?', 'Everything is read out loud. If a line was already recorded, you have to record it again.'],
  ['Confused or stuck?', 'Hit Save, then hit Check. It tells you the exact line number for every mistake.'],
]
const track = ref<HTMLElement>()
// one card's width per click; the browser's scroll-snap lines the cards up
const slide = (dir: number) => track.value?.scrollBy({ left: dir * (track.value.firstElementChild?.clientWidth ?? 280), behavior: 'smooth' })
</script>

<template>
  <aside class="raised min-w-0 p-4" aria-labelledby="story-tips">
    <div class="flex items-center gap-2">
      <h4 id="story-tips" class="font-display text-lg font-semibold">Tips and tricks</h4>
      <button type="button" class="btn btn-secondary ml-auto px-2" aria-label="Previous tips" @click="slide(-1)"><ChevronLeft :size="16" /></button>
      <button type="button" class="btn btn-secondary px-2" aria-label="Next tips" @click="slide(1)"><ChevronRight :size="16" /></button>
    </div>
    <ul ref="track" class="mt-3 flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2 text-sm">
      <li v-for="[t, d] in TIPS" :key="t" class="inset w-72 shrink-0 snap-start p-3">
        <p class="font-semibold text-ink">{{ t }}</p>
        <p class="mt-1 text-muted">{{ d }}</p>
      </li>
    </ul>
  </aside>
</template>
