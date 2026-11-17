import { ref, shallowRef } from 'vue'

/** Load once on setup. `reload()` shows the skeleton again (retry); `refresh()` keeps the data on screen
 *  (live updates after an event or an action). */
export function useApi<T>(load: () => Promise<T>) {
  const data = shallowRef<T>()
  const error = ref<string>()
  const loading = ref(true)
  async function fetchIt(silent: boolean) {
    if (!silent) loading.value = true
    try {
      data.value = await load()
      error.value = undefined
    } catch (e) {
      if (!silent || !data.value) error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }
  fetchIt(false)
  return { data, error, loading, reload: () => fetchIt(false), refresh: () => fetchIt(true) }
}
