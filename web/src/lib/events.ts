// One EventSource with our own reconnect: exponential backoff (1 s, 2 s, 4 s ... 30 s), reset once a
// connection opens. The browser's built-in retry is bypassed (we close on error) so the delay is ours and a
// reconnect is visible: `onOpen(reconnected)` lets callers refetch what they missed while offline.

export const backoff = (attempt: number) => Math.min(30_000, 1000 * 2 ** attempt)

export interface EventSourceLike {
  onopen: ((e: Event) => void) | null
  onerror: ((e: Event) => void) | null
  addEventListener(type: string, fn: (e: MessageEvent) => void): void
  close(): void
}

export interface StreamOptions {
  url: string
  types: readonly string[]
  onEvent: (type: string, data: any) => void
  onOpen?: (reconnected: boolean) => void
  onDown?: (retryInMs: number) => void
  create?: (url: string) => EventSourceLike
  setTimer?: (fn: () => void, ms: number) => unknown
}

export function connectStream(o: StreamOptions): () => void {
  const create = o.create ?? ((u: string) => new EventSource(u))
  const setTimer = o.setTimer ?? ((fn: () => void, ms: number) => setTimeout(fn, ms))
  let attempt = 0, opened = false, stopped = false
  let es: EventSourceLike

  function open() {
    if (stopped) return
    es = create(o.url)
    es.onopen = () => {
      o.onOpen?.(opened)
      opened = true
      attempt = 0
    }
    es.onerror = () => {
      es.close()
      if (stopped) return
      const ms = backoff(attempt++)
      o.onDown?.(ms)
      setTimer(open, ms)
    }
    for (const t of o.types) {
      es.addEventListener(t, (e) => {
        let data: unknown
        try {
          data = JSON.parse(e.data)
        } catch {
          return // malformed: ignore
        }
        o.onEvent(t, data)
      })
    }
  }
  open()
  return () => {
    stopped = true
    es.close()
  }
}
