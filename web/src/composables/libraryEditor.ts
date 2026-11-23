import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { slugify } from '../lib/slug'
import { act, confirm, toast } from './feedback'

/** What the five library editors (props, sets, actions, creatures, wardrobe) share: /<kind>/new or /<kind>/<id>, a
 *  new one's id following its name until edited, save (a cleared list toasts; a new one moves to its own page) and
 *  delete (confirm, then back to the list). Each page keeps its own form, checks and preview. */
export function useLibraryEditor(o: {
  id: () => string // the route's id: 'new' for a new one
  base: string // the list page, e.g. '/props'
  form: { id: string; name: string; idEdited: boolean }
  custom: () => { id: string }[] | undefined // the saved custom items; undefined while loading
  toId?: (name: string) => string // a new one's id from its name
}) {
  const router = useRouter()
  const isNew = computed(() => o.id() === 'new')
  const missing = computed(() => !isNew.value && !!o.custom() && !o.custom()!.some((x) => x.id === o.id()))
  watch(() => o.form.name, (n) => { if (isNew.value && !o.form.idEdited) o.form.id = (o.toId ?? slugify)(n) })

  const saving = ref(false)
  /** call the API; on success apply the catalog it returns, then (a new one) go to its page */
  async function save<C>(call: () => Promise<C>, done: string, id: string, apply?: (c: C) => void) {
    saving.value = true
    const c = await act(call, done)
    saving.value = false
    if (!c) return
    const cleared = (c as { cleared?: string[] }).cleared
    if (cleared?.length) toast(`Drawing changed: approval cleared for ${cleared.join(', ')}. Re-run their cast sheets.`, 'info')
    apply?.(c)
    if (isNew.value) router.replace(`${o.base}/${id}`)
  }
  /** confirm, call the API, then back to the list. what: "prop" (the button says "Delete prop"); rule: when it can go */
  async function remove(call: () => Promise<unknown>, what: string, rule: string, done: string) {
    const ok = await confirm({ title: `Delete “${o.form.name}”?`, body: rule, confirm: `Delete ${what}`, danger: true })
    if (ok && (await act(call, done))) router.push(o.base)
  }
  return { isNew, missing, saving, save, remove }
}
