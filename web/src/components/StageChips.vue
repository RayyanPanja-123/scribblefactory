<script setup lang="ts">
import { RotateCw } from 'lucide-vue-next'
import { onBeforeUnmount, ref } from 'vue'
import { label, statusChip } from '../composables/ui'

// 9 stage chips. With `menu`, each chip opens a small menu: the error (failed) and "re-run (force)".
const p = defineProps<{ stages: Record<string, string>; errors?: Record<string, string | null>; menu?: boolean; disabled?: string | null }>()
const emit = defineEmits<{ rerun: [stage: string] }>()
const SHORT: Record<string, string> = { import_check: 'import', thumbnails: 'thumbs' }
const open = ref<string | null>(null)

const close = (e: MouseEvent) => {
  if (!(e.target as HTMLElement).closest('[data-stage-menu]')) open.value = null
}
document.addEventListener('click', close)
onBeforeUnmount(() => document.removeEventListener('click', close))
</script>

<template>
  <ol class="inset flex flex-wrap gap-2 p-3" aria-label="Stages">
    <li v-for="(status, stage) in p.stages" :key="stage" class="relative" data-stage-menu>
      <component :is="p.menu ? 'button' : 'span'" class="chip" :class="statusChip(status)"
        :title="`${label(String(stage))}: ${status}${p.errors?.[stage] ? ` (${p.errors[stage]})` : ''}`"
        :aria-expanded="p.menu ? open === stage : undefined" @click="p.menu && (open = open === stage ? null : String(stage))">
        <span class="size-1.5 rounded-full bg-current" :class="{ pulse: status === 'running' }" aria-hidden="true" />
        {{ SHORT[stage] ?? stage }}<span class="sr-only">: {{ status }}</span>
      </component>
      <div v-if="open === stage" class="raised absolute top-full left-0 z-20 mt-2 w-64 p-3 text-sm" role="menu">
        <p class="font-semibold">{{ label(String(stage)) }} <span class="font-normal text-muted">· {{ status }}</span></p>
        <p v-if="p.errors?.[stage]" class="mt-1 rounded-sm bg-[#f8e6e1] px-2 py-1 text-xs text-red-ink">{{ p.errors[stage] }}</p>
        <button class="btn btn-secondary mt-3 w-full justify-center" role="menuitem" :disabled="!!p.disabled"
          :title="p.disabled ?? undefined" @click="emit('rerun', String(stage)); open = null">
          <RotateCw :size="14" aria-hidden="true" /> Re-run (force)
        </button>
        <p v-if="p.disabled" class="mt-1 text-xs text-muted">{{ p.disabled }}</p>
      </div>
    </li>
  </ol>
</template>
