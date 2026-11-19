import type { components } from '../api/types'

export type SfxView = components['schemas']['SfxView']
export type SfxEntry = Omit<SfxView, 'missing' | 'users'>
export type SfxCatalog = components['schemas']['SfxCatalog']
export type SfxSuggestion = components['schemas']['SfxSuggestion']
export type SfxSuggestions = components['schemas']['SfxSuggestions']
export type Anchor = SfxEntry['anchor']

export const ANCHORS: { id: Anchor; label: string; note: string }[] = [
  { id: 'start', label: 'Line start', note: 'plays as the line starts' },
  { id: 'end_on_line', label: 'Ends on line', note: 'pre-roll: ends exactly as the line starts (risers)' },
  { id: 'after_line', label: 'After line', note: 'plays once the line has been said' },
]

/** a file name as a sound id: "Vine Boom.mp3" -> vine_boom */
export const idFromFile = (name: string) =>
  name.replace(/\.[^.]+$/, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 60) || 'sound'
