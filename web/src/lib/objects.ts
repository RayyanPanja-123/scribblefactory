export type ObjectCategory = 'vehicle' | 'container' | 'furniture' | 'equipment' | 'debris' | 'other'
export type CarryMode = 'none' | 'one-hand' | 'two-hand' | 'vehicle'
export type Capability = 'move' | 'carry' | 'enter' | 'ride' | 'open' | 'close' | 'break' | 'steal' | 'remove'
export type ObjectPiece = { shape: 'box' | 'cyl' | 'ball' | 'mound'; at: number[]; size: number[]; color: string; backdrop?: boolean; outline?: boolean }
export type WorldObject = { id: string; name: string; category: ObjectCategory; capabilities: Capability[]; carry_mode: CarryMode; pieces: ObjectPiece[] }
export type ObjectCatalog = { objects: WorldObject[] }

export const CATEGORIES: ObjectCategory[] = ['vehicle', 'container', 'furniture', 'equipment', 'debris', 'other']
export const CAPABILITIES: Capability[] = ['move', 'carry', 'enter', 'ride', 'open', 'close', 'break', 'steal', 'remove']
export const CARRY_MODES: CarryMode[] = ['none', 'one-hand', 'two-hand', 'vehicle']
export const PIECES: Record<ObjectPiece['shape'], { label: string; size: string[]; start: ObjectPiece }> = {
  box: { label: 'Box', size: ['width', 'height', 'depth'], start: { shape: 'box', at: [0, .5, 0], size: [1, 1, 1], color: '#8a5a32' } },
  cyl: { label: 'Cylinder', size: ['top radius', 'bottom radius', 'height'], start: { shape: 'cyl', at: [0, .6, 0], size: [.35, .35, 1.2], color: '#8a5a32' } },
  ball: { label: 'Ball', size: ['radius'], start: { shape: 'ball', at: [0, .5, 0], size: [.5], color: '#43aa8b' } },
  mound: { label: 'Mound', size: ['radius', 'height factor'], start: { shape: 'mound', at: [0, 0, 0], size: [1, .3], color: '#a9b779' } },
}
