// Thin typed client over fetch. Types come from docs/openapi.json (npm run gen:api).
import type { CreatureCatalog, CustomCreature } from '../lib/creatures'
import type { CustomSet, SetCatalog } from '../lib/sets'
import type { SfxCatalog, SfxEntry, SfxSuggestion, SfxSuggestions } from '../lib/sfx'
import type { WardrobeCatalog, WardrobeItem } from '../lib/wardrobe'
import type { components } from './types'
import type { ObjectCatalog, WorldObject } from '../lib/objects'

type S = components['schemas']
export type Overview = S['Overview']
export type SeriesCard = S['SeriesCard']
export type SeriesDetail = S['SeriesDetail']
export type SeriesModel = S['SeriesModel']
export type PartSummary = S['PartSummary']
export type PartDetail = S['PartDetail']
export type StoredFile = S['StoredFile']
export type PartModel = S['PartModel']
export type CastMember = S['CastMember']
export type Job = S['Job']
export type PropCatalog = S['PropCatalog']
export type CustomProp = import('../lib/props').CustomProp
export type ActionCatalog = S['ActionCatalog']
export type CustomAction = S['CustomAction']
export type StoryCheck = S['StoryCheck']
export type SettingsView = S['SettingsView']
export type Settings = S['Settings']
export type PackageResult = S['PackageResult']
export type CaptionReply = S['Captions']
export type GalleryEntry = S['GalleryEntry']
export type TtsVoice = S['TtsVoice']
export type VoiceFx = S['VoiceFx']
export type TtsVoices = S['Voices']
export type TtsLine = S['TtsLine']
export type Approval = 'stills' | 'final'
export type Platform = 'youtube' | 'instagram'
export type ExportResult = { path: string; filename: string }
export type Notification = { id: string; title: string; message: string; slug: string; series_title: string; href: string }

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let r: Response
  const raw = body instanceof Blob // files go up as-is, everything else as JSON
  try {
    r = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': raw ? body.type || 'application/octet-stream' : 'application/json' },
      body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'The API is not reachable. Is uvicorn running on port 8765?')
  }
  if (!r.ok) {
    const detail = await r.json().then((b) => b?.detail, () => null)
    // 409s carry the CLI's own message: show it verbatim
    const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join('; ') : null
    throw new ApiError(r.status, msg ?? `${r.status} ${r.statusText}`)
  }
  return r.json() as Promise<T>
}

const e = encodeURIComponent
const part = (slug: string, p: string) => `/api/series/${e(slug)}/parts/${e(p)}`

/** a library sound's audio file; v: a cache-buster after a re-upload */
export const sfxAudio = (id: string, v?: number) => `/api/sfx/${e(id)}/audio${v ? `?v=${v}` : ''}`

/** a cached TTS line (a part's voice-tts.json lines[].clip) */
export const ttsClip = (key: string) => `/api/tts/clip/${e(key)}`

export const media = (slug: string, rel: string) => `/api/media/${e(slug)}/${rel.split('/').map(e).join('/')}`

export const api = {
  overview: () => call<Overview>('GET', '/api/overview'),
  storage: () => call<StoredFile[]>('GET', '/api/storage'),
  series: () => call<SeriesCard[]>('GET', '/api/series'),
  notifications: () => call<Notification[]>('GET', '/api/notifications'),
  seriesDetail: (slug: string) => call<SeriesDetail>('GET', `/api/series/${e(slug)}`),
  /** every series in full (the library pages show who uses what) */
  allSeriesDetails: async () => Promise.all((await api.series()).map((s) => api.seriesDetail(s.slug))),
  part: (slug: string, p: string) => call<PartDetail>('GET', part(slug, p)),
  approve: (slug: string, p: string, what: Approval) => call<PartModel>('POST', `${part(slug, p)}/approve/${what}`),
  approveCast: (slug: string, castId: string) =>
    call<SeriesModel>('POST', `/api/series/${e(slug)}/approve-cast`, { cast_id: castId }),
  markPosted: (slug: string, p: string, body: { platform: Platform; url: string; date?: string; force?: boolean }) =>
    call<PartModel>('POST', `${part(slug, p)}/mark-posted`, body),
  reopen: (slug: string, p: string) => call<PartModel>('POST', `${part(slug, p)}/reopen`),
  saveUpload: (slug: string, p: string, text: string) => call<PartDetail>('PUT', `${part(slug, p)}/upload.md`, { text }),
  mobileDownloadUrl: (slug: string, p: string) => call<{ url: string }>('GET', `/api/mobile-download-url/${e(slug)}/${e(p)}`),
  exportPart: (slug: string, p: string) => call<ExportResult>('POST', `${part(slug, p)}/export`),
  saveStory: (slug: string, p: string, text: string) => call<PartDetail>('PUT', `${part(slug, p)}/story.md`, { text }),
  createSeries: (body: S['NewSeries']) => call<SeriesModel>('POST', '/api/series', body),
  addCast: (slug: string, cast: Record<string, unknown>[]) => call<SeriesModel>('POST', `/api/series/${e(slug)}/cast`, { cast }),
  importCast: (slug: string, cast: Record<string, unknown>[]) => call<SeriesModel>('PUT', `/api/series/${e(slug)}/cast`, { cast }),
  deleteCast: (slug: string, castId: string, force = false) =>
    call<SeriesModel>('DELETE', `/api/series/${e(slug)}/cast/${e(castId)}${force ? '?force=true' : ''}`),
  editCast: (slug: string, castId: string, entry: Record<string, unknown>) =>
    call<SeriesModel>('PUT', `/api/series/${e(slug)}/cast/${e(castId)}`, entry),
  createPart: (slug: string, body: S['NewPart']) => call<PartDetail>('POST', `/api/series/${e(slug)}/parts`, body),
  uploadVoice: (slug: string, p: string, file: File, replace = false) =>
    call<PartDetail>('PUT', `${part(slug, p)}/voice.mp3${replace ? '?replace=true' : ''}`, file),
  checkStory: (slug: string, p: string) => call<StoryCheck>('GET', `${part(slug, p)}/check-story`),
  deletePart: (slug: string, p: string) => call<SeriesModel>('DELETE', part(slug, p)),
  deleteSeries: (slug: string) => call<{ ok: boolean }>('DELETE', `/api/series/${e(slug)}`),
  moveToGallery: (slug: string) => call<GalleryEntry>('POST', `/api/series/${e(slug)}/gallery`),
  gallery: () => call<GalleryEntry[]>('GET', '/api/gallery'),
  cleanFrames: (slug: string, p: string) => call<PartModel>('POST', `${part(slug, p)}/clean-frames`),
  writeCaptions: (prompt: string) => call<CaptionReply>('POST', '/api/captions', { prompt }),
  settings: () => call<SettingsView>('GET', '/api/settings'),
  ttsVoices: () => call<TtsVoices>('GET', '/api/tts/voices'),
  /** a voice sample as an object URL (revoke it when done); the server's error as an ApiError */
  ttsPreview: async (voice: string, speed: number, text = '', fx: VoiceFx | null = null) => {
    const q = new URLSearchParams({ voice, speed: String(speed), text, ...(fx ? { fx: JSON.stringify(fx) } : {}) })
    const r = await fetch(`/api/tts/preview?${q}`).catch(() => null)
    if (!r) throw new ApiError(0, 'The API is not reachable. Is uvicorn running on port 8765?')
    if (!r.ok) throw new ApiError(r.status, await r.json().then((b) => String(b?.detail), () => `${r.status} ${r.statusText}`))
    return URL.createObjectURL(await r.blob())
  },
  setNarrator: (slug: string, tts: TtsVoice | null) => call<SeriesModel>('PUT', `/api/series/${e(slug)}/voice`, { tts }),
  setVoiceSource: (slug: string, p: string, source: 'recorded' | 'tts') =>
    call<PartModel>('PUT', `${part(slug, p)}/voice-source`, { source }),
  saveSettings: (body: Settings) => call<SettingsView>('PUT', '/api/settings', body),
  saveGeminiKey: (key: string) => call<SettingsView>('PUT', '/api/settings/gemini-key', { key }),
  jobs: () => call<Job[]>('GET', '/api/jobs'),
  submitJob: (slug: string, p: string, steps: string[]) => call<Job>('POST', '/api/jobs', { slug, part: p, steps }),
  cancelJob: (id: number) => call<Job>('DELETE', `/api/jobs/${id}`),
  cleanupJobs: (before: string | null) => call<Job[]>('POST', '/api/jobs/cleanup', { before }),
  props: () => call<PropCatalog>('GET', '/api/props'),
  saveProp: (p: CustomProp) => call<PropCatalog>('PUT', `/api/props/${e(p.id)}`, p),
  deleteProp: (id: string) => call<PropCatalog>('DELETE', `/api/props/${e(id)}`),
  creatures: () => call<CreatureCatalog>('GET', '/api/creatures'),
  saveCreature: (c: CustomCreature) => call<CreatureCatalog>('PUT', `/api/creatures/${e(c.id)}`, c),
  deleteCreature: (id: string) => call<CreatureCatalog>('DELETE', `/api/creatures/${e(id)}`),
  actions: () => call<ActionCatalog>('GET', '/api/actions'),
  saveAction: (a: CustomAction) => call<ActionCatalog>('PUT', `/api/actions/${e(a.id)}`, a),
  deleteAction: (id: string) => call<ActionCatalog>('DELETE', `/api/actions/${e(id)}`),
  sets: () => call<SetCatalog>('GET', '/api/sets'),
  saveSet: (s: CustomSet) => call<SetCatalog>('PUT', `/api/sets/${e(s.id)}`, s),
  deleteSet: (id: string) => call<SetCatalog>('DELETE', `/api/sets/${e(id)}`),
  objects: () => call<ObjectCatalog>('GET', '/api/objects'),
  saveObject: (o: WorldObject) => call<ObjectCatalog>('PUT', `/api/objects/${e(o.id)}`, o),
  deleteObject: (id: string) => call<ObjectCatalog>('DELETE', `/api/objects/${e(id)}`),
  wardrobe: () => call<WardrobeCatalog>('GET', '/api/wardrobe'),
  saveWardrobeItem: (w: WardrobeItem) => call<WardrobeCatalog>('PUT', `/api/wardrobe/${e(w.id)}`, w),
  deleteWardrobeItem: (id: string) => call<WardrobeCatalog>('DELETE', `/api/wardrobe/${e(id)}`),
  sfx: () => call<SfxCatalog>('GET', '/api/sfx'),
  saveSfx: (x: SfxEntry) => call<SfxCatalog>('PUT', `/api/sfx/${e(x.id)}`, x),
  uploadSfx: (id: string, file: File) => call<SfxCatalog>('PUT', `/api/sfx/${e(id)}/audio?name=${e(file.name)}`, file),
  deleteSfx: (id: string) => call<SfxCatalog>('DELETE', `/api/sfx/${e(id)}`),
  sfxSuggestions: (slug: string, p: string) => call<SfxSuggestions>('GET', `${part(slug, p)}/sfx-suggestions`),
  decideSfx: (slug: string, p: string, s: SfxSuggestion, accept: boolean) =>
    call<SfxSuggestions>('POST', `${part(slug, p)}/sfx-suggestions`, { ...s, accept }),
  attachBackgroundMusic: (slug: string, p: string) => call<{ cues: number }>('POST', `${part(slug, p)}/background-music`),
  validatePackage: (text: string) => call<PackageResult>('POST', '/api/packages/validate', { text }),
  importPackage: (text: string) => call<PackageResult>('POST', '/api/packages/import', { text }),
}
