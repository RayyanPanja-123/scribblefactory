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
const field = 'inset mt-1.5 block h-9 w-full rounded-md px-3 text-sm font-normal text-ink outline-none focus:border-blue'
// GitHub-style side nav: one item per section below
const sections = [{ id: 'ai-gateway', label: 'AI gateway' }, { id: 'api-key', label: 'Getting an API key' }]
const active = ref(sections[0].id)
// select-all: one click selects the whole command for Ctrl+C
const block = 'inset my-1.5 overflow-x-auto rounded-md px-3 py-2 font-mono text-xs leading-5 text-ink select-all'
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="font-display text-2xl font-semibold">Settings</h2>
      <p class="text-sm text-muted">Manage how Scribble Factory talks to your AI gateway.</p>
    </div>
    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="skeleton h-72" aria-busy="true" aria-label="Loading settings" />
    <div v-else class="grid gap-8 md:grid-cols-[13rem_minmax(0,1fr)]">
      <nav aria-label="Settings sections" class="md:sticky md:top-4 md:self-start">
        <ul class="space-y-0.5">
          <li v-for="s in sections" :key="s.id">
            <a :href="`#${s.id}`" :aria-current="active === s.id ? 'true' : undefined" @click="active = s.id"
              class="relative block rounded-md px-3 py-1.5 text-sm hover:bg-well"
              :class="active === s.id ? 'bg-well font-semibold text-ink before:absolute before:inset-y-1 before:-left-2 before:w-1 before:rounded-full before:bg-blue' : 'text-muted'">
              {{ s.label }}</a>
          </li>
        </ul>
      </nav>

      <div class="space-y-10">
        <section id="ai-gateway" class="scroll-mt-4">
          <h3 class="border-b border-rule pb-2 text-xl font-semibold">AI gateway</h3>
          <form class="mt-4 max-w-md space-y-5" @submit.prevent="save(form.api_key.trim() || null)">
            <p class="text-sm text-muted">With an OmniRoute API key, “Build with AI” sends the prompt and loads the reply for you. Without one, you copy and paste as usual.</p>
            <label class="block text-sm font-semibold">Base URL
              <input v-model="form.base_url" required type="url" placeholder="http://localhost:20128/v1" :class="field" />
            </label>
            <label class="block text-sm font-semibold">Model
              <input v-model="form.model" required placeholder="cc/claude-opus-4-6" spellcheck="false" :class="field" />
              <span class="mt-1 block text-xs font-normal text-muted">Written <code>provider/model</code>, as listed in the OmniRoute dashboard, or <code>auto</code> to use all connected providers.</span>
            </label>
            <label class="block text-sm font-semibold">API key
              <input v-model="form.api_key" type="password" autocomplete="off" spellcheck="false"
                :placeholder="data?.has_key ? 'Saved: type a new one to replace it' : 'Paste your OmniRoute key'" :class="field" />
              <span class="mt-1 block text-xs font-normal" :class="data?.has_key ? 'text-blue-ink' : 'text-muted'">
                {{ data?.has_key ? 'Key saved: Build with AI runs automatically.' : 'No key: Build with AI uses copy/paste.' }}</span>
            </label>
            <div class="flex flex-wrap gap-2">
              <button type="submit" class="btn btn-primary" :disabled="saving">Save settings</button>
              <button v-if="data?.has_key" type="button" class="btn btn-secondary" :disabled="saving" @click="save('')">Remove key</button>
            </div>
          </form>
        </section>

        <section id="api-key" class="scroll-mt-4 text-sm">
          <h3 class="border-b border-rule pb-2 text-xl font-semibold">Getting an API key</h3>
        <ol class="mt-4 list-decimal space-y-2 pl-5 text-muted">
          <li>Install and start OmniRoute (Node 22 or 24+):
            <pre :class="block">npm install -g omniroute</pre>
            then start it:
            <pre :class="block">omniroute</pre>
            Or with Docker:
            <pre :class="block">docker run -p 20128:20128 diegosouzapw/omniroute:latest</pre></li>
          <li>Open the dashboard at <a class="underline" href="http://localhost:20128" target="_blank" rel="noopener">localhost:20128</a> and log in.
            The default password is <code>123456</code> unless <code>INITIAL_PASSWORD</code> is set: change it.</li>
          <li>Connect at least one provider: a Claude Code or Gemini CLI subscription, or a provider API key.</li>
          <li>On the <strong>Endpoints</strong> page, create an API key and paste it here.</li>
          <li>Base URL:
            <pre :class="block">http://localhost:20128/v1</pre>
            Model: an id from the dashboard, written <code>provider/model</code>, e.g.
            <pre :class="block">cc/claude-opus-4-6</pre>
            Or let OmniRoute pick: it chains every provider you've connected (free ones included) and falls back to the next when one runs out of quota or fails.
            <pre :class="block">auto</pre></li>
          <li>Keys are only checked when OmniRoute runs with this set; otherwise any text works as the key.
            <pre :class="block">REQUIRE_API_KEY=true</pre></li>
        </ol>
        <p class="mt-3 text-muted">More: <a class="underline" href="https://github.com/diegosouzapw/OmniRoute" target="_blank" rel="noopener">github.com/diegosouzapw/OmniRoute</a></p>
        </section>
      </div>
    </div>
  </div>
</template>
