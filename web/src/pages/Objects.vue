<script setup lang="ts">
import { shortName } from '../lib/aiName'
import { Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref } from 'vue'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import { act, confirm } from '../composables/feedback'
import { useApi } from '../composables/useApi'
import { CAPABILITIES, CARRY_MODES, CATEGORIES, PIECES, type Capability, type ObjectPiece, type WorldObject } from '../lib/objects'
import AiGenerateModal from '../components/AiGenerateModal.vue'
import { buildObjectPrompt, importObject } from '../lib/objectPrompt'
import { slugify } from '../lib/slug'

const { data, error, loading, reload } = useApi(() => api.objects())
const aiOpen = ref(false)
const aiPrompt = (description: string) => buildObjectPrompt(shortName(description), data.value?.objects.map((x) => x.id) ?? [], description)
const aiParse = (text: string) => { const r = importObject(text); return { data: r.object, error: r.error } }
const aiSave = async (value: unknown) => { const result = await api.saveObject(value as WorldObject); data.value = result }
const selected = ref<string | null>(null)
const form = reactive<WorldObject>({ id: '', name: '', category: 'other', capabilities: [], carry_mode: 'none', pieces: [] })
const isNew = computed(() => selected.value === null)
const copy = <T,>(x: T): T => JSON.parse(JSON.stringify(x))
function edit(o: WorldObject) { selected.value = o.id; Object.assign(form, copy(o)) }
function fresh() { selected.value = null; Object.assign(form, { id: '', name: '', category: 'other', capabilities: [], carry_mode: 'none', pieces: [] }) }
function addPiece(shape: ObjectPiece['shape']) { form.pieces.push(copy(PIECES[shape].start)) }
const taken = computed(() => !!data.value?.objects.some((x) => x.id === form.id && x.id !== selected.value))
const valid = computed(() => !!form.name.trim() && /^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.id) && !taken.value && form.pieces.length > 0)
const saving = ref(false)
async function save() {
  saving.value = true
  const result = await act(() => api.saveObject({ ...copy(form), name: form.name.trim() }), `World object “${form.name}” saved`)
  saving.value = false
  if (result) { data.value = result; selected.value = form.id }
}
async function remove() {
  if (!selected.value) return
  const ok = await confirm({ title: `Delete “${form.name}”?`, body: 'This removes the reusable definition. Set placements must be removed first.', confirm: 'Delete object', danger: true })
  if (ok && (await act(() => api.deleteObject(selected.value!), 'World object deleted'))) { data.value = await api.objects(); fresh() }
}
const field = 'inset mt-1 block h-10 w-full rounded-md px-3 text-sm text-ink outline-none focus:border-blue'
const num = 'inset mt-1 block h-9 w-full rounded-md px-2 text-sm text-ink outline-none focus:border-blue num'
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading world objects" />
  <div v-else class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
    <section class="space-y-5">
      <div class="flex flex-wrap items-baseline gap-3"><h2 class="font-display text-2xl font-semibold">World Objects</h2><span class="text-sm text-muted">{{ data?.objects.length ?? 0 }} reusable scene objects</span><button class="btn btn-secondary ml-auto" @click="aiOpen = true"><Sparkles :size="16" /> Build with AI</button><button class="btn btn-primary" @click="fresh"><Plus :size="16" /> New object</button></div>
      <p class="text-sm text-muted">Large objects that live in a scene rather than in a character’s hand: vehicles, crates, barrels and equipment. Capabilities become available to staged interactions.</p>
      <div v-if="!data?.objects.length" class="raised p-8 text-center text-sm text-muted">No World Objects yet. Create a barrel, vehicle or crate.</div>
      <div v-for="o in data?.objects" :key="o.id" class="raised flex items-center gap-4 p-4" :class="selected === o.id && 'ring-2 ring-blue'" @click="edit(o)">
        <div class="grid size-16 shrink-0 place-items-center rounded-md bg-well text-3xl" aria-hidden="true">{{ o.category === 'vehicle' ? '🚚' : o.category === 'container' ? '🛢️' : '◼' }}</div>
        <div class="min-w-0"><h3 class="font-display text-lg font-semibold">{{ o.name }}</h3><p class="text-xs text-muted"><code>{{ o.id }}</code> · {{ o.category }} · {{ o.capabilities.join(', ') || 'static' }}</p></div>
        <button class="btn btn-secondary ml-auto" @click.stop="edit(o)">Edit</button>
      </div>
    </section>
    <form class="raised space-y-5 p-5" @submit.prevent="save">
      <div class="flex items-center justify-between"><h3 class="font-display text-xl font-semibold">{{ isNew ? 'New World Object' : form.name || form.id }}</h3><button v-if="!isNew" type="button" class="btn btn-secondary text-red-ink" @click="remove"><Trash2 :size="16" /> Delete</button></div>
      <div class="grid gap-3 sm:grid-cols-2"><label class="text-xs font-semibold text-muted">Name<input v-model="form.name" :class="field" maxlength="40" required /></label><label class="text-xs font-semibold text-muted">Id<input v-model="form.id" :readonly="!isNew" :class="field" pattern="[a-z0-9]+(-[a-z0-9]+)*" required /></label></div>
      <div class="grid gap-3 sm:grid-cols-2"><label class="text-xs font-semibold text-muted">Category<select v-model="form.category" :class="field"><option v-for="x in CATEGORIES" :key="x">{{ x }}</option></select></label><label class="text-xs font-semibold text-muted">Carry mode<select v-model="form.carry_mode" :class="field"><option v-for="x in CARRY_MODES" :key="x">{{ x }}</option></select></label></div>
      <fieldset><legend class="mb-2 text-xs font-semibold text-muted">Capabilities</legend><div class="grid grid-cols-3 gap-2 text-xs"><label v-for="x in CAPABILITIES" :key="x" class="flex items-center gap-2"><input v-model="form.capabilities" type="checkbox" :value="x" />{{ x }}</label></div></fieldset>
      <fieldset><legend class="mb-2 font-display text-lg font-semibold">Geometry</legend><div v-for="(p, i) in form.pieces" :key="i" class="inset mb-2 space-y-2 rounded-md p-3"><div class="flex gap-2"><select v-model="p.shape" :class="field"><option v-for="(_, k) in PIECES" :key="k" :value="k">{{ PIECES[k].label }}</option></select><button type="button" class="btn btn-secondary" @click="form.pieces.splice(i, 1)"><Trash2 :size="16" /></button></div><div class="grid grid-cols-3 gap-2"><input v-for="(_, j) in ['x','y','z']" :key="j" v-model.number="p.at[j]" type="number" step="any" :class="num" /></div><div class="flex gap-2"><input v-for="(_, j) in PIECES[p.shape].size" :key="j" v-model.number="p.size[j]" type="number" step="any" min="0" :placeholder="PIECES[p.shape].size[j]" :class="num" /><input v-model="p.color" type="color" class="h-9 w-12" /></div></div><div class="flex flex-wrap gap-2"><button v-for="(_, k) in PIECES" :key="k" type="button" class="btn btn-secondary" @click="addPiece(k)"><Plus :size="15" /> {{ PIECES[k].label }}</button></div></fieldset>
      <button class="btn btn-primary w-full" :disabled="!valid || saving">{{ saving ? 'Saving…' : isNew ? 'Create object' : 'Save object' }}</button>
    </form>
  </div>
  <AiGenerateModal :open="aiOpen" title="Generate a World Object" description-hint="A wooden maple syrup barrel with metal hoops, large enough for two thieves to carry" :prompt-builder="aiPrompt" :parser="aiParse" :save="aiSave" @close="aiOpen = false" @done="aiOpen = false" />
</template>
