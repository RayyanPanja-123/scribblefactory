<script setup lang="ts">
import { shortName } from '../lib/aiName'
import { Backpack, Plus, Sparkles } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import LibraryCard from '../components/LibraryCard.vue'
import LibrarySection from '../components/LibrarySection.vue'
import AiGenerateModal from '../components/AiGenerateModal.vue'
import PropPreview from '../components/PropPreview.vue'
import { act, confirm } from '../composables/feedback'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { buildPrompt, importProp } from '../lib/propPrompt'
import { builtinNote, propOptions, type BuiltinProp } from '../lib/props'

// Every prop a cast member can hold (one per hand): the built-ins and the library's custom ones, shared by every
// series, with who holds each.
const { data, error, loading, reload, refresh } = useApi(async () => {
  const [catalog, list] = await Promise.all([api.props(), api.series()])
  return { catalog, series: await Promise.all(list.map((s) => api.seriesDetail(s.slug))) }
})
refetchOn(() => null, () => null, refresh)

const custom = computed(() => data.value?.catalog.custom ?? [])
const options = computed(() => propOptions(data.value?.catalog))
const isBuiltin = (id: string) => (data.value?.catalog.builtin as string[] | undefined)?.includes(id) ?? false
const groups = computed(() => [
  { id: 'builtin', title: 'Built in', items: options.value.filter((o) => isBuiltin(o.id)).map((o) => ({ ...o, name: o.name[0].toUpperCase() + o.name.slice(1) })) },
  { id: 'custom', title: 'Custom', items: options.value.filter((o) => !isBuiltin(o.id)) },
])
// ?ai=<id> (the story check's "Make <id> with AI"): open the generator for the id the story already uses
const aiQuery = useRoute().query.ai
const aiId = ref(typeof aiQuery === 'string' ? aiQuery : '')
const aiOpen = ref(!!aiId.value)
const aiPrompt = (description: string) => buildPrompt(shortName(description) || 'new-prop', data.value?.catalog.builtin ?? [], description, aiId.value)
const aiParse = (text: string) => { const r = importProp(text); return { data: r.prop, error: r.error } }
const aiSave = async (data: unknown) => { await api.saveProp(data as Parameters<typeof api.saveProp>[0]); refresh() }
const holders = computed(() => {
  const by: Record<string, { slug: string; name: string; detail: string }[]> = {}
  for (const d of data.value?.series ?? [])
    for (const c of d.series.cast)
      for (const p of c.props) (by[p.kind] ??= []).push({ slug: d.series.slug, name: c.name, detail: `${p.hand} hand` })
  return by
})

// the server refuses (409, naming them) while a cast member holds it or a story's @do uses it
async function remove(o: { id: string; name: string }) {
  const ok = await confirm({ title: `Delete “${o.name}”?`, body: 'Only possible while nobody holds it and no story uses it in @do.', confirm: 'Delete prop', danger: true })
  if (ok && (await act(() => api.deleteProp(o.id), 'Prop deleted'))) refresh()
}
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading props" />
  <div v-else class="space-y-6">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Props</h2>
      <span class="text-sm text-muted">{{ options.length }} things a cast member can hold, one per hand · {{ custom.length }} custom</span>
      <button type="button" class="btn btn-secondary ml-auto" @click="aiOpen = true"><Sparkles :size="16" aria-hidden="true" /> Generate with AI</button>
      <RouterLink to="/props/new" class="btn btn-primary"><Plus :size="16" aria-hidden="true" /> New prop</RouterLink>
    </div>
    <p class="text-sm text-muted">
      Custom props are shared by every series: any character can hold one once it’s assigned (left / right hand) when you
      create the series, or in its cast JSON as <code>"props": [{ "kind": "flag", "hand": "right" }]</code>. Stories use
      them too: <code>@do fred: eat apple</code>, <code>@do fred: give flag sam</code>. Changing a prop’s drawing clears
      the cast approval of everyone holding it.
    </p>
    <LibrarySection v-for="g in groups" :id="g.id" :key="g.id" :title="g.title" :count="g.items.length"
      empty="No custom props yet: draw one with New prop, or Generate with AI.">
      <LibraryCard v-for="o in g.items" :key="o.id" :name="o.name" :code="o.id" :tag="isBuiltin(o.id) ? 'built in' : 'custom'"
        :note="isBuiltin(o.id) ? builtinNote(o.id as BuiltinProp) : undefined" :users="holders[o.id] ?? []" used-by="held by"
        unused="nobody holds one yet" :icon="Backpack" :edit-to="isBuiltin(o.id) ? undefined : `/props/${o.id}`"
        :deletable="!isBuiltin(o.id) && !holders[o.id]?.length" readonly="hand-drawn: read only" @delete="remove(o)">
        <template #preview><PropPreview :kind="o.id" :custom="custom" :label="`Stickman holding ${o.name}`" class="h-full w-full" /></template>
      </LibraryCard>
    </LibrarySection>
  </div>
  <AiGenerateModal :open="aiOpen" title="Generate a prop" description-hint="A red umbrella with a curved wooden handle" :prompt-builder="aiPrompt" :parser="aiParse" :save="aiSave" :initial="aiId.replaceAll('-', ' ')" @close="aiOpen = false; aiId = ''" @done="aiOpen = false; aiId = ''" />
</template>
