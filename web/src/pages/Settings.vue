<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { BadgeCheck, CircleDollarSign } from 'lucide-vue-next'
import { api, type OmniRouteModels } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import { act } from '../composables/feedback'
import { useApi } from '../composables/useApi'

const { data, error, loading, reload } = useApi(() => api.settings())
const form = reactive({ provider: 'omniroute' as 'omniroute' | 'gemini' | 'openrouter', base_url: '', omniroute_model: '', gemini_model: '', openrouter_model: '', api_key: '', gemini_api_key: '', openrouter_api_key: '' })
watch(data, (s) => s && Object.assign(form, { provider: s.provider, base_url: s.base_url, omniroute_model: s.omniroute_model, gemini_model: s.gemini_model, openrouter_model: s.openrouter_model, api_key: '', gemini_api_key: '', openrouter_api_key: '' }), { immediate: true })
const geminiModels = ref<string[]>([])
watch(data, (s) => { if (s?.gemini_model && !geminiModels.value.length) geminiModels.value = [s.gemini_model] }, { immediate: true })

const saving = ref(false)
const testingGemini = ref(false)
const omniModels = ref<OmniRouteModels | null>(null)
const omniModelsError = ref('')
const loadingOmniModels = ref(false)
const omniPriceFilter = ref<'all' | 'free' | 'paid'>('all')
let omniWatch: ReturnType<typeof setInterval> | undefined
async function refreshOmniModels(showError = true) {
  if (form.provider !== 'omniroute') return
  loadingOmniModels.value = true
  if (showError) omniModelsError.value = ''
  try {
    omniModels.value = await api.omnirouteModels()
  } catch (e) {
    if (showError) omniModelsError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loadingOmniModels.value = false
  }
}
watch(() => form.provider, (provider) => {
  if (provider === 'omniroute') refreshOmniModels(false)
})
function useOmniModel(model: string) {
  form.omniroute_model = model
}
const modelPricing = (model: OmniRouteModels['models'][number]) => model.is_free === true ? 'Free' : 'Paid / varies'
const filteredOmniModels = computed(() => {
  const models = omniModels.value?.models ?? []
  if (omniPriceFilter.value === 'free') return models.filter((model) => model.is_free === true)
  if (omniPriceFilter.value === 'paid') return models.filter((model) => model.is_free !== true)
  return models
})
onMounted(() => {
  refreshOmniModels(false)
  omniWatch = setInterval(() => refreshOmniModels(false), 30000)
})
onUnmounted(() => { if (omniWatch) clearInterval(omniWatch) })
async function loadGeminiModels() {
  testingGemini.value = true
  const r = await act(() => api.geminiModels(form.gemini_api_key.trim() || null), 'Gemini models loaded')
  testingGemini.value = false
  if (r) {
    geminiModels.value = r.models
    if (!r.models.includes(form.gemini_model)) form.gemini_model = r.recommended
  }
}
async function save(apiKey: string | null = null) {
  saving.value = true
  const s = await act(() => api.saveSettings({
    provider: form.provider,
    base_url: form.provider === 'openrouter' ? 'https://openrouter.ai/api/v1' : form.base_url.trim() === 'https://openrouter.ai/api/v1' ? 'http://localhost:20128/v1' : form.base_url.trim() || 'http://localhost:20128/v1',
    model: form.provider === 'omniroute' ? form.omniroute_model.trim() : form.provider === 'gemini' ? form.gemini_model.trim() : form.openrouter_model.trim(),
    omniroute_model: form.omniroute_model.trim(),
    gemini_model: form.gemini_model.trim(),
    openrouter_model: form.openrouter_model.trim(),
    api_key: form.provider === 'omniroute' ? apiKey : null,
    gemini_api_key: form.provider === 'gemini' ? (apiKey === '' ? '' : form.gemini_api_key.trim() || null) : null,
    openrouter_api_key: form.provider === 'openrouter' ? (apiKey === '' ? '' : form.openrouter_api_key.trim() || null) : null,
  }), apiKey === '' ? 'API key removed' : 'Settings saved')
  saving.value = false
  if (s) data.value = s
}

const field = 'inset mt-1.5 block h-9 w-full rounded-md px-3 text-sm font-normal text-ink outline-none focus:border-blue'
const sections = [{ id: 'preferences', label: 'Preferences' }, { id: 'omniroute', label: 'OmniRoute' }, { id: 'gemini', label: 'Gemini' }, { id: 'openrouter', label: 'OpenRouter' }]
const active = ref(sections[0].id)
const block = 'inset my-1.5 overflow-x-auto rounded-md px-3 py-2 font-mono text-xs leading-5 text-ink select-all'
</script>

<template>
  <div class="space-y-6">
    <div><h2 class="font-display text-2xl font-semibold">Settings</h2><p class="text-sm text-muted">Choose an AI provider and configure its connection.</p></div>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-72" aria-busy="true" aria-label="Loading settings" />
    <div v-else class="grid gap-8 md:grid-cols-[13rem_minmax(0,1fr)]">
      <nav aria-label="Settings sections" class="md:sticky md:top-4 md:self-start"><ul class="space-y-0.5">
        <li v-for="s in sections" :key="s.id"><a :href="`#${s.id}`" :aria-current="active === s.id ? 'true' : undefined" @click="active = s.id"
          class="relative block rounded-md px-3 py-1.5 text-sm hover:bg-well" :class="active === s.id ? 'bg-well font-semibold text-ink before:absolute before:inset-y-1 before:-left-2 before:w-1 before:rounded-full before:bg-blue' : 'text-muted'">{{ s.label }}</a></li>
      </ul></nav>

      <div class="space-y-10">
        <Transition name="settings-panel" mode="out-in">
        <section v-if="active === 'preferences'" id="preferences">
          <h3 class="border-b border-rule pb-2 text-xl font-semibold">Preferences</h3>
          <form class="mt-4 max-w-md space-y-5" @submit.prevent="save()">
            <p class="text-sm text-muted">Select which configured provider powers “Build with AI”. Configure each provider in its own tab.</p>
            <label class="block text-sm font-semibold">Active provider
              <select v-model="form.provider" :class="field"><option value="omniroute">OmniRoute</option><option value="gemini">Google Gemini</option><option value="openrouter">OpenRouter</option></select>
            </label>
            <p class="text-xs text-muted">{{ form.provider === 'gemini' ? (data?.has_gemini_key ? 'Gemini is configured and ready.' : 'Gemini needs an API key in the Gemini tab.') : form.provider === 'openrouter' ? (data?.has_openrouter_key ? 'OpenRouter is configured and ready.' : 'OpenRouter needs an API key in the OpenRouter tab.') : (data?.has_omniroute_key ? 'OmniRoute is configured and ready.' : 'OmniRoute needs an API key in the OmniRoute tab.') }}</p>
            <button type="submit" class="btn btn-primary" :disabled="saving">Save preference</button>
          </form>
        </section>

        <section v-else-if="active === 'omniroute'" id="omniroute">
          <h3 class="border-b border-rule pb-2 text-xl font-semibold">OmniRoute</h3>
          <form class="mt-4 max-w-md space-y-5" @submit.prevent="save(form.api_key.trim() || null)">
            <p class="text-sm text-muted">Use your local or remote OmniRoute gateway for OpenAI-compatible model routing.</p>
            <label class="block text-sm font-semibold">Base URL<input v-model="form.base_url" required type="url" placeholder="http://localhost:20128/v1" :class="field" /></label>
            <label class="block text-sm font-semibold">Model<input v-model="form.omniroute_model" required placeholder="cc/claude-opus-4-6" spellcheck="false" :class="field" /><span class="mt-1 block text-xs font-normal text-muted">Use a <code>provider/model</code> id from OmniRoute, or <code>auto</code>.</span></label>
            <label class="block text-sm font-semibold">OmniRoute API key<input v-model="form.api_key" type="password" autocomplete="off" spellcheck="false" :placeholder="data?.has_omniroute_key ? 'Saved: type a new one to replace it' : 'Paste your OmniRoute key'" :class="field" /><span class="mt-1 block text-xs font-normal" :class="data?.has_omniroute_key ? 'text-blue-ink' : 'text-muted'">{{ data?.has_omniroute_key ? `Key saved · ends in ${data.omniroute_key_hint}` : 'No key saved.' }}</span></label>
            <div class="flex flex-wrap gap-2"><button type="submit" class="btn btn-primary" :disabled="saving">Save OmniRoute</button><button v-if="data?.has_omniroute_key" type="button" class="btn btn-secondary" :disabled="saving" @click="save('')">Remove key</button></div>
          </form>
          <div class="mt-8 max-w-2xl text-sm"><h4 class="border-b border-rule pb-2 font-semibold">OmniRoute setup</h4><ol class="mt-4 list-decimal space-y-2 pl-5 text-muted"><li>Install and start it:<pre :class="block">npm install -g omniroute</pre><pre :class="block">omniroute</pre></li><li>Open <a class="underline" href="http://localhost:20128" target="_blank" rel="noopener">localhost:20128</a> and create an API key from the Endpoints page.</li><li>Connect a provider in OmniRoute, then paste its endpoint key above.</li></ol></div>
          <div class="mt-8 max-w-2xl">
            <div class="flex items-center gap-3 border-b border-rule pb-2"><h4 class="font-semibold">Available models</h4><span v-if="omniModels" class="text-xs text-muted">{{ omniModels.models.length }} found · checked {{ new Date(omniModels.checked_at).toLocaleTimeString() }}</span><button type="button" class="btn btn-secondary ml-auto px-3 py-1 text-xs" :disabled="loadingOmniModels" @click="refreshOmniModels()">{{ loadingOmniModels ? 'Checking…' : 'Refresh' }}</button></div>
            <div v-if="omniModels" class="mt-3 flex flex-wrap gap-1 rounded-md border border-rule bg-well p-1" role="group" aria-label="Filter models by pricing"><button v-for="filter in [{ id: 'all', label: 'All' }, { id: 'free', label: 'Free' }, { id: 'paid', label: 'Paid / varies' }]" :key="filter.id" type="button" class="rounded px-3 py-1.5 text-xs font-semibold transition-colors" :class="omniPriceFilter === filter.id ? 'bg-panel text-ink shadow-[var(--shadow-sheet)]' : 'text-muted hover:text-ink'" @click="omniPriceFilter = filter.id as 'all' | 'free' | 'paid'">{{ filter.label }}</button></div>
            <p v-if="omniModelsError" class="mt-3 text-sm text-red-ink">{{ omniModelsError }}</p>
            <p v-else-if="!omniModels && loadingOmniModels" class="mt-3 text-sm text-muted">Checking the OmniRoute gateway…</p>
            <p v-else-if="omniModels && !omniModels.models.length" class="mt-3 text-sm text-muted">No models are exposed by this OmniRoute key. Connect a provider in the OmniRoute dashboard.</p>
            <p v-else-if="omniModels && !filteredOmniModels.length" class="mt-3 text-sm text-muted">No models match this pricing filter.</p>
            <div v-else-if="omniModels" class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <article v-for="model in filteredOmniModels" :key="model.id" class="inset flex min-h-36 flex-col justify-between gap-4 p-4">
                <div class="min-w-0"><div class="flex items-start gap-2"><component :is="model.is_free === true ? BadgeCheck : CircleDollarSign" :size="17" class="mt-0.5 shrink-0" :class="model.is_free === true ? 'text-green-ink' : 'text-amber-ink'" aria-hidden="true" /><code class="break-all text-sm font-semibold">{{ model.id }}</code></div><p v-if="model.owned_by" class="mt-2 truncate text-xs text-muted">{{ model.owned_by }}</p></div>
                <div class="flex items-center justify-between gap-2"><span class="text-xs font-semibold" :class="model.is_free === true ? 'text-green-ink' : 'text-amber-ink'"><component :is="model.is_free === true ? BadgeCheck : CircleDollarSign" :size="13" class="mr-1 inline" aria-hidden="true" />{{ modelPricing(model) }}</span><span v-if="model.context_window" class="text-xs text-muted">{{ model.context_window.toLocaleString() }} context</span></div>
                <button type="button" class="btn btn-secondary w-full px-2 py-1.5 text-xs" @click="useOmniModel(model.id)">{{ form.omniroute_model === model.id ? 'Selected model' : 'Use this model' }}</button>
              </article>
            </div>
            <p class="mt-2 text-xs text-muted">This list watches the models available through the configured key. Provider quotas and account connections remain managed in <a class="underline" href="http://localhost:20128" target="_blank" rel="noopener">OmniRoute</a>.</p>
          </div>
        </section>

        <section v-else-if="active === 'gemini'" id="gemini">
          <h3 class="border-b border-rule pb-2 text-xl font-semibold">Gemini</h3>
          <form class="mt-4 max-w-md space-y-5" @submit.prevent="save(form.gemini_api_key.trim() || null)">
            <p class="text-sm text-muted">Call Google Gemini directly with your Gemini API key. The key remains on the local API server.</p>
            <label class="block text-sm font-semibold">Model
              <select v-if="geminiModels.length" v-model="form.gemini_model" required :class="field"><option v-for="model in geminiModels" :key="model" :value="model">{{ model }}</option></select>
              <input v-else v-model="form.gemini_model" required placeholder="gemini-2.5-flash" spellcheck="false" :class="field" />
              <span class="mt-1 block text-xs font-normal text-muted">Enter a key and test it to load the Gemini models available to that key.</span>
            </label>
            <label class="block text-sm font-semibold">Gemini API key<input v-model="form.gemini_api_key" type="password" autocomplete="off" spellcheck="false" :placeholder="data?.has_gemini_key ? 'Saved: type a new one to replace it' : 'Paste your Gemini API key'" :class="field" /><span class="mt-1 block text-xs font-normal" :class="data?.has_gemini_key ? 'text-blue-ink' : 'text-muted'">{{ data?.has_gemini_key ? `Key saved · ends in ${data.gemini_key_hint}` : 'No key saved.' }}</span></label>
            <div class="flex flex-wrap gap-2"><button type="button" class="btn btn-secondary" :disabled="saving || testingGemini" @click="loadGeminiModels">{{ testingGemini ? 'Loading models…' : 'Test key / load models' }}</button><button type="submit" class="btn btn-primary" :disabled="saving">Save Gemini</button><button v-if="data?.has_gemini_key" type="button" class="btn btn-secondary" :disabled="saving" @click="save('')">Remove key</button></div>
          </form>
          <p class="mt-8 text-sm text-muted">Create a key in <a class="underline" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">Google AI Studio</a>, then paste it above.</p>
        </section>

        <section v-else-if="active === 'openrouter'" id="openrouter">
          <h3 class="border-b border-rule pb-2 text-xl font-semibold">OpenRouter</h3>
          <form class="mt-4 max-w-md space-y-5" @submit.prevent="save(form.openrouter_api_key.trim() || null)">
            <p class="text-sm text-muted">Use OpenRouter’s OpenAI-compatible API with free or paid models from multiple providers.</p>
            <label class="block text-sm font-semibold">Model<input v-model="form.openrouter_model" required placeholder="openrouter/free" spellcheck="false" :class="field" /><span class="mt-1 block text-xs font-normal text-muted">Use an OpenRouter model id. <code>openrouter/free</code> routes to an available free model.</span></label>
            <label class="block text-sm font-semibold">OpenRouter API key<input v-model="form.openrouter_api_key" type="password" autocomplete="off" spellcheck="false" :placeholder="data?.has_openrouter_key ? 'Saved: type a new one to replace it' : 'Paste your OpenRouter key'" :class="field" /><span class="mt-1 block text-xs font-normal" :class="data?.has_openrouter_key ? 'text-blue-ink' : 'text-muted'">{{ data?.has_openrouter_key ? `Key saved · ends in ${data.openrouter_key_hint}` : 'No key saved.' }}</span></label>
            <div class="flex flex-wrap gap-2"><button type="submit" class="btn btn-primary" :disabled="saving">Save OpenRouter</button><button v-if="data?.has_openrouter_key" type="button" class="btn btn-secondary" :disabled="saving" @click="save('')">Remove key</button></div>
          </form>
          <p class="mt-8 text-sm text-muted">Create a key at <a class="underline" href="https://openrouter.ai/keys" target="_blank" rel="noopener">OpenRouter Keys</a>.</p>
        </section>
        </Transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-panel-enter-active,
.settings-panel-leave-active {
  transition: opacity 180ms ease, transform 220ms cubic-bezier(.2, .8, .2, 1);
}

.settings-panel-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.settings-panel-leave-to {
  opacity: 0;
  transform: translateY(-5px);
}
</style>
