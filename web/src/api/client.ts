// Thin typed client over fetch. Types come from docs/openapi.json (npm run gen:api).
import type { components } from './types'

type S = components['schemas']
export type Overview = S['Overview']
export type SeriesCard = S['SeriesCard']
export type SeriesDetail = S['SeriesDetail']
export type PartSummary = S['PartSummary']
export type CastMember = S['CastMember']

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function get<T>(path: string): Promise<T> {
  let r: Response
  try {
    r = await fetch(path)
  } catch {
    throw new ApiError(0, 'The API is not reachable. Is uvicorn running on port 8765?')
  }
  if (!r.ok) {
    const detail = await r.json().then((b) => b?.detail, () => null)
    throw new ApiError(r.status, typeof detail === 'string' ? detail : `${r.status} ${r.statusText}`)
  }
  return r.json() as Promise<T>
}

export const api = {
  overview: () => get<Overview>('/api/overview'),
  series: () => get<SeriesCard[]>('/api/series'),
  seriesDetail: (slug: string) => get<SeriesDetail>(`/api/series/${encodeURIComponent(slug)}`),
}
