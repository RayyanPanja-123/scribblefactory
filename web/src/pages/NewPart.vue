<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import PartStepper from '../components/PartStepper.vue'
import { act } from '../composables/feedback'
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

const saving = ref(false)
async function create() {
  saving.value = true
  const d = await act(() => api.createPart(props.slug, { title: title.value.trim() || null, story: story.value }), 'Part created')
  saving.value = false
  if (d) router.push(`/series/${props.slug}/${d.part.id}`)
}
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />

  <div v-else class="mx-auto max-w-3xl space-y-6">
    <RouterLink :to="`/series/${slug}`" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> {{ data?.series.title ?? slug }}</RouterLink>

    <form class="raised space-y-5 p-6" @submit.prevent="create">
      <h2 class="font-display text-3xl font-semibold">New part <span class="text-muted">#{{ number }}</span></h2>
      <PartStepper :steps="steps" />

      <label class="block text-xs font-semibold text-muted">Title
        <input v-model="title" :placeholder="`Part ${number}`" class="inset mt-1 block w-full rounded-full px-4 py-2 text-sm text-ink outline-none" />
      </label>

      <label class="block text-xs font-semibold text-muted" for="story-md">story.md</label>
      <textarea id="story-md" v-model="story" class="paper inset block min-h-96 w-full resize-y p-5 font-mono text-sm leading-7 outline-none"
        spellcheck="true" @input="storyEdited = true" />
      <p class="text-xs text-muted">
        Narration lines, with directives on their own lines: <code>@set</code>, <code>@cast</code>, <code>@car</code>, <code>@do</code>,
        <code>@crowd</code>. Full syntax in docs/brief.md. Cast ids:
        <code>{{ data?.series.cast.map((c) => c.id).join(', ') || 'none yet' }}</code>.
      </p>

      <div class="flex justify-end">
        <button class="btn btn-primary" :disabled="saving || !data">{{ saving ? 'Creating…' : 'Create part' }}</button>
      </div>
    </form>
  </div>
</template>
