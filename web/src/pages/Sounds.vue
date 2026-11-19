<script setup lang="ts">
import { AudioLines, Save, Trash2, TriangleAlert, Upload } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { api, sfxAudio } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import { act, confirm } from '../composables/feedback'
import { useApi } from '../composables/useApi'
import { ANCHORS, idFromFile, type SfxEntry, type SfxView } from '../lib/sfx'

// The sound effects a story plays with @sfx <id> [volume]: files in library/sfx/, their entries in sfx.json.
// A missing file only warns (that sound is left out of the mix); deleting is refused while a story uses it.
const { data, error, loading, reload } = useApi(() => api.sfx())
const sounds = computed(() => data.value?.sfx ?? [])

// one editable copy per sound; tags edited as a comma list
type Form = SfxEntry & { tagText: string }
const forms = reactive<Record<string, Form>>({})
const toForm = (x: SfxView): Form => ({ id: x.id, file: x.file, name: x.name, purpose: x.purpose ?? '', tags: x.tags ?? [],
  anchor: x.anchor ?? 'start', default_volume: x.default_volume ?? 0.8, tagText: (x.tags ?? []).join(', ') })
watch(sounds, (xs) => { for (const x of xs) forms[x.id] = toForm(x) }, { immediate: true })
const dirty = (x: SfxView) => JSON.stringify(entry(forms[x.id])) !== JSON.stringify(entry(toForm(x)))
const entry = ({ tagText, ...f }: Form): SfxEntry => ({ ...f, tags: tagText.split(',').map((t) => t.trim()).filter(Boolean) })

const versions = ref<Record<string, number>>({}) // re-uploaded: a new audio url, never the cached copy
const set = (r: Awaited<ReturnType<typeof api.sfx>> | undefined) => { if (r) data.value = r }

async function save(x: SfxView) {
  set(await act(() => api.saveSfx(entry(forms[x.id])), `${forms[x.id].name} saved`))
}
async function upload(e: Event, id?: string) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const sid = id ?? idFromFile(file.name)
  if (!id && sounds.value.some((s) => s.id === sid)
    && !await confirm({ title: `Replace the file of “${sid}”?`, body: `${file.name} becomes its sound; its settings stay.`, confirm: 'Replace' })) return
  const r = await act(() => api.uploadSfx(sid, file), `${file.name} uploaded as ${sid}`)
  if (r) {
    versions.value[sid] = Date.now()
    set(r)
  }
}
async function remove(x: SfxView) {
  const ok = await confirm({ title: `Delete “${x.name}”?`, body: 'Its entry and its file go. Only possible while no story uses it.', confirm: 'Delete sound', danger: true })
  if (ok) set(await act(() => api.deleteSfx(x.id), 'Sound deleted'))
}
const field = 'inset mt-1 block h-10 w-full rounded-md px-3 text-sm text-ink outline-none focus:border-blue'
</script>

<template>
  <ErrorCard v-if="error" :message="error" @retry="reload" />
  <div v-else-if="loading" class="skeleton h-96" aria-busy="true" aria-label="Loading sounds" />
  <div v-else class="space-y-5">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Sounds</h2>
      <span class="text-sm text-muted">{{ sounds.length }} sound effects · {{ sounds.filter((s) => s.missing).length }} missing a file</span>
      <label class="btn btn-primary ml-auto cursor-pointer">
        <Upload :size="16" aria-hidden="true" /> Upload sound
        <input type="file" accept=".mp3,.wav,.ogg,.m4a,audio/*" class="sr-only" @change="upload($event)" />
      </label>
    </div>
    <p class="text-sm text-muted">
      A story plays one with <code>@sfx &lt;id&gt; [volume 0-1]</code> on its own line, right above the narration line it
      belongs to. <b>Line start</b> sounds play as the line starts; <b>ends on line</b> sounds (risers) end exactly as it
      starts. At most 5 per part, mixed under the voice. Files live in <code>library/sfx/</code>; an upload's id comes
      from its file name.
    </p>
    <ul class="grid gap-3 lg:grid-cols-2">
      <li v-for="x in sounds" :key="x.id" class="raised space-y-3 p-4">
        <div class="flex flex-wrap items-center gap-2">
          <AudioLines :size="18" class="text-muted" aria-hidden="true" />
          <p class="font-semibold">{{ x.name }}</p>
          <code class="chip">{{ x.id }}</code>
          <span v-if="x.missing" class="chip chip-red"><TriangleAlert :size="12" aria-hidden="true" /> {{ x.file }} missing</span>
          <span class="ml-auto text-xs text-muted">{{ x.users.length ? `used in ${x.users.join(', ')}` : 'not used yet' }}</span>
        </div>
        <audio v-if="!x.missing" :src="sfxAudio(x.id, versions[x.id])" controls preload="none" class="h-9 w-full" :aria-label="`Play ${x.name}`" />
        <form v-if="forms[x.id]" class="grid gap-3 sm:grid-cols-2" @submit.prevent="save(x)">
          <label class="text-xs font-semibold">Name<input v-model="forms[x.id].name" required maxlength="60" :class="field" /></label>
          <label class="text-xs font-semibold">Purpose<input v-model="forms[x.id].purpose" maxlength="200" placeholder="suspense before payoff" :class="field" /></label>
          <label class="text-xs font-semibold">Tags<input v-model="forms[x.id].tagText" placeholder="tension, reveal" :class="field" /></label>
          <label class="text-xs font-semibold">Anchor
            <select v-model="forms[x.id].anchor" :class="field">
              <option v-for="a in ANCHORS" :key="a.id" :value="a.id">{{ a.label }}: {{ a.note }}</option>
            </select>
          </label>
          <label class="text-xs font-semibold sm:col-span-2">Default volume <span class="num font-normal text-muted">{{ forms[x.id].default_volume.toFixed(2) }}</span>
            <input v-model.number="forms[x.id].default_volume" type="range" min="0" max="1" step="0.05" class="mt-1 block w-full" />
          </label>
          <div class="flex flex-wrap gap-2 sm:col-span-2">
            <button type="submit" class="btn btn-primary" :disabled="!dirty(x)"><Save :size="16" aria-hidden="true" /> Save</button>
            <label class="btn btn-secondary cursor-pointer">
              <Upload :size="16" aria-hidden="true" /> {{ x.missing ? 'Add file' : 'Replace file' }}
              <input type="file" accept=".mp3,.wav,.ogg,.m4a,audio/*" class="sr-only" @change="upload($event, x.id)" />
            </label>
            <button type="button" class="btn btn-secondary ml-auto text-red-ink" :disabled="!!x.users.length"
              :title="x.users.length ? `used in ${x.users.join(', ')}` : undefined" :aria-label="`Delete ${x.name}`" @click="remove(x)">
              <Trash2 :size="16" aria-hidden="true" />
            </button>
          </div>
        </form>
      </li>
    </ul>
  </div>
</template>
