// The expression vocabulary shared by cast editing, wardrobe conditions and previews.
// Expressions are engine-drawn, so this is a read-only library of built-ins rather than
// user-authored JSON assets.
export const EXPRESSIONS = ['neutral', 'happy', 'cheer', 'sad', 'angry', 'surprised', 'sleepy', 'cheeky', 'exhausted', 'worried', 'dead'] as const
export type Expression = typeof EXPRESSIONS[number]

export const expressionOptions = EXPRESSIONS.map((id) => ({
  id,
  name: id[0].toUpperCase() + id.slice(1),
}))

export const expressionNote: Record<Expression, string> = {
  neutral: 'calm baseline', happy: 'smile', cheer: 'big smile', sad: 'downturned mouth', angry: 'furrowed brows',
  surprised: 'wide eyes and open mouth', sleepy: 'half-closed eyes', cheeky: 'lopsided grin',
  exhausted: 'drooping lids', worried: 'raised inner brows', dead: 'X eyes'
}
