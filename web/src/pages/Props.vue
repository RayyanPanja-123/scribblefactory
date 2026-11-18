<script setup lang="ts">
import { Backpack, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed } from 'vue'
import { api } from '../api/client'
import Card from '../components/Card.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { act, confirm } from '../composables/feedback'
import PropPreview from '../components/PropPreview.vue'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
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
const isBuiltin = (id: string) => (data.value?.catalog.builtin as string[] | undefined)?.includes(id)
const holders = computed(() => {
  const by: Record<string, { slug: string; title: string; name: string; hand: string }[]> = {}
  for (const d of data.value?.series ?? [])
    for (const c of d.series.cast)
      for (const p of c.props) (by[p.kind] ??= []).push({ slug: d.series.slug, title: d.series.title, name: c.name, hand: p.hand })
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
  <div v-else class="space-y-5">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Props</h2>
      <span class="text-sm text-muted">{{ options.length }} things a cast member can hold, one per hand · {{ custom.length }} custom</span>
      <RouterLink to="/props/new#ai" class="btn btn-secondary ml-auto"><Sparkles :size="16" aria-hidden="true" /> Build with AI</RouterLink>
      <RouterLink to="/props/new" class="btn btn-primary"><Plus :size="16" aria-hidden="true" /> New prop</RouterLink>
    </div>
    <p class="text-sm text-muted">
      Custom props are shared by every series: any character can hold one once it’s assigned (left / right hand) when you
      create the series, or in its cast JSON as <code>"props": [{ "kind": "flag", "hand": "right" }]</code>. Stories use
      them too: <code>@do fred: eat apple</code>, <code>@do fred: give flag sam</code>. Changing a prop’s drawing clears
      the cast approval of everyone holding it.
    </p>
    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <Card v-for="o in options" :key="o.id" class="flex gap-4 p-4">
        <PropPreview :kind="o.id" :custom="custom" :label="`Stickman holding ${o.name}`" class="h-40 w-28 shrink-0" />
        <div class="min-w-0 flex-1 space-y-2">
          <div>
            <h3 class="font-display text-lg font-semibold">{{ o.name }}</h3>
            <p class="text-xs text-muted">
              <template v-if="isBuiltin(o.id)">built in · {{ builtinNote(o.id as BuiltinProp) }}</template>
              <template v-else>custom · <code>{{ o.id }}</code></template>
            </p>
          </div>
          <ul v-if="holders[o.id]?.length" class="space-y-1 text-sm">
            <li v-for="h in holders[o.id]" :key="`${h.slug}/${h.name}/${h.hand}`">
              <RouterLink :to="`/series/${h.slug}`" class="font-semibold hover:underline">{{ h.name }}</RouterLink>
              <span class="text-muted"> · {{ h.title }} · {{ h.hand }}</span>
            </li>
          </ul>
          <p v-else class="flex items-center gap-1.5 text-sm text-muted"><Backpack :size="14" aria-hidden="true" /> nobody holds one yet</p>
          <div v-if="!isBuiltin(o.id)" class="flex gap-2">
            <RouterLink :to="`/props/${o.id}`" class="btn btn-secondary">Edit</RouterLink>
            <button v-if="!holders[o.id]?.length" type="button" class="btn btn-secondary text-red-ink" :aria-label="`Delete ${o.name}`" @click="remove(o)"><Trash2 :size="16" aria-hidden="true" /> Delete</button>
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>
