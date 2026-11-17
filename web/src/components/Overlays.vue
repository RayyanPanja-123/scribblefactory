<script setup lang="ts">
import { CircleAlert, CircleCheck, Info, X } from 'lucide-vue-next'
import { AnimatePresence, motion } from 'motion-v'
import { nextTick, ref, watch } from 'vue'
import { confirmState, dismiss, toasts, zoomed } from '../composables/feedback'
import { drawerOpen } from '../composables/live'
import { SPRING } from '../composables/ui'

// Toasts (bottom right), the confirm dialog and the image zoom: rendered once, driven by composables/feedback.
const ICON = { ok: CircleCheck, error: CircleAlert, info: Info }
const confirmBtn = ref<HTMLButtonElement>()
const confirmDialog = ref<HTMLElement>()
const returnFocus = ref<HTMLElement | null>(null)
watch(confirmState, async (s) => {
  if (s) {
    returnFocus.value = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    confirmBtn.value?.focus()
  } else {
    await nextTick()
    returnFocus.value?.focus()
    returnFocus.value = null
  }
})
// Esc closes the top layer only: capture phase + stopImmediatePropagation, so the job drawer (which also listens
// for Esc) stays open until the next press
function onKey(e: KeyboardEvent) {
  if (confirmState.value) {
    if (e.key === 'Escape') {
      e.stopImmediatePropagation()
      confirmState.value.resolve(false)
      return
    }
    if (e.key === 'Tab' && confirmDialog.value) {
      const focusable = [...confirmDialog.value.querySelectorAll<HTMLElement>('button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])')]
        .filter((el) => !el.hasAttribute('disabled'))
      if (!focusable.length) return
      const first = focusable[0], last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    return
  }
  if (e.key === 'Escape' && zoomed.value) {
    e.stopImmediatePropagation()
    zoomed.value = null
  }
}
window.addEventListener('keydown', onKey, true)
</script>

<template>
  <!-- toasts -->
  <!-- toasts move left of the job drawer while it is open, so they never cover its log -->
  <div class="pointer-events-none fixed right-2 bottom-24 z-50 flex w-[calc(100%-16px)] max-w-96 flex-col items-end gap-3 sm:bottom-28" :class="drawerOpen ? 'sm:right-[480px]' : 'sm:right-8'"
    aria-live="polite">
    <AnimatePresence>
      <motion.div v-for="t in toasts" :key="t.id" layout
        class="raised pointer-events-auto flex w-full items-start gap-3 px-4 py-3 text-sm"
        :initial="{ opacity: 0, y: 24 }" :animate="{ opacity: 1, y: 0 }" :exit="{ opacity: 0, y: 12 }" :transition="SPRING"
        :role="t.kind === 'error' ? 'alert' : 'status'">
        <component :is="ICON[t.kind]" :size="18" class="mt-px shrink-0"
          :class="{ 'text-green-ink': t.kind === 'ok', 'text-red-ink': t.kind === 'error', 'text-blue-ink': t.kind === 'info' }" aria-hidden="true" />
        <p class="min-w-0 flex-1 break-words">{{ t.text }}</p>
        <button class="shrink-0 text-muted hover:text-ink" aria-label="Dismiss" @click="dismiss(t.id)"><X :size="16" /></button>
      </motion.div>
    </AnimatePresence>
  </div>

  <!-- confirm -->
  <AnimatePresence>
    <motion.div v-if="confirmState" key="confirm" class="fixed inset-0 z-50 grid place-items-center bg-ink/40 backdrop-blur-sm"
      :initial="{ opacity: 0 }" :animate="{ opacity: 1 }" :exit="{ opacity: 0 }" @click.self="confirmState.resolve(false)">
      <motion.div ref="confirmDialog" class="raised w-[420px] max-w-[90vw] p-6" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-body"
        :initial="{ scale: 0.94, opacity: 0 }" :animate="{ scale: 1, opacity: 1 }" :exit="{ scale: 0.96, opacity: 0 }" :transition="SPRING">
        <h2 id="confirm-title" class="font-display text-xl font-semibold">{{ confirmState.title }}</h2>
        <p id="confirm-body" class="mt-2 text-sm text-muted">{{ confirmState.body }}</p>
        <div class="mt-6 flex justify-end gap-3">
          <button class="btn btn-secondary" @click="confirmState.resolve(false)">Cancel</button>
          <button ref="confirmBtn" class="btn btn-primary" :class="{ 'bg-red-ink!': confirmState.danger }"
            @click="confirmState.resolve(true)">{{ confirmState.confirm }}</button>
        </div>
      </motion.div>
    </motion.div>
  </AnimatePresence>

  <!-- zoom -->
  <AnimatePresence>
    <motion.div v-if="zoomed" key="zoom" class="fixed inset-0 z-40 flex cursor-zoom-out overflow-auto overscroll-contain bg-ink/70 p-4 backdrop-blur-sm sm:p-10"
      :initial="{ opacity: 0 }" :animate="{ opacity: 1 }" :exit="{ opacity: 0 }" role="dialog" aria-modal="true"
      :aria-label="zoomed.alt" @click.self="zoomed = null">
      <button class="round-btn fixed top-4 right-4 z-10 bg-panel" aria-label="Close image" title="Close image" @click="zoomed = null"><X :size="18" /></button>
      <motion.img :src="zoomed.src" :alt="zoomed.alt" class="m-auto h-auto max-w-full shrink-0 cursor-default rounded-md shadow-2xl"
        :initial="{ scale: 0.88 }" :animate="{ scale: 1 }" :exit="{ scale: 0.92 }" :transition="SPRING" />
    </motion.div>
  </AnimatePresence>
</template>
