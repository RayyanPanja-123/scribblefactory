// The closing section of every "Generate with AI" prompt: plan the design first, then check the reply before sending.
// steps = how to design this kind of item well; checks = the item's own mistakes to look for (on top of the JSON ones).
export const aiCheck = (steps: string[], checks: string[]) => `## How to design it well
${steps.map((s, i) => `${i + 1}. ${s}`).join('\n')}

## Check before you reply (fix anything that fails, then send)
- Plain JSON: double quotes, no comments, no trailing commas, no "..." placeholders, no keys besides the ones above.
${checks.map((c) => `- ${c}`).join('\n')}`

/** for the 2D shape formats (props, creatures, wardrobe) */
export const PTS_CHECK = 'Every "pts" is a list of points, each exactly [x, y] with two numbers: a rect is [[x0, y0], [x1, y1]], a circle [[cx, cy]]. Never [[[x, y], ...]] (one bracket too many) or [x, y, x, y].'
