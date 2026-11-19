<script setup lang="ts">
import { ArrowLeft, Check, CircleAlert } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type CustomAction, type CustomProp, type PackageResult } from '../api/client'
import ActionPreview from '../components/ActionPreview.vue'
import CreaturePreview from '../components/CreaturePreview.vue'
import PropPreview from '../components/PropPreview.vue'
import SetPreview from '../components/SetPreview.vue'
import WardrobePreview from '../components/WardrobePreview.vue'
import { toast } from '../composables/feedback'
import { packageText } from '../composables/storyDraft'
import { allCreatures, type CustomCreature } from '../lib/creatures'
import type { CustomSet } from '../lib/sets'
import type { WardrobeItem } from '../lib/wardrobe'

// Story Review: the step between a clean Story Package and Import. Every new prop, set, creature, action, wardrobe
// item and cast member is shown as it will render, every part's script and voice text in full, and each one is
// approved on its own. Import stays locked until all are. Not happy with something: back to the Story Writer to fix it.
const router = useRouter()
const result = ref<PackageResult | null>(null)
const error = ref('')
const importing = ref(false)
const lib = ref<{ props: CustomProp[]; wardrobe: WardrobeItem[]; creatures: CustomCreature[] }>({ props: [], wardrobe: [], creatures: [] })
const approved = ref(new Set<string>())

onMounted(async () => {
  if (!packageText.value.trim()) return router.replace('/story-writer')
  try {
    const [r, props, wardrobe, creatures] = await Promise.all([api.validatePackage(packageText.value), api.props(), api.wardrobe(), api.creatures()])
    if (!r.ok) {
      toast('The package has errors: fix them first', 'error')
      return router.replace('/story-writer')
    }
    result.value = r
    lib.value = { props: props.custom as CustomProp[], wardrobe: wardrobe.custom, creatures: allCreatures(creatures) }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})

const pkg = <T,>(k: 'props' | 'sets' | 'creatures' | 'actions' | 'wardrobe') => (result.value?.[k] ?? []).map((x) => x.data as T)
const newProps = computed(() => pkg<CustomProp>('props'))
const newSets = computed(() => pkg<CustomSet>('sets'))
const newWardrobe = computed(() => pkg<WardrobeItem>('wardrobe'))
const creatures = computed(() => [...lib.value.creatures, ...pkg<CustomCreature>('creatures')])
const castLibrary = computed(() => ({ props: [...lib.value.props, ...newProps.value], wardrobe: [...lib.value.wardrobe, ...newWardrobe.value] }))
const bodyOf = (c: Record<string, unknown>) => creatures.value.find((x) => x.id === ((c.body as string) ?? 'human'))
const topColor = (c: Record<string, unknown>) => (c.top as { color?: string } | undefined)?.color

const GROUPS = [['props', 'Props'], ['sets', 'Sets'], ['creatures', 'Creatures'], ['actions', 'Actions'], ['wardrobe', 'Wardrobe'], ['cast', 'Cast']] as const
const groups = computed(() => GROUPS.map(([k, title]) => ({ k, title, items: result.value?.[k] ?? [] })).filter((g) => g.items.length))
const keys = computed(() => [...groups.value.flatMap((g) => g.items.map((x) => `${g.k}:${x.id}`)), ...(result.value?.parts ?? []).map((p) => `part:${p.number}`)])
const left = computed(() => keys.value.filter((k) => !approved.value.has(k)).length)
const toggle = (k: string) => {
  const s = new Set(approved.value)
  if (!s.delete(k)) s.add(k)
  approved.value = s
}
const renamedFrom = (k: string, id: string) => Object.entries(result.value?.renames[k] ?? {}).find(([, v]) => v === id)?.[0]
const partWarnings = (n: number) => (result.value?.warnings ?? []).filter((w) => w.section.startsWith(`PART ${n} `))
const otherWarnings = computed(() => (result.value?.warnings ?? []).filter((w) => !w.section.startsWith('PART ')))
const wordsOk = (w: number) => w >= 110 && w <= 175 // the package checker's WORDS range

async function runImport() {
  importing.value = true
  try {
    const r = await api.importPackage(packageText.value)
    toast(`Imported “${r.series!.title}”: ${r.parts.length} part${r.parts.length === 1 ? '' : 's'}`, 'ok')
    packageText.value = ''
    router.push(`/series/${r.series!.slug}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <div class="max-w-5xl space-y-6">
    <div>
      <RouterLink to="/story-writer" class="inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft :size="14" aria-hidden="true" /> Story Writer</RouterLink>
      <h2 class="font-display text-2xl font-semibold">Review {{ result?.series ? `“${result.series.title}”` : 'the package' }}</h2>
      <p class="text-sm text-muted">Check every new item as it will render and read every part. Approve each one: Import unlocks when all are.
        Something off? Go back to the Story Writer and have your AI fix it.</p>
    </div>

    <p v-if="error" class="raised p-4 text-sm text-red-ink" role="alert">{{ error }}</p>
    <p v-if="!result && !error" class="text-sm text-muted" role="status">Checking the package…</p>

    <template v-if="result">
      <div class="raised sticky top-0 z-10 flex flex-wrap items-center gap-2 px-6 py-3">
        <span class="chip" :class="left ? 'chip-amber' : 'chip-green'">{{ left ? `${left} of ${keys.length} left to approve` : 'all approved' }}</span>
        <span v-if="result.warnings.length" class="chip chip-amber">{{ result.warnings.length }} warning{{ result.warnings.length === 1 ? '' : 's' }}</span>
        <button type="button" class="btn btn-primary ml-auto" :disabled="!!left || importing" :aria-busy="importing"
          :title="left ? 'Approve everything first' : 'Write it all to the library'" @click="runImport">{{ importing ? 'Importing…' : 'Import' }}</button>
      </div>

      <section v-if="otherWarnings.length" class="raised space-y-1 p-6" aria-label="Warnings">
        <p v-for="(w, i) in otherWarnings" :key="i" class="flex items-start gap-2 text-sm">
          <CircleAlert :size="16" class="mt-0.5 shrink-0 text-amber-ink" aria-label="warning" /><span><strong>{{ w.section }}</strong> {{ w.message }}</span></p>
      </section>

      <section v-for="g in groups" :key="g.k" class="raised p-6" :aria-labelledby="`sr-${g.k}`">
        <h3 :id="`sr-${g.k}`" class="font-display text-xl font-semibold">{{ g.title }} ({{ g.items.length }} new)</h3>
        <ul class="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <li v-for="x in g.items" :key="x.id" class="rounded-md border p-3"
            :class="approved.has(`${g.k}:${x.id}`) ? 'border-green-ink' : 'border-rule'">
            <PropPreview v-if="g.k === 'props'" class="h-56 grid-rows-1" :kind="x.id" :custom="newProps" :label="`${x.name}, preview`" />
            <SetPreview v-else-if="g.k === 'sets'" class="h-56 grid-rows-1" :id="x.id" :custom="newSets" :weather="(x.data as CustomSet).default_weather" :label="`${x.name}, preview`" />
            <CreaturePreview v-else-if="g.k === 'creatures'" class="h-56 grid-rows-1" :creature="x.data as CustomCreature" :label="`${x.name}, preview`" />
            <ActionPreview v-else-if="g.k === 'actions'" class="h-56 grid-rows-1" :action="x.data as CustomAction" :label="`${x.name}, preview`" />
            <WardrobePreview v-else-if="g.k === 'wardrobe'" class="h-56 grid-rows-1" :id="x.id" :slot="(x.data as WardrobeItem).slot" :custom="newWardrobe"
              :color="(x.data as WardrobeItem).default_color ?? undefined" :label="`${x.name}, preview`" />
            <template v-else>
              <WardrobePreview v-if="bodyOf(x.data)?.rig === 'humanoid'" class="h-56 grid-rows-1" :wear="x.data" :library="castLibrary"
                :build="bodyOf(x.data)?.build" :seed="`review:${x.id}`" :label="`${x.name}, preview`" />
              <CreaturePreview v-else-if="bodyOf(x.data)" class="h-56 grid-rows-1" :creature="bodyOf(x.data)!" :color="topColor(x.data)" :label="`${x.name}, preview`" />
              <p v-else class="drawing grid h-56 place-items-center text-sm text-muted">No preview for this body</p>
            </template>
            <div class="mt-2 flex flex-wrap items-center gap-2 text-sm">
              <strong>{{ x.name }}</strong><code class="text-xs text-muted">{{ x.id }}</code>
              <span v-if="g.k !== 'cast' && renamedFrom(g.k, x.id)" class="text-xs text-red-ink">“{{ renamedFrom(g.k, x.id) }}” is taken</span>
              <button type="button" class="btn ml-auto" :class="approved.has(`${g.k}:${x.id}`) ? 'btn-secondary' : 'btn-primary'"
                :aria-pressed="approved.has(`${g.k}:${x.id}`)" @click="toggle(`${g.k}:${x.id}`)">
                <Check v-if="approved.has(`${g.k}:${x.id}`)" :size="16" aria-hidden="true" />{{ approved.has(`${g.k}:${x.id}`) ? 'Approved' : 'Approve' }}</button>
            </div>
          </li>
        </ul>
      </section>

      <section v-for="p in result.parts" :key="p.number" class="raised p-6" :class="approved.has(`part:${p.number}`) && 'border-green-ink'" :aria-labelledby="`sr-part-${p.number}`">
        <div class="flex flex-wrap items-center gap-2">
          <span class="chip">Part {{ p.number }}</span>
          <h3 :id="`sr-part-${p.number}`" class="font-display text-xl font-semibold">{{ p.title }}</h3>
          <span class="chip" :class="wordsOk(p.words) ? 'chip-green' : 'chip-amber'" title="Aim for 110 to 175 words">{{ p.words }} words</span>
          <button type="button" class="btn ml-auto" :class="approved.has(`part:${p.number}`) ? 'btn-secondary' : 'btn-primary'"
            :aria-pressed="approved.has(`part:${p.number}`)" @click="toggle(`part:${p.number}`)">
            <Check v-if="approved.has(`part:${p.number}`)" :size="16" aria-hidden="true" />{{ approved.has(`part:${p.number}`) ? 'Approved' : 'Approve' }}</button>
        </div>
        <p v-for="(w, i) in partWarnings(p.number)" :key="i" class="mt-2 flex items-start gap-2 text-sm">
          <CircleAlert :size="16" class="mt-0.5 shrink-0 text-amber-ink" aria-label="warning" /><span><strong>{{ w.section }}</strong> {{ w.message }}</span></p>
        <div class="mt-4 grid gap-4 md:grid-cols-2">
          <div><h4 class="text-xs font-semibold uppercase tracking-wide text-muted">Script</h4>
            <pre class="mt-1 max-h-96 overflow-auto whitespace-pre-wrap rounded-md bg-well p-3 text-sm">{{ p.story }}</pre></div>
          <div><h4 class="text-xs font-semibold uppercase tracking-wide text-muted">Voice</h4>
            <pre class="mt-1 max-h-96 overflow-auto whitespace-pre-wrap rounded-md bg-well p-3 font-sans text-sm">{{ p.voice }}</pre></div>
        </div>
      </section>
    </template>
  </div>
</template>
