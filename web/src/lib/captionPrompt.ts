// Captions with Gemini (POST /api/captions, the one task an outside AI does here): a prompt from the part's narration,
// the next part's opening and the handles; four fields back. upload.md keeps them as markdown sections.

/** narration lines of a story.md: no title, @ directives or the !! marker */
const narration = (md: string) => md.split('\n').map((l) => l.trim())
  .filter((l) => l && !l.startsWith('#') && !l.startsWith('@')).map((l) => l.replace(/^!!\s*/, '')).join('\n')

export type CaptionInput = {
  series: string; number: number; parts: number
  title: string; story: string // this part's story.md
  before?: { number: number; title: string; story: string }[] // earlier parts, in order: the story so far
  next?: { title: string; story: string } // the next part, for a teaser
  cast?: { name: string; body: string }[]
  handles?: { youtube?: string; instagram?: string }
}

export function buildCaptionPrompt(c: CaptionInput): string {
  const last = c.number === c.parts
  const ig = c.handles?.instagram?.trim()
  const cast = c.cast?.length ? `\nCharacters: ${c.cast.map((x) => x.body === 'human' ? x.name : `${x.name} (a ${x.body})`).join(', ')}\n` : ''
  const before = c.before?.length
    ? `\nThe story so far (earlier parts, for context only; the captions are about this part):\n${c.before.map((b) => `Part ${b.number}, "${b.title}":\n${narration(b.story)}`).join('\n\n')}\n`
    : ''
  return `Write YouTube Shorts and Instagram Reels captions for one part of a stickman animated series.

Series: ${c.series}
${cast}${before}
This is part ${c.number} of ${c.parts}${last ? ' (the finale)' : ''}: "${c.title}"

Its narration (what the video says):
${narration(c.story)}
${c.next ? `\nThe next part, "${c.next.title}", opens with: ${narration(c.next.story).split('\n')[0]}\n` : ''}
Fields:
- youtube_title: at most 70 characters, a curiosity hook from the most surprising claim, not the series name. One emoji at most.
- youtube_description: three blocks separated by blank lines, no emoji:
  1. One plain sentence stating the story's premise as a fact, its most surprising claim in concrete detail.
  2. "Part ${c.number} of ${c.parts}."${last ? '' : ' then "Follow for the next part."'}
  3. 4 hashtags: #shorts #AnimatedStory #Reels and one genre tag (#fiction, or #history for true history).
  Example of the shape (copy its structure, never its words):
  A tech billionaire sold a night on a private island sitting twenty-four hours in the future.

  Part 1 of 3. Follow for the next part.

  #shorts #AnimatedStory #Reels #fiction
- youtube_pinned_comment: the creator's pinned comment that starts a conversation: one short, specific question or a "would you have..." choice about this story's twist, plus at most one emoji. No hashtags, no links, no "like and subscribe".
- instagram_caption: the whole post as one text, four blocks separated by blank lines:
  1. The hook: one line under 100 characters (all that shows before "more"), the story's most surprising situation as a "When..." or a bold claim, ending with two fitting emoji.
  2. One paragraph of two or three sentences: it opens "In Part ${c.number} of this original <genre> short story told in stickman animation," (pick the genre from the story, e.g. sci-fi, comedy, mystery; for true history say "true story" instead of "original <genre> short story"), then what happens and what it sets off, in concrete detail.
  3. One line: a question that invites comments (a "Would you..." choice about this story), then "Part ${c.number} of ${c.parts}."${ig && !last ? ` then "Follow ${ig} for Part ${c.number + 1}."` : ''}, ending with 👇.
  4. 4 to 6 hashtags: the format (#stickmananimation), the genre (e.g. #scifistory), broad story tags (#shortstory #animatedstories).
  Example of the shape (copy its structure and tone, never its words or story):
  When fourteen million strangers all win the exact same lottery jackpot. 🎟️💸

  In Part 2 of this original sci-fi short story told in stickman animation, a leaked photo from the future broke the rules and bankrupted the national lottery in minutes. Every winner walked away with just twelve cents, and furious billionaires immediately retaliated.

  Would you risk your safety for a twelve-cent prize? Part 2 of 3. Follow @scribblesagashorts for Part 3. 👇

  #stickmananimation #shortstory #scifistory #animatedstories
- Every field is about this part's own events, in concrete detail from its narration, using the characters' names and the story's real objects; nothing generic that could caption any video, nothing the story never says.
- Tease the last line's twist; never quote it. If the story is true history, say so ("True story").
- Plain, punchy, no clickbait lies, no markdown.`
}

export type Captions = { title: string; description: string; pinned: string; instagram: string }
const YT = { title: 'Title', description: 'Description', pinned: 'Pinned comment' } as const

/** the text under each "## name" (or "### name") heading of md */
function sections(md: string, level: '##' | '###'): Record<string, string> {
  const out: Record<string, string> = {}
  const parts = md.split(new RegExp(`^${level} +(.+?)\\s*$`, 'm'))
  for (let i = 1; i < parts.length; i += 2) out[parts[i].toLowerCase()] = parts[i + 1].trim()
  return out
}

/** upload.md -> the four captions. Older files ("Title: ..." then the description under ## YouTube) still load */
export function parseUpload(md: string): Captions {
  const top = sections(md, '##')
  const yt = top.youtube ?? ''
  const sub = sections(yt, '###')
  if (/^### /m.test(yt)) {
    return { title: sub.title ?? '', description: sub.description ?? '', pinned: sub['pinned comment'] ?? '', instagram: top.instagram ?? '' }
  }
  const title = /^Title:\s*(.*)$/m.exec(yt)
  return { title: title?.[1].trim() ?? '', description: yt.replace(/^Title:.*$/m, '').trim(), pinned: '', instagram: top.instagram ?? '' }
}

export function composeUpload(head: string, c: Captions): string {
  const yt = (Object.keys(YT) as (keyof typeof YT)[]).map((k) => `### ${YT[k]}\n\n${c[k].trim()}`).join('\n\n')
  return `# ${head}\n\n## YouTube\n\n${yt}\n\n## Instagram\n\n${c.instagram.trim()}\n`
}
