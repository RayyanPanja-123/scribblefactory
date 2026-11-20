<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { act } from '../composables/feedback'

const router = useRouter()
const slugify = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')

const title = ref('')
const slug = ref('')
const slugEdited = ref(false)
const aspect = ref<'9:16' | '16:9'>('9:16')
watch(title, (t) => { if (!slugEdited.value) slug.value = slugify(t) })

const saving = ref(false)
const ready = computed(() => title.value.trim() && slug.value)

async function create() {
  saving.value = true
  const body = { slug: slug.value, title: title.value.trim(), aspect: aspect.value, cast: [] } // the cast is added later, from the series or any part
  const s = await act(() => api.createSeries(body), `Series “${body.title}” created`)
  saving.value = false
  if (s) router.push(`/series/${s.slug}/new-part`)
}
const field = 'inset mt-1 block h-10 w-full rounded-md px-4 text-sm text-ink outline-none focus:border-blue'
</script>

<template>
  <div class="space-y-6">
    <RouterLink to="/series" class="btn btn-secondary"><ArrowLeft :size="16" aria-hidden="true" /> All series</RouterLink>

    <form class="max-w-xl" @submit.prevent="create">
      <div class="raised space-y-6 p-6">
      <h2 class="font-display text-3xl font-semibold">New series</h2>

      <div class="grid gap-4">
        <label class="block text-xs font-semibold text-muted">Title
          <input v-model="title" required placeholder="Marathon 1904" :class="field" />
        </label>
        <label class="block text-xs font-semibold text-muted">Slug (folder name)
          <input v-model="slug" required pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="marathon-1904" :class="field"
            @input="slugEdited = true" />
        </label>
        <label class="block text-xs font-semibold text-muted">Frame
          <select v-model="aspect" :class="field">
            <option value="9:16">9:16 tall (Shorts, Reels)</option>
            <option value="16:9">16:9 wide (YouTube)</option>
          </select>
        </label>
      </div>

      <div class="flex justify-end">
        <button class="btn btn-primary" :disabled="!ready || saving">{{ saving ? 'Creating…' : 'Create series' }}</button>
      </div>
      </div>

    </form>
  </div>
</template>
