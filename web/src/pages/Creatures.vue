<script setup lang="ts">
import { PawPrint, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed } from 'vue'
import { api } from '../api/client'
import CreaturePreview from '../components/CreaturePreview.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { act, confirm } from '../composables/feedback'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { RIG_NOTES, allCreatures, isBuiltinCreature } from '../lib/creatures'

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
  const by: Record<string, { slug: string; title: string; name: string; color: string; headless: boolean }[]> = {}
  for (const d of data.value?.series ?? [])
    for (const c of d.series.cast)
      (by[c.body] ??= []).push({ slug: d.series.slug, title: d.series.title, name: c.name, color: c.top.color, headless: c.headless || Object.values(c.looks ?? {}).some((l) => l.headless) })
  return by
})

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
      <RouterLink to="/ai-creations?type=creature" class="btn btn-secondary ml-auto"><Sparkles :size="16" aria-hidden="true" /> Build with AI</RouterLink>
      <RouterLink to="/creatures/new" class="btn btn-primary"><Plus :size="16" aria-hidden="true" /> New creature</RouterLink>
    </div>
    <p class="text-sm text-muted">
      Every cast member has a body: <code>"body": "cat"</code> in its cast entry (or the Body choice when you create a
      series), <code>human</code> when it says none. Humanoids are stickmen with their own proportions and head colour:
      face, expressions, costume and hands. Every other creature is drawn in the top colour and accent colour, with eyes
      and a mouth only; <code>"headless": true</code> swaps its head for a stump, and bipeds have hands. Changing a
      creature clears the cast approval of everyone using it.
    </p>
    <!-- the creatures sheet: one ruled row per body -->
    <div class="raised overflow-x-auto">
      <table class="w-full min-w-[680px] border-collapse text-sm">
        <thead>
          <tr class="border-b-2 border-rule-strong">
            <th scope="col" class="colhead w-44 px-4 py-2.5 text-left">Drawing</th>
            <th scope="col" class="colhead border-l border-rule px-4 py-2.5 text-left">Creature</th>
            <th scope="col" class="colhead border-l border-rule px-4 py-2.5 text-left">Cast</th>
            <th scope="col" class="colhead w-48 border-l border-rule px-4 py-2.5 text-left"><span class="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in creatures" :key="c.id" class="border-b border-rule align-top last:border-b-0">
            <td class="px-4 py-3"><CreaturePreview :creature="c" :color="users[c.id]?.[0]?.color" :label="`${c.name}, standing`" class="h-24 w-36" /></td>
            <th scope="row" class="border-l border-rule px-4 py-3 text-left font-normal">
              <p class="font-display text-lg font-semibold">{{ c.name }}</p>
              <p class="text-xs text-muted">{{ isBuiltinCreature(c.id) ? 'built in' : 'custom' }} · <code>{{ c.id }}</code> · {{ c.rig }}</p>
              <p class="mt-1 max-w-sm text-xs text-muted">{{ RIG_NOTES[c.rig] }}</p>
            </th>
            <td class="border-l border-rule px-4 py-3">
              <ul v-if="users[c.id]?.length" class="space-y-1">
                <li v-for="u in users[c.id]" :key="`${u.slug}/${u.name}`">
                  <RouterLink :to="`/series/${u.slug}`" class="font-semibold hover:underline">{{ u.name }}</RouterLink>
                  <span class="text-muted"> · {{ u.title }}<template v-if="u.headless"> · headless</template></span>
                </li>
              </ul>
              <p v-else class="flex items-center gap-1.5 text-muted"><PawPrint :size="14" aria-hidden="true" /> no cast member yet</p>
            </td>
            <td class="border-l border-rule px-4 py-3">
              <div class="flex flex-wrap gap-2">
                <RouterLink :to="isBuiltinCreature(c.id) ? `/creatures/new?from=${c.id}` : `/creatures/${c.id}`" class="btn btn-secondary">
                  {{ isBuiltinCreature(c.id) ? 'Copy' : 'Edit' }}
                </RouterLink>
                <button v-if="!isBuiltinCreature(c.id) && !users[c.id]?.length" type="button" class="btn btn-secondary text-red-ink" :aria-label="`Delete ${c.name}`" @click="remove(c)"><Trash2 :size="16" aria-hidden="true" /> Delete</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
