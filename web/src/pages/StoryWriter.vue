<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import { act, toast } from '../composables/feedback'
import { useApi } from '../composables/useApi'

type Prop = Parameters<typeof api.saveProp>[0]
type Set = Parameters<typeof api.saveSet>[0]
type Creature = Parameters<typeof api.saveCreature>[0]
type Action = Parameters<typeof api.saveAction>[0]
type Plan = {
  title: string
  slug?: string
  cast: Record<string, unknown>[]
  assets?: { props?: Prop[]; sets?: Set[]; creatures?: Creature[]; actions?: Action[] }
  parts: { title: string; story: string }[]
}

const router = useRouter()
const { data: settings, error: settingsError, loading: settingsLoading, reload } = useApi(() => api.settings())
const premise = ref('')
const partCount = ref(3)
const busy = ref(false)
const result = ref<Plan | null>(null)
const error = ref('')
const ready = computed(() => settings.value?.provider === 'gemini' || settings.value?.provider === 'openrouter')
const field = 'inset mt-1 block w-full rounded-md px-4 py-2 text-sm text-ink outline-none focus:border-blue'

const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'new-story'
const jsonOnly = (text: string) => {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i)?.[1] ?? text
  return JSON.parse(fenced.trim()) as Plan
}

async function inventory() {
  const [props, sets, creatures, actions] = await Promise.all([api.props(), api.sets(), api.creatures(), api.actions()])
  return { props, sets, creatures, actions }
}

async function generate() {
  if (!premise.value.trim() || !ready.value) return
  busy.value = true
  error.value = ''
  try {
    const [{ default: guide }, library] = await Promise.all([import('../../../docs/STORY_GUIDE.md?raw'), inventory()])
    const prompt = `You are Scribble Factory Story Writer. Follow the attached STORY_GUIDE.md exactly for story.md syntax, directives, cast, pacing, props, sets, creatures, and actions.

Create a basic series from this premise: ${premise.value.trim()}
Plan exactly ${partCount.value} parts. Unlike the guide's one-part chat behavior, return all requested parts in one machine-readable plan.

Return ONLY valid JSON, with this shape:
{"title":"...","slug":"lowercase-slug","cast":[...],"assets":{"props":[...],"sets":[...],"creatures":[...],"actions":[...]},"parts":[{"title":"...","story":"complete story.md text"}]}

Use existing library items whenever possible. Put only genuinely needed new custom items in assets, using the exact schemas and valid primitive/keyframe values from the guide and existing conventions. Every asset id used by a story or cast must be present in the corresponding assets list. Keep each story self-contained with # title, @set, @cast, directives, and narration. Do not include audio, voice.mp3, markdown fences, explanations, or NEW blocks outside the JSON. The user will build no audio automatically: TTS and audio upload stay manual.

CURRENT LIBRARY INVENTORY:
${JSON.stringify(library)}

STORY_GUIDE.md:
${guide}`
    const text = (await api.storyWriter(prompt)).text
    const plan = jsonOnly(text)
    if (!plan.title || !Array.isArray(plan.cast) || !Array.isArray(plan.parts) || !plan.parts.length) throw new Error('Gemini returned an incomplete story plan')
    result.value = plan
    toast('Story plan ready for review', 'ok')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

async function create() {
  if (!result.value) return
  busy.value = true
  error.value = ''
  try {
    const plan = result.value
    for (const p of plan.assets?.props ?? []) await api.saveProp(p)
    for (const s of plan.assets?.sets ?? []) await api.saveSet(s)
    for (const c of plan.assets?.creatures ?? []) await api.saveCreature(c)
    for (const a of plan.assets?.actions ?? []) await api.saveAction(a)
    const series = await api.createSeries({ slug: slugify(plan.slug || plan.title), title: plan.title, cast: plan.cast })
    for (const part of plan.parts) await api.createPart(series.slug, { title: part.title, story: part.story })
    toast(`Created “${series.title}” with ${plan.parts.length} parts`, 'ok')
    router.push(`/series/${series.slug}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="max-w-4xl space-y-6">
    <div>
      <h2 class="font-display text-2xl font-semibold">Story Writer</h2>
      <p class="text-sm text-muted">Generate a standards-compliant series using your existing library.</p>
    </div>
    <ErrorCard v-if="settingsError" :message="settingsError" @retry="reload" />
    <div v-else-if="settingsLoading" class="skeleton h-72" aria-busy="true" />
    <section v-else-if="!ready" class="raised max-w-2xl space-y-4 p-6">
      <h3 class="font-display text-xl font-semibold">Gemini is required</h3>
      <p class="text-sm text-muted">Story Writer uses a dedicated provider such as Gemini or OpenRouter and is not available through OmniRoute.</p>
      <RouterLink to="/settings#preferences" class="btn btn-primary">Choose Gemini in Settings</RouterLink>
    </section>
    <template v-else>
      <section class="raised max-w-2xl space-y-5 p-6">
        <div><h3 class="font-display text-xl font-semibold">Plan a series</h3><p class="text-sm text-muted">Gemini will use your props, sets, creatures and actions, adding valid custom items only when needed.</p></div>
        <label class="block text-sm font-semibold">Story premise<textarea v-model="premise" rows="6" required :class="field" placeholder="A night-shift baker discovers that the town's statues move whenever the oven bell rings..." /></label>
        <label class="block max-w-xs text-sm font-semibold">Number of parts<select v-model.number="partCount" :class="field"><option v-for="n in 5" :key="n" :value="n">{{ n }} parts</option></select></label>
        <button class="btn btn-primary" :disabled="busy || !premise.trim()" @click="generate">{{ busy ? 'Writing…' : 'Write series with Gemini' }}</button>
      </section>
      <p v-if="error" class="text-sm text-red-ink" role="alert">{{ error }}</p>
      <section v-if="result" class="raised space-y-5 p-6">
        <div><h3 class="font-display text-xl font-semibold">{{ result.title }}</h3><p class="text-sm text-muted">{{ result.parts.length }} parts · {{ result.cast.length }} cast members · {{ (result.assets?.props?.length ?? 0) + (result.assets?.sets?.length ?? 0) + (result.assets?.creatures?.length ?? 0) + (result.assets?.actions?.length ?? 0) }} new library items</p></div>
        <ol class="list-decimal space-y-2 pl-5 text-sm"> <li v-for="part in result.parts" :key="part.title"><strong>{{ part.title }}</strong><pre class="mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-well p-3 text-xs text-muted">{{ part.story }}</pre></li></ol>
        <div class="flex flex-wrap gap-2"><button class="btn btn-primary" :disabled="busy" @click="create">{{ busy ? 'Creating…' : 'Create series and parts' }}</button><button class="btn btn-secondary" :disabled="busy" @click="result = null">Discard plan</button></div>
        <p class="text-xs text-muted">This creates scripts and library definitions only. Record voice with FreeTTS and upload each voice.mp3 manually.</p>
      </section>
    </template>
  </div>
</template>
