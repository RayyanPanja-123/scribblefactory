<script setup lang="ts">
import { shortName } from '../lib/aiName'
import { Braces, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref } from 'vue'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import ItemPreview from '../components/ItemPreview.vue'
import { act, confirm, copyJson } from '../composables/feedback'
import { useApi } from '../composables/useApi'
import { ANCHORS, ANIMS, CAPABILITIES, CARRY_MODES, CATEGORIES, DRAWINGS, LAYERS, PIECES, RESERVED_STATES, blankObject, type AnimKind, type ObjectPiece, type WorldObject } from '../lib/objects'
import AiGenerateModal from '../components/AiGenerateModal.vue'
import { buildObjectPrompt, importObject } from '../lib/objectPrompt'

const { data, error, loading, reload } = useApi(() => api.objects())
const aiOpen = ref(false)
const aiPrompt = (description: string) => buildObjectPrompt(shortName(description), data.value?.objects.map((x) => x.id) ?? [], description)
const aiParse = (text: string) => { const r = importObject(text); return { data: r.object, error: r.error } }
const aiSave = async (value: unknown) => { const result = await api.saveObject(value as WorldObject); data.value = result }
const selected = ref<string | null>(null)
const form = reactive<WorldObject>(blankObject())
const statesText = ref('')
const previewState = ref<string | null>(null)
const isNew = computed(() => selected.value === null)
const isCard = computed(() => form.look === 'card')
const copy = <T,>(x: T): T => JSON.parse(JSON.stringify(x))
/** replace the whole form (fields a card has and a pieces item hasn't must not linger) */
function load(o: WorldObject) {
  for (const k of Object.keys(form)) delete (form as Record<string, unknown>)[k]
  Object.assign(form, copy(o))
  form.anims?.forEach((a) => { a.when ??= [] }) // a multiple select needs a list
  statesText.value = (o.states ?? []).join(', ')
  previewState.value = null
}
function edit(o: WorldObject) { selected.value = o.id; load(o) }
function fresh(look: 'pieces' | 'card' = 'pieces') { selected.value = null; load(blankObject(look)) }
function setLook(look: 'pieces' | 'card') { const { id, name, category, capabilities, carry_mode } = form; load({ ...blankObject(look), id, name, category, capabilities, carry_mode }) }
function addPiece(shape: ObjectPiece['shape']) { form.pieces.push(copy(PIECES[shape].start)) }
function addAnim(kind: AnimKind) { (form.anims ??= []).push(copy(ANIMS[kind].start)) }
const states = computed(() => statesText.value.split(',').map((s) => s.trim()).filter(Boolean))
const badStates = computed(() => states.value.filter((s) => RESERVED_STATES.includes(s) || !/^[a-z0-9]+(-[a-z0-9]+)*$/.test(s)))
const taken = computed(() => !!data.value?.objects.some((x) => x.id === form.id && x.id !== selected.value))
const valid = computed(() => !!form.name.trim() && /^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.id) && !taken.value
  && (isCard.value ? !!form.draw && !badStates.value.length : form.pieces.length > 0))
/** what is saved: a card's states from the text box, and anim `when`s that name a state it still has */
const item = computed<WorldObject>(() => isCard.value
  ? { ...copy(form), name: form.name.trim(), states: states.value, anims: (form.anims ?? []).map((a) => ({ ...a, when: a.when?.filter((w) => states.value.includes(w)).length ? a.when.filter((w) => states.value.includes(w)) : null })) }
  : { ...copy(form), name: form.name.trim() })
const saving = ref(false)
async function save() {
  saving.value = true
  const result = await act(() => api.saveObject(item.value), `World Item “${form.name}” saved`)
  saving.value = false
  if (result) { data.value = result; selected.value = form.id }
}
async function remove() {
  if (!selected.value) return
  const ok = await confirm({ title: `Delete “${form.name}”?`, body: 'This removes the reusable definition. Set placements must be removed first.', confirm: 'Delete item', danger: true })
  if (ok && (await act(() => api.deleteObject(selected.value!), 'World Item deleted'))) { data.value = await api.objects(); fresh() }
}
const field = 'inset mt-1 block h-10 w-full rounded-md px-3 text-sm text-ink outline-none focus:border-blue'
const num = 'inset mt-1 block h-9 w-full rounded-md px-2 text-sm text-ink outline-none focus:border-blue num'
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading World Items" />
  <div v-else class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
    <section class="space-y-5">
      <div class="flex flex-wrap items-baseline gap-3"><h2 class="font-display text-2xl font-semibold">World Items</h2><span class="text-sm text-muted">{{ data?.objects.length ?? 0 }} reusable scene items</span><button class="btn btn-secondary ml-auto" @click="aiOpen = true"><Sparkles :size="16" /> Build with AI</button><button class="btn btn-secondary" @click="fresh('card')"><Plus :size="16" /> New drawn item</button><button class="btn btn-primary" @click="fresh()"><Plus :size="16" /> New built item</button></div>
      <p class="text-sm text-muted">Things that live in a scene, not in a hand. <strong>Built</strong> items are 3D pieces placed in a set (crates, barrels). <strong>Drawn</strong> items are ink cards that animate and can be placed, flown and switched between states in a story with <code>@item</code> (planets, ships).</p>
      <div v-if="!data?.objects.length" class="raised p-8 text-center text-sm text-muted">No World Items yet. Draw a planet or a ship, or build a barrel.</div>
      <div v-for="o in data?.objects" :key="o.id" class="raised flex items-center gap-4 p-4" :class="selected === o.id && 'ring-2 ring-blue'" @click="edit(o)">
        <div class="grid size-16 shrink-0 place-items-center rounded-md bg-well text-3xl" aria-hidden="true">{{ o.look === 'card' ? '✎' : o.category === 'vehicle' ? '🚚' : o.category === 'container' ? '🛢️' : '◼' }}</div>
        <div class="min-w-0"><h3 class="font-display text-lg font-semibold">{{ o.name }}</h3><p class="text-xs text-muted"><code>{{ o.id }}</code> · {{ o.look === 'card' ? `drawn ${o.draw ?? 'shapes'}, ${o.layer ?? 'mid'}` : 'built' }} · {{ o.category }}<template v-if="o.states?.length"> · states {{ o.states.join(', ') }}</template> · {{ o.capabilities.join(', ') || 'static' }}</p></div>
        <button class="btn btn-secondary ml-auto" @click.stop="edit(o)">Edit</button>
        <button type="button" class="btn btn-secondary" :aria-label="`Copy ${o.name} JSON`" title="Copy JSON" @click.stop="copyJson(o, o.name)"><Braces :size="16" aria-hidden="true" /> JSON</button>
      </div>
    </section>
    <form class="raised space-y-5 p-5" @submit.prevent="save">
      <div class="flex items-center justify-between"><h3 class="font-display text-xl font-semibold">{{ isNew ? `New ${isCard ? 'drawn' : 'built'} item` : form.name || form.id }}</h3><button v-if="!isNew" type="button" class="btn btn-secondary text-red-ink" @click="remove"><Trash2 :size="16" /> Delete</button></div>
      <div class="grid gap-3 sm:grid-cols-2"><label class="text-xs font-semibold text-muted">Name<input v-model="form.name" :class="field" maxlength="40" required /></label><label class="text-xs font-semibold text-muted">Id<input v-model="form.id" :readonly="!isNew" :class="field" pattern="[a-z0-9]+(-[a-z0-9]+)*" required /></label></div>
      <div class="grid gap-3 sm:grid-cols-2">
        <label class="text-xs font-semibold text-muted">Look<select :value="form.look ?? 'pieces'" :class="field" @change="setLook(($event.target as HTMLSelectElement).value as 'pieces' | 'card')"><option value="pieces">built (3D pieces)</option><option value="card">drawn (ink card)</option></select></label>
        <label class="text-xs font-semibold text-muted">Category<select v-model="form.category" :class="field"><option v-for="x in CATEGORIES" :key="x">{{ x }}</option></select></label>
      </div>
      <template v-if="isCard">
        <ItemPreview :item="item" :state="previewState" :label="`Preview of ${form.name || 'the item'}`" />
        <div class="grid gap-3 sm:grid-cols-3">
          <label class="text-xs font-semibold text-muted">Drawing<select v-model="form.draw" :class="field"><option v-for="x in DRAWINGS" :key="x">{{ x }}</option></select></label>
          <label class="text-xs font-semibold text-muted">Layer<select v-model="form.layer" :class="field"><option v-for="x in LAYERS" :key="x">{{ x }}</option></select></label>
          <label class="text-xs font-semibold text-muted">Height (units)<input v-model.number="form.size" type="number" step="any" min="0.05" max="60" :class="num" /></label>
        </div>
        <label class="block text-xs font-semibold text-muted">States <span class="font-normal">(comma-separated, the first is the default; e.g. flying, landed)</span><input v-model="statesText" :class="field" :aria-invalid="badStates.length > 0" /></label>
        <p v-if="badStates.length" class="text-xs text-red-ink" role="alert">Not usable as a state: {{ badStates.join(', ') }} (lowercase-with-dashes; remove and state are reserved for @item).</p>
        <div v-if="states.length" class="flex flex-wrap items-center gap-2 text-xs"><span class="font-semibold text-muted">Preview state</span><button v-for="s in states" :key="s" type="button" class="btn btn-secondary" :aria-pressed="(previewState ?? states[0]) === s" @click="previewState = s">{{ s }}</button></div>
        <fieldset><legend class="mb-2 font-display text-lg font-semibold">Animation</legend>
          <div v-for="(a, i) in form.anims ?? []" :key="i" class="inset mb-2 grid grid-cols-[1fr_1fr_1fr_auto] items-end gap-2 rounded-md p-3">
            <label class="text-xs font-semibold text-muted">Kind<select v-model="a.kind" :class="field"><option v-for="(_, k) in ANIMS" :key="k">{{ k }}</option></select></label>
            <label class="text-xs font-semibold text-muted">Amount <span class="font-normal">{{ ANIMS[a.kind].amp }}</span><input v-model.number="a.amp" type="number" step="any" min="0" :disabled="a.kind === 'flow'" :class="num" /></label>
            <label class="text-xs font-semibold text-muted">Speed (hz)<input v-model.number="a.hz" type="number" step="any" min="0.001" max="5" :disabled="!ANIMS[a.kind].hz" :class="num" /></label>
            <button type="button" class="btn btn-secondary" :aria-label="`Remove ${a.kind}`" @click="form.anims!.splice(i, 1)"><Trash2 :size="16" /></button>
            <label v-if="states.length > 1" class="col-span-4 text-xs font-semibold text-muted">Only in states <span class="font-normal">(empty: always)</span><select v-model="a.when" multiple :class="`${field} h-auto py-1`"><option v-for="s in states" :key="s" :value="s">{{ s }}</option></select></label>
          </div>
          <div class="flex flex-wrap gap-2"><button v-for="(_, k) in ANIMS" :key="k" type="button" class="btn btn-secondary" @click="addAnim(k)"><Plus :size="15" /> {{ k }}</button></div>
        </fieldset>
        <fieldset class="space-y-3"><legend class="mb-2 font-display text-lg font-semibold">Interactions</legend>
          <div class="grid grid-cols-3 gap-2 text-xs"><label v-for="x in CAPABILITIES" :key="x" class="flex items-center gap-2"><input v-model="form.capabilities" type="checkbox" :value="x" />{{ x }}</label></div>
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="text-xs font-semibold text-muted">Carry mode<select v-model="form.carry_mode" :class="field"><option v-for="x in CARRY_MODES" :key="x">{{ x }}</option></select></label>
            <label class="text-xs font-semibold text-muted">Held as prop <span class="font-normal">(pickup)</span><input v-model.trim="form.prop" :class="field" placeholder="a prop id" @change="form.prop ||= null" /></label>
          </div>
          <p class="text-xs text-muted">Points are world units from the item's base: x toward its front, y up.</p>
          <div v-for="a in ANCHORS" :key="a" class="grid grid-cols-[6rem_1fr_1fr_auto] items-end gap-2">
            <span class="pb-2 text-xs font-semibold text-muted">{{ a }}</span>
            <template v-if="form.anchors?.[a]"><input v-for="j in [0, 1]" :key="j" v-model.number="form.anchors[a]![j]" type="number" step="any" :aria-label="`${a} ${j ? 'y' : 'x'}`" :class="num" /><button type="button" class="btn btn-secondary" :aria-label="`Remove the ${a} point`" @click="delete form.anchors![a]"><Trash2 :size="16" /></button></template>
            <button v-else type="button" class="btn btn-secondary col-span-3" @click="(form.anchors ??= {})[a] = [0, (form.size ?? 1) / 2]"><Plus :size="15" /> {{ a }} point</button>
          </div>
          <div class="grid grid-cols-[6rem_1fr_1fr_auto] items-end gap-2" v-for="(s, i) in form.seats ?? []" :key="`seat${i}`">
            <span class="pb-2 text-xs font-semibold text-muted">seat {{ i + 1 }}</span>
            <input v-for="j in [0, 1]" :key="j" v-model.number="s[j]" type="number" step="any" :aria-label="`seat ${i + 1} ${j ? 'y' : 'x'}`" :class="num" />
            <button type="button" class="btn btn-secondary" :aria-label="`Remove seat ${i + 1}`" @click="form.seats!.splice(i, 1)"><Trash2 :size="16" /></button>
          </div>
          <div class="flex flex-wrap items-end gap-3">
            <button v-if="(form.seats?.length ?? 0) < 4" type="button" class="btn btn-secondary" @click="(form.seats ??= []).push([0, (form.size ?? 1) * 0.4])"><Plus :size="15" /> Seat (enter)</button>
            <label class="w-48 text-xs font-semibold text-muted">Rim height <span class="font-normal">(riders hidden below)</span><input :value="form.clip_y ?? ''" type="number" step="any" :class="num" @input="form.clip_y = ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value)" /></label>
          </div>
        </fieldset>
      </template>
      <template v-else>
        <div class="grid gap-3 sm:grid-cols-2"><label class="text-xs font-semibold text-muted">Carry mode<select v-model="form.carry_mode" :class="field"><option v-for="x in CARRY_MODES" :key="x">{{ x }}</option></select></label></div>
        <fieldset><legend class="mb-2 text-xs font-semibold text-muted">Capabilities</legend><div class="grid grid-cols-3 gap-2 text-xs"><label v-for="x in CAPABILITIES" :key="x" class="flex items-center gap-2"><input v-model="form.capabilities" type="checkbox" :value="x" />{{ x }}</label></div></fieldset>
        <fieldset><legend class="mb-2 font-display text-lg font-semibold">Geometry</legend><div v-for="(p, i) in form.pieces" :key="i" class="inset mb-2 space-y-2 rounded-md p-3"><div class="flex gap-2"><select v-model="p.shape" :class="field"><option v-for="(_, k) in PIECES" :key="k" :value="k">{{ PIECES[k].label }}</option></select><button type="button" class="btn btn-secondary" @click="form.pieces.splice(i, 1)"><Trash2 :size="16" /></button></div><div class="grid grid-cols-3 gap-2"><input v-for="(_, j) in ['x','y','z']" :key="j" v-model.number="p.at[j]" type="number" step="any" :class="num" /></div><div class="flex gap-2"><input v-for="(_, j) in PIECES[p.shape].size" :key="j" v-model.number="p.size[j]" type="number" step="any" min="0" :placeholder="PIECES[p.shape].size[j]" :class="num" /><input v-model="p.color" type="color" class="h-9 w-12" /></div></div><div class="flex flex-wrap gap-2"><button v-for="(_, k) in PIECES" :key="k" type="button" class="btn btn-secondary" @click="addPiece(k)"><Plus :size="15" /> {{ PIECES[k].label }}</button></div></fieldset>
      </template>
      <button class="btn btn-primary w-full" :disabled="!valid || saving">{{ saving ? 'Saving…' : isNew ? 'Create item' : 'Save item' }}</button>
    </form>
  </div>
  <AiGenerateModal :open="aiOpen" title="Generate a built World Item" description-hint="A wooden maple syrup barrel with metal hoops, large enough for two thieves to carry" :prompt-builder="aiPrompt" :parser="aiParse" :save="aiSave" @close="aiOpen = false" @done="aiOpen = false" />
</template>
