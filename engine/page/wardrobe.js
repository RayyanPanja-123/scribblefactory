// Wardrobe: clothing, hair and cosmetics a humanoid wears, one item per slot (accessory and face: up to 3).
// Built-in items (the original tops, headwear and legwear) keep their hand-written drawing in stickman.js, so old casts
// render exactly as before; custom items (library/wardrobe.json, schema WardrobeItem) are ink layers anchored to body
// points (stickman.js anchors), which scale with the build and move with every pose. Pure functions (Node-testable).
import { ellPts } from "./borrowed.js";
import { lookup } from "./library.js";

export const SLOTS = ["hair", "facial_hair", "headwear", "top", "legwear", "footwear", "back", "accessory", "face"];
/** back to front */
export const DRAW_ORDER = ["back", "legwear", "footwear", "top", "accessory", "face", "facial_hair", "hair", "headwear"];
export const LIST_SLOTS = new Set(["accessory", "face"]);
export const MAX_LIST = 3;
/** the built-in items: id -> slot (keep equal to pipeline/scribble/schemas BUILTIN_WARDROBE) */
export const BUILTIN_WARDROBE = {
  plain: "top", suit: "top", tank: "top", shirt: "top", dress: "top",
  flat_cap: "headwear", postman_cap: "headwear", bowler: "headwear", straw_hat: "headwear", wide_hat: "headwear",
  shorts: "legwear", ragged_shorts: "legwear", trousers: "legwear",
};
/** anchors drawn in head space (scaled with the head, over the face); the rest are body anchors */
export const HEAD_ANCHORS = new Set(["head", "head_top", "face", "eyes", "mouth"]);
/** anchors that come in a left / right pair: a layer is drawn at both, mirrored on the left (-x) side */
export const PAIRED = new Set(["shoulders", "arms", "hands", "legs", "feet"]);
export const ANCHORS = [...HEAD_ANCHORS, "neck", "shoulders", "chest", "waist", "hips", "back", "arms", "hands", "legs", "feet"];

/** one slot value -> { id, color } or null (none). Accepts a plain id, { id, color }, the original { kind } (headwear,
 *  legwear) / { style } (top) objects, null and "none". */
export function slotValue(v) {
  if (v == null || v === "none") return null;
  if (typeof v === "string") return { id: v, color: null };
  const id = v.id ?? v.kind ?? v.style;
  return !id || id === "none" ? null : { id, color: v.color ?? null };
}

/** every slot value of a figure's options, in draw order: [{ slot, id, color }] (list slots flattened) */
export function slotsOf(o) {
  const out = [];
  for (const slot of DRAW_ORDER) {
    const raw = o[slot];
    for (const v of LIST_SLOTS.has(slot) && Array.isArray(raw) ? raw.slice(0, MAX_LIST) : [raw]) {
      const s = slotValue(v);
      if (s) out.push({ slot, ...s });
    }
  }
  return out;
}

/** the custom items a figure wears, in draw order: [{ slot, item, color }]; built-ins are left to stickman.js.
 *  color: the cast member's colour for the slot when the item is colorable, else the item's default. Throws for an
 *  unknown id or an item in the wrong slot (a typo never renders as something else). */
export function wearing(o) {
  const out = [];
  for (const { slot, id, color } of slotsOf(o)) {
    if (BUILTIN_WARDROBE[id]) {
      if (BUILTIN_WARDROBE[id] !== slot) throw new Error(`wardrobe item "${id}" is a ${BUILTIN_WARDROBE[id]}, not ${slot}`);
      continue;
    }
    const item = lookup("wardrobe", id);
    if (item.slot !== slot) throw new Error(`wardrobe item "${id}" is a ${item.slot}, not ${slot}`);
    out.push({ slot, item, color: item.colorable !== false && color ? color : item.default_color });
  }
  return out;
}

/** a layer's points in canvas px for one anchor frame { at, sx, sy, ang (radians from straight down, + toward +x),
 *  m (1, or -1 mirrored for the left side) }: local x across (+ outward on paired anchors), y down / along the limb */
export function layerPoints(L, fr) {
  const [[x0, y0], [x1, y1] = [0, 0]] = L.pts;
  const local = L.shape === "rect" ? [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    : L.shape === "circle" ? ellPts(x0, y0, L.r, L.r, 0, 360, 0, 24)
    : L.shape === "ellipse" ? ellPts(x0, y0, L.r, L.ry, 0, 360, L.rot || 0, 24)
    : L.pts;
  const c = Math.cos(fr.ang), s = Math.sin(fr.ang);
  return local.map(([x, y]) => {
    const u = x * fr.m * fr.sx, v = y * fr.sy;
    return [fr.at[0] + u * c + v * s, fr.at[1] - u * s + v * c];
  });
}

/** a layer's fill / line colour: "$color" is the worn colour; a line without one is ink (null) */
export const layerFill = (L, color) => (L.fill === "$color" ? color : L.fill ?? null);
