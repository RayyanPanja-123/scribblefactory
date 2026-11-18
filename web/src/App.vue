<script setup lang="ts">
import { Backpack, ClipboardCheck, Film, History, Layers, LayoutDashboard, Menu, Monitor, Moon, Mountain, PawPrint, Search, Send, Settings, Sparkles, Sun, X } from 'lucide-vue-next'
import { AnimatePresence, motion, MotionConfig } from 'motion-v'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandMark from './components/BrandMark.vue'
import JobDrawer from './components/JobDrawer.vue'
import Overlays from './components/Overlays.vue'
import { api } from './api/client'
import { toast } from './composables/feedback'
import { drawerOpen, online, queuedCount, runningJob, startLive } from './composables/live'
import { theme, type Theme } from './composables/theme'
import { search } from './composables/ui'

// The shell is an exposure sheet's left margin: brand, ruled nav groups, theme at the foot.
// Under 1024 px the margin becomes a drawer behind the menu button.
const route = useRoute()
const router = useRouter()
type Tab = { to: string; name: string; icon: typeof Layers; match: (n: string) => boolean }
const groups: { title: string; tabs: Tab[] }[] = [
  { title: 'Production', tabs: [
    { to: '/', name: 'Overview', icon: LayoutDashboard, match: (n) => n === 'overview' },
    { to: '/series', name: 'Series', icon: Layers, match: (n) => n.startsWith('series') || n === 'part' || n === 'new-series' || n === 'new-part' },
    { to: '/review', name: 'Review', icon: ClipboardCheck, match: (n) => n === 'review' },
    { to: '/posted', name: 'Posted', icon: Send, match: (n) => n === 'posted' },
    { to: '/history', name: 'History', icon: History, match: (n) => n === 'history' },
  ] },
  { title: 'Library', tabs: [
    { to: '/props', name: 'Props', icon: Backpack, match: (n) => n.startsWith('prop') },
    { to: '/creatures', name: 'Creatures', icon: PawPrint, match: (n) => n.startsWith('creature') },
    { to: '/sets', name: 'Sets', icon: Mountain, match: (n) => n === 'sets' || n === 'set-edit' },
  ] },
  { title: 'Setup', tabs: [
    { to: '/settings', name: 'Settings', icon: Settings, match: (n) => n === 'settings' },
  ] },
]
const THEMES: { id: Theme; label: string; icon: typeof Sun }[] = [
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
  { id: 'system', label: 'System', icon: Monitor },
]
onMounted(startLive)
const reelLabel = computed(() =>
  `Jobs: ${runningJob.value ? `job ${runningJob.value.id} running` : 'none running'}${queuedCount.value ? `, ${queuedCount.value} queued` : ''}`)

// AI gateway switch: starts/stops the local OmniRoute so "Build with AI" works
const aiOn = ref(false)
const aiBusy = ref(false)
api.gateway().then((g) => (aiOn.value = g.running), () => {}) // ponytail: checked once on load, poll if it gets stopped elsewhere often
async function toggleAi() {
  aiBusy.value = true
  try {
    aiOn.value = (await api.setGateway(!aiOn.value)).running
    toast(aiOn.value ? 'OmniRoute started' : 'OmniRoute stopped', 'ok')
  } catch (e) {
    toast(e instanceof Error ? e.message : String(e), 'error')
  } finally {
    aiBusy.value = false
  }
}
const isActive = (t: Tab) => t.match(String(route.name ?? ''))
const current = computed(() => groups.flatMap((g) => g.tabs).find(isActive))

const menuOpen = ref(false)
watch(() => route.fullPath, () => (menuOpen.value = false))

// searching jumps to the series list, where the filter applies
watch(search, (q) => {
  if (q && route.name !== 'series') router.push('/series')
})
</script>

<template>
  <MotionConfig :transition="{ type: 'spring', stiffness: 400, damping: 36 }" reduced-motion="user">
    <a href="#main" class="sr-only z-50 rounded-md bg-ink px-3 py-2 text-[var(--on-ink)] focus:not-sr-only focus:fixed focus:top-2 focus:left-2">Skip to content</a>
    <div class="flex h-full">
      <!-- left margin rail -->
      <div v-if="menuOpen" class="fixed inset-0 z-30 bg-[var(--scrim)] lg:hidden" aria-hidden="true" @click="menuOpen = false" />
      <aside
        class="fixed inset-y-0 left-0 z-40 flex w-[var(--rail-w)] flex-col border-r border-rule bg-panel transition-transform duration-200 lg:static lg:translate-x-0"
        :class="menuOpen ? 'translate-x-0 shadow-[var(--shadow-pop)]' : '-translate-x-full'" aria-label="Main">
        <div class="flex items-center gap-3 border-b border-rule px-4 py-4">
          <BrandMark class="size-10 shrink-0" />
          <div class="min-w-0">
            <p class="font-display text-[17px] leading-tight font-semibold whitespace-nowrap">Scribble Factory</p>
            <p class="text-xs text-muted">Stickman shorts studio</p>
          </div>
          <button class="round-btn ml-auto size-9! lg:hidden" aria-label="Close menu" @click="menuOpen = false"><X :size="18" /></button>
        </div>

        <nav class="min-h-0 flex-1 overflow-y-auto px-3 py-3">
          <section v-for="g in groups" :key="g.title" class="mb-4">
            <h2 class="colhead px-2 pb-1.5">{{ g.title }}</h2>
            <ul class="space-y-0.5">
              <li v-for="t in g.tabs" :key="t.to">
                <RouterLink :to="t.to" :aria-current="isActive(t) ? 'page' : undefined"
                  class="group relative flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors"
                  :class="isActive(t) ? 'bg-ink text-[var(--on-ink)]' : 'text-muted hover:bg-well hover:text-ink'">
                  <component :is="t.icon" :size="17" class="shrink-0" aria-hidden="true" />
                  {{ t.name }}
                </RouterLink>
              </li>
            </ul>
          </section>
        </nav>

        <fieldset class="border-t border-rule px-4 py-4">
          <legend class="colhead float-left mb-2 w-full">Theme</legend>
          <div class="clear-both grid grid-cols-3 gap-1 rounded-md border border-rule bg-well p-1">
            <label v-for="t in THEMES" :key="t.id"
              class="flex cursor-pointer flex-col items-center gap-0.5 rounded-sm py-1.5 text-[11px] font-semibold transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-blue"
              :class="theme === t.id ? 'bg-panel text-ink shadow-[var(--shadow-sheet)]' : 'text-muted hover:text-ink'">
              <input v-model="theme" type="radio" name="theme" :value="t.id" class="sr-only" />
              <component :is="t.icon" :size="15" aria-hidden="true" />{{ t.label }}
            </label>
          </div>
        </fieldset>
      </aside>

      <div class="flex min-w-0 flex-1 flex-col">
        <header class="flex items-center gap-3 border-b border-rule bg-panel px-4 py-3 lg:px-8">
          <button class="round-btn shrink-0 lg:hidden" aria-label="Open menu" :aria-expanded="menuOpen" @click="menuOpen = true"><Menu :size="18" /></button>
          <p class="truncate font-display text-lg font-semibold lg:hidden">{{ current?.name ?? 'Scribble Factory' }}</p>
          <label class="ml-auto hidden w-full max-w-72 min-w-0 items-center sm:flex gap-2 rounded-md border border-rule bg-well px-3 py-2 focus-within:border-blue">
            <Search :size="16" class="shrink-0 text-faint" aria-hidden="true" />
            <span class="sr-only">Search series</span>
            <input v-model="search" type="search" placeholder="Search series" class="w-full bg-transparent text-sm outline-none placeholder:text-muted" />
          </label>
          <RouterLink to="/series" class="round-btn ml-auto shrink-0 sm:hidden" aria-label="Search series"><Search :size="18" aria-hidden="true" /></RouterLink>
          <button class="round-btn shrink-0 transition-colors" :class="aiOn ? 'border-ink! bg-ink! text-[var(--on-ink)]!' : ''"
            :aria-pressed="aiOn" :disabled="aiBusy" :title="aiBusy ? 'OmniRoute: working…' : `OmniRoute ${aiOn ? 'on: click to stop' : 'off: click to start'}`"
            aria-label="AI gateway (OmniRoute)" @click="toggleAi">
            <Sparkles :size="18" :class="{ 'animate-pulse': aiBusy }" aria-hidden="true" />
          </button>
          <!-- job indicator: spins while a job runs, badge = queued jobs; opens the drawer -->
          <button class="round-btn relative shrink-0" :class="{ 'text-blue-ink!': runningJob }" :aria-label="reelLabel"
            :title="online ? reelLabel : 'Live updates offline: reconnecting'" @click="drawerOpen = true">
            <Film :size="19" :class="{ reel: runningJob }" aria-hidden="true" />
            <span v-if="queuedCount" class="num absolute -top-1.5 -right-1.5 grid size-5 place-items-center rounded-full bg-amber text-[11px] text-[#1b2531]">
              {{ queuedCount }}</span>
            <span v-if="!online" class="absolute right-0.5 bottom-0.5 size-2 rounded-full bg-faint" aria-hidden="true" />
          </button>
        </header>

        <main id="main" class="min-h-0 flex-1 overflow-y-auto px-4 pt-6 pb-16 lg:px-8">
          <RouterView v-slot="{ Component, route: r }">
            <AnimatePresence mode="wait">
              <motion.div :key="r.path" :initial="{ opacity: 0, y: 6 }" :animate="{ opacity: 1, y: 0 }"
                :exit="{ opacity: 0 }" :transition="{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }">
                <component :is="Component" />
              </motion.div>
            </AnimatePresence>
          </RouterView>
        </main>
      </div>
      <JobDrawer />
    </div>
    <Overlays />
  </MotionConfig>
</template>
