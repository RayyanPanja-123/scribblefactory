import type { components } from '../api/types'

type S = components['schemas']
// as the API accepts them: fields with a server default may be left out
export type SetPiece = Omit<S['SetPiece'], 'backdrop' | 'outline'> & Partial<Pick<S['SetPiece'], 'backdrop' | 'outline'>>
export type WorldObjectInstance = { id: string; object: string; at: number[]; visible?: boolean }
export type CustomSet = Omit<S['CustomSet'], 'pieces' | 'objects'> & { pieces?: SetPiece[]; objects?: WorldObjectInstance[] }
export type SetCatalog = Omit<S['SetCatalog'], 'custom'> & { custom: CustomSet[] }
export type SetKind = CustomSet['kind']

const NOTES: Record<string, string> = {
  room: 'living room: sofa, lamp, window',
  office: 'two desks, water cooler, plants',
  street: 'town houses and a pavement',
  dirt_road: 'crossroads, fence, telegraph poles',
  countryside: 'fields, oaks, a farmhouse',
  orchard: 'rows of fruit trees',
  stadium: 'track, stands and a finish line',
}
export const builtinNote = (id: string) => NOTES[id] ?? ''

/** per shape: what each size value means, and a starting piece placed behind the stage */
export const SHAPES: Record<SetPiece['shape'], { label: string; size: string[]; start: SetPiece }> = {
  box: { label: 'Box', size: ['width', 'height', 'depth'], start: { shape: 'box', at: [-2.8, 0.5, -2], size: [1, 1, 0.6], color: '#8a5a32' } },
  cyl: { label: 'Cylinder', size: ['top radius', 'bottom radius', 'height'], start: { shape: 'cyl', at: [2.8, 0.6, -2], size: [0.25, 0.25, 1.2], color: '#e9c46a' } },
  ball: { label: 'Ball', size: ['radius'], start: { shape: 'ball', at: [2.8, 0.5, -2], size: [0.5], color: '#43aa8b' } },
  mound: { label: 'Mound', size: ['radius', 'height factor'], start: { shape: 'mound', at: [0, -1, -30], size: [10, 0.3], color: '#a9b779', backdrop: true } },
}

export const STARTER: Record<SetKind, Pick<CustomSet, 'floor' | 'back' | 'pieces'>> = {
  indoor: { floor: '#d9c7a3', back: '#f6e7c8', pieces: [
    { shape: 'box', at: [-1.8, 0.45, -2.2], size: [1.6, 0.9, 0.6], color: '#8a5a32' },
    { shape: 'box', at: [1.6, 2.2, -2.55], size: [1.4, 1.2, 0.08], color: '#9fd3f5', backdrop: true },
  ] },
  outdoor: { floor: '#f2d8a0', back: '#8fd0f0', pieces: [
    { shape: 'cyl', at: [-3, 1.5, -3], size: [0.1, 0.15, 3], color: '#7b5132' },
    { shape: 'ball', at: [-3, 3.1, -3], size: [0.9], color: '#4caf50' },
    { shape: 'mound', at: [10, -1, -40], size: [14, 0.3], color: '#98a86e', backdrop: true },
  ] },
}
