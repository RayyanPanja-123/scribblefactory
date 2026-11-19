<script setup lang="ts">
import { Cpu, Hash, KeyRound, Megaphone, Save, Trash2 } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { api, type Settings, type SettingsView } from '../api/client'
import { act, toast } from '../composables/feedback'

// Machine-level options in library/settings.json. Moving to a stronger PC: open this page, check "This PC", and
// pick Auto (or a number) for the render workers. A change applies to the next render job.
const MAX = 16
const view = ref<SettingsView | null>(null)
const auto = ref(true)
const workers = ref(2)
const softwareGl = ref(false)
// handles on every part's closing "Follow for more" screen (finish); empty ones are left off it
const SOCIALS = [['youtube', 'YouTube', '@yourchannel'], ['instagram', 'Instagram', '@yourname'], ['facebook', 'Facebook', 'yourpage']] as const
const socials = ref({ youtube: '', instagram: '', facebook: '' })
const brandTags = ref('') // on every Gemini-written caption, after the story's own tags
const captionModel = ref('') // free Gemini model tried first; the API falls through the other free ones
// the Gemini key (captions only) is write-only: the page only ever learns whether one is set
const geminiKey = ref('')
async function saveKey(key: string) {
  const v = await act(() => api.saveGeminiKey(key), key ? 'Gemini key saved' : 'Gemini key removed')
  if (v) {
    view.value = { ...view.value!, gemini_key_last4: v.gemini_key_last4 }
    geminiKey.value = ''
  }
}

function fill(v: SettingsView) {
  view.value = v
  const w = v.settings.render_workers
  auto.value = w === 'auto'
  workers.value = typeof w === 'number' ? w : v.machine.recommended_workers
  softwareGl.value = !!v.settings.force_software_gl
  socials.value = { ...socials.value, ...v.settings.socials }
  brandTags.value = v.settings.brand_tags ?? ''
  captionModel.value = v.settings.caption_model ?? v.caption_models[0]
}
onMounted(async () => {
  try {
    fill(await api.settings())
  } catch (e) {
    toast(e instanceof Error ? e.message : String(e), 'error')
  }
})

const chosen = computed(() => (auto.value ? 'auto' : workers.value))
const dirty = computed(() => !!view.value && (chosen.value !== view.value.settings.render_workers
  || softwareGl.value !== !!view.value.settings.force_software_gl
  || brandTags.value.trim() !== (view.value.settings.brand_tags ?? '')
  || SOCIALS.some(([k]) => socials.value[k].trim() !== (view.value!.settings.socials?.[k] ?? ''))))
const valid = computed(() => auto.value || (Number.isInteger(workers.value) && workers.value >= 1 && workers.value <= MAX))
async function save() {
  const v = await act(() => api.saveSettings({ render_workers: chosen.value, force_software_gl: softwareGl.value,
    socials: { youtube: socials.value.youtube.trim(), instagram: socials.value.instagram.trim(), facebook: socials.value.facebook.trim() },
    brand_tags: brandTags.value.trim(), caption_model: captionModel.value as Settings['caption_model'] }), 'Settings saved')
  if (v) fill(v)
}
// saved on its own, from the last saved settings: unsaved edits in the form above stay as they are
async function saveModel() {
  const caption_model = captionModel.value as Settings['caption_model']
  const v = await act(() => api.saveSettings({ ...view.value!.settings, caption_model }), 'Caption model saved')
  if (v) view.value = { ...view.value!, settings: { ...view.value!.settings, caption_model } }
  else captionModel.value = view.value!.settings.caption_model ?? view.value!.caption_models[0]
}
const m = computed(() => view.value?.machine)
const field = 'inset mt-1 block h-10 w-28 rounded-md px-4 text-sm text-ink outline-none focus:border-blue'
</script>

<template>
  <div class="max-w-3xl space-y-5">
    <div class="flex flex-wrap items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Settings</h2>
      <span class="text-sm text-muted">for this PC · saved in library/settings.json</span>
    </div>

    <section v-if="m" class="raised p-4" aria-labelledby="this-pc">
      <h3 id="this-pc" class="flex items-center gap-2 text-sm font-semibold"><Cpu :size="16" aria-hidden="true" /> This PC</h3>
      <dl class="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm">
        <dt class="text-muted">CPU threads</dt><dd class="num">{{ m.cpu_threads }}</dd>
        <dt class="text-muted">RAM</dt><dd class="num">{{ m.ram_gb ? `${m.ram_gb} GB` : 'unknown' }}</dd>
        <dt class="text-muted">GPU</dt><dd class="break-words">{{ m.gpu ?? 'not known yet: shows after the first render' }}</dd>
        <dt class="text-muted">Recommended</dt>
        <dd><span class="num font-semibold">{{ m.recommended_workers }}</span> render worker{{ m.recommended_workers === 1 ? '' : 's' }}</dd>
      </dl>
      <p class="mt-3 text-xs text-muted">About one worker per CPU core, at most one per 1.5 GB of RAM and at most 8.
        An integrated GPU (Intel UHD / Iris), software rendering, or a GPU not known yet gets 2: on a new PC, render once and Auto raises it on a strong GPU.</p>
    </section>

    <form v-if="view" class="raised space-y-5 p-4" aria-label="Render settings" @submit.prevent="save">
      <fieldset>
        <legend class="text-sm font-semibold">Render workers</legend>
        <p class="mt-1 text-xs text-muted">Parallel browsers per render. More only helps with a real GPU and enough RAM
          (each worker is one Chromium); if renders fail or slow down, lower it.</p>
        <div class="mt-3 flex flex-wrap items-end gap-4">
          <label class="flex items-center gap-2 text-sm">
            <input v-model="auto" type="radio" :value="true" name="workers-mode" />
            Auto <span class="text-muted">({{ m?.recommended_workers }} on this PC)</span>
          </label>
          <label class="flex items-center gap-2 text-sm">
            <input v-model="auto" type="radio" :value="false" name="workers-mode" /> Fixed
          </label>
          <label class="text-xs font-semibold text-muted">Workers
            <input v-model.number="workers" type="number" min="1" :max="MAX" step="1" :disabled="auto" :class="field" />
          </label>
        </div>
        <p v-if="!valid" class="mt-2 text-xs text-red-ink">Pick 1 to {{ MAX }}.</p>
        <p class="mt-2 text-xs text-muted">The next render uses <span class="num">{{ view.workers_now }}</span>
          · a running render keeps its workers.</p>
      </fieldset>

      <label class="flex items-start gap-2 text-sm">
        <input v-model="softwareGl" type="checkbox" class="mt-1" />
        <span>Force software rendering (SwiftShader)<span class="block text-xs text-muted">Debugging only: much slower, but
          works without a GPU. Renders, test renders and frames rendered before are redone when this changes.</span></span>
      </label>

      <fieldset>
        <legend class="flex items-center gap-2 text-sm font-semibold"><Megaphone :size="16" aria-hidden="true" /> Follow screen</legend>
        <p class="mt-1 text-xs text-muted">Every part ends on a silent black screen: "Follow for more" and these handles.
          Leave one empty to leave it off. A change shows after re-running a part's final stage.</p>
        <div class="mt-3 grid gap-3 sm:grid-cols-3">
          <label v-for="[k, name, hint] in SOCIALS" :key="k" class="text-xs font-semibold text-muted">{{ name }}
            <input v-model="socials[k]" type="text" maxlength="60" :placeholder="hint" autocomplete="off"
              class="inset mt-1 block h-10 w-full rounded-md px-3 text-sm text-ink outline-none focus:border-blue" />
          </label>
        </div>
      </fieldset>

      <label class="block text-sm font-semibold"><span class="flex items-center gap-2"><Hash :size="16" aria-hidden="true" /> Brand tags</span>
        <span class="mt-1 block text-xs font-normal text-muted">Hashtags Gemini puts on every YouTube and Instagram caption, after the story's own.</span>
        <input v-model="brandTags" type="text" maxlength="300" placeholder="#scribblefactory #stickman" autocomplete="off"
          class="inset mt-2 block h-10 w-full rounded-md px-3 text-sm font-normal text-ink outline-none focus:border-blue" />
      </label>

      <button class="btn btn-primary" :disabled="!dirty || !valid"><Save :size="16" aria-hidden="true" /> Save</button>
    </form>

    <form v-if="view" class="raised p-4" aria-labelledby="gemini" @submit.prevent="saveKey(geminiKey.trim())">
      <h3 id="gemini" class="flex items-center gap-2 text-sm font-semibold"><KeyRound :size="16" aria-hidden="true" /> Gemini API key</h3>
      <p class="mt-1 text-xs text-muted">Only used to write YouTube and Instagram captions. Get one at aistudio.google.com/apikey.
        Kept in library/settings.json on this PC and never shown again, only its last 4 characters.</p>
      <p class="mt-2 text-sm" :class="view.gemini_key_last4 ? 'text-green-ink' : 'text-muted'">
        <template v-if="view.gemini_key_last4">Key set, ending in <span class="num font-semibold">••••{{ view.gemini_key_last4 }}</span></template>
        <template v-else>No key set.</template></p>
      <div class="mt-2 flex flex-wrap gap-2">
        <label class="sr-only" for="gemini-key">Gemini API key</label>
        <input id="gemini-key" v-model="geminiKey" type="password" maxlength="200" autocomplete="off" spellcheck="false"
          :placeholder="view.gemini_key_last4 ? 'Paste a new key to replace it' : 'Paste your key'"
          class="inset block h-10 min-w-0 flex-1 rounded-md px-3 text-sm text-ink outline-none focus:border-blue" />
        <button class="btn btn-primary" :disabled="!geminiKey.trim()"><Save :size="16" aria-hidden="true" /> Save key</button>
        <button v-if="view.gemini_key_last4" type="button" class="btn btn-secondary" @click="saveKey('')"><Trash2 :size="16" aria-hidden="true" /> Remove</button>
      </div>
      <label class="mt-4 block text-sm font-semibold">Caption model
        <span class="mt-1 block text-xs font-normal text-muted">Free Gemini models only, saved when picked. When this one is
          busy or out of quota, the next one in the list writes the captions.</span>
        <select v-model="captionModel" class="inset mt-2 block h-10 w-full rounded-md px-3 text-sm font-normal text-ink outline-none focus:border-blue sm:w-80"
          @change="saveModel">
          <option v-for="id in view.caption_models" :key="id" :value="id">{{ id }}</option>
        </select>
      </label>
    </form>

    <section v-if="view" class="raised p-4" aria-labelledby="examples">
      <h3 id="examples" class="text-sm font-semibold">Recommended for other PCs</h3>
      <p class="mt-1 text-xs text-muted">What Auto picks on a typical machine. Moving to a new PC: leave it on Auto, or
        start from this and measure.</p>
      <table class="mt-3 w-full text-sm">
        <thead><tr class="text-left text-xs text-muted"><th class="py-1 font-semibold">PC</th><th class="py-1 text-right font-semibold">Workers</th></tr></thead>
        <tbody class="divide-y divide-rule">
          <tr v-for="e in view.examples" :key="e.pc"><td class="py-1.5">{{ e.pc }}</td><td class="num py-1.5 text-right">{{ e.workers }}</td></tr>
        </tbody>
      </table>
    </section>
  </div>
</template>
