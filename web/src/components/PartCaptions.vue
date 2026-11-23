<script setup lang="ts">
import { Copy, Instagram, Save, Sparkles, Youtube } from 'lucide-vue-next'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { api, type PartDetail, type SeriesModel } from '../api/client'
import { act, confirm, toast } from '../composables/feedback'
import { buildCaptionPrompt, composeUpload, parseUpload, type Captions } from '../lib/captionPrompt'

// upload.md: the captions as two cards (YouTube: title, description, pinned comment; Instagram: one caption)
const props = defineProps<{ slug: string; part: string; detail: PartDetail; series?: SeriesModel }>()

const cap = reactive<Captions>({ title: '', description: '', pinned: '', instagram: '' })
const head = computed(() => {
  const s = props.series
  const top = /^# +(.+)$/m.exec(props.detail.upload_md ?? '')?.[1]
  return top ?? `${s?.title ?? props.slug} — Part ${(s?.parts.indexOf(props.part) ?? 0) + 1}`
})
const saved = ref(parseUpload(''))
const dirty = computed(() => (Object.keys(cap) as (keyof Captions)[]).some((k) => cap[k] !== saved.value[k]))
watch(() => props.detail.upload_md, (md) => {
  if (dirty.value) return // never clobber unsaved edits on a live refresh
  saved.value = parseUpload(md ?? '')
  Object.assign(cap, saved.value)
}, { immediate: true })
async function save() {
  if (!dirty.value) return
  const now = { ...cap }
  if (await act(() => api.saveUpload(props.slug, props.part, composeUpload(head.value, now)), 'upload.md saved')) saved.value = now
}

// captions from Gemini: they land in the cards unsaved (review, then Save)
const writing = ref(false)
async function writeCaptions() {
  const s = props.series
  const me = props.detail
  if (!s || writing.value) return
  if (dirty.value && !(await confirm({ title: 'Replace the captions?', body: 'Your unsaved edits in the cards are replaced.', confirm: 'Replace' }))) return
  writing.value = true
  try {
    const i = s.parts.indexOf(props.part)
    const nextId = s.parts[i + 1]
    const [next, cfg] = await Promise.all([nextId ? api.part(props.slug, nextId).catch(() => null) : null, api.settings().catch(() => null)])
    const prompt = buildCaptionPrompt({
      series: s.title, number: i + 1, parts: s.parts.length, title: me.part.title, story: me.story_md ?? '',
      next: next?.story_md ? { title: next.part.title, story: next.story_md } : undefined,
      handles: cfg?.settings.socials,
    })
    const r = await act(() => api.writeCaptions(prompt), 'Captions written: check them, then Save')
    if (r) Object.assign(cap, { title: r.youtube_title, description: r.youtube_description, pinned: r.youtube_pinned_comment, instagram: r.instagram_caption })
  } finally {
    writing.value = false
  }
}
async function copy(t: string, what: string) {
  try {
    await navigator.clipboard.writeText(t.trim())
    toast(`${what} copied`, 'ok')
  } catch {
    toast('Could not copy: clipboard not available', 'error')
  }
}
const CARDS = [
  { name: 'YouTube', icon: Youtube, color: 'text-youtube', fields: [
    { k: 'title', label: 'Title', max: 100, rows: 1 }, { k: 'description', label: 'Description + tags', max: 5000, rows: 6 },
    { k: 'pinned', label: 'Pinned comment', max: 10000, rows: 3 }] },
  { name: 'Instagram', icon: Instagram, color: 'text-instagram', fields: [{ k: 'instagram', label: 'Caption + tags', max: 2200, rows: 12 }] },
] as const
function onKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    save()
  }
}
window.addEventListener('keydown', onKey)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <section id="upload" class="raised p-6">
    <div class="flex flex-wrap items-center gap-2">
      <h3 class="font-display text-lg font-semibold">Captions</h3>
      <span v-if="dirty" class="size-2.5 rounded-full bg-amber" title="Unsaved changes" aria-label="Unsaved changes" />
      <button class="btn btn-secondary ml-auto" :disabled="!detail.story_md || writing" @click="writeCaptions">
        <Sparkles :size="16" aria-hidden="true" /> {{ writing ? 'Writing…' : 'Write with Gemini' }}</button>
      <button class="btn btn-primary" :disabled="!dirty" @click="save"><Save :size="16" aria-hidden="true" /> Save</button>
    </div>
    <p class="mt-1 text-xs text-muted">Saved to upload.md (Ctrl+S). Gemini (key in Settings) uses the story; nothing is saved until you Save.</p>
    <div class="mt-4 space-y-4" :aria-busy="writing">
      <div v-for="c in CARDS" :key="c.name" class="inset space-y-3 p-4">
        <p class="flex items-center gap-2 font-semibold"><component :is="c.icon" :size="18" :class="c.color" aria-hidden="true" />{{ c.name }}</p>
        <div v-for="f in c.fields" :key="f.k">
          <div class="flex items-center gap-2">
            <label :for="`cap-${f.k}`" class="text-xs font-semibold text-muted">{{ f.label }}</label>
            <span class="num ml-auto text-xs" :class="cap[f.k].length > f.max ? 'text-red-ink' : 'text-muted'">{{ cap[f.k].length }}/{{ f.max }}</span>
            <button type="button" class="btn btn-secondary h-7 px-2 text-xs" :disabled="!cap[f.k].trim()" :aria-label="`Copy ${c.name} ${f.label}`"
              @click="copy(cap[f.k], `${c.name} ${f.label.toLowerCase()}`)"><Copy :size="14" aria-hidden="true" /> Copy</button>
          </div>
          <input v-if="f.rows === 1" :id="`cap-${f.k}`" v-model="cap[f.k]" type="text" spellcheck="true" @keydown="onKey"
            class="paper mt-1 block h-10 w-full rounded-md px-3 text-sm outline-none focus:border-blue" />
          <textarea v-else :id="`cap-${f.k}`" v-model="cap[f.k]" :rows="f.rows" spellcheck="true" @keydown="onKey"
            class="paper mt-1 block w-full resize-y rounded-md p-3 text-sm leading-6 outline-none focus:border-blue" />
        </div>
      </div>
    </div>
  </section>
</template>
