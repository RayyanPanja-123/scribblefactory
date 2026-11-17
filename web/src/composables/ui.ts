import { ref } from 'vue'

/** Top-bar search, shared with the Series page. */
export const search = ref('')

export const SPRING = { type: 'spring', stiffness: 320, damping: 30 } as const
export const STAGGER = 0.04

export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function bytes(n: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  while (n >= 1000 && i < units.length - 1) {
    n /= 1000
    i++
  }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${units[i]}`
}

export const label = (s: string) => s.replace(/_/g, ' ')

/** Chart / donut colours, in order. */
export const PALETTE = ['#5b6cf0', '#ff6b4a', '#3fbf7f', '#f5b544', '#b44cf0', '#2bb3c0']

const CHIP: Record<string, string> = {
  active: 'chip-blue', complete: 'chip-green',
  done: 'chip-green', running: 'chip-blue', failed: 'chip-red',
}
/** chip class for a series status or a stage status (draft / archived / pending stay grey) */
export const statusChip = (s: string) => CHIP[s] ?? ''
