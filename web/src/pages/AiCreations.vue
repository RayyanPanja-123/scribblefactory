<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import AiBridge from '../components/AiBridge.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { toast } from '../composables/feedback'
import { useApi } from '../composables/useApi'
import { buildCreationPrompt, chosen, isKind, parseReply, reviewItems, TYPE_LABEL, TYPES, type Brief, type Item, type Kind, type Library } from '../lib/aiCreations'
import { RIG_LIST, RIG_NOTES, type CustomCreature, type Rig } from '../lib/creatures'
import type { CustomProp } from '../lib/props'
import type { CustomSet } from '../lib/sets'

// One screen to create library items and cast with AI. Series are created from the Series flow.
const route = useRoute()
const router = useRouter()
const { data, error, loading, reload } = useApi(() => Promise.all([api.props(), api.sets(), api.creatures(), api.actions(), api.series()]))
const lib = computed<Library | null>(() => !data.value ? null : { props: data.value[0], sets: data.value[1], creatures: data.value[2], actions: data.value[3] })

const q = (k: string) => (typeof route.query[k] === 'string' ? (route.query[k] as string) : '')
const kind = computed<Kind>(() => (isKind(route.query.type) ? route.query.type : 'prop'))
const brief = reactive<Brief & { rig: Rig; series: string }>({ description: '', rig: 'quadruped', series: '' })

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
  if (kind.value === 'cast' && !guide) guide = (await import('../../../docs/STORY_GUIDE.md?raw')).default
  prompt.value = buildCreationPrompt(kind.value, { ...brief, cast: targetCast.value }, lib.value, guide)
  return prompt.value
}
function loadReply() {
  const { plan, error: err } = parseReply(kind.value, reply.value)
  replyError.value = err ?? ''
  items.value = plan && lib.value ? reviewItems(plan, lib.value, targetCast.value) : []
  if (plan) toast('Ready to review: uncheck anything you don\'t want', 'ok')
}

// ---- review ----
const KIND_LABEL: Record<Item['kind'], string> = TYPE_LABEL
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
    if (cast.length) {
      await api.addCast(brief.series, cast.map((i) => i.data as Record<string, unknown>))
      cast.forEach((i) => mark(i, `Cast “${i.name}” in ${brief.series}`, `/series/${brief.series}`))
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
      <p class="text-sm text-muted">Create props, sets, creatures, actions and cast with AI. You review it all before anything is written.
        To create a series, use <RouterLink to="/new-series" class="underline">Create series</RouterLink>.</p>
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
        <label class="block text-sm font-semibold" for="ai-desc">Description
          <textarea id="ai-desc" v-model="brief.description" rows="5" :class="field" :placeholder="{
            prop: 'A red umbrella with a curved wooden handle', set: 'A rainy bus stop at night with a flickering lamp',
            creature: 'A grumpy goose with a long neck', action: 'A slow, proud bow with one arm across the chest',
            cast: 'Two rival bakers: one tall in a white apron, one short and cheeky' }[kind]" />
        </label>
        <div v-if="kind === 'creature'" class="max-w-xs">
          <label class="block text-sm font-semibold" for="ai-rig">Rig
            <select id="ai-rig" v-model="brief.rig" :class="field"><option v-for="r in RIG_LIST" :key="r" :value="r">{{ r }}</option></select>
          </label>
          <p class="mt-1 text-xs text-muted">{{ RIG_NOTES[brief.rig] }}</p>
        </div>
        <label v-if="kind === 'cast'" class="block max-w-sm text-sm font-semibold" for="ai-series">Add to series
          <select id="ai-series" v-model="brief.series" :class="field" required>
            <option value="" disabled>Choose a series</option>
            <option v-for="s in data![4]" :key="s.slug" :value="s.slug">{{ s.title }}</option>
          </select>
        </label>
      </section>

      <!-- 3: the reply, from any chat AI -->
      <section class="raised space-y-4 p-6" aria-labelledby="ai-mode">
        <h3 id="ai-mode" class="font-display text-xl font-semibold">Get the reply</h3>
        <button type="button" class="btn btn-primary" :disabled="!ready" @click="makePrompt">Make prompt</button>
        <AiBridge v-model="reply" :prompt="prompt" :error="replyError" load-label="Review" @load="loadReply" />
      </section>

      <!-- 4 + 5: review and import -->
      <section v-if="items.length || created.length" class="raised space-y-4 p-6" aria-labelledby="ai-review">
        <h3 id="ai-review" class="font-display text-xl font-semibold">Review</h3>
        <ul class="divide-y divide-rule">
          <li v-for="i in items" :key="i.key" class="flex flex-wrap items-center gap-3 py-2">
            <input :id="`rv-${i.key}`" v-model="i.checked" type="checkbox" class="size-4"
              :disabled="i.status === 'existing'" />
            <label :for="`rv-${i.key}`" class="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-sm">
              <span class="chip">{{ KIND_LABEL[i.kind] }}</span>
              <strong>{{ i.name }}</strong>
              <code class="text-xs text-muted">{{ i.id }}</code>
              <span v-if="i.was" class="text-xs text-red-ink">“{{ i.was }}” is taken: saved as {{ i.id }}</span>
            </label>
            <span class="chip" :class="i.status === 'new' ? 'text-blue-ink' : 'text-muted'">{{ i.status }}</span>
          </li>
        </ul>
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
