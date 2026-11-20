import { computed, ref } from 'vue'
import { api, type Notification } from '../api/client'

const SEEN_KEY = 'scribblefactory.notifications.seen'

function readSeen(): string[] {
  try {
    const stored = localStorage.getItem(SEEN_KEY)
    const parsed: unknown = stored ? JSON.parse(stored) : []
    return Array.isArray(parsed) && parsed.every((id) => typeof id === 'string') ? parsed : []
  } catch {
    return []
  }
}

export const notifications = ref<Notification[]>([])
export const notificationError = ref('')
export const notificationLoading = ref(true)
const seenIds = ref(readSeen())
export const unreadNotifications = computed(() => notifications.value.some((notice) => !seenIds.value.includes(notice.id)))

export async function refreshNotifications() {
  notificationLoading.value = true
  try {
    notifications.value = await api.notifications()
    notificationError.value = ''
  } catch (error) {
    notificationError.value = error instanceof Error ? error.message : String(error)
  } finally {
    notificationLoading.value = false
  }
}

export function markNotificationsRead() {
  seenIds.value = notifications.value.map((notice) => notice.id)
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(seenIds.value))
  } catch {
    // The badge still clears for this session when browser storage is unavailable.
  }
}
