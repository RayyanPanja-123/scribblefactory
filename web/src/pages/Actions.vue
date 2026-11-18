<script setup lang="ts">
import { PersonStanding, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed } from 'vue'
import { api } from '../api/client'
import ActionPreview from '../components/ActionPreview.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { act, confirm } from '../composables/feedback'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'

// Every move a story's @do can ask for: the engine's built-ins (code) and the library's custom ones (keyframes the
// stickman plays), shared by every series.
const { data, error, loading, reload, refresh } = useApi(() => api.actions())
refetchOn(() => null, () => null, refresh)
const custom = computed(() => data.value?.custom ?? [])

// the server refuses (409, naming the parts) while a story's @do uses it
async function remove(a: { id: string; name: string }) {
  const ok = await confirm({ title: `Delete “${a.name}”?`, body: 'Only possible while no story uses it in @do.', confirm: 'Delete action', danger: true })
  if (ok && (await act(() => api.deleteAction(a.id), 'Action deleted'))) refresh()
}
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading actions" />
  <div v-else-if="data" class="space-y-5">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Actions</h2>
      <span class="text-sm text-muted">{{ data.do.length }} built in · {{ custom.length }} custom</span>
      <RouterLink to="/ai-creations?type=action" class="btn btn-secondary ml-auto"><Sparkles :size="16" aria-hidden="true" /> Build with AI</RouterLink>
      <RouterLink to="/actions/new" class="btn btn-primary"><Plus :size="16" aria-hidden="true" /> New action</RouterLink>
    </div>
    <p class="text-sm text-muted">
      A story asks for one with <code>@do fred: salute</code> on the line before the narration it covers (see
      <RouterLink to="/help#do" class="underline">Help</RouterLink>). Custom actions are in-place moves made of keyframes:
      humanoids (every human) play them; other creatures stand idle through them.
    </p>
    <section class="raised p-4" aria-labelledby="builtin-h">
      <h3 id="builtin-h" class="colhead">Built in</h3>
      <p class="mt-2 flex flex-wrap gap-1.5">
        <code v-for="a in data.do" :key="a" class="chip">{{ a }}</code>
      </p>
    </section>
    <div v-if="custom.length" class="raised overflow-x-auto">
      <table class="w-full min-w-[560px] border-collapse text-sm">
        <thead>
          <tr class="border-b-2 border-rule-strong">
            <th scope="col" class="colhead w-32 px-4 py-2.5 text-left">Preview</th>
            <th scope="col" class="colhead border-l border-rule px-4 py-2.5 text-left">Action</th>
            <th scope="col" class="colhead w-48 border-l border-rule px-4 py-2.5 text-left"><span class="sr-only">Edit or delete</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in custom" :key="a.id" class="border-b border-rule align-top last:border-b-0">
            <td class="px-4 py-3"><ActionPreview :action="a" :label="`Stickman playing ${a.name}`" class="h-32 w-24" /></td>
            <th scope="row" class="border-l border-rule px-4 py-3 text-left font-normal">
              <p class="font-display text-lg font-semibold">{{ a.name }}</p>
              <p class="text-xs text-muted"><code>@do &lt;cast&gt;: {{ a.id }}</code> · {{ a.duration }} s · {{ a.loop ? 'loops' : 'plays once' }} · {{ a.keys.length }} keys</p>
            </th>
            <td class="border-l border-rule px-4 py-3">
              <div class="flex flex-wrap gap-2">
                <RouterLink :to="`/actions/${a.id}`" class="btn btn-secondary">Edit</RouterLink>
                <button type="button" class="btn btn-secondary text-red-ink" :aria-label="`Delete ${a.name}`" @click="remove(a)"><Trash2 :size="16" aria-hidden="true" /> Delete</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="raised flex items-center gap-2 p-6 text-muted"><PersonStanding :size="18" aria-hidden="true" /> No custom actions yet: make a salute, a bow or a dance with New action.</p>
  </div>
</template>
