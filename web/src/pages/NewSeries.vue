<script setup lang="ts">
import { ArrowLeft, Download, FileJson, Plus, Trash2 } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useApi } from '../composables/useApi'
import { HANDS, propOptions, type Hand, type Prop } from '../lib/props'
import { allCreatures } from '../lib/creatures'
import { act, toast } from '../composables/feedback'

const router = useRouter()
const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
const PALETTE = ['#3a7bd5', '#d53a3a', '#2e9e5b', '#e0a020', '#8a4fd5', '#d5703a']

const title = ref('')
const slug = ref('')
const slugEdited = ref(false)
watch(title, (t) => { if (!slugEdited.value) slug.value = slugify(t) })

type Obj = Record<string, unknown>
type Eyes = 'dots' | 'half_closed'
// look: everything else an imported entry carries (top style, headwear, ...), sent back untouched
type Row = { name: string; id: string; idEdited: boolean; color: string; eyes: Eyes; hands: Record<Hand, string>; body: string; headless: boolean; look: Obj }
// built-in + custom props (library/props.json); an imported kind not in the list still shows, the server checks it
const { data: catalog } = useApi(() => api.props())
// bodies: stickman, or a creature (built in + library/creatures.json); headless only where it has a stump
const { data: creatureCatalog } = useApi(() => api.creatures())
const creatures = computed(() => allCreatures(creatureCatalog.value))
const hasStump = (body: string) => !!creatures.value.find((c) => c.id === body)?.parts.stump
const options = (r: Row) => {
  const o = propOptions(catalog.value)
  return [...o, ...HANDS.map((h) => r.hands[h]).filter((k) => k && !o.some((x) => x.id === k)).map((k) => ({ id: k, name: `${k} (unknown)` }))]
}
const cast = reactive<Row[]>([])
const nextColor = () => PALETTE[cast.length % PALETTE.length]
const addCast = () => cast.push({ name: '', id: '', idEdited: false, color: nextColor(), eyes: 'dots', hands: { left: '', right: '' }, body: 'stickman', headless: false, look: {} })
const propsOf = (r: Row): Prop[] => HANDS.filter((h) => r.hands[h]).map((h) => ({ kind: r.hands[h], hand: h }))
addCast()
const onName = (r: Row) => { if (!r.idEdited) r.id = slugify(r.name) }

/** "tank #31 · bowler · trousers · cheeky": what an import adds beyond the row's fields */
function lookSummary(l: Obj): string {
  const top = (l.top ?? {}) as Obj
  const kind = (x: unknown) => (x as Obj | undefined)?.kind
  return [
    [top.style !== 'plain' && top.style, top.number && `#${top.number}`].filter(Boolean).join(' '),
    kind(l.headwear) !== 'none' && kind(l.headwear),
    kind(l.legwear) !== 'none' && kind(l.legwear),
    l.default_expression !== 'neutral' && l.default_expression,
  ].filter(Boolean).join(' · ').replaceAll('_', ' ')
}

// ---- JSON import: an array of cast entries, {"cast": [...]}, or a whole series.json ----
const importOpen = ref(false)
const customizeCast = ref(false)
const importText = ref('')
const importError = ref('')
async function loadFile(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = ''
  if (f) importText.value = await f.text()
}
async function loadExample() {
  importText.value = await fetch('/cast-reference.json').then((r) => r.text())
}
function runImport() {
  importError.value = ''
  let entries: unknown
  try {
    const j = JSON.parse(importText.value)
    entries = Array.isArray(j) ? j : j?.cast
  } catch (e) {
    importError.value = `Not valid JSON: ${(e as Error).message}`
    return
  }
  if (!Array.isArray(entries) || !entries.length) {
    importError.value = 'Expected a non-empty array of cast entries, or an object with a "cast" array.'
    return
  }
  const bad = entries.findIndex((x) => typeof x?.id !== 'string' || typeof x?.name !== 'string')
  if (bad >= 0) {
    importError.value = `Entry #${bad + 1} needs a string "id" and "name".`
    return
  }
  cast.splice(0, cast.length, ...cast.filter((r) => r.name.trim() || r.id.trim())) // drop empty rows
  for (const x of entries as Obj[]) {
    const { id, name, color, eyes, props, body, headless, approved_at: _approved, ...look } = x
    const top = (look.top ?? {}) as Obj
    const hands: Row['hands'] = { left: '', right: '' }
    for (const p of (props ?? []) as Partial<Prop>[]) if (p.kind) hands[p.hand ?? 'right'] = p.kind
    const row: Row = {
      id: id as string, name: name as string, idEdited: true, eyes: (eyes as Eyes | undefined) ?? 'dots', hands,
      body: (body as string | undefined) ?? 'stickman', headless: headless === true,
      color: ((color ?? top.color) as string | undefined)?.toLowerCase() ?? nextColor(), look,
    }
    const at = cast.findIndex((r) => r.id === row.id) // same id: the import replaces that row
    if (at >= 0) cast.splice(at, 1, row)
    else cast.push(row)
  }
  toast(`Imported ${entries.length} cast ${entries.length === 1 ? 'member' : 'members'}`, 'ok')
  importOpen.value = false
  importText.value = ''
}

const saving = ref(false)
const filled = computed(() => cast.filter((r) => r.name.trim() || r.id.trim()))
const ready = computed(() => title.value.trim() && slug.value && filled.value.every((r) => r.name.trim() && r.id))

async function create() {
  saving.value = true
  const body = {
    slug: slug.value, title: title.value.trim(),
    cast: filled.value.map((r) => ({ ...r.look, id: r.id, name: r.name.trim(), eyes: r.eyes, props: propsOf(r), top: { ...(r.look.top as Obj), color: r.color },
      body: r.body, headless: r.body !== 'stickman' && r.headless && hasStump(r.body) })),
  }
  const s = await act(() => api.createSeries(body), `Series “${body.title}” created`)
  saving.value = false
  if (s) router.push(`/series/${s.slug}/new-part`)
}
const field = 'inset mt-1 block h-10 w-full rounded-md px-4 text-sm text-ink outline-none focus:border-blue'
</script>

<template>
  <div class="max-w-3xl space-y-6">
    <RouterLink to="/series" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> All series</RouterLink>

    <form class="raised space-y-6 p-6" @submit.prevent="create">
      <h2 class="font-display text-3xl font-semibold">New series</h2>

      <div class="grid gap-4 sm:grid-cols-2">
        <label class="block text-xs font-semibold text-muted">Title
          <input v-model="title" required placeholder="Marathon 1904" :class="field" />
        </label>
        <label class="block text-xs font-semibold text-muted">Slug (folder name)
          <input v-model="slug" required pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="marathon-1904" :class="field"
            @input="slugEdited = true" />
        </label>
      </div>

      <fieldset id="cast-customize" class="space-y-3">
        <legend class="font-display text-lg font-semibold">Cast</legend>
        <div class="flex flex-wrap items-start gap-3">
          <p class="flex-1 text-xs text-muted">Add names now and customize outfits later. Cast is optional; you can add characters after creating the series.</p>
          <button type="button" class="btn btn-secondary" :aria-expanded="customizeCast" aria-controls="cast-customize" @click="customizeCast = !customizeCast">
            {{ customizeCast ? 'Hide cast details' : 'Customize cast' }}
          </button>
          <button type="button" class="btn btn-secondary" :aria-expanded="importOpen" aria-controls="cast-import" @click="importOpen = !importOpen">
            <FileJson :size="16" aria-hidden="true" /> Advanced: import JSON
          </button>
        </div>

        <div v-if="importOpen" id="cast-import" class="inset space-y-3 p-4">
          <div class="flex flex-wrap items-center gap-2">
            <label class="btn btn-secondary cursor-pointer">Choose file
              <input type="file" accept=".json,application/json" class="sr-only" @change="loadFile" />
            </label>
            <button type="button" class="btn btn-secondary" @click="loadExample">Paste example</button>
            <a href="/cast-reference.json" download class="btn btn-secondary ml-auto"><Download :size="16" aria-hidden="true" /> Reference JSON</a>
          </div>
          <label class="sr-only" for="cast-json">Cast JSON</label>
          <textarea id="cast-json" v-model="importText" rows="8" spellcheck="false"
            placeholder="[{ &quot;id&quot;: &quot;fred&quot;, &quot;name&quot;: &quot;Fred Lorz&quot;, &quot;color&quot;: &quot;#e53935&quot; }]"
            class="paper block w-full resize-y rounded-md p-4 font-mono text-xs leading-6 text-ink outline-none focus:border-blue" />
          <p v-if="importError" class="text-sm text-red-ink" role="alert">{{ importError }}</p>
          <p class="text-xs text-muted">An array of entries, <code>{"cast": [...]}</code>, or a whole series.json. An entry with the same id as a row below replaces it.
            The server checks every field when you create the series.</p>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn btn-secondary" @click="importOpen = false">Cancel</button>
            <button type="button" class="btn btn-primary" :disabled="!importText.trim()" @click="runImport">Import</button>
          </div>
        </div>
        <div v-for="(r, i) in cast" :key="i" class="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto_auto_auto]">
          <label class="block text-xs font-semibold text-muted">Name
            <input v-model="r.name" placeholder="Fred Lorz" :class="field" @input="onName(r)" />
          </label>
          <label v-if="customizeCast" class="block text-xs font-semibold text-muted">Id (used in @cast)
            <input v-model="r.id" pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="fred" :class="field" @input="r.idEdited = true" />
          </label>
          <label v-if="customizeCast" class="block text-xs font-semibold text-muted">Outfit
            <span class="inset mt-1 flex h-10 cursor-pointer items-center gap-2 rounded-md pr-4 pl-1.5 focus-within:outline-2 focus-within:outline-ink">
              <!-- native picker, drawn as a round raised swatch -->
              <input v-model="r.color" type="color" :aria-label="`Outfit colour for ${r.name || `character ${i + 1}`}`"
                class="size-8 shrink-0 cursor-pointer appearance-none rounded-full border-0 bg-transparent p-0 ring-1 ring-rule-strong outline-none
                  [&::-moz-color-swatch]:rounded-full [&::-moz-color-swatch]:border-2 [&::-moz-color-swatch]:border-white
                  [&::-webkit-color-swatch]:rounded-full [&::-webkit-color-swatch]:border-2 [&::-webkit-color-swatch]:border-white [&::-webkit-color-swatch-wrapper]:p-0" />
              <span class="num font-mono text-sm text-ink uppercase">{{ r.color }}</span>
            </span>
          </label>
          <label v-if="customizeCast" class="block text-xs font-semibold text-muted">Eyes
            <select v-model="r.eyes" :class="field">
              <option value="dots">dots</option>
              <option value="half_closed">half closed</option>
            </select>
          </label>
          <button type="button" class="btn btn-secondary size-11 justify-center p-0" :aria-label="`Remove cast row ${i + 1}`" @click="cast.splice(i, 1)">
            <Trash2 :size="16" aria-hidden="true" />
          </button>
          <div v-if="customizeCast" class="flex flex-wrap gap-3 sm:col-span-5">
            <label class="block min-w-40 flex-1 text-xs font-semibold text-muted">Body
              <select v-model="r.body" :class="field">
                <option value="stickman">stickman</option>
                <option v-for="c in creatures" :key="c.id" :value="c.id">{{ c.name }} ({{ c.rig }})</option>
                <option v-if="r.body !== 'stickman' && !creatures.some((c) => c.id === r.body)" :value="r.body">{{ r.body }} (unknown)</option>
              </select>
            </label>
            <label v-if="r.body !== 'stickman' && hasStump(r.body)" class="flex h-11 items-center gap-2 self-end text-sm">
              <input v-model="r.headless" type="checkbox" class="size-4" /> Headless
            </label>
            <label v-for="h in HANDS" :key="h" class="block min-w-40 flex-1 text-xs font-semibold text-muted">{{ h === 'left' ? 'Left hand' : 'Right hand' }}
              <select v-model="r.hands[h]" :class="field">
                <option value="">nothing</option>
                <option v-for="p in options(r)" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
            </label>
          </div>
          <p v-if="customizeCast && lookSummary(r.look)" class="-mt-1 pl-4 text-xs text-muted sm:col-span-5">Imported look: {{ lookSummary(r.look) }}</p>
        </div>
        <button type="button" class="btn btn-secondary" @click="addCast"><Plus :size="16" aria-hidden="true" /> Add character</button>
      </fieldset>

      <div class="flex justify-end">
        <button class="btn btn-primary" :disabled="!ready || saving">{{ saving ? 'Creating…' : 'Create series' }}</button>
      </div>
    </form>
  </div>
</template>
