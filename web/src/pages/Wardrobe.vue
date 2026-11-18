<script setup lang="ts">
import { Plus, Shirt } from 'lucide-vue-next'
import { computed } from 'vue'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import LibraryCard from '../components/LibraryCard.vue'
import LibrarySection from '../components/LibrarySection.vue'
import WardrobePreview from '../components/WardrobePreview.vue'
import { act, confirm } from '../composables/feedback'
import { refetchOn } from '../composables/live'
import { useApi } from '../composables/useApi'
import { SLOT_LABEL, SLOTS, wardrobeOptions, wearers } from '../lib/wardrobe'

// Every wardrobe item a humanoid cast member can wear, by slot: the hand-drawn built-ins and the library's custom items,
// shared by every series, with who wears each.
const { data, error, loading, reload, refresh } = useApi(async () => {
  const [catalog, list] = await Promise.all([api.wardrobe(), api.series()])
  return { catalog, series: await Promise.all(list.map((s) => api.seriesDetail(s.slug))) }
})
refetchOn(() => null, () => null, refresh)

const custom = computed(() => data.value?.catalog.custom ?? [])
const bySlot = computed(() => SLOTS.map((slot) => ({ slot, items: wardrobeOptions(data.value?.catalog).filter((o) => o.slot === slot) })))
const worn = computed(() => Object.fromEntries(wardrobeOptions(data.value?.catalog)
  .map((o) => [o.id, wearers((data.value?.series ?? []) as never, o.id)])))
const colorOf = (id: string) => custom.value.find((w) => w.id === id)?.default_color ?? '#6b4f3a'

// the server refuses (409, naming them) while anyone wears it
async function remove(o: { id: string; name: string }) {
  const ok = await confirm({ title: `Delete “${o.name}”?`, body: 'Only possible while no cast member wears it.', confirm: 'Delete item', danger: true })
  if (ok && (await act(() => api.deleteWardrobeItem(o.id), 'Wardrobe item deleted'))) refresh()
}
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading wardrobe" />
  <div v-else class="space-y-5">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Wardrobe</h2>
      <span class="text-sm text-muted">{{ wardrobeOptions(data?.catalog).length }} items in {{ SLOTS.length }} slots · {{ custom.length }} custom</span>
      <RouterLink to="/wardrobe/new" class="btn btn-primary ml-auto"><Plus :size="16" aria-hidden="true" /> New item</RouterLink>
    </div>
    <p class="text-sm text-muted">
      Clothing, hair and cosmetics for humanoid cast members, one item per slot (accessory and face: up to 3). In the cast
      JSON: <code>"hair": {"id": "wild_hair", "color": "#e8e8e8"}</code>, or just <code>"hair": "wild_hair"</code>;
      <code>null</code> for none. A look (<code>@look</code>) can swap any of them; <code>"none"</code> takes one off.
      Items scale with every build and move with every pose. Changing an item clears the cast approval of everyone wearing it.
    </p>
    <LibrarySection v-for="g in bySlot" :id="g.slot" :key="g.slot" :title="SLOT_LABEL[g.slot]" :count="g.items.length">
      <LibraryCard v-for="o in g.items" :key="o.id" :name="o.name" :code="o.id" :tag="o.builtin ? 'built in' : 'custom'"
        :users="worn[o.id]" used-by="worn by" unused="nobody wears it" :icon="Shirt" :edit-to="o.builtin ? undefined : `/wardrobe/${o.id}`"
        :deletable="!o.builtin && !worn[o.id]?.length" readonly="hand-drawn: read only" @delete="remove(o)">
        <template #preview><WardrobePreview :id="o.id" :slot="o.slot" :custom="custom" :color="colorOf(o.id)" :label="`Stickman wearing ${o.name}`" class="h-full w-full" /></template>
      </LibraryCard>
    </LibrarySection>
  </div>
</template>
