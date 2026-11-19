// Captions with Gemini (POST /api/captions, the one task an outside AI does here): a prompt from the part's narration,
// the next part's opening and the brand tags; four fields back. upload.md keeps them as markdown sections.

/** narration lines of a story.md: no title, @ directives or the !! marker */
const narration = (md: string) => md.split('\n').map((l) => l.trim())
  .filter((l) => l && !l.startsWith('#') && !l.startsWith('@')).map((l) => l.replace(/^!!\s*/, '')).join('\n')

export type CaptionInput = {
  series: string; number: number; parts: number
  title: string; story: string // this part's story.md
  next?: { title: string; story: string } // the next part, for a teaser
  brandTags?: string // e.g. "#scribblefactory #stickmanhistory": on every caption
  handles?: { youtube?: string; instagram?: string }
}

export function buildCaptionPrompt(c: CaptionInput): string {
  const last = c.number === c.parts
  const brand = c.brandTags?.trim()
  const ig = c.handles?.instagram?.trim()
  return `Write YouTube Shorts and Instagram Reels captions for one part of a stickman animated series.

Series: ${c.series}
This is part ${c.number} of ${c.parts}${last ? ' (the finale)' : ''}: "${c.title}"

Its narration (what the video says):
${narration(c.story)}
${c.next ? `\nThe next part, "${c.next.title}", opens with: ${narration(c.next.story).split('\n')[0]}\n` : ''}
Hashtags: story tags first (the people, places, era and topic of THIS story, specific beats generic), then the brand tags${brand ? `, exactly as written: ${brand}` : ' (#stickman #animation)'}.

Fields:
- youtube_title: at most 70 characters, a curiosity hook from the most surprising claim, not the series name. One emoji at most.
- youtube_description: two short lines (the hook, then "Part ${c.number} of ${c.parts}."${last ? '' : ' and a nudge to follow for the next part'}), a blank line, then 5 to 7 hashtags starting with #shorts.
- youtube_pinned_comment: the creator's pinned comment that starts a conversation: one short, specific question or a "would you have..." choice about this story's twist, plus at most one emoji. No hashtags, no links, no "like and subscribe".
- instagram_caption: the whole post as one text. First line is the hook (under 100 characters: all that shows before "more"). Then two or three short lines of story, "Part ${c.number} of ${c.parts}"${ig && !last ? ` and "Follow ${ig} for part ${c.number + 1}"` : ''}, and a question that invites comments, ending with 👇. A blank line, then 8 to 12 hashtags ending with #reels.
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

/** text with hashtags gets the brand tags it lacks appended (case-insensitive match); text without any is left alone */
export function withBrandTags(text: string, brand: string): string {
  const t = text.trim()
  const has = new Set((t.match(/#[\p{L}\p{N}_]+/gu) ?? []).map((h) => h.toLowerCase()))
  if (!has.size) return t
  const missing = (brand.match(/#[\p{L}\p{N}_]+/gu) ?? []).filter((h) => !has.has(h.toLowerCase()) && has.add(h.toLowerCase()))
  return missing.length ? `${t} ${missing.join(' ')}` : t
}
