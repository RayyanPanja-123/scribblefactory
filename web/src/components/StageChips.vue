<script setup lang="ts">
import { RotateCw } from 'lucide-vue-next'
import { onBeforeUnmount, ref } from 'vue'
import { label, statusChip } from '../composables/ui'

// 8 stage chips. With `menu`, each chip opens a small menu: the error (failed) and "re-run (force)".
const p = defineProps<{ stages: Record<string, string>; errors?: Record<string, string | null>; menu?: boolean; disabled?: string | null }>()
const emit = defineEmits<{ rerun: [stage: string] }>()
const SHORT: Record<string, string> = { prep: 'script', import_check: 'voice check', timing: 'timing', shots: 'shots', render: 'video', audio: 'sound', finish: 'final', validate: 'story check' }
const FRIENDLY: Record<string, string> = { prep: 'Prepare script', import_check: 'Check voice', timing: 'Align voice', shots: 'Plan shots', render: 'Render video', audio: 'Make sound', finish: 'Finish and QA', validate: 'Check story' }
// what each stage does (pipeline/scribble/stages/*.py headers), shown in the chip's hover / focus tooltip
const ABOUT: Record<string, string> = {
  prep: 'Turns story.md into script-for-tts.txt: the plain spoken text to paste into the voice site (every @ line stripped).',
  import_check: 'Checks voice.mp3 plays and reports long silences or a length that does not fit the script. Changes nothing.',
  timing: 'Listens to the voice on this machine and finds when each word is spoken (phrases.json). Makes voice-tight.wav with long pauses shortened; voice.mp3 is never changed.',
  shots: 'Plans the video from story.md\'s @ lines and the word timings (story.json): set, cast, positions, actions, faces, camera, weather, lightning and sound cues. Fixed rules and seed, no AI: the same script gives the same plan.',
  validate: 'Checks the plan against the word timings and the cast: sets, actions and cast members exist, no gaps. Changes nothing.',
  render: 'Draws every frame in the 3D engine, in batches; resumable and only redraws what changed. Stills live here too.',
  audio: 'Makes music and sound effects from the plan\'s cues, adds the @sfx sounds, and mixes them under the voice.',
  finish: 'Joins frames and mixed audio into final.mp4 with word-by-word captions, caption effects and the end card, then checks the result (qa.json). Also writes upload.md if missing.',
}
const open = ref<string | null>(null)

const close = (e: MouseEvent) => {
  if (!(e.target as HTMLElement).closest('[data-stage-menu]')) open.value = null
}
document.addEventListener('click', close)
onBeforeUnmount(() => document.removeEventListener('click', close))
</script>

<template>
  <ol class="inset flex flex-wrap gap-2 p-3" aria-label="Stages">
    <li v-for="(status, stage, i) in p.stages" :key="stage" class="group relative" data-stage-menu>
      <component :is="p.menu ? 'button' : 'span'" class="chip" :class="statusChip(status)" :tabindex="p.menu ? undefined : 0"
        :aria-describedby="`stage-tip-${stage}`"
        :aria-expanded="p.menu ? open === stage : undefined" @click="p.menu && (open = open === stage ? null : String(stage))">
        <span class="size-1.5 rounded-full bg-current" :class="{ pulse: status === 'running' }" aria-hidden="true" />
        {{ SHORT[stage] ?? stage }}<span class="sr-only">: {{ status }}</span>
      </component>
      <!-- hover / focus tooltip: what the stage does; right-aligned on the later chips so it stays on screen -->
      <div v-if="open !== stage" :id="`stage-tip-${stage}`" role="tooltip"
        class="raised pointer-events-none absolute top-full z-20 mt-2 hidden w-72 p-3 text-xs group-hover:block group-focus-within:block"
        :class="i >= 5 ? 'right-0' : 'left-0'">
        <p class="text-sm font-semibold">{{ FRIENDLY[String(stage)] ?? label(String(stage)) }} <span class="font-normal text-muted">· {{ status }}</span></p>
        <p v-if="ABOUT[String(stage)]" class="mt-1 text-muted">{{ ABOUT[String(stage)] }}</p>
        <p v-if="p.errors?.[stage]" class="mt-1 rounded-sm bg-red/10 px-2 py-1 text-red-ink">{{ p.errors[stage] }}</p>
      </div>
      <div v-if="open === stage" class="raised absolute top-full left-0 z-20 mt-2 w-64 p-3 text-sm" role="menu">
        <p class="font-semibold">{{ FRIENDLY[String(stage)] ?? label(String(stage)) }} <span class="font-normal text-muted">· {{ status }}</span></p>
        <p v-if="p.errors?.[stage]" class="mt-1 rounded-sm bg-red/10 px-2 py-1 text-xs text-red-ink">{{ p.errors[stage] }}</p>
        <button class="btn btn-secondary mt-3 w-full justify-center" role="menuitem" :disabled="!!p.disabled"
          :title="p.disabled ?? undefined" @click="emit('rerun', String(stage)); open = null">
          <RotateCw :size="14" aria-hidden="true" /> Re-run (force)
        </button>
        <p v-if="p.disabled" class="mt-1 text-xs text-muted">{{ p.disabled }}</p>
      </div>
    </li>
  </ol>
</template>
