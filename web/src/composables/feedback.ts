// Toasts, the confirm dialog and the image zoom: app-wide singletons rendered once in App.vue.
import { ref, shallowRef } from 'vue'

export type ToastKind = 'ok' | 'error' | 'info'
export const toasts = ref<{ id: number; text: string; kind: ToastKind }[]>([])
let nextId = 1

export function toast(text: string, kind: ToastKind = 'info') {
  const id = nextId++
  toasts.value.push({ id, text, kind })
  setTimeout(() => dismiss(id), kind === 'error' ? 8000 : 4000)
}
export const dismiss = (id: number) => (toasts.value = toasts.value.filter((t) => t.id !== id))

/** Run an action: toast its result, or the API's message verbatim (409s explain themselves). */
export async function act<T>(fn: () => Promise<T>, ok: string): Promise<T | undefined> {
  try {
    const r = await fn()
    toast(ok, 'ok')
    return r
  } catch (e) {
    toast(e instanceof Error ? e.message : String(e), 'error')
    return undefined
  }
}

export interface ConfirmOptions {
  title: string
  body: string
  confirm: string
  danger?: boolean
}
export const confirmState = shallowRef<(ConfirmOptions & { resolve: (ok: boolean) => void }) | null>(null)

export function confirm(o: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    confirmState.value = {
      ...o,
      resolve: (ok) => {
        confirmState.value = null
        resolve(ok)
      },
    }
  })
}

export const zoomed = ref<{ src: string; alt: string } | null>(null)
export const zoom = (src: string, alt: string) => (zoomed.value = { src, alt })
