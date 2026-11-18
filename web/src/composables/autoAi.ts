// With an OmniRoute API key in Settings, "Build with AI" sends its prompt through the API instead of copy/paste.
import { computed, ref } from 'vue'
import { api, type AiSettings } from '../api/client'
import { toast } from './feedback'

const settings = ref<AiSettings | null>(null)

export function useAutoAi() {
  api.settings().then((s) => (settings.value = s), () => {}) // no settings = the manual flow
  const busy = ref(false)
  /** the AI's reply text, or undefined after toasting the error */
  async function generate(prompt: string): Promise<string | undefined> {
    busy.value = true
    try {
      return (await api.aiComplete(prompt)).text
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'error')
    } finally {
      busy.value = false
    }
  }
  return { auto: computed(() => !!settings.value?.has_key), busy, generate }
}
