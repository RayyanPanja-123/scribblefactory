<script setup lang="ts">
import { Backpack, ClipboardCheck, PawPrint, Film, History, Layers, LayoutDashboard, Mountain, Search, Send, Settings } from 'lucide-vue-next'
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
  { to: '/series', name: 'Series', icon: Layers, match: (n: string) => n.startsWith('series') || n === 'part' || n === 'new-series' || n === 'new-part' },
  { to: '/review', name: 'Review', icon: ClipboardCheck, match: (n: string) => n === 'review' },
  { to: '/props', name: 'Props', icon: Backpack, match: (n: string) => n.startsWith('prop') },
  { to: '/creatures', name: 'Creatures', icon: PawPrint, match: (n: string) => n.startsWith('creature') },
  { to: '/sets', name: 'Sets', icon: Mountain, match: (n: string) => n === 'sets' || n === 'set-edit' },
  { to: '/posted', name: 'Posted', icon: Send, match: (n: string) => n === 'posted' },
  { to: '/history', name: 'History', icon: History, match: (n: string) => n === 'history' },
  { to: '/settings', name: 'Settings', icon: Settings, match: (n: string) => n === 'settings' },
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
    <!-- one dark layer: the bezel is the outer frame (8 px margin, 6 px under 1280 px), same colour as the page -->
    <div class="h-full">
      <div class="bezel h-full rounded-frame bg-bezel p-1">
        <div class="screen grain relative flex h-full overflow-hidden rounded-[22px] bg-surface">
          <div class="relative flex min-w-0 flex-1 flex-col">
            <header class="flex flex-wrap items-center gap-x-6 gap-y-3 py-4 pr-4 pl-4 lg:py-5 lg:pr-8 lg:pl-8">
              <BrandMark class="size-10 shrink-0" />
              <p class="font-display text-xl font-semibold whitespace-nowrap">Scribble Factory</p>
              <span class="hidden h-9 w-px bg-[#cfc8bb] lg:block" aria-hidden="true" />
              <div class="min-w-0">
                <h1 class="font-display text-xl font-semibold lg:text-2xl">Welcome, Rayyan</h1>
                <p class="text-sm text-muted">{{ today }}</p>
              </div>
              <label class="inset order-last flex basis-full items-center gap-2 rounded-full px-4 py-2.5 lg:order-none lg:ml-auto lg:w-full lg:max-w-sm">
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

            <main class="scroll fade-bottom min-h-0 flex-1 overflow-y-auto pt-2 pr-4 pb-[calc(var(--tabbar-h)+20px+24px)] pl-4 lg:pr-8 lg:pl-8"
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
            <nav class="absolute bottom-2 left-1/2 flex h-14 w-[calc(100%-16px)] max-w-[560px] -translate-x-1/2 items-center gap-0 rounded-full border border-white/60 bg-white/45 p-1 shadow-[0_10px_30px_rgb(120_104_82/0.25)] backdrop-blur-xl lg:bottom-5 lg:h-[var(--tabbar-h)] lg:w-auto lg:max-w-none lg:gap-1 lg:p-1.5"
              aria-label="Tabs">
              <RouterLink v-for="t in tabs" :key="t.to" :to="t.to"
                class="relative flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-full px-1 py-1 text-[10px] font-semibold lg:flex-none lg:flex-row lg:gap-2 lg:px-4 lg:py-2.5 lg:text-sm"
                :class="active === t ? 'text-white' : 'text-ink'" :aria-current="active === t ? 'page' : undefined">
                <motion.span v-if="active === t" layout-id="tab-pill" class="absolute inset-0 rounded-full bg-ink shadow-[var(--shadow-dark)]"
                  :transition="SPRING" />
                <component :is="t.icon" :size="16" class="relative shrink-0" aria-hidden="true" />
                <span class="relative">{{ t.name }}</span>
              </RouterLink>
            </nav>
          </div>
          <!-- the jobs drawer lives inside the screen: it dims the screen only, never the bezel -->
          <JobDrawer />
        </div>
      </div>
    </div>
    <Overlays />
  </MotionConfig>
</template>
