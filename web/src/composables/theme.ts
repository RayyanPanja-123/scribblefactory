// Light / Dark / System. "system" leaves data-theme off so the CSS follows prefers-color-scheme.
// index.html applies the stored choice before first paint, so there is no flash.
import { ref, watch } from 'vue'

export type Theme = 'light' | 'dark' | 'system'
const KEY = 'sf-theme'

function stored(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

export const theme = ref<Theme>(stored())
watch(theme, (t) => {
  if (t === 'system') delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = t
  try {
    if (t === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, t)
  } catch { /* private mode: the choice lasts this tab only */ }
}, { immediate: true })
