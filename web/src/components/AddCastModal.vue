<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { ref, watch } from 'vue'
import { api } from '../api/client'
import { act } from '../composables/feedback'
import { nameOf } from '../lib/storyIssues'

// Add the characters a story uses but the cast lacks, all at once: ids fixed (the story already uses them), names
// and outfit colours editable. Outfits and looks come after, in the cast editor.
const props = defineProps<{ open: boolean; slug: string; ids: string[]; taken: number }>()
const emit = defineEmits<{ close: []; done: [] }>()
const PALETTE = ['#3a7bd5', '#d53a3a', '#2e9e5b', '#e0a020', '#8a4fd5', '#d5703a']
const rows = ref<{ id: string; name: string; color: string }[]>([])
const saving = ref(false)
watch(() => props.open, (o) => {
  if (o) rows.value = props.ids.map((id, i) => ({ id, name: nameOf(id), color: PALETTE[(props.taken + i) % PALETTE.length] }))
}, { immediate: true })

async function save() {
  saving.value = true
  const ok = await act(() => api.addCast(props.slug, rows.value.map((r) => ({ ...r, name: r.name.trim() || nameOf(r.id) }))),
    `${rows.value.length} character${rows.value.length === 1 ? '' : 's'} added: Edit each for the outfit`)
  saving.value = false
  if (ok) { emit('done'); emit('close') }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 grid place-items-center bg-[var(--scrim)] p-4" role="presentation" @keydown.esc="emit('close')">
      <form class="raised max-h-[calc(100vh-2rem)] w-full max-w-lg overflow-y-auto p-6 shadow-[var(--shadow-pop)]" role="dialog" aria-modal="true"
        aria-labelledby="add-cast-title" @submit.prevent="save">
        <div class="flex items-start gap-3">
          <div>
            <h2 id="add-cast-title" class="font-display text-2xl font-semibold">Add characters</h2>
            <p class="mt-1 text-sm text-muted">The story already uses these ids. Name them now; outfits and looks come after, with Edit.</p>
          </div>
          <button type="button" class="round-btn ml-auto" aria-label="Close" @click="emit('close')"><X :size="18" /></button>
        </div>
        <div class="mt-5 space-y-3">
          <div v-for="r in rows" :key="r.id" class="flex items-end gap-3">
            <label class="block min-w-0 flex-1 text-xs font-semibold text-muted">Name <code class="font-normal">{{ r.id }}</code>
              <input v-model="r.name" class="inset mt-1 block h-10 w-full rounded-md px-4 text-sm text-ink outline-none focus:border-blue" />
            </label>
            <label class="block text-xs font-semibold text-muted">Outfit
              <input v-model="r.color" type="color" class="mt-1 block h-10 w-14 cursor-pointer rounded-md" />
            </label>
          </div>
        </div>
        <div class="mt-5 flex justify-end gap-2">
          <button type="button" class="btn btn-secondary" @click="emit('close')">Cancel</button>
          <button class="btn btn-primary" :disabled="saving">{{ saving ? 'Adding…' : `Add ${rows.length}` }}</button>
        </div>
      </form>
    </div>
  </Teleport>
</template>
