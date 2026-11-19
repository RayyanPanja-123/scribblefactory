// Captions with any chat AI (copy/paste, like every AI feature here): a prompt from the part's narration and the
// next part's opening, and the reply back as upload.md text. The user reviews and saves it; nothing is written here.

/** narration lines of a story.md: no title, @ directives or the !! marker */
const narration = (md: string) => md.split('\n').map((l) => l.trim())
  .filter((l) => l && !l.startsWith('#') && !l.startsWith('@')).map((l) => l.replace(/^!!\s*/, '')).join('\n')

export type CaptionInput = {
  series: string; number: number; parts: number
  title: string; story: string // this part's story.md
  next?: { title: string; story: string } // the next part, for a teaser
}

export function buildCaptionPrompt(c: CaptionInput): string {
  const head = `${c.series} — Part ${c.number}`
  const last = c.number === c.parts
  return `Write YouTube Shorts and Instagram Reels captions for one part of a stickman animated series.

Series: ${c.series}
This is part ${c.number} of ${c.parts}${last ? ' (the finale)' : ''}: "${c.title}"

Its narration (what the video says):
${narration(c.story)}
${c.next ? `\nThe next part, "${c.next.title}", opens with: ${narration(c.next.story).split('\n')[0]}\n` : ''}
Rules:
- YouTube title: at most 70 characters, a curiosity hook from the most surprising claim, not the series name. One emoji at most.
- YouTube description: two short lines (the hook, then "Part ${c.number} of ${c.parts}."${last ? '' : ' and a nudge to follow for the next part'}), then 4 to 5 hashtags starting with #shorts.
- Instagram: the first line is the hook (under 100 characters: it is all that shows before "more"). Then two or three short lines of story, "Part ${c.number} of ${c.parts}", and a question that invites comments, ending with 👇. Then 8 to 10 hashtags ending with #reels.
- Tease the last line's twist; never quote it. If the story is true history, say so ("True story").
- Plain, punchy, no clickbait lies, no markdown besides the headings below.

Reply with only this, in one fenced \`md\` block:

# ${head}

## YouTube

Title: <title>

<description>

<hashtags>

## Instagram

<caption>

<hashtags>
`
}

/** the reply -> upload.md text, or an error. A fenced block, or the whole message from "# " on */
export function parseCaptionReply(text: string): { md?: string; error?: string } {
  const fenced = /```(?:md|markdown)?\s*\n([\s\S]*?)```/i.exec(text)?.[1]
  const body = (fenced ?? text.slice(Math.max(0, text.search(/^# /m)))).trim()
  if (!/^## YouTube$/m.test(body) || !/^## Instagram$/m.test(body)) return { error: 'Expected a "## YouTube" and a "## Instagram" section.' }
  return { md: `${body}\n` }
}
