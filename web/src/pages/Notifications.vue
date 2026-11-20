<script setup lang="ts">
import { ArrowUpRight, Bell, Info } from 'lucide-vue-next'
import { api } from '../api/client'
import EmptyState from '../components/EmptyState.vue'
import ErrorCard from '../components/ErrorCard.vue'
import { useApi } from '../composables/useApi'

const { data, error, loading, reload } = useApi(api.notifications)
</script>

<template>
  <div class="max-w-4xl space-y-5">
    <div class="flex items-baseline gap-3">
      <h2 class="font-display text-2xl font-semibold">Notifications</h2>
      <span v-if="data?.length" class="text-sm text-muted">{{ data.length }} informational notice{{ data.length === 1 ? '' : 's' }}</span>
    </div>

    <ErrorCard v-if="error" :message="error" @retry="reload" />
    <div v-else-if="loading" class="raised h-28 animate-pulse" aria-busy="true" aria-label="Loading notifications" />
    <EmptyState v-else-if="!data?.length" :icon="Bell" title="You're all caught up"
      text="Library notes that don't need to interrupt story checks will appear here." />

    <ul v-else class="space-y-3">
      <li v-for="notice in data" :key="notice.id" class="raised flex items-start gap-4 p-4">
        <span class="round-btn mt-0.5 shrink-0 text-blue-ink"><Info :size="18" aria-hidden="true" /></span>
        <div class="min-w-0 flex-1">
          <h3 class="font-semibold">{{ notice.title }}</h3>
          <p class="mt-1 text-sm leading-relaxed text-muted">{{ notice.message }}</p>
          <p class="mt-2 text-xs font-semibold text-faint">{{ notice.series_title }}</p>
        </div>
        <RouterLink :to="notice.href" class="btn btn-secondary shrink-0" :aria-label="`Open ${notice.series_title}`">
          Open series <ArrowUpRight :size="15" aria-hidden="true" />
        </RouterLink>
      </li>
    </ul>
  </div>
</template>
