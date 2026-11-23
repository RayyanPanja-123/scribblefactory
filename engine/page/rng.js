// Seeded randomness. Never Math.random: every value derives from the story seed and stable keys.

/** FNV-1a over the string form of each key -> uint32 */
export function hash(...keys) {
  let h = 2166136261;
  for (const k of keys) {
    const s = String(k);
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    h ^= 0x1f; h = Math.imul(h, 16777619); // key separator
  }
  return h >>> 0;
}

/** mulberry32 PRNG: () -> [0, 1) */
function mulberry32(a) {
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const rng = (...keys) => mulberry32(hash(...keys));

/** prop variant of a set for a run of shots: hash(set, id of the run's first shot) mod count */
export const setVariant = (set, shotId, count) => (count > 1 ? hash(set, shotId) % count : 0);
