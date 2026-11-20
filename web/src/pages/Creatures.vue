<script setup lang="ts">
import { shortName } from '../lib/aiName'
import { DEFAULT_TOP_COLOR } from '../lib/wardrobe'
import { PawPrint, Plus, Sparkles } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import CreaturePreview from '../components/CreaturePreview.vue'
import ErrorCard from '../components/ErrorCard.vue'
import LibraryCard from '../components/LibraryCard.vue'
import LibrarySection from '../components/LibrarySection.vue'
import AiGenerateModal from '../components/AiGenerateModal.vue'
import { act, confirm } from '../composables/feedback'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { buildCreaturePrompt, importCreature } from '../lib/creatures'
import { RIG_LIST, RIG_NOTES, allCreatures, isBuiltinCreature, type Rig } from '../lib/creatures'

// Every body a cast member can have (default human): the engine's built-ins and the library's custom creatures, shared
// by every series, with who uses each.
const { data, error, loading, reload, refresh } = useApi(async () => {
  const [catalog, list] = await Promise.all([api.creatures(), api.series()])
  return { catalog, series: await Promise.all(list.map((s) => api.seriesDetail(s.slug))) }
})
refetchOn(() => null, () => null, refresh)

const creatures = computed(() => allCreatures(data.value?.catalog))
const custom = computed(() => data.value?.catalog.custom.length ?? 0)
const users = computed(() => {
  const by: Record<string, { slug: string; name: string; color: string; detail?: string }[]> = {}
  for (const d of data.value?.series ?? [])
    for (const c of d.series.cast)
      (by[c.body] ??= []).push({ slug: d.series.slug, name: c.name, color: c.top.color ?? DEFAULT_TOP_COLOR,
        detail: c.headless || Object.values(c.looks ?? {}).some((l) => l.headless) ? 'headless' : undefined })
  return by
})
const byRig = computed(() => RIG_LIST.map((rig) => ({ rig, items: creatures.value.filter((c) => c.rig === rig) })))
const aiOpen = ref(false)
const aiRig = ref<Rig>('quadruped')
const aiPrompt = (description: string, choice?: string) => buildCreaturePrompt(shortName(description) || 'new-creature', (choice || aiRig.value) as Rig, creatures.value.map((x) => x.id), description)
const aiParse = (text: string) => { const r = importCreature(text); return { data: r.creature, error: r.error } }
const aiSave = async (data: unknown) => { await api.saveCreature(data as Parameters<typeof api.saveCreature>[0]); refresh() }

// the server refuses (409, naming them) while a cast member has it as its body
async function remove(o: { id: string; name: string }) {
  const ok = await confirm({ title: `Delete “${o.name}”?`, body: 'Only possible while no cast member uses it.', confirm: 'Delete creature', danger: true })
  if (ok && (await act(() => api.deleteCreature(o.id), 'Creature deleted'))) refresh()
}
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading creatures" />
  <div v-else class="space-y-5">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Creatures</h2>
      <span class="text-sm text-muted">{{ creatures.length }} bodies for cast members · {{ custom }} custom</span>
      <button type="button" class="btn btn-secondary ml-auto" @click="aiOpen = true"><Sparkles :size="16" aria-hidden="true" /> Generate with AI</button>
      <RouterLink to="/creatures/new" class="btn btn-primary"><Plus :size="16" aria-hidden="true" /> New creature</RouterLink>
    </div>
    <p class="text-sm text-muted">
      Every cast member has a body: <code>"body": "cat"</code> in its cast entry (or the Body choice when you create a
      series), <code>human</code> when it says none. Humanoids are stickmen with their own proportions and head colour:
      face, expressions, costume and hands. Every other creature is drawn in the top colour and accent colour, with eyes
      and a mouth only; <code>"headless": true</code> swaps its head for a stump, and bipeds have hands. Changing a
      creature clears the cast approval of everyone using it.
    </p>
    <LibrarySection v-for="g in byRig" :id="g.rig" :key="g.rig" :title="g.rig[0].toUpperCase() + g.rig.slice(1)" :count="g.items.length" :note="RIG_NOTES[g.rig]"
      :empty="`No ${g.rig} bodies yet.`">
      <LibraryCard v-for="c in g.items" :key="c.id" :name="c.name" :code="c.id" :tag="isBuiltinCreature(c.id) ? 'built in' : 'custom'"
        :users="users[c.id] ?? []" unused="no cast member yet" :icon="PawPrint"
        :edit-to="isBuiltinCreature(c.id) ? `/creatures/new?from=${c.id}` : `/creatures/${c.id}`" :edit-label="isBuiltinCreature(c.id) ? 'Copy' : 'Edit'"
        :deletable="!isBuiltinCreature(c.id) && !users[c.id]?.length" @delete="remove(c)">
        <template #preview><CreaturePreview :creature="c" :color="users[c.id]?.[0]?.color" :label="`${c.name}, standing`" class="h-full w-full" /></template>
      </LibraryCard>
    </LibrarySection>
  </div>
  <AiGenerateModal :open="aiOpen" title="Generate a creature" description-hint="A grumpy goose with a long neck" choice-label="Body rig" :choice-options="RIG_LIST.map((r) => ({ value: r, label: r }))" v-model:choice="aiRig" :prompt-builder="aiPrompt" :parser="aiParse" :save="aiSave" @close="aiOpen = false" @done="aiOpen = false" />
</template>
