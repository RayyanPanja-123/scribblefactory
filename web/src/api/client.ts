// Thin typed client over fetch. Types come from docs/openapi.json (npm run gen:api).
import type { CreatureCatalog, CustomCreature } from '../lib/creatures'
import type { CustomSet, SetCatalog } from '../lib/sets'
import type { WardrobeCatalog, WardrobeItem } from '../lib/wardrobe'
import type { components } from './types'

type S = components['schemas']
export type Overview = S['Overview']
export type SeriesCard = S['SeriesCard']
export type SeriesDetail = S['SeriesDetail']
export type SeriesModel = S['SeriesModel']
export type PartSummary = S['PartSummary']
export type PartDetail = S['PartDetail']
export type PartModel = S['PartModel']
export type CastMember = S['CastMember']
export type Job = S['Job']
export type PropCatalog = S['PropCatalog']
export type CustomProp = S['CustomProp']
export type ActionCatalog = S['ActionCatalog']
export type CustomAction = S['CustomAction']
export type StoryCheck = S['StoryCheck']
export type PackageResult = S['PackageResult']
export type Approval = 'stills' | 'test_render' | 'final'
export type Platform = 'youtube' | 'instagram'

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

export const media = (slug: string, rel: string) => `/api/media/${e(slug)}/${rel.split('/').map(e).join('/')}`

export const api = {
  overview: () => call<Overview>('GET', '/api/overview'),
  series: () => call<SeriesCard[]>('GET', '/api/series'),
  seriesDetail: (slug: string) => call<SeriesDetail>('GET', `/api/series/${e(slug)}`),
  part: (slug: string, p: string) => call<PartDetail>('GET', part(slug, p)),
  approve: (slug: string, p: string, what: Approval) => call<PartModel>('POST', `${part(slug, p)}/approve/${what}`),
  approveCast: (slug: string, castId: string) =>
    call<SeriesModel>('POST', `/api/series/${e(slug)}/approve-cast`, { cast_id: castId }),
  pickThumbnail: (slug: string, p: string, n: 1 | 2 | 3) => call<PartModel>('POST', `${part(slug, p)}/pick-thumbnail`, { n }),
  markPosted: (slug: string, p: string, body: { platform: Platform; url: string; date?: string; force?: boolean }) =>
    call<PartModel>('POST', `${part(slug, p)}/mark-posted`, body),
  saveUpload: (slug: string, p: string, text: string) => call<PartDetail>('PUT', `${part(slug, p)}/upload.md`, { text }),
  saveStory: (slug: string, p: string, text: string) => call<PartDetail>('PUT', `${part(slug, p)}/story.md`, { text }),
  createSeries: (body: S['NewSeries']) => call<SeriesModel>('POST', '/api/series', body),
  addCast: (slug: string, cast: Record<string, unknown>[]) => call<SeriesModel>('POST', `/api/series/${e(slug)}/cast`, { cast }),
  importCast: (slug: string, cast: Record<string, unknown>[]) => call<SeriesModel>('PUT', `/api/series/${e(slug)}/cast`, { cast }),
  editCast: (slug: string, castId: string, entry: Record<string, unknown>) =>
    call<SeriesModel>('PUT', `/api/series/${e(slug)}/cast/${e(castId)}`, entry),
  createPart: (slug: string, body: S['NewPart']) => call<PartDetail>('POST', `/api/series/${e(slug)}/parts`, body),
  uploadVoice: (slug: string, p: string, file: File, replace = false) =>
    call<PartDetail>('PUT', `${part(slug, p)}/voice.mp3${replace ? '?replace=true' : ''}`, file),
  checkStory: (slug: string, p: string) => call<StoryCheck>('GET', `${part(slug, p)}/check-story`),
  deletePart: (slug: string, p: string) => call<SeriesModel>('DELETE', part(slug, p)),
  deleteSeries: (slug: string) => call<{ ok: boolean }>('DELETE', `/api/series/${e(slug)}`),
  cleanFrames: (slug: string, p: string) => call<PartModel>('POST', `${part(slug, p)}/clean-frames`),
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
  wardrobe: () => call<WardrobeCatalog>('GET', '/api/wardrobe'),
  saveWardrobeItem: (w: WardrobeItem) => call<WardrobeCatalog>('PUT', `/api/wardrobe/${e(w.id)}`, w),
  deleteWardrobeItem: (id: string) => call<WardrobeCatalog>('DELETE', `/api/wardrobe/${e(id)}`),
  validatePackage: (text: string) => call<PackageResult>('POST', '/api/packages/validate', { text }),
  importPackage: (text: string) => call<PackageResult>('POST', '/api/packages/import', { text }),
}
