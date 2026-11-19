<script setup lang="ts">
import { Cpu, Save } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { api, type SettingsView } from '../api/client'
import { act, toast } from '../composables/feedback'

// Machine-level options in library/settings.json. Moving to a stronger PC: open this page, check "This PC", and
// pick Auto (or a number) for the render workers. A change applies to the next render job.
const MAX = 16
const view = ref<SettingsView | null>(null)
const auto = ref(true)
const workers = ref(2)
const softwareGl = ref(false)

function fill(v: SettingsView) {
  view.value = v
  const w = v.settings.render_workers
  auto.value = w === 'auto'
  workers.value = typeof w === 'number' ? w : v.machine.recommended_workers
  softwareGl.value = !!v.settings.force_software_gl
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
  || softwareGl.value !== !!view.value.settings.force_software_gl))
const valid = computed(() => auto.value || (Number.isInteger(workers.value) && workers.value >= 1 && workers.value <= MAX))
async function save() {
  const v = await act(() => api.saveSettings({ render_workers: chosen.value, force_software_gl: softwareGl.value }), 'Settings saved')
  if (v) fill(v)
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

      <button class="btn btn-primary" :disabled="!dirty || !valid"><Save :size="16" aria-hidden="true" /> Save</button>
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
