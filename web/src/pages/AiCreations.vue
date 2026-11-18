<script setup lang="ts">
import { Sparkles } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import AiBridge from '../components/AiBridge.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { useAutoAi } from '../composables/autoAi'
import { toast } from '../composables/feedback'
import { useApi } from '../composables/useApi'
import { buildCreationPrompt, chosen, isKind, needsSeries, parseReply, reviewItems, TYPE_LABEL, TYPES, type Brief, type Item, type Kind, type Library } from '../lib/aiCreations'
import { DRAWN_RIGS, RIG_NOTES, type CustomCreature, type Rig } from '../lib/creatures'
import type { CustomProp } from '../lib/props'
import type { CustomSet } from '../lib/sets'

// One screen to create anything with AI: pick a type, describe it, get a reply (configured provider or any chat AI
// via copy/paste), review what it creates, import. Existing library items are never overwritten.
const route = useRoute()
const router = useRouter()
const { data, error, loading, reload } = useApi(() => Promise.all([api.props(), api.sets(), api.creatures(), api.actions(), api.series()]))
const lib = computed<Library | null>(() => !data.value ? null : { props: data.value[0], sets: data.value[1], creatures: data.value[2], actions: data.value[3], series: data.value[4].map((s) => s.slug) })

const q = (k: string) => (typeof route.query[k] === 'string' ? (route.query[k] as string) : '')
const kind = computed<Kind>(() => (isKind(route.query.type) ? route.query.type : 'prop'))
const brief = reactive<Brief & { rig: Rig; parts: number; series: string }>({ description: '', rig: 'quadruped', parts: 3, series: '' })
const mode = ref<'generate' | 'bridge'>('bridge')
const { auto, busy, generate, label, provider } = useAutoAi()
watch(auto, (a) => a && (mode.value = 'generate'), { immediate: true })

const prompt = ref('')
const reply = ref('')
const replyError = ref('')
const items = ref<Item[]>([])
const created = ref<Recent[]>([])
const importing = ref(false)
const importError = ref('')

// a new type (picker, or an editor's "Build with AI" link) starts over, pre-filled from the link
watch(() => [route.query.type, route.query.name, route.query.id], () => {
  Object.assign(brief, { name: q('name'), id: q('id'), description: q('name') })
  if (q('rig')) brief.rig = q('rig') as Rig
  prompt.value = reply.value = replyError.value = importError.value = ''
  items.value = []
  created.value = []
}, { immediate: true })
const pick = (k: Kind) => router.replace({ query: { type: k } })

// cast goes into an existing series: its cast ids are taken
const targetCast = ref<string[]>([])
watch(() => brief.series, async (s) => {
  targetCast.value = s ? (await api.seriesDetail(s).catch(() => null))?.series.cast.map((c) => c.id) ?? [] : []
})
const ready = computed(() => !!brief.description.trim() && !!lib.value && (kind.value !== 'cast' || !!brief.series))

let guide = ''
async function makePrompt() {
  if (!lib.value) return ''
  if ((kind.value === 'cast' || kind.value === 'series') && !guide) guide = (await import('../../../docs/STORY_GUIDE.md?raw')).default
  prompt.value = buildCreationPrompt(kind.value, { ...brief, cast: targetCast.value }, lib.value, guide)
  return prompt.value
}
function loadReply() {
  const { plan, error: err } = parseReply(kind.value, reply.value)
  replyError.value = err ?? ''
  items.value = plan && lib.value ? reviewItems(kind.value, plan, lib.value, targetCast.value) : []
  if (plan) toast('Ready to review: uncheck anything you don\'t want', 'ok')
}
async function generateReply() {
  const text = await generate(await makePrompt())
  if (text === undefined) return
  reply.value = text
  loadReply()
}

// ---- review ----
const KIND_LABEL: Record<Item['kind'], string> = { prop: 'Prop', set: 'Set', creature: 'Creature', action: 'Action', cast: 'Cast', series: 'Series', part: 'Part' }
const seriesOff = computed(() => items.value.some((i) => i.kind === 'series' && !i.checked))
const toImport = computed(() => chosen(items.value))

// ---- import: the editors' own save calls, in dependency order ----
type Recent = { label: string; href: string; at: string }
const KEY = 'sf.ai-creations.recent'
const recent = ref<Recent[]>(read())
function read(): Recent[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '[]')
  } catch {
    return []
  }
}
function remember(xs: Recent[]) {
  recent.value = [...xs, ...recent.value].slice(0, 10)
  try {
    localStorage.setItem(KEY, JSON.stringify(recent.value))
  } catch { /* private window: the list just isn't kept */ }
}
const SAVE = {
  prop: (d: unknown) => api.saveProp(d as CustomProp),
  set: (d: unknown) => api.saveSet(d as CustomSet),
  creature: (d: unknown) => api.saveCreature(d as CustomCreature),
  action: (d: unknown) => api.saveAction(d as Parameters<typeof api.saveAction>[0]),
}
async function runImport() {
  importing.value = true
  importError.value = ''
  const done: Recent[] = []
  const at = new Date().toISOString()
  const mark = (i: Item, label: string, href: string) => {
    Object.assign(i, { status: 'existing', checked: false })
    done.push({ label, href, at })
  }
  try {
    const go = toImport.value
    for (const i of go) {
      if (i.kind in SAVE) {
        await SAVE[i.kind as keyof typeof SAVE](i.data)
        mark(i, `${KIND_LABEL[i.kind]} “${i.name}”`, `/${i.kind}s/${i.id}`)
      }
    }
    const cast = go.filter((i) => i.kind === 'cast')
    const series = go.find((i) => i.kind === 'series')
    if (kind.value === 'cast' && cast.length) {
      await api.addCast(brief.series, cast.map((i) => i.data as Record<string, unknown>))
      cast.forEach((i) => mark(i, `Cast “${i.name}” in ${brief.series}`, `/series/${brief.series}`))
    }
    if (series) {
      const s = series.data as { slug: string; title: string }
      await api.createSeries({ slug: s.slug, title: s.title, cast: cast.map((i) => i.data as Record<string, unknown>) })
      cast.forEach((i) => Object.assign(i, { status: 'existing', checked: false }))
      mark(series, `Series “${s.title}”`, `/series/${s.slug}`)
      for (const p of go.filter((i) => i.kind === 'part')) {
        const part = (await api.createPart(s.slug, p.data as { title: string; story: string })).part
        mark(p, `${s.title}: ${part.title ?? p.name}`, `/series/${s.slug}/${part.id}`)
      }
    }
    toast(`Created ${done.length} item${done.length === 1 ? '' : 's'}`, 'ok')
  } catch (e) {
    importError.value = `${e instanceof Error ? e.message : String(e)}${done.length ? ` (${done.length} created before this; Import again continues with the rest)` : ''}`
  } finally {
    created.value = [...created.value, ...done]
    if (done.length) remember(done)
    importing.value = false
    reload()
  }
}
const field = 'inset mt-1 block w-full rounded-md px-4 py-2 text-sm text-ink outline-none focus:border-blue'
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
</script>

<template>
  <div class="max-w-4xl space-y-6">
    <div>
      <h2 class="font-display text-2xl font-semibold">AI Creations</h2>
      <p class="text-sm text-muted">Create anything with AI, from one prop to a whole series. You review it all before anything is written.</p>
    </div>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-72" aria-busy="true" aria-label="Loading library" />
    <template v-else>
      <!-- 1: type -->
      <section class="raised space-y-3 p-6" aria-labelledby="ai-type">
        <h3 id="ai-type" class="font-display text-xl font-semibold">What to create</h3>
        <div class="flex flex-wrap gap-2" role="group" aria-label="Type">
          <button v-for="t in TYPES" :key="t" type="button" class="btn" :class="kind === t ? 'btn-primary' : 'btn-secondary'"
            :aria-pressed="kind === t" @click="pick(t)">{{ TYPE_LABEL[t] }}</button>
        </div>
      </section>

      <!-- 2: brief -->
      <section class="raised space-y-4 p-6" aria-labelledby="ai-brief">
        <h3 id="ai-brief" class="font-display text-xl font-semibold">Brief</h3>
        <p v-if="brief.id" class="text-xs text-muted">For <code>{{ brief.id }}</code>. If that id is taken, the new one gets a suffix: nothing is overwritten.</p>
        <label class="block text-sm font-semibold" for="ai-desc">{{ kind === 'series' ? 'Story premise' : 'Description' }}
          <textarea id="ai-desc" v-model="brief.description" rows="5" :class="field" :placeholder="{
            prop: 'A red umbrella with a curved wooden handle', set: 'A rainy bus stop at night with a flickering lamp',
            creature: 'A grumpy goose with a long neck', action: 'A slow, proud bow with one arm across the chest',
            cast: 'Two rival bakers: one tall in a white apron, one short and cheeky', series: 'A night-shift baker discovers that the town\'s statues move whenever the oven bell rings…' }[kind]" />
        </label>
        <div v-if="kind === 'creature'" class="max-w-xs">
          <label class="block text-sm font-semibold" for="ai-rig">Rig
            <select id="ai-rig" v-model="brief.rig" :class="field"><option v-for="r in DRAWN_RIGS" :key="r" :value="r">{{ r }}</option></select>
          </label>
          <p class="mt-1 text-xs text-muted">{{ RIG_NOTES[brief.rig] }}</p>
        </div>
        <label v-if="kind === 'series'" class="block max-w-xs text-sm font-semibold" for="ai-parts">Number of parts
          <select id="ai-parts" v-model.number="brief.parts" :class="field"><option v-for="n in 5" :key="n" :value="n">{{ n }} part{{ n === 1 ? '' : 's' }}</option></select>
        </label>
        <label v-if="kind === 'cast'" class="block max-w-sm text-sm font-semibold" for="ai-series">Add to series
          <select id="ai-series" v-model="brief.series" :class="field" required>
            <option value="" disabled>Choose a series</option>
            <option v-for="s in data![4]" :key="s.slug" :value="s.slug">{{ s.title }}</option>
          </select>
        </label>
      </section>

      <!-- 3: mode -->
      <section class="raised space-y-4 p-6" aria-labelledby="ai-mode">
        <h3 id="ai-mode" class="font-display text-xl font-semibold">Get the reply</h3>
        <div class="flex flex-wrap gap-2" role="group" aria-label="Mode">
          <button type="button" class="btn" :class="mode === 'generate' ? 'btn-primary' : 'btn-secondary'" :aria-pressed="mode === 'generate'"
            :disabled="!auto" @click="mode = 'generate'"><Sparkles :size="16" aria-hidden="true" /> Generate{{ auto ? ` with ${provider}` : '' }}</button>
          <button type="button" class="btn" :class="mode === 'bridge' ? 'btn-primary' : 'btn-secondary'" :aria-pressed="mode === 'bridge'"
            @click="mode = 'bridge'">Use any chat AI</button>
        </div>
        <p v-if="!auto" class="text-xs text-muted">Generate needs a provider: <RouterLink to="/settings" class="underline">set up OmniRoute, Gemini or OpenRouter in Settings</RouterLink>. Any chat AI always works, even offline.</p>
        <template v-if="mode === 'generate'">
          <button type="button" class="btn btn-primary" :disabled="!ready || busy" :aria-busy="busy" @click="generateReply">
            <Sparkles :size="16" aria-hidden="true" /> {{ label }}</button>
          <p v-if="replyError" class="text-sm text-red-ink" role="alert">{{ replyError }} <button type="button" class="underline" @click="mode = 'bridge'">Fix the reply by hand</button></p>
        </template>
        <template v-else>
          <button type="button" class="btn btn-primary" :disabled="!ready" @click="makePrompt">Make prompt</button>
          <AiBridge v-model="reply" :prompt="prompt" :error="replyError" load-label="Review" @load="loadReply" />
        </template>
      </section>

      <!-- 4 + 5: review and import -->
      <section v-if="items.length || created.length" class="raised space-y-4 p-6" aria-labelledby="ai-review">
        <h3 id="ai-review" class="font-display text-xl font-semibold">Review</h3>
        <ul class="divide-y divide-rule">
          <li v-for="i in items" :key="i.key" class="flex flex-wrap items-center gap-3 py-2">
            <input :id="`rv-${i.key}`" v-model="i.checked" type="checkbox" class="size-4"
              :disabled="i.status === 'existing' || (seriesOff && needsSeries(i, items))" />
            <label :for="`rv-${i.key}`" class="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-sm">
              <span class="chip">{{ KIND_LABEL[i.kind] }}</span>
              <strong>{{ i.name }}</strong>
              <code class="text-xs text-muted">{{ i.id }}</code>
              <span v-if="i.was" class="text-xs text-red-ink">“{{ i.was }}” is taken: saved as {{ i.id }}</span>
            </label>
            <span class="chip" :class="i.status === 'new' ? 'text-blue-ink' : 'text-muted'">{{ i.status }}</span>
          </li>
        </ul>
        <p v-if="kind === 'series'" class="text-xs text-muted">This creates scripts and library items only. Record each voice with FreeTTS and upload voice.mp3 on the part page, as before.</p>
        <p v-if="importError" class="text-sm text-red-ink" role="alert">{{ importError }}</p>
        <button v-if="items.length" type="button" class="btn btn-primary" :disabled="!toImport.length || importing" :aria-busy="importing" @click="runImport">
          {{ importing ? 'Importing…' : `Import ${toImport.length} item${toImport.length === 1 ? '' : 's'}` }}</button>
        <div v-if="created.length">
          <h4 class="font-semibold">Created</h4>
          <ul class="list-disc pl-5 text-sm"><li v-for="c in created" :key="c.href + c.label"><RouterLink :to="c.href" class="underline">{{ c.label }}</RouterLink></li></ul>
        </div>
      </section>

      <section class="raised space-y-3 p-6" aria-labelledby="ai-recent">
        <h3 id="ai-recent" class="font-display text-xl font-semibold">Recent creations</h3>
        <p v-if="!recent.length" class="text-sm text-muted">Nothing yet: what you import shows up here.</p>
        <ul v-else class="divide-y divide-rule text-sm">
          <li v-for="r in recent" :key="r.at + r.href" class="flex flex-wrap justify-between gap-2 py-2">
            <RouterLink :to="r.href" class="underline">{{ r.label }}</RouterLink><span class="text-xs text-muted">{{ when(r.at) }}</span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>
