<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { api } from '../api/client'
import ErrorCard from '../components/ErrorCard.vue'
import { act } from '../composables/feedback'
import { useApi } from '../composables/useApi'

// The OmniRoute gateway behind "Build with AI": with a key here, Props/Sets/Creatures generate in one click.
// The key goes to the local API (library/settings.json) and is never sent back to the browser.
const { data, error, loading, reload } = useApi(() => api.settings())
const form = reactive({ base_url: '', model: '', api_key: '' })
watch(data, (s) => s && Object.assign(form, { base_url: s.base_url, model: s.model, api_key: '' }), { immediate: true })

const saving = ref(false)
async function save(api_key: string | null) {
  saving.value = true
  const s = await act(() => api.saveSettings({ base_url: form.base_url.trim(), model: form.model.trim(), api_key }), api_key === '' ? 'API key removed' : 'Settings saved')
  saving.value = false
  if (s) data.value = s
}
const field = 'inset mt-1 block h-10 w-full rounded-md px-4 text-sm text-ink outline-none focus:border-blue'
</script>

<template>
  <div class="max-w-5xl space-y-6">
    <h2 class="font-display text-2xl font-semibold">Settings</h2>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-72" aria-busy="true" aria-label="Loading settings" />
    <div v-else class="grid gap-6 lg:grid-cols-[1fr_340px]">
      <form class="raised space-y-4 p-6" @submit.prevent="save(form.api_key.trim() || null)">
        <div>
          <h3 class="font-display text-lg font-semibold">AI gateway (OmniRoute)</h3>
          <p class="text-xs text-muted">With an API key, “Build with AI” sends the prompt and loads the reply for you. Without one, you copy and paste as usual.</p>
        </div>
        <label class="block text-xs font-semibold text-muted">Base URL
          <input v-model="form.base_url" required type="url" placeholder="http://localhost:20128/v1" :class="field" />
        </label>
        <label class="block text-xs font-semibold text-muted">Model
          <input v-model="form.model" required placeholder="cc/claude-opus-4-6" spellcheck="false" :class="field" />
        </label>
        <label class="block text-xs font-semibold text-muted">API key
          <input v-model="form.api_key" type="password" autocomplete="off" spellcheck="false"
            :placeholder="data?.has_key ? 'Saved: type a new one to replace it' : 'Paste your OmniRoute key'" :class="field" />
        </label>
        <p class="text-xs" :class="data?.has_key ? 'text-blue-ink' : 'text-muted'">
          {{ data?.has_key ? 'Key saved: Build with AI runs automatically.' : 'No key: Build with AI uses copy/paste.' }}</p>
        <div class="flex flex-wrap justify-end gap-2">
          <button v-if="data?.has_key" type="button" class="btn btn-secondary" :disabled="saving" @click="save('')">Remove key</button>
          <button type="submit" class="btn btn-primary" :disabled="saving">Save</button>
        </div>
      </form>

      <details class="raised p-6 text-sm" open>
        <summary class="cursor-pointer font-display text-lg font-semibold">How to get an OmniRoute API key</summary>
        <ol class="mt-3 list-decimal space-y-2 pl-5 text-muted">
          <li>Install and start OmniRoute (Node 22 or 24+): <code>npm install -g omniroute</code> then <code>omniroute</code>.
            Or Docker: <code>docker run -p 20128:20128 diegosouzapw/omniroute:latest</code>.</li>
          <li>Open the dashboard at <a class="underline" href="http://localhost:20128" target="_blank" rel="noopener">localhost:20128</a> and log in.
            The default password is <code>123456</code> unless <code>INITIAL_PASSWORD</code> is set: change it.</li>
          <li>Connect at least one provider: a Claude Code or Gemini CLI subscription, or a provider API key.</li>
          <li>On the <strong>Endpoints</strong> page, create an API key and paste it here.</li>
          <li>Base URL: <code>http://localhost:20128/v1</code>. Model: an id from the dashboard, written <code>provider/model</code>, e.g. <code>cc/claude-opus-4-6</code>.</li>
          <li>Keys are only checked when OmniRoute runs with <code>REQUIRE_API_KEY=true</code>; otherwise any text works as the key.</li>
        </ol>
        <p class="mt-3 text-muted">More: <a class="underline" href="https://github.com/ChrisCompton/omniroute" target="_blank" rel="noopener">github.com/ChrisCompton/omniroute</a></p>
      </details>
    </div>
  </div>
</template>
