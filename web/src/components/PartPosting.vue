<script setup lang="ts">
import { ExternalLink, Instagram, QrCode, RotateCcw, Youtube } from 'lucide-vue-next'
import { reactive } from 'vue'
import { api, type PartModel, type Platform } from '../api/client'
import { act, confirm } from '../composables/feedback'
import { shortDate, today } from '../composables/ui'

// Mark a part posted on each platform (link + date), or replace a posted link. Instagram also offers the phone QR.
const props = defineProps<{ slug: string; part: string; posted: PartModel['posted']; hasFinal: boolean }>()
const emit = defineEmits<{ posted: []; qr: [] }>()

const PLATFORMS: { key: Platform; name: string; icon: typeof Youtube; color: string }[] = [
  { key: 'youtube', name: 'YouTube', icon: Youtube, color: 'text-youtube' },
  { key: 'instagram', name: 'Instagram', icon: Instagram, color: 'text-instagram' },
]
const form = reactive<Record<Platform, { url: string; date: string; replacing: boolean }>>({
  youtube: { url: '', date: today(), replacing: false },
  instagram: { url: '', date: today(), replacing: false },
})
async function replace(pl: Platform) {
  const ok = await confirm({ title: `Replace the ${pl} link?`, body: 'The current link and date are overwritten.', confirm: 'Replace', danger: true })
  if (ok) form[pl].replacing = true
}
async function post(pl: Platform) {
  const f = form[pl]
  const r = await act(() => api.markPosted(props.slug, props.part, { platform: pl, url: f.url.trim(), date: f.date || undefined, force: f.replacing }),
    `Marked posted on ${pl}`)
  if (r) {
    Object.assign(f, { url: '', replacing: false })
    emit('posted')
  }
}
async function reopen() {
  const ok = await confirm({ title: 'Start this part over?', body: 'Clears its posted links, approvals and pipeline stages. Files stay; record a new voice, then Run next.', confirm: 'Start over', danger: true })
  if (ok && await act(() => api.reopen(props.slug, props.part), 'Part reopened')) emit('posted')
}
</script>

<template>
  <div v-for="pl in PLATFORMS" :key="pl.key" class="raised p-5">
    <p class="flex items-center gap-2 font-display text-lg font-semibold">
      <component :is="pl.icon" :size="20" :class="pl.color" aria-hidden="true" />{{ pl.name }}
    </p>
    <template v-if="posted[pl.key] && !form[pl.key].replacing">
      <a :href="posted[pl.key]!.url" target="_blank" rel="noopener noreferrer"
        class="mt-3 flex items-center gap-1 text-sm font-semibold break-all text-blue-ink hover:underline">
        {{ posted[pl.key]!.url }} <ExternalLink :size="14" class="shrink-0" aria-hidden="true" />
      </a>
      <p class="mt-1 text-sm text-muted">posted {{ shortDate(posted[pl.key]!.posted_at) }}</p>
      <button class="btn btn-secondary mt-4" @click="replace(pl.key)">Replace</button>
    </template>
    <form v-else class="mt-3 space-y-3" @submit.prevent="post(pl.key)">
      <label class="block text-xs font-semibold text-muted">Link
        <input v-model="form[pl.key].url" type="url" required placeholder="https://"
          class="inset mt-1 block w-full rounded-md px-4 py-2 text-sm text-ink outline-none focus:border-blue" />
      </label>
      <label class="block text-xs font-semibold text-muted">Date
        <input v-model="form[pl.key].date" type="date" class="inset mt-1 block w-full rounded-md px-4 py-2 text-sm text-ink outline-none focus:border-blue" />
      </label>
      <div class="flex gap-2">
        <button class="btn btn-primary" :disabled="!form[pl.key].url.trim()">Mark posted</button>
        <button v-if="form[pl.key].replacing" type="button" class="btn btn-secondary" @click="form[pl.key].replacing = false">Cancel</button>
      </div>
    </form>
    <div v-if="pl.key === 'instagram' && hasFinal" class="mt-5 border-t border-rule pt-4">
      <p class="text-sm font-semibold">Send video to phone</p>
      <p class="mt-1 text-xs text-muted">Scan this QR code with your phone to download the Instagram-ready video.</p>
      <button type="button" class="btn btn-secondary mt-3" @click="emit('qr')">
        <QrCode :size="16" aria-hidden="true" /> Show phone QR
      </button>
    </div>
  </div>
  <div class="raised p-5">
    <p class="font-display text-lg font-semibold">Start over</p>
    <p class="mt-1 text-sm text-muted">Video taken down or redoing it? Clear posts, approvals and stages.</p>
    <button type="button" class="btn btn-secondary mt-4" @click="reopen">
      <RotateCcw :size="16" aria-hidden="true" /> Start part over
    </button>
  </div>
</template>
