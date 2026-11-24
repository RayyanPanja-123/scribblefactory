export type ObjectCategory = 'vehicle' | 'container' | 'furniture' | 'equipment' | 'debris' | 'sky' | 'env' | 'scifi' | 'other'
export type CarryMode = 'none' | 'one-hand' | 'two-hand' | 'vehicle'
export type Capability = 'move' | 'carry' | 'enter' | 'ride' | 'open' | 'close' | 'break' | 'steal' | 'remove' | 'sit' | 'push'
export type ObjectPiece = { shape: 'box' | 'cyl' | 'ball' | 'mound'; at: number[]; size: number[]; color: string; backdrop?: boolean; outline?: boolean }
export type ItemLayer = 'sky' | 'back' | 'mid' | 'stage'
export type AnimKind = 'rotate' | 'sway' | 'bob' | 'drift' | 'pulse' | 'blink' | 'flow'
export type ItemAnim = { kind: AnimKind; amp?: number; hz?: number; when?: string[] | null }
/** a World Item (pipeline schemas WorldObject): look pieces = set-piece primitives, card = a 2D ink drawing */
export type WorldObject = {
  id: string; name: string; category: ObjectCategory; capabilities: Capability[]; carry_mode: CarryMode; pieces: ObjectPiece[]
  look?: 'pieces' | 'card'; draw?: string | null; shapes?: unknown[]; size?: number; layer?: ItemLayer; states?: string[]; anims?: ItemAnim[]
  anchors?: Partial<Record<'handle' | 'seat' | 'pickup', number[]>>; seats?: number[][]; clip_y?: number | null; prop?: string | null
  params?: { main?: string; accent?: string; rings?: number; stalks?: number }
}
export type ObjectCatalog = { objects: WorldObject[] }

export const CATEGORIES: ObjectCategory[] = ['vehicle', 'container', 'furniture', 'equipment', 'debris', 'sky', 'env', 'scifi', 'other']
export const DRAWINGS = ['planet', 'saucer', 'pod', 'bench', 'crystal', 'sun', 'plant'] // engine/page/items.js DRAWERS
export const LAYERS: ItemLayer[] = ['sky', 'back', 'mid', 'stage']
export const RESERVED_STATES = ['remove', 'state'] // @item <tag>: remove | state <s>
/** what amp means per animation kind (pipeline schemas ItemAnim) */
export const ANIMS: Record<AnimKind, { amp: string; hz: boolean; start: ItemAnim }> = {
  rotate: { amp: 'degrees / s', hz: false, start: { kind: 'rotate', amp: 10 } },
  sway: { amp: '± degrees', hz: true, start: { kind: 'sway', amp: 6, hz: 0.4 } },
  bob: { amp: '± units', hz: true, start: { kind: 'bob', amp: 0.15, hz: 0.5 } },
  drift: { amp: '± units', hz: true, start: { kind: 'drift', amp: 0.4, hz: 0.05 } },
  pulse: { amp: 'share 0–0.9', hz: true, start: { kind: 'pulse', amp: 0.05, hz: 0.5 } },
  blink: { amp: 'share 0–1', hz: true, start: { kind: 'blink', amp: 0.6, hz: 1 } },
  flow: { amp: 'unused', hz: true, start: { kind: 'flow', hz: 0.02 } },
}
/** a fresh item of each look (every field set, so switching rows never carries fields over) */
export const blankObject = (look: 'pieces' | 'card' = 'pieces'): WorldObject => look === 'card'
  ? { id: '', name: '', category: 'other', capabilities: [], carry_mode: 'none', pieces: [], look: 'card', draw: 'saucer', size: 1.6, layer: 'back', states: [], anims: [] }
  : { id: '', name: '', category: 'other', capabilities: [], carry_mode: 'none', pieces: [] }
export const CAPABILITIES: Capability[] = ['move', 'carry', 'enter', 'ride', 'open', 'close', 'break', 'steal', 'remove', 'sit', 'push']
export const ANCHORS = ['handle', 'seat', 'pickup'] as const // what open/close/push, sit and pickup reach for (world units from the base)
export const CARRY_MODES: CarryMode[] = ['none', 'one-hand', 'two-hand', 'vehicle']
export const PIECES: Record<ObjectPiece['shape'], { label: string; size: string[]; start: ObjectPiece }> = {
  box: { label: 'Box', size: ['width', 'height', 'depth'], start: { shape: 'box', at: [0, .5, 0], size: [1, 1, 1], color: '#8a5a32' } },
  cyl: { label: 'Cylinder', size: ['top radius', 'bottom radius', 'height'], start: { shape: 'cyl', at: [0, .6, 0], size: [.35, .35, 1.2], color: '#8a5a32' } },
  ball: { label: 'Ball', size: ['radius'], start: { shape: 'ball', at: [0, .5, 0], size: [.5], color: '#43aa8b' } },
  mound: { label: 'Mound', size: ['radius', 'height factor'], start: { shape: 'mound', at: [0, 0, 0], size: [1, .3], color: '#a9b779' } },
}
