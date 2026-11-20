// Story step 1, title -> voice scripts: a small self-contained prompt (only docs/ai/tts.md, no library, no directives)
// and the reader for its reply. Each script becomes a part whose story.md is the narration under a starter @set;
// staging comes later, one part at a time.
import ttsRules from '../../../docs/ai/tts.md?raw'

export type VoicePart = { title: string; lines: string[] }

export function voicePrompt(o: { title: string; parts: number; notes?: string; cast?: string[] }): string {
  return [
    'You write narration for scribblefactory: vertical stickman history Shorts. A voice reads each part aloud.',
    `Story: "${o.title}". Write exactly ${o.parts} part${o.parts === 1 ? '' : 's'}.`,
    'Research the real story on the web first. Use known events, names and context; never present a guess as fact.',
    o.cast?.length ? `Characters already in this series (use these names): ${o.cast.join(', ')}.` : '',
    o.notes?.trim() ? `Notes from the creator: ${o.notes.trim()}` : '',
    '',
    ttsRules.trim(),
    '',
    '## Reply',
    'Only this block, markers alone on their line, one narration line per line, no directives (`@`), no markdown in the lines:',
    '```text',
    ...Array.from({ length: Math.min(o.parts, 2) }, (_, i) => `<<<PART ${i + 1}>>>\n# Part title\nFirst narration line.\n...\n!! The twist line.`),
    ...(o.parts > 2 ? ['...'] : []),
    '<<<END>>>',
    '```',
    '',
  ].filter((l, i, a) => l !== '' || a[i - 1] !== '').join('\n')
}

/** the reply's parts, or the first problem found */
export function parseVoiceReply(text: string, parts: number): { parts?: VoicePart[]; error?: string } {
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
  }
  return { parts: out }
}

/** a part's starter story.md: the narration under a placeholder @set, staged later */
export const voiceStory = (p: VoicePart, cast: string[]) =>
  `# ${p.title}\n\n@set street\n${cast.length ? `@cast ${cast.join(', ')}\n` : ''}${p.lines.join('\n')}\n`
