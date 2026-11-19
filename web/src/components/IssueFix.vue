<script setup lang="ts">
import { computed, ref, useId } from 'vue'

// Fix an issue where it is reported: lines line-context … line+context of the text, editable; Update splices the
// edit back (the line count may change) and the parent re-checks the whole text, so line numbers refresh themselves.
const props = withDefaults(defineProps<{ line: number; context?: number; label?: string }>(), { context: 2, label: 'Fix here' })
const text = defineModel<string>({ required: true })
const id = useId()
const open = ref(false)
const draft = ref('')
const lines = computed(() => text.value.split('\n'))
const from = computed(() => Math.max(1, props.line - props.context)) // 1-based, inclusive
const to = computed(() => Math.min(lines.value.length, props.line + props.context))

function start() {
  draft.value = lines.value.slice(from.value - 1, to.value).join('\n')
  open.value = true
}
function update() {
  const ls = lines.value
  text.value = [...ls.slice(0, from.value - 1), draft.value, ...ls.slice(to.value)].join('\n')
  open.value = false
}
const rows = computed(() => draft.value.split('\n').length)
</script>

<template>
  <button v-if="!open" type="button" class="text-xs font-semibold text-blue-ink underline underline-offset-2" @click="start">{{ label }}</button>
  <div v-else class="mt-2 w-full space-y-2">
    <div class="flex overflow-hidden rounded-md border border-rule bg-well font-mono text-xs leading-5">
      <ol class="select-none border-r border-rule px-2 py-2 text-right text-muted" aria-hidden="true">
        <li v-for="n in rows" :key="n" :class="from + n - 1 === line && 'font-bold text-red-ink'">{{ from + n - 1 }}</li>
      </ol>
      <label class="sr-only" :for="id">Lines {{ from }} to {{ to }}</label>
      <textarea :id="id" v-model="draft" :rows="rows" spellcheck="false" wrap="off"
        class="block min-w-0 flex-1 resize-none overflow-x-auto bg-transparent px-2 py-2 text-ink outline-none focus:bg-panel"
        @keydown.ctrl.enter.prevent="update" @keydown.esc.prevent="open = false" />
    </div>
    <div class="flex gap-2">
      <button type="button" class="btn btn-primary" @click="update">Update</button>
      <button type="button" class="btn btn-secondary" @click="open = false">Cancel</button>
      <span class="self-center text-xs text-muted">Ctrl+Enter updates, Esc cancels</span>
    </div>
  </div>
</template>
