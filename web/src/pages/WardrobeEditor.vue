<script setup lang="ts">
import { ArrowDown, ArrowLeft, ArrowUp, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import AiBridge from '../components/AiBridge.vue'
import ErrorCard from '../components/ErrorCard.vue'
import WardrobePreview from '../components/WardrobePreview.vue'
import { act, confirm, toast } from '../composables/feedback'
import { useApi } from '../composables/useApi'
import { allCreatures } from '../lib/creatures'
import { ANCHORS, PREVIEW_POSES, SHAPES, SLOT_LABEL, SLOTS, buildWardrobePrompt, importWardrobe, wardrobeOptions,
  type Anchor, type Slot, type WardrobeItem, type WardrobeLayer } from '../lib/wardrobe'
import { EXPRESSIONS } from '../lib/expressions'

// Create (/wardrobe/new) or edit one custom wardrobe item: ink layers anchored to body points, previewed live by the
// engine's own drawing code on the default human and on a chosen humanoid creature, in any pose. The server (schema
// WardrobeItem) has the final say on every field.
const props = defineProps<{ id: string }>()
const router = useRouter()
const isNew = computed(() => props.id === 'new')
const { data, error, loading, reload } = useApi(async () => {
  const [catalog, creatures] = await Promise.all([api.wardrobe(), api.creatures()])
  return { catalog, creatures }
})

type Shape = WardrobeLayer['shape']
type Fill = 'none' | 'color' | 'hex'
type Row = { shape: Shape; anchor: Anchor; pts: string; r: number; ry: number; rot: number; fill: Fill; hex: string; width: number; behind: boolean; when: string }
const HINT: Record<Shape, string> = { rect: 'two corners', circle: 'the centre', ellipse: 'the centre', line: '2 or more points', poly: '3 or more points, closed' }
const START: Record<Shape, string> = { rect: '-40,-20 40,20', circle: '0,0', ellipse: '0,0', line: '-40,0 40,0', poly: '-40,0 0,-40 40,0' }
const toRow = (L: WardrobeLayer): Row => ({
  shape: L.shape, anchor: L.anchor, pts: L.pts.map(([x, y]) => `${x},${y}`).join(' '), r: L.r ?? 20, ry: L.ry ?? 12, rot: L.rot ?? 0,
  fill: L.fill === '$color' ? 'color' : L.fill ? 'hex' : 'none', hex: L.fill && L.fill !== '$color' ? L.fill : '#ffffff',
  width: L.width ?? 8, behind: !!L.behind, when: (L.when ?? []).join(' '),
})
const STARTER: Row[] = [toRow({ shape: 'poly', anchor: 'head', pts: [[-150, -40], [-120, -120], [0, -165], [120, -120], [150, -40], [90, -95], [-90, -95]],
  fill: '$color', width: 8, r: null, ry: null, rot: 0, behind: false, when: null })]

const form = reactive({ id: '', name: '', idEdited: false, slot: 'hair' as Slot, colorable: true, default_color: '#6b4f3a', rows: [] as Row[] })
const load = (w: WardrobeItem | null) => Object.assign(form, w
  ? { id: w.id, name: w.name, idEdited: true, slot: w.slot, colorable: w.colorable, default_color: w.default_color, rows: w.layers.map(toRow) }
  : { id: '', name: '', idEdited: false, slot: 'hair', colorable: true, default_color: '#6b4f3a', rows: STARTER.map((r) => ({ ...r })) })
watch(data, (d) => {
  if (!d) return
  const w = d.catalog.custom.find((x) => x.id === props.id)
  if (!isNew.value && !w) return
  load(w ?? null)
}, { immediate: true })
const missing = computed(() => !isNew.value && data.value && !data.value.catalog.custom.some((x) => x.id === props.id))
const toId = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
watch(() => form.name, (n) => { if (isNew.value && !form.idEdited) form.id = toId(n) })

/** "x,y x,y" -> a layer, or an error for the row */
function parse(r: Row): { layer?: WardrobeLayer; err?: string } {
  const pts = r.pts.trim().split(/\s+/).filter(Boolean).map((t) => t.split(',').map(Number))
  if (!pts.length || pts.some((p) => p.length !== 2 || p.some((v) => !Number.isFinite(v)))) return { err: 'points as x,y x,y …' }
  const [lo, hi] = { rect: [2, 2], circle: [1, 1], ellipse: [1, 1], line: [2, 40], poly: [3, 40] }[r.shape]
  if (pts.length < lo || pts.length > hi) return { err: `${r.shape}: ${HINT[r.shape]}` }
  if (pts.some((p) => p.some((v) => Math.abs(v) > 600))) return { err: 'keep points within 600 of the anchor' }
  const when = r.when.trim().split(/[\s,]+/).filter(Boolean)
  if (when.some((w) => !(EXPRESSIONS as readonly string[]).includes(w))) return { err: `only with: ${EXPRESSIONS.join(', ')}` }
  const round = r.shape === 'circle' || r.shape === 'ellipse'
  return { layer: { shape: r.shape, anchor: r.anchor, pts: pts as [number, number][], r: round ? r.r : null, ry: r.shape === 'ellipse' ? r.ry : null,
    rot: r.shape === 'ellipse' ? r.rot : 0, fill: r.fill === 'color' ? '$color' : r.fill === 'hex' ? r.hex : null, width: r.width, behind: r.behind,
    when: when.length ? (when as WardrobeLayer['when']) : null } }
}
const parsed = computed(() => form.rows.map(parse))
const draft = computed<WardrobeItem>(() => ({ id: form.id || 'draft', name: form.name, slot: form.slot, colorable: form.colorable,
  default_color: form.default_color, layers: parsed.value.flatMap((p) => p.layer ?? []) }))
const previewList = computed(() => [...(data.value?.catalog.custom ?? []).filter((w) => w.id !== draft.value.id), draft.value])
const taken = computed(() => wardrobeOptions(data.value?.catalog).some((o) => o.id === form.id && (o.builtin || isNew.value)))
const valid = computed(() => form.name.trim() && /^[a-z0-9]+([_-][a-z0-9]+)*$/.test(form.id) && !taken.value && parsed.value.every((p) => p.layer))

const addRow = (shape: Shape) => form.rows.push({ shape, anchor: form.rows.at(-1)?.anchor ?? 'head', pts: START[shape], r: 30, ry: 15, rot: 0,
  fill: 'color', hex: '#ffffff', width: 8, behind: false, when: '' })
const move = (i: number, d: number) => form.rows.splice(i + d, 0, ...form.rows.splice(i, 1))

// preview: the default human and a chosen humanoid creature, any pose, expression, facing and colour
const humanoids = computed(() => allCreatures(data.value?.creatures).filter((c) => c.rig === 'humanoid' && c.id !== 'human'))
const creatureId = ref('')
watch(humanoids, (h) => { if (!creatureId.value && h.length) creatureId.value = h[0].id }, { immediate: true })
const creatureBuild = computed(() => humanoids.value.find((c) => c.id === creatureId.value)?.build ?? null)
const view = reactive({ pose: 'idle', expression: 'neutral', facing: 'camera' as 'camera' | 'left' | 'right', color: '' })
const wornColor = computed(() => (form.colorable && view.color ? view.color : form.default_color))

// Build with AI: the copy/paste bridge
const aiOpen = ref(false)
const details = ref('')
const reply = ref('')
const replyError = ref('')
const prompt = computed(() => buildWardrobePrompt(form.name, form.slot, wardrobeOptions(data.value?.catalog).map((o) => o.id)
  .filter((i) => isNew.value || i !== form.id), details.value, form.id))
function loadReply() {
  const r = importWardrobe(reply.value, form.slot)
  replyError.value = r.error ?? ''
  if (!r.item) return
  const keepId = !isNew.value ? form.id : r.item.id
  load({ ...r.item, id: keepId })
  form.idEdited = true
  toast('Loaded: check the preview, then save', 'ok')
}

const saving = ref(false)
async function save() {
  saving.value = true
  const body = { ...draft.value, name: form.name.trim() }
  const c = await act(() => api.saveWardrobeItem(body), `“${body.name}” saved`)
  saving.value = false
  if (!c) return
  if (c.cleared.length) toast(`Drawing changed: approval cleared for ${c.cleared.join(', ')}. Re-run their cast sheets.`, 'info')
  data.value = { ...data.value!, catalog: c }
  if (isNew.value) router.replace(`/wardrobe/${body.id}`)
}
async function remove() {
  const ok = await confirm({ title: `Delete “${form.name}”?`, body: 'Only possible while no cast member wears it.', confirm: 'Delete item', danger: true })
  if (ok && (await act(() => api.deleteWardrobeItem(props.id), 'Wardrobe item deleted'))) router.push('/wardrobe')
}
const field = 'inset mt-1 block h-10 w-full rounded-md px-3 text-sm text-ink outline-none focus:border-blue'
</script>

<template>
  <div class="max-w-6xl space-y-6">
    <RouterLink to="/wardrobe" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> Wardrobe</RouterLink>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading wardrobe item" />
    <ErrorCard v-else-if="missing" :message="`No custom wardrobe item “${id}”.`" @retry="reload" />
    <form v-else class="raised grid gap-6 p-6 lg:grid-cols-[1fr_340px]" @submit.prevent="save">
      <div class="min-w-0 space-y-5">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="font-display text-3xl font-semibold">{{ isNew ? 'New wardrobe item' : form.name || id }}</h2>
          <button type="button" class="btn btn-secondary ml-auto" :aria-expanded="aiOpen" @click="aiOpen = !aiOpen">
            <Sparkles :size="16" aria-hidden="true" /> Build with AI
          </button>
        </div>
        <section v-if="aiOpen" class="inset space-y-3 rounded-md p-4" aria-label="Build with AI">
          <label class="block text-xs font-semibold text-muted">What it should look like (optional)
            <input v-model="details" placeholder="a tall feathered helmet with a red plume" :class="field" />
          </label>
          <AiBridge v-model="reply" :prompt="prompt" :error="replyError" load-label="Load into the editor" @load="loadReply" />
        </section>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block text-xs font-semibold text-muted">Name
            <input v-model="form.name" required maxlength="40" placeholder="Feathered helmet" :class="field" />
          </label>
          <label class="block text-xs font-semibold text-muted">Id (used in cast slots)
            <input v-model="form.id" required :readonly="!isNew" pattern="[a-z0-9]+([_\-][a-z0-9]+)*" placeholder="feathered_helmet"
              :class="[field, !isNew && 'opacity-70']" :aria-invalid="!!taken" @input="form.idEdited = true" />
            <span v-if="taken" class="mt-1 block text-red-ink" role="alert">“{{ form.id }}” is already a wardrobe item</span>
          </label>
          <label class="block text-xs font-semibold text-muted">Slot
            <select v-model="form.slot" :class="field"><option v-for="s in SLOTS" :key="s" :value="s">{{ SLOT_LABEL[s] }}</option></select>
          </label>
          <div class="flex items-end gap-4">
            <label class="block text-xs font-semibold text-muted">Default colour
              <input v-model="form.default_color" type="color" class="mt-1 block h-10 w-16 cursor-pointer rounded-md" />
            </label>
            <label class="flex h-10 items-center gap-2 text-sm"><input v-model="form.colorable" type="checkbox" class="size-4" /> Cast can recolour it</label>
          </div>
        </div>

        <fieldset class="space-y-3">
          <legend class="font-display text-lg font-semibold">Layers</legend>
          <p class="text-xs text-muted">Canvas px around the anchor: x across (outward on paired anchors, drawn on both sides),
            y down (along the limb on arms and legs). The head has radius 150. “Colour” fills take the worn colour. Later layers draw on top;
            “behind” ones go under the head and body.</p>
          <div v-for="(r, i) in form.rows" :key="i" class="inset space-y-2 rounded-md p-3">
            <div class="grid items-end gap-2 sm:grid-cols-[7rem_9rem_1fr_auto]">
              <label class="block text-xs font-semibold text-muted">Shape
                <select v-model="r.shape" :class="field"><option v-for="s in SHAPES" :key="s" :value="s">{{ s }}</option></select>
              </label>
              <label class="block text-xs font-semibold text-muted">Anchor
                <select v-model="r.anchor" :class="field" :title="ANCHORS[r.anchor]"><option v-for="(d, a) in ANCHORS" :key="a" :value="a">{{ a }}</option></select>
              </label>
              <label class="block text-xs font-semibold text-muted">Points ({{ HINT[r.shape] }})
                <input v-model="r.pts" spellcheck="false" :class="[field, 'font-mono']" :aria-invalid="!!parsed[i].err" />
              </label>
              <div class="flex gap-1">
                <button type="button" class="btn btn-secondary size-11 justify-center p-0" :disabled="i === 0" :aria-label="`Move layer ${i + 1} up (drawn earlier)`" @click="move(i, -1)"><ArrowUp :size="16" aria-hidden="true" /></button>
                <button type="button" class="btn btn-secondary size-11 justify-center p-0" :disabled="i === form.rows.length - 1" :aria-label="`Move layer ${i + 1} down (drawn later)`" @click="move(i, 1)"><ArrowDown :size="16" aria-hidden="true" /></button>
                <button type="button" class="btn btn-secondary size-11 justify-center p-0" :aria-label="`Remove layer ${i + 1}`" @click="form.rows.splice(i, 1)"><Trash2 :size="16" aria-hidden="true" /></button>
              </div>
            </div>
            <p class="text-xs text-muted">{{ ANCHORS[r.anchor] }}</p>
            <div class="flex flex-wrap items-end gap-3">
              <label v-if="r.shape === 'circle' || r.shape === 'ellipse'" class="block w-24 text-xs font-semibold text-muted">{{ r.shape === 'ellipse' ? 'Radius x' : 'Radius' }}
                <input v-model.number="r.r" type="number" min="1" max="400" :class="field" />
              </label>
              <template v-if="r.shape === 'ellipse'">
                <label class="block w-24 text-xs font-semibold text-muted">Radius y<input v-model.number="r.ry" type="number" min="1" max="400" :class="field" /></label>
                <label class="block w-24 text-xs font-semibold text-muted">Turn °<input v-model.number="r.rot" type="number" min="-180" max="180" :class="field" /></label>
              </template>
              <label class="block w-24 text-xs font-semibold text-muted">{{ r.shape === 'line' ? 'Line width' : 'Outline' }}
                <input v-model.number="r.width" type="number" min="0" max="40" :class="field" />
              </label>
              <label class="block w-36 text-xs font-semibold text-muted">{{ r.shape === 'line' ? 'Colour' : 'Fill' }}
                <select v-model="r.fill" :class="field">
                  <option value="color">worn colour</option><option value="hex">fixed colour</option><option value="none">{{ r.shape === 'line' ? 'ink' : 'none' }}</option>
                </select>
              </label>
              <input v-if="r.fill === 'hex'" v-model="r.hex" type="color" :aria-label="`Fixed colour of layer ${i + 1}`" class="h-11 w-14 cursor-pointer rounded-md" />
              <label class="flex h-11 items-center gap-2 text-sm"><input v-model="r.behind" type="checkbox" class="size-4" /> Behind</label>
              <label class="block min-w-40 flex-1 text-xs font-semibold text-muted">Only with expressions
                <input v-model="r.when" placeholder="always (or: happy cheeky)" spellcheck="false" :class="field" />
              </label>
            </div>
            <p v-if="parsed[i].err" class="text-xs text-red-ink" role="alert">{{ parsed[i].err }}</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button v-for="s in SHAPES" :key="s" type="button" class="btn btn-secondary" @click="addRow(s)"><Plus :size="16" aria-hidden="true" /> {{ s }}</button>
          </div>
        </fieldset>

        <div class="flex flex-wrap justify-end gap-2">
          <button v-if="!isNew" type="button" class="btn btn-secondary mr-auto text-red-ink" @click="remove"><Trash2 :size="16" aria-hidden="true" /> Delete</button>
          <button class="btn btn-primary" :disabled="!valid || saving">{{ saving ? 'Saving…' : isNew ? 'Create item' : 'Save item' }}</button>
        </div>
      </div>

      <aside class="space-y-3 lg:sticky lg:top-0 lg:self-start">
        <div class="grid grid-cols-2 gap-2">
          <figure class="space-y-1">
            <WardrobePreview :id="draft.id" :slot="form.slot" :custom="previewList" :color="wornColor" :pose="view.pose" :expression="view.expression"
              :facing="view.facing" :label="`Preview: human wearing ${form.name || 'the item'}`" class="h-72" />
            <figcaption class="text-center text-xs text-muted">human</figcaption>
          </figure>
          <figure class="space-y-1">
            <WardrobePreview :id="draft.id" :slot="form.slot" :custom="previewList" :color="wornColor" :pose="view.pose" :expression="view.expression"
              :facing="view.facing" :build="creatureBuild" :label="`Preview: ${creatureId || 'creature'} wearing ${form.name || 'the item'}`" class="h-72" />
            <figcaption>
              <label class="sr-only" for="wd-creature">Creature</label>
              <select id="wd-creature" v-model="creatureId" class="inset block h-9 w-full rounded-md px-2 text-xs" :disabled="!humanoids.length">
                <option v-if="!humanoids.length" value="">no humanoid creatures yet</option>
                <option v-for="c in humanoids" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </figcaption>
          </figure>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <label class="block text-xs font-semibold text-muted">Pose
            <select v-model="view.pose" :class="field"><option v-for="(_, k) in PREVIEW_POSES" :key="k" :value="k">{{ k }}</option></select>
          </label>
          <label class="block text-xs font-semibold text-muted">Expression
            <select v-model="view.expression" :class="field"><option v-for="x in EXPRESSIONS" :key="x" :value="x">{{ x }}</option></select>
          </label>
          <label class="block text-xs font-semibold text-muted">Facing
            <select v-model="view.facing" :class="field"><option value="camera">camera</option><option value="right">right</option><option value="left">left</option></select>
          </label>
          <label class="block text-xs font-semibold text-muted">Cast colour
            <span class="mt-1 flex items-center gap-2">
              <input :value="wornColor" type="color" :disabled="!form.colorable" class="h-10 w-14 cursor-pointer rounded-md"
                @input="view.color = ($event.target as HTMLInputElement).value" />
              <button v-if="view.color" type="button" class="btn btn-secondary" @click="view.color = ''">default</button>
            </span>
          </label>
        </div>
        <p class="text-center text-xs text-muted">Drawn by the render engine: what you see is what renders.</p>
      </aside>
    </form>
  </div>
</template>
