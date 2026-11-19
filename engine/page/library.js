// The library's custom items, one registry for every kind: what the user made in the dashboard (library/<kind>.json),
// handed to the page once (main.js setup, or a dashboard preview) and looked up by id while drawing. Built-ins stay
// in their own modules (stickman.js props, world.js sets, creatures.js bodies, actions.js moves); each module asks
// here for anything it doesn't build in. A new kind of item is a new key here and one lookup where it is drawn.
// Unknown ids throw: a typo never silently renders as something else.
export const KINDS = ["props", "sets", "objects", "creatures", "actions", "wardrobe"];
const lib = Object.fromEntries(KINDS.map((k) => [k, new Map()]));

/** replace the custom items of each kind given ({ props: [...], sets: [...] }); kinds left out keep theirs */
export function setLibrary(data = {}) {
  for (const k of KINDS) if (data[k]) lib[k] = new Map(data[k].map((x) => [x.id, x]));
}

/** the custom item of this kind, or undefined */
export const find = (kind, id) => lib[kind].get(id);

/** the custom item of this kind; throws for an unknown id (the caller checked its built-ins first) */
export function lookup(kind, id) {
  const v = lib[kind].get(id);
  if (v === undefined) throw new Error(`unknown ${kind.endsWith("s") ? kind.slice(0, -1) : kind} "${id}": not built in and not in library/${kind}.json`);
  return v;
}
