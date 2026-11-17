<script setup lang="ts">
import { ClipboardCheck, Film, Layers, LayoutDashboard, Search, Send } from 'lucide-vue-next'
import { AnimatePresence, motion, MotionConfig } from 'motion-v'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandMark from './components/BrandMark.vue'
import JobDrawer from './components/JobDrawer.vue'
import Overlays from './components/Overlays.vue'
import { drawerOpen, online, queuedCount, runningJob, startLive } from './composables/live'
import { search, SPRING } from './composables/ui'

const route = useRoute()
const router = useRouter()
const tabs = [
  { to: '/', name: 'Overview', icon: LayoutDashboard, match: (n: string) => n === 'overview' },
  { to: '/series', name: 'Series', icon: Layers, match: (n: string) => n.startsWith('series') || n === 'part' },
  { to: '/review', name: 'Review', icon: ClipboardCheck, match: (n: string) => n === 'review' },
  { to: '/posted', name: 'Posted', icon: Send, match: (n: string) => n === 'posted' },
]
onMounted(startLive)
const reelLabel = computed(() =>
  `Jobs: ${runningJob.value ? `job ${runningJob.value.id} running` : 'none running'}${queuedCount.value ? `, ${queuedCount.value} queued` : ''}`)
const active = computed(() => tabs.find((t) => t.match(String(route.name ?? ''))))
const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

// searching jumps to the series list, where the filter applies
watch(search, (q) => {
  if (q && route.name !== 'series') router.push('/series')
})

// scrollbar thumb only while scrolling
const scrolling = ref(false)
let idle: ReturnType<typeof setTimeout> | undefined
function onScroll() {
  scrolling.value = true
  clearTimeout(idle)
  idle = setTimeout(() => (scrolling.value = false), 800)
}
</script>

<template>
  <MotionConfig :transition="SPRING" reduced-motion="user">
    <div class="h-full p-4">
      <div class="bezel h-full rounded-frame bg-bezel p-3">
        <div class="screen grain flex h-full overflow-hidden rounded-lg bg-surface">
          <!-- icon rail -->
          <nav class="flex w-[88px] shrink-0 flex-col items-center gap-4 py-6" aria-label="Main">
            <BrandMark class="mb-4" />
            <RouterLink v-for="t in tabs" :key="t.to" :to="t.to" class="round-btn"
              :aria-current="active === t ? 'page' : undefined" :aria-label="t.name" :title="t.name">
              <component :is="t.icon" :size="20" aria-hidden="true" />
            </RouterLink>
          </nav>

          <div class="relative flex min-w-0 flex-1 flex-col">
            <header class="flex items-center gap-6 py-5 pr-8">
              <p class="font-display text-xl font-semibold whitespace-nowrap">Scribble Factory</p>
              <span class="h-9 w-px bg-[#cfc8bb]" aria-hidden="true" />
              <div class="min-w-0">
                <h1 class="font-display text-2xl font-semibold">Welcome, Rayyan</h1>
                <p class="text-sm text-muted">{{ today }}</p>
              </div>
              <label class="inset ml-auto flex w-full max-w-sm items-center gap-2 rounded-full px-4 py-2.5">
                <Search :size="18" class="shrink-0 text-faint" aria-hidden="true" />
                <span class="sr-only">Search series</span>
                <input v-model="search" type="search" placeholder="Search series"
                  class="w-full bg-transparent text-sm outline-none placeholder:text-muted" />
              </label>
              <!-- job indicator: spins while a job runs, badge = queued jobs; opens the drawer -->
              <button class="round-btn relative" :class="{ 'text-blue-ink!': runningJob }" :aria-label="reelLabel"
                :title="online ? reelLabel : 'Live updates offline: reconnecting'" @click="drawerOpen = true">
                <Film :size="20" :class="{ reel: runningJob }" aria-hidden="true" />
                <span v-if="queuedCount" class="num absolute -top-1 -right-1 grid size-5 place-items-center rounded-full bg-amber-ink text-[11px] text-white">
                  {{ queuedCount }}</span>
                <span v-if="!online" class="absolute right-0 bottom-0 size-2.5 rounded-full border-2 border-panel bg-faint" aria-hidden="true" />
              </button>
            </header>

            <main class="scroll fade-bottom min-h-0 flex-1 overflow-y-auto pr-8 pb-[calc(var(--tabbar-h)+20px+24px)]"
              :class="{ scrolling }" @scroll.passive="onScroll">
              <RouterView v-slot="{ Component, route: r }">
                <AnimatePresence mode="wait">
                  <motion.div :key="r.path" :initial="{ opacity: 0, y: 12 }" :animate="{ opacity: 1, y: 0 }"
                    :exit="{ opacity: 0, y: -12 }" :transition="{ ...SPRING, opacity: { duration: 0.18 } }">
                    <component :is="Component" />
                  </motion.div>
                </AnimatePresence>
              </RouterView>
            </main>

            <!-- floating tab bar: the dark pill slides between tabs (shared layout) -->
            <nav class="absolute bottom-5 left-1/2 flex h-[var(--tabbar-h)] -translate-x-1/2 items-center gap-1 rounded-full border border-white/60 bg-white/45 p-1.5 shadow-[0_10px_30px_rgb(120_104_82/0.25)] backdrop-blur-xl"
              aria-label="Tabs">
              <RouterLink v-for="t in tabs" :key="t.to" :to="t.to"
                class="relative flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold"
                :class="active === t ? 'text-white' : 'text-ink'" :aria-current="active === t ? 'page' : undefined">
                <motion.span v-if="active === t" layout-id="tab-pill" class="absolute inset-0 rounded-full bg-ink shadow-[var(--shadow-dark)]"
                  :transition="SPRING" />
                <component :is="t.icon" :size="16" class="relative" aria-hidden="true" />
                <span class="relative">{{ t.name }}</span>
              </RouterLink>
            </nav>
          </div>
        </div>
      </div>
    </div>
    <JobDrawer />
    <Overlays />
  </MotionConfig>
</template>

<style scoped>
.reel { animation: spin 1.6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .reel { animation: pulse-o 1.6s ease-in-out infinite; } }
@keyframes pulse-o { 50% { opacity: 0.5; } }
</style>
