<script setup lang="ts">
import { shortName } from '../lib/aiName'
import { Eye, Plus, Sparkles, X } from 'lucide-vue-next'
import { computed, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import LibraryCard from '../components/LibraryCard.vue'
import LibrarySection from '../components/LibrarySection.vue'
import AiGenerateModal from '../components/AiGenerateModal.vue'
import SetPreview from '../components/SetPreview.vue'
import { act, confirm } from '../composables/feedback'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { builtinNote } from '../lib/sets'
import { buildSetPrompt, importSet } from '../lib/setPrompt'

// Every place a story can happen (@set <name>): the engine's built-in sets and the library's custom ones, shared by
// every series.
const { data, error, loading, reload, refresh } = useApi(() => api.sets())
refetchOn(() => null, () => null, refresh)

const custom = computed(() => data.value?.custom ?? [])
const { data: objectData } = useApi(() => api.objects()) // World Items the custom sets place
// previews are slow to draw, so each card draws its set only when asked
const shown = reactive(new Set<string>())
const big = ref<{ id: string; name: string } | null>(null) // set open in the large view
const all = computed(() => [
  ...(data.value?.builtin ?? []).map((b) => ({ id: b.id, name: b.id[0].toUpperCase() + b.id.slice(1).replace('_', ' '), kind: b.kind, builtin: true })),
  ...custom.value.map((c) => ({ id: c.id, name: c.name, kind: c.kind, builtin: false })),
])
const groups = computed(() => [
  { kind: 'indoor', title: 'Indoor', note: 'a floor and a back wall', items: all.value.filter((s) => s.kind === 'indoor') },
  { kind: 'outdoor', title: 'Outdoor', note: 'floor and sky; walking lines become travelling shots', items: all.value.filter((s) => s.kind === 'outdoor') },
])
// ?ai=<id> (the story check's "Make <id> with AI"): open the generator for the id the story already uses
const aiQuery = useRoute().query.ai
const aiId = ref(typeof aiQuery === 'string' ? aiQuery : '')
const aiOpen = ref(!!aiId.value)
const aiPrompt = (description: string) => buildSetPrompt(shortName(description) || 'new-set', all.value.map((x) => x.id), description, aiId.value)
const aiParse = (text: string) => { const r = importSet(text); return { data: r.set, error: r.error } }
const aiSave = async (data: unknown) => { await api.saveSet(data as Parameters<typeof api.saveSet>[0]); refresh() }

// the server refuses (409, naming the stories) while any part's story.md still has @set <id>
async function remove(s: { id: string; name: string }) {
  const ok = await confirm({ title: `Delete “${s.name}”?`, body: 'Only possible while no story uses it: change their @set lines first.', confirm: 'Delete set', danger: true })
  if (ok && (await act(() => api.deleteSet(s.id), 'Set deleted'))) refresh()
}
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading sets" />
  <div v-else class="space-y-6">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Sets</h2>
      <span class="text-sm text-muted">{{ all.length }} places a story can happen · {{ custom.length }} custom</span>
      <button type="button" class="btn btn-secondary ml-auto" @click="aiOpen = true"><Sparkles :size="16" aria-hidden="true" /> Generate with AI</button>
      <RouterLink to="/sets/new" class="btn btn-primary"><Plus :size="16" aria-hidden="true" /> New set</RouterLink>
    </div>
    <p class="text-sm text-muted">
      A story picks its set with a line like <code>@set kitchen</code> before the narration. Custom sets are shared by
      every series. Outdoor sets allow travelling shots (the world scrolls past walking actors); indoor ones have a
      back wall. Changing a set changes every part that uses it on its next render.
    </p>
    <LibrarySection v-for="g in groups" :id="g.kind" :key="g.kind" :title="g.title" :count="g.items.length" :note="g.note">
      <LibraryCard v-for="s in g.items" :key="s.id" :name="s.name" :code="`@set ${s.id}`" :tag="s.builtin ? 'built in' : 'custom'"
        :note="s.builtin ? builtinNote(s.id) : undefined" :edit-to="s.builtin ? undefined : `/sets/${s.id}`" :deletable="!s.builtin"
        readonly="built in: read only" :json="custom.find((c) => c.id === s.id)" @delete="remove(s)">
        <template #preview>
          <button v-if="shown.has(s.id)" type="button" class="block h-full w-full" :aria-label="`Large view of ${s.name}`" title="Large view" @click="big = s">
            <SetPreview :id="s.id" :custom="custom" :objects="objectData?.objects ?? []" :label="`The ${s.name} set, wide shot`" class="h-full w-full" />
          </button>
          <button v-else type="button" class="flex h-full w-full flex-col items-center justify-center gap-1 rounded-md bg-well text-xs text-muted hover:text-ink" :aria-label="`Preview ${s.name}`" @click="shown.add(s.id)">
            <Eye :size="16" aria-hidden="true" /> Preview
          </button>
        </template>
      </LibraryCard>
    </LibrarySection>
  </div>
  <Teleport to="body">
    <div v-if="big" class="fixed inset-0 z-50 grid place-items-center bg-[var(--scrim)] p-4" role="presentation" @click.self="big = null" @keydown.esc="big = null">
      <section class="raised flex max-h-[calc(100vh-2rem)] flex-col gap-3 p-4 shadow-[var(--shadow-pop)]" role="dialog" aria-modal="true" aria-labelledby="set-big-title">
        <div class="flex items-center gap-3">
          <h2 id="set-big-title" class="font-display text-xl font-semibold">{{ big.name }}</h2>
          <code class="text-xs text-muted">@set {{ big.id }}</code>
          <button type="button" class="round-btn ml-auto" aria-label="Close" autofocus @click="big = null"><X :size="18" /></button>
        </div>
        <SetPreview :id="big.id" :custom="custom" :objects="objectData?.objects ?? []" :label="`The ${big.name} set, wide shot`" :w="540" :h="960" class="aspect-[9/16] h-[calc(100vh-7rem)] max-w-full" />
      </section>
    </div>
  </Teleport>
  <AiGenerateModal :open="aiOpen" title="Generate a set" description-hint="A rainy bus stop at night with a flickering lamp" :prompt-builder="aiPrompt" :parser="aiParse" :save="aiSave" :initial="aiId.replaceAll('-', ' ')" @close="aiOpen = false; aiId = ''" @done="aiOpen = false; aiId = ''" />
</template>
