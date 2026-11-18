<script setup lang="ts">
import { Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed } from 'vue'
import { api } from '../api/client'
import Card from '../components/Card.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { act, confirm } from '../composables/feedback'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { builtinNote } from '../lib/sets'

// Every place a story can happen (@set <name>): the engine's built-in sets and the library's custom ones, shared by
// every series.
const { data, error, loading, reload, refresh } = useApi(() => api.sets())
refetchOn(() => null, () => null, refresh)

const custom = computed(() => data.value?.custom ?? [])
const all = computed(() => [
  ...(data.value?.builtin ?? []).map((b) => ({ id: b.id, name: b.id.replace('_', ' '), kind: b.kind, builtin: true })),
  ...custom.value.map((c) => ({ id: c.id, name: c.name, kind: c.kind, builtin: false })),
])

// the server refuses (409, naming the stories) while any part's story.md still has @set <id>
async function remove(s: { id: string; name: string }) {
  const ok = await confirm({ title: `Delete “${s.name}”?`, body: 'Only possible while no story uses it: change their @set lines first.', confirm: 'Delete set', danger: true })
  if (ok && (await act(() => api.deleteSet(s.id), 'Set deleted'))) refresh()
}
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading sets" />
  <div v-else class="space-y-5">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Sets</h2>
      <span class="text-sm text-muted">{{ all.length }} places a story can happen · {{ custom.length }} custom</span>
      <RouterLink to="/sets/new#ai" class="btn btn-secondary ml-auto"><Sparkles :size="16" aria-hidden="true" /> Build with AI</RouterLink>
      <RouterLink to="/sets/new" class="btn btn-primary"><Plus :size="16" aria-hidden="true" /> New set</RouterLink>
    </div>
    <p class="text-sm text-muted">
      A story picks its set with a line like <code>@set kitchen</code> before the narration. Custom sets are shared by
      every series. Outdoor sets allow travelling shots (the world scrolls past walking actors); indoor ones have a
      back wall. Changing a set changes every part that uses it on its next render.
    </p>
    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <Card v-for="s in all" :key="s.id" class="flex items-center gap-3 p-4">
        <div class="min-w-0 flex-1">
          <div>
            <h3 class="truncate font-display text-lg font-semibold capitalize">{{ s.name }}</h3>
            <p class="text-xs text-muted"><code>@set {{ s.id }}</code><template v-if="s.builtin"> · {{ builtinNote(s.id) }}</template></p>
          </div>
        </div>
        <span class="chip shrink-0" :class="s.kind === 'outdoor' ? 'chip-green' : 'chip-amber'">{{ s.kind }}</span>
        <template v-if="!s.builtin">
          <RouterLink :to="`/sets/${s.id}`" class="btn btn-secondary shrink-0 px-3" :aria-label="`Edit ${s.name}`">Edit</RouterLink>
          <button type="button" class="btn btn-secondary size-11 shrink-0 justify-center p-0 text-red-ink" :aria-label="`Delete ${s.name}`" @click="remove(s)"><Trash2 :size="16" aria-hidden="true" /></button>
        </template>
        <span v-else class="shrink-0 text-xs text-muted">built in</span>
      </Card>
    </div>
  </div>
</template>
