// Story step 1, title -> voice scripts: a small self-contained prompt (only docs/ai/tts.md, no library, no directives)
// and the reader for its reply. Each script becomes a part whose story.md is the lines under a starter @set; staging
// comes later, one part at a time. The voice mode (single narration or cast voice acting) is the creator's choice,
// asked in the app before the prompt is made: the prompt states it, the AI never guesses it.
import ttsRules from '../../../docs/ai/tts.md?raw'

export type VoicePart = { title: string; lines: string[] }
export type VoiceMode = 'narration' | 'cast'
type Cast = { id: string; name: string }

/** "kai: line" -> kai (a speaker's line, as story.md reads it; prep.SPEAKER) */
const SPEAKER = /^(?:!!\s+)?([a-z0-9]+(?:-[a-z0-9]+)*):\s/
export const speakerOf = (line: string) => line.match(SPEAKER)?.[1] ?? null
/** the words a line says: without the twist marker and the speaker */
const spoken = (line: string) => line.replace(/^!!\s*/, '').replace(/^[a-z0-9]+(?:-[a-z0-9]+)*:\s+/, '').replace(/^["“](.*)["”]$/, '$1')
export const spokenWords = (p: VoicePart) => p.lines.map(spoken).join(' ').split(/\s+/).filter(Boolean).length

export function voicePrompt(o: { title: string; parts: number; mode: VoiceMode; notes?: string; cast?: Cast[] }): string {
  const cast = o.cast ?? []
  const acting = o.mode === 'cast'
  return [
    acting
      ? 'You write the spoken lines for scribblefactory: vertical stickman story Shorts. A narrator and the characters each speak in their own voice.'
      : 'You write narration for scribblefactory: vertical stickman story Shorts. A voice reads each part aloud.',
    `Story: "${o.title}". Write exactly ${o.parts} part${o.parts === 1 ? '' : 's'}.`,
    'Real history or invented fantasy are both fine: follow the title and the notes.',
    acting
      ? 'Voice mode (the creator chose it): **cast voice acting**. Lines 1 to 3 are narration; after that the characters speak their own lines as `<cast id>: words`.'
      : 'Voice mode (the creator chose it): **single narration**. Every line is the narrator\'s: no `id: ` speaker lines.',
    cast.length
      ? `Characters already in this series: ${cast.map((c) => (acting ? `\`${c.id}\` ${c.name}` : c.name)).join(', ')}.${acting ? ' Only these may speak: use their id before the colon.' : ' Use these names.'}`
      : '',
    o.notes?.trim() ? `Notes from the creator: ${o.notes.trim()}` : '',
    '',
    ttsRules.trim(),
    '',
    '## Reply',
    `Only this block, markers alone on their line, one line per line, no directives (\`@\`), no markdown in the lines${acting ? ', a character\'s own line as `<cast id>: words`' : ''}:`,
    '```text',
    ...Array.from({ length: Math.min(o.parts, 2) }, (_, i) => acting
      ? `<<<PART ${i + 1}>>>\n# Part title\nFirst narration line.\n...\n${cast[0]?.id ?? 'kai'}: A line ${cast[0]?.name ?? 'Kai'} says.\nA narration line.\n...\n!! The twist line.`
      : `<<<PART ${i + 1}>>>\n# Part title\nFirst narration line.\n...\n!! The twist line.`),
    ...(o.parts > 2 ? ['...'] : []),
    '<<<END>>>',
    '```',
    'Then the self-check lines, below the block.',
    '',
  ].filter((l, i, a) => l !== '' || a[i - 1] !== '').join('\n')
}

/** the reply's parts, or the first problem found. speakers: the cast ids that may speak (cast voice acting), or null
 *  (single narration: no line may be a speaker's) */
export function parseVoiceReply(text: string, parts: number, speakers: string[] | null = null): { parts?: VoicePart[]; error?: string } {
  const body = text.replace(/\r/g, '').split('\n').filter((l) => !l.trim().startsWith('```'))
  const out: VoicePart[] = []
  let cur: VoicePart | null = null
  for (const raw of body) {
    const l = raw.trim()
    const m = l.match(/^<<<PART (\d+)>>>$/)
    if (m) { cur = { title: '', lines: [] }; out.push(cur); continue }
    if (l === '<<<END>>>') break
    if (!cur || !l) continue
    if (!cur.title && l.startsWith('# ')) cur.title = l.slice(2).trim()
    else cur.lines.push(l)
  }
  if (out.length !== parts) return { error: `Expected ${parts} part${parts === 1 ? '' : 's'} (<<<PART N>>> markers), found ${out.length}.` }
  for (const [i, p] of out.entries()) {
    const n = `Part ${i + 1}`
    if (!p.title) return { error: `${n} has no "# title" line.` }
    if (!p.lines.length) return { error: `${n} has no narration.` }
    const bad = p.lines.find((l) => l.startsWith('@') || /\d/.test(l))
    if (bad) return { error: `${n}: narration only, numbers as words: "${bad}"` }
    if (p.lines.filter((l) => l.startsWith('!!')).length !== 1) return { error: `${n} needs exactly one "!!" twist line.` }
    const said = p.lines.find((l) => speakerOf(l) && (!speakers || !speakers.includes(speakerOf(l)!)))
    if (said) return { error: speakers
      ? `${n}: "${speakerOf(said)}" is not in this series' cast (${speakers.join(', ')}): "${said}"`
      : `${n}: single narration, but this is a character's line: "${said}"` }
  }
  return { parts: out }
}

/** a part's starter story.md: the lines under a placeholder @set, staged later */
export const voiceStory = (p: VoicePart, cast: string[]) =>
  `# ${p.title}\n\n@set street\n${cast.length ? `@cast ${cast.join(', ')}\n` : ''}${p.lines.join('\n')}\n`
