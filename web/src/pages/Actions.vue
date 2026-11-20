<script setup lang="ts">
import { shortName } from '../lib/aiName'
import { Plus, Sparkles } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import ActionPreview from '../components/ActionPreview.vue'
import ErrorCard from '../components/ErrorCard.vue'
import LibraryCard from '../components/LibraryCard.vue'
import LibrarySection from '../components/LibrarySection.vue'
import AiGenerateModal from '../components/AiGenerateModal.vue'
import WardrobePreview from '../components/WardrobePreview.vue'
import { act, confirm } from '../composables/feedback'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { buildActionPrompt, importAction } from '../lib/actionPrompt'

// Every move a story's @do can ask for: the engine's built-ins (code) and the library's custom ones (keyframes the
// stickman plays), shared by every series.
const { data, error, loading, reload, refresh } = useApi(() => api.actions())
refetchOn(() => null, () => null, refresh)
const custom = computed(() => data.value?.custom ?? [])
const title = (id: string) => id[0].toUpperCase() + id.slice(1).replaceAll('_', ' ')
// ?ai=<id> (the story check's "Make <id> with AI"): open the generator for the id the story already uses
const aiQuery = useRoute().query.ai
const aiId = ref(typeof aiQuery === 'string' ? aiQuery : '')
const aiOpen = ref(!!aiId.value)
const aiPrompt = (description: string) => buildActionPrompt(shortName(description) || 'new-action', [...(data.value?.do ?? []), ...custom.value.map((x) => x.id)], description, aiId.value)
const aiParse = (text: string) => { const r = importAction(text); return { data: r.action, error: r.error } }
const aiSave = async (data: unknown) => { await api.saveAction(data as Parameters<typeof api.saveAction>[0]); refresh() }

// the server refuses (409, naming the parts) while a story's @do uses it
async function remove(a: { id: string; name: string }) {
  const ok = await confirm({ title: `Delete “${a.name}”?`, body: 'Only possible while no story uses it in @do.', confirm: 'Delete action', danger: true })
  if (ok && (await act(() => api.deleteAction(a.id), 'Action deleted'))) refresh()
}
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading actions" />
  <div v-else-if="data" class="space-y-6">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Actions</h2>
      <span class="text-sm text-muted">{{ data.do.length }} built in · {{ custom.length }} custom</span>
      <button type="button" class="btn btn-secondary ml-auto" @click="aiOpen = true"><Sparkles :size="16" aria-hidden="true" /> Generate with AI</button>
      <RouterLink to="/actions/new" class="btn btn-primary"><Plus :size="16" aria-hidden="true" /> New action</RouterLink>
    </div>
    <p class="text-sm text-muted">
      A story asks for one with <code>@do fred: salute</code> on the line before the narration it covers (see
      <RouterLink to="/help#do" class="underline">Help</RouterLink>). Custom actions are in-place moves made of keyframes:
      humanoids (every human) play them; other creatures stand idle through them.
    </p>
    <LibrarySection id="builtin" title="Built in" :count="data.do.length">
      <LibraryCard v-for="a in data.do" :key="a" :name="title(a)" :code="`@do <cast>: ${a}`" tag="built in" readonly="engine code: read only">
        <template #preview><WardrobePreview :pose="a" :label="`Stickman: ${a}`" class="h-full w-full" /></template>
      </LibraryCard>
    </LibrarySection>
    <LibrarySection id="custom" title="Custom" :count="custom.length" empty="No custom actions yet: make a salute, a bow or a dance with New action.">
      <LibraryCard v-for="a in custom" :key="a.id" :name="a.name" :code="`@do <cast>: ${a.id}`" tag="custom"
        :note="`${a.duration} s · ${a.loop ? 'loops' : 'plays once'} · ${a.keys.length} keys`" :edit-to="`/actions/${a.id}`" deletable @delete="remove(a)">
        <template #preview><ActionPreview :action="a" :label="`Stickman playing ${a.name}`" class="h-full w-full" /></template>
      </LibraryCard>
    </LibrarySection>
  </div>
  <AiGenerateModal :open="aiOpen" title="Generate an action" description-hint="A slow, proud bow with one arm across the chest" :prompt-builder="aiPrompt" :parser="aiParse" :save="aiSave" :initial="aiId.replaceAll('-', ' ')" @close="aiOpen = false; aiId = ''" @done="aiOpen = false; aiId = ''" />
</template>
