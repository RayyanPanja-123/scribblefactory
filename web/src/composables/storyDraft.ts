import { ref, watch } from 'vue'

// The pasted Story Package, shared by the Story Writer and its review page, and kept for the tab's session so a reload
// or a trip back to fix something keeps it.
const KEY = 'story-writer:package'
const read = () => { try { return sessionStorage.getItem(KEY) ?? '' } catch { return '' } }
export const packageText = ref(read())
watch(packageText, (t) => { try { sessionStorage.setItem(KEY, t) } catch { /* private mode: in memory only */ } })
