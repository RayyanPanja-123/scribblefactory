// The expression vocabulary shared by cast editing, wardrobe conditions and previews.
// Expressions are engine-drawn, so this is a read-only library of built-ins rather than
// user-authored JSON assets.
export const EXPRESSIONS = ['neutral', 'happy', 'cheer', 'sad', 'angry', 'surprised', 'sleepy', 'cheeky', 'exhausted', 'worried', 'dead',
  'smug', 'proud', 'love', 'excited', 'relieved', 'laughing', 'wink', 'furious', 'annoyed', 'disgusted', 'crying', 'scared', 'embarrassed', 'jealous', 'guilty', 'confused', 'thinking', 'suspicious', 'shocked', 'deadpan', 'bored', 'facepalm_ready', 'dizzy', 'drunk', 'knocked_out', 'evil', 'crazy', 'blank', 'sick', 'determined'] as const
export type Expression = typeof EXPRESSIONS[number]

export const expressionOptions = EXPRESSIONS.map((id) => ({
  id,
  name: id[0].toUpperCase() + id.slice(1),
}))

export const expressionNote: Record<Expression, string> = {
  neutral: 'calm baseline', happy: 'smile', cheer: 'big smile', sad: 'downturned mouth', angry: 'furrowed brows',
  surprised: 'wide eyes and open mouth', sleepy: 'half-closed eyes', cheeky: 'lopsided grin',
  exhausted: 'drooping lids', worried: 'raised inner brows', dead: 'X eyes',
  smug: 'one brow up, smirk', proud: 'half-closed eyes, soft smile', love: 'heart eyes', excited: 'huge eyes, open grin',
  relieved: 'closed eyes, small exhale', laughing: 'squeezed eyes, open mouth', wink: 'one eye closed',
  furious: 'heavy brows, gritted teeth', annoyed: 'half lids, one brow low', disgusted: 'squint, wavy mouth',
  crying: 'tear drops', scared: 'tiny pupils, jagged mouth', embarrassed: 'blush, looking away', jealous: 'side-eye, tight frown',
  guilty: 'eyes down', confused: 'uneven brows, squiggle mouth', thinking: 'eyes up, mouth to one side',
  suspicious: 'narrow eyes', shocked: 'tiny pupils, huge open mouth', deadpan: 'dot eyes, straight mouth',
  bored: 'half lids, flat mouth', facepalm_ready: 'eyes closed, tired frown', dizzy: 'spiral eyes',
  drunk: 'wobbly eyes, goofy grin', knocked_out: '> < eyes, tongue out', evil: 'angled brows, wide grin',
  crazy: 'mismatched pupils, big teeth', blank: 'empty eyes, no mouth', sick: 'green tint, droopy eyes', determined: 'brows low and set, firm straight mouth'
}
