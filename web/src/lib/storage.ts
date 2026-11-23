// The Storage page: the library's stored files (GET /api/storage, frames aside) by kind, and the biggest.
import type { StoredFile } from '../api/client'

export const KINDS = [
  { key: 'video', label: 'Video' },
  { key: 'audio', label: 'Audio' },
  { key: 'image', label: 'Images' },
  { key: 'text', label: 'Text and data' },
] as const
export type Kind = (typeof KINDS)[number]['key']

/** a content type's kind: video/*, audio/*, image/*; everything else (markdown, json, captions...) is text */
export function kindOf(contentType: string): Kind {
  const top = contentType.split('/')[0]
  return top === 'video' || top === 'audio' || top === 'image' ? top : 'text'
}

export type KindTotal = { key: Kind; label: string; files: number; bytes: number; seconds: number; pct: number }

/** files, bytes and seconds (audio and video) per kind, every kind listed; pct: bytes to scale against the largest */
export function byKind(files: StoredFile[]): KindTotal[] {
  const out = KINDS.map((k) => ({ ...k, files: 0, bytes: 0, seconds: 0, pct: 0 }))
  for (const f of files) {
    const t = out.find((k) => k.key === kindOf(f.content_type))!
    t.files += 1
    t.bytes += f.size_bytes
    t.seconds += f.duration_s ?? 0
  }
  const max = Math.max(1, ...out.map((k) => k.bytes))
  return out.map((k) => ({ ...k, pct: (k.bytes / max) * 100 }))
}

/** the n biggest files, largest first */
export const biggest = (files: StoredFile[], n = 5): StoredFile[] => [...files].sort((a, b) => b.size_bytes - a.size_bytes).slice(0, n)

/** 196.1 -> "3 min 16 s", 36.1 -> "36 s" */
export function duration(seconds: number): string {
  const s = Math.round(seconds)
  return s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`
}
