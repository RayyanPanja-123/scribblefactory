<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import PartStepper from '../components/PartStepper.vue'
import StoryPainter from '../components/StoryPainter.vue'
import StoryTips from '../components/StoryTips.vue'
import { act, toast } from '../composables/feedback'
import { useApi } from '../composables/useApi'
import { partSteps } from '../lib/partSteps'

// the whole journey, so it is clear what follows the story (no links: those sections live on the part page)
const steps = partSteps({ stages: {}, approvals: { stills: false, test_render: false, final: false },
  files: { voice: false, stillsSheet: false, testRender: false }, castApproved: false, busy: null, failed: null,
  thumbs: false, thumbnailPicked: false, posted: { youtube: false, instagram: false } }).map((s) => ({ ...s, href: '' }))

const props = defineProps<{ slug: string }>()
const router = useRouter()
const { data, error, reload } = useApi(() => api.seriesDetail(props.slug))

const title = ref('')
const story = ref('')
const storyEdited = ref(false)
const number = computed(() => (data.value?.parts.length ?? 0) + 1)
// a starter story using this series' cast, until the user types in it
watch([title, data], () => {
  if (storyEdited.value || !data.value) return
  const ids = data.value.series.cast.map((c) => c.id)
  story.value = `# ${title.value.trim() || `Part ${number.value}`}\n\n@set street\n${ids.length ? `@cast ${ids.join(', ')}\n` : ''}First line of narration.\n`
}, { immediate: true })
// after the story is edited, the Title field still renames its "# title" line (the painter has no title field here)
watch(title, (t) => {
  if (storyEdited.value) story.value = story.value.replace(/^#.*$/m, `# ${t.trim() || `Part ${number.value}`}`)
})

const storyView = ref<'text' | 'painter'>('text')
const painterCast = computed(() => (data.value?.series.cast ?? []).map((c) => ({ id: c.id, name: c.name, looks: Object.keys(c.looks ?? {}) })))

const saving = ref(false)
async function create() {
  saving.value = true
  const d = await act(() => api.createPart(props.slug, { title: title.value.trim() || null, story: story.value }), 'Part created')
  saving.value = false
  if (d) {
    if (d.audio_notice) toast(d.audio_notice, d.audio_notice.startsWith('Audio auto-selected') ? 'ok' : 'info')
    router.push(`/series/${props.slug}/${d.part.id}`)
  }
}
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />

  <div v-else class="space-y-6">
    <RouterLink :to="`/series/${slug}`" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> {{ data?.series.title ?? slug }}</RouterLink>

    <form class="space-y-6" @submit.prevent="create">
      <div class="raised space-y-5 p-6">
        <h2 class="font-display text-3xl font-semibold">New part <span class="text-muted">#{{ number }}</span></h2>
        <PartStepper :steps="steps" />
        <label class="block text-xs font-semibold text-muted">Title
          <input v-model="title" :placeholder="`Part ${number}`" class="inset mt-1 block w-full rounded-md px-4 py-2 text-sm text-ink outline-none focus:border-blue" />
        </label>
      </div>

      <StoryTips />
      <div>
        <div class="raised min-w-0 space-y-3 p-6">
          <div class="flex items-center gap-3">
            <label class="text-xs font-semibold text-muted" for="story-md">story.md</label>
            <div class="inline-flex rounded-md border border-rule p-0.5" role="group" aria-label="Story view">
              <button v-for="v in (['text', 'painter'] as const)" :key="v" type="button" class="rounded px-3 py-1 text-sm font-semibold"
                :class="storyView === v ? 'bg-ink text-panel' : 'text-muted hover:text-ink'" :aria-pressed="storyView === v" @click="storyView = v">
                {{ v === 'text' ? 'Text' : 'Typewriter' }}</button>
            </div>
          </div>
          <StoryPainter v-if="storyView === 'painter'" v-model="story" :cast="painterCast" no-title @update:model-value="storyEdited = true" @close="storyView = 'text'">
            <template #actions>
              <button type="button" class="btn btn-primary" :disabled="saving || !data" @click="create">{{ saving ? 'Creating…' : 'Create part' }}</button>
            </template>
          </StoryPainter>
          <textarea id="story-md" v-model="story" class="paper inset block min-h-96 w-full resize-y p-5 font-mono text-sm leading-7 outline-none focus:border-blue"
            spellcheck="true" @input="storyEdited = true" />
          <p class="text-xs text-muted">
            Cast ids: <code>{{ data?.series.cast.map((c) => c.id).join(', ') || 'none yet' }}</code>. Every directive: the Help page.
          </p>
          <div class="flex justify-end">
            <button class="btn btn-primary" :disabled="saving || !data">{{ saving ? 'Creating…' : 'Create part' }}</button>
          </div>
        </div>
      </div>
    </form>
  </div>
</template>
