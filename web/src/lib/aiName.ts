// "Generate with AI": a short name (and so a short id) from the free-text description; the whole description still
// goes into the prompt as the brief. "A bright red baker's hat with a soft, floppy crown" -> "Red bakers hat".

/** where the thing itself ends and its details start */
const DETAILS = /\s(?:with|that|which|who|at|on|in|for|from|wearing|holding|while|where|under|over|near|by)\s|[.;:()!?\n]/i
const FILLER = new Set(['a', 'an', 'the', 'some', 'of', 'and', 'or', 'very', 'really', 'my'])
const MAX_WORDS = 3, MAX_CHARS = 24

export function shortName(description: string): string {
  const words = (s: string) => s.replace(/['’]/g, '').split(/[^\p{L}\p{N}]+/u).filter((w) => w && !FILLER.has(w.toLowerCase()))
  const head = words(description.split(DETAILS)[0])
  let picked = (head.length ? head : words(description)).slice(-MAX_WORDS) // the noun comes last: "... baker's hat"
  while (picked.length > 1 && picked.join(' ').length > MAX_CHARS) picked = picked.slice(1)
  const name = picked.join(' ').toLowerCase().slice(0, MAX_CHARS)
  return name.charAt(0).toUpperCase() + name.slice(1)
}
