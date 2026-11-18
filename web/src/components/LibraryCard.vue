<script setup lang="ts">
// One library item as every library page lists it: the engine's own drawing, name, id (as a story or cast writes
// it), who uses it, and Edit / Delete for custom items (built-ins are read only, or copyable).
import { Trash2 } from 'lucide-vue-next'
import type { Component } from 'vue'

defineProps<{
  name: string; code: string; tag: string; note?: string
  users?: { slug: string; name: string; detail?: string }[]; usedBy?: string; unused?: string; icon?: Component
  editTo?: string; editLabel?: string; deletable?: boolean; readonly?: string
}>()
defineEmits<{ delete: [] }>()
</script>

<template>
  <li class="inset flex gap-3 rounded-md p-3">
    <div class="h-32 w-20 shrink-0"><slot name="preview" /></div>
    <div class="min-w-0 flex-1 space-y-1">
      <p class="font-semibold">{{ name }}</p>
      <p class="text-xs text-muted"><code>{{ code }}</code> · {{ tag }}</p>
      <p v-if="note" class="text-xs text-muted">{{ note }}</p>
      <template v-if="users">
        <p v-if="users.length" class="text-xs">
          {{ usedBy ?? 'used by' }} <template v-for="(u, i) in users.slice(0, 3)" :key="`${u.slug}/${u.name}/${u.detail}/${i}`"><template v-if="i">, </template>
            <RouterLink :to="`/series/${u.slug}`" class="font-semibold hover:underline">{{ u.name }}</RouterLink><span v-if="u.detail" class="text-muted"> ({{ u.detail }})</span></template>
          <span v-if="users.length > 3" class="text-muted"> +{{ users.length - 3 }} more</span>
        </p>
        <p v-else class="flex items-center gap-1 text-xs text-muted"><component :is="icon" v-if="icon" :size="12" aria-hidden="true" /> {{ unused ?? 'nobody uses it' }}</p>
      </template>
      <div v-if="editTo || deletable" class="flex flex-wrap gap-2 pt-1">
        <RouterLink v-if="editTo" :to="editTo" class="btn btn-secondary">{{ editLabel ?? 'Edit' }}</RouterLink>
        <button v-if="deletable" type="button" class="btn btn-secondary text-red-ink" :aria-label="`Delete ${name}`" @click="$emit('delete')"><Trash2 :size="16" aria-hidden="true" /></button>
      </div>
      <p v-else-if="readonly" class="text-xs text-muted">{{ readonly }}</p>
    </div>
  </li>
</template>
