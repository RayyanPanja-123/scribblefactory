import { ref, shallowRef } from 'vue'

/** Load once on setup; `reload` for the retry button. */
export function useApi<T>(load: () => Promise<T>) {
  const data = shallowRef<T>()
  const error = ref<string>()
  const loading = ref(true)
  async function reload() {
    loading.value = true
    error.value = undefined
    try {
      data.value = await load()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }
  reload()
  return { data, error, loading, reload }
}
