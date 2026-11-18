// With a configured provider key in Settings, "Build with AI" sends its prompt instead of copy/paste.
import { computed, ref } from 'vue'
import { api, type AiSettings } from '../api/client'
import { toast } from './feedback'

const settings = ref<AiSettings | null>(null)

export function useAutoAi() {
  api.settings().then((s) => (settings.value = s), () => {}) // no settings = the manual flow
  const busy = ref(false)
  const secs = ref(0) // a full prompt takes OmniRoute a minute or more: count up so it doesn't look stuck
  /** the AI's reply text, or undefined after toasting the error */
  async function generate(prompt: string): Promise<string | undefined> {
    busy.value = true
    secs.value = 0
    const tick = setInterval(() => secs.value++, 1000)
    const provider = settings.value?.provider === 'gemini' ? 'Gemini' : settings.value?.provider === 'openrouter' ? 'OpenRouter' : 'OmniRoute'
    toast(`Sent to ${provider}: replies can take a minute or two`, 'info')
    try {
      return (await api.aiComplete(prompt)).text
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'error')
    } finally {
      clearInterval(tick)
      busy.value = false
    }
  }
  const label = computed(() => (busy.value ? `Generating… ${secs.value}s` : 'Generate'))
  return { auto: computed(() => !!settings.value?.has_key), busy, generate, label }
}
