<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { api } from '../api/client'
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
        <section id="preferences" class="scroll-mt-4">
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

        <section id="omniroute" class="scroll-mt-4">
          <h3 class="border-b border-rule pb-2 text-xl font-semibold">OmniRoute</h3>
          <form class="mt-4 max-w-md space-y-5" @submit.prevent="save(form.api_key.trim() || null)">
            <p class="text-sm text-muted">Use your local or remote OmniRoute gateway for OpenAI-compatible model routing.</p>
            <label class="block text-sm font-semibold">Base URL<input v-model="form.base_url" required type="url" placeholder="http://localhost:20128/v1" :class="field" /></label>
            <label class="block text-sm font-semibold">Model<input v-model="form.omniroute_model" required placeholder="cc/claude-opus-4-6" spellcheck="false" :class="field" /><span class="mt-1 block text-xs font-normal text-muted">Use a <code>provider/model</code> id from OmniRoute, or <code>auto</code>.</span></label>
            <label class="block text-sm font-semibold">OmniRoute API key<input v-model="form.api_key" type="password" autocomplete="off" spellcheck="false" :placeholder="data?.has_omniroute_key ? 'Saved: type a new one to replace it' : 'Paste your OmniRoute key'" :class="field" /><span class="mt-1 block text-xs font-normal" :class="data?.has_omniroute_key ? 'text-blue-ink' : 'text-muted'">{{ data?.has_omniroute_key ? `Key saved · ends in ${data.omniroute_key_hint}` : 'No key saved.' }}</span></label>
            <div class="flex flex-wrap gap-2"><button type="submit" class="btn btn-primary" :disabled="saving">Save OmniRoute</button><button v-if="data?.has_omniroute_key" type="button" class="btn btn-secondary" :disabled="saving" @click="save('')">Remove key</button></div>
          </form>
          <div class="mt-8 max-w-2xl text-sm"><h4 class="border-b border-rule pb-2 font-semibold">OmniRoute setup</h4><ol class="mt-4 list-decimal space-y-2 pl-5 text-muted"><li>Install and start it:<pre :class="block">npm install -g omniroute</pre><pre :class="block">omniroute</pre></li><li>Open <a class="underline" href="http://localhost:20128" target="_blank" rel="noopener">localhost:20128</a> and create an API key from the Endpoints page.</li><li>Connect a provider in OmniRoute, then paste its endpoint key above.</li></ol></div>
        </section>

        <section id="gemini" class="scroll-mt-4">
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

        <section id="openrouter" class="scroll-mt-4">
          <h3 class="border-b border-rule pb-2 text-xl font-semibold">OpenRouter</h3>
          <form class="mt-4 max-w-md space-y-5" @submit.prevent="save(form.openrouter_api_key.trim() || null)">
            <p class="text-sm text-muted">Use OpenRouter’s OpenAI-compatible API with free or paid models from multiple providers.</p>
            <label class="block text-sm font-semibold">Model<input v-model="form.openrouter_model" required placeholder="openrouter/free" spellcheck="false" :class="field" /><span class="mt-1 block text-xs font-normal text-muted">Use an OpenRouter model id. <code>openrouter/free</code> routes to an available free model.</span></label>
            <label class="block text-sm font-semibold">OpenRouter API key<input v-model="form.openrouter_api_key" type="password" autocomplete="off" spellcheck="false" :placeholder="data?.has_openrouter_key ? 'Saved: type a new one to replace it' : 'Paste your OpenRouter key'" :class="field" /><span class="mt-1 block text-xs font-normal" :class="data?.has_openrouter_key ? 'text-blue-ink' : 'text-muted'">{{ data?.has_openrouter_key ? `Key saved · ends in ${data.openrouter_key_hint}` : 'No key saved.' }}</span></label>
            <div class="flex flex-wrap gap-2"><button type="submit" class="btn btn-primary" :disabled="saving">Save OpenRouter</button><button v-if="data?.has_openrouter_key" type="button" class="btn btn-secondary" :disabled="saving" @click="save('')">Remove key</button></div>
          </form>
          <p class="mt-8 text-sm text-muted">Create a key at <a class="underline" href="https://openrouter.ai/keys" target="_blank" rel="noopener">OpenRouter Keys</a>.</p>
        </section>
      </div>
    </div>
  </div>
</template>
