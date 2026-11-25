// Story step "stage": one part's narration -> a staged story.md. Small prompt: docs/ai/script.md, this series' cast
// and the live inventory list, nothing about other parts, packages or schemas.
import scriptRules from '../../../docs/ai/script.md?raw'

type Look = { props?: { kind: string }[] | null }
type Cast = { id: string; name: string; body?: string; looks?: Record<string, Look> }

/** one cast line: its looks for @look (with what each holds), and a non-human body, which wears no wardrobe */
// ponytail: every non-human body is labelled rideable; a humanoid custom creature is not (prep refuses it). Pass the
// creature gaits in if that ever misleads the AI.
const castLine = (c: Cast) => {
  const looks = ['default', ...Object.entries(c.looks ?? {}).map(([k, l]) => (l.props?.length ? `${k} (holds ${l.props.map((p) => p.kind).join(', ')})` : k))]
  return `- \`${c.id}\` ${c.name}${c.body && c.body !== 'human' ? ` (body ${c.body}: no wardrobe, rideable with @ride)` : ''}; looks: ${looks.join(', ')}`
}

/** the spoken lines of a story.md: no title, no directives, no blanks */
export const narration = (md: string) =>
  md.replace(/\r/g, '').split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('@') && !l.startsWith('# '))

export function stagePrompt(o: { series: string; title: string; story: string; cast: Cast[]; inventory: string }): string {
  const cast = o.cast.map(castLine)
  return [
    `You stage one part of the scribblefactory series "${o.series}": turn its narration into a story.md with directives.`,
    'Keep every narration line word for word and in order (the voice is read from them); only add `@` lines above them.',
    'A line starting `<cast id>: ` is that character speaking in their own voice: keep the prefix exactly, and have',
    'the speaker on stage (`@cast`) for it; they are the one who talks, the others react (`@do`, `@face`).',
    'Use only ids from the cast and inventory below. If the part truly needs an item that does not exist, still write the',
    'best script with what exists, then after the block add one line per missing item: `MISSING: <kind> <id>: <why>`.',
    '',
    scriptRules.trim(),
    '',
    '## Cast of this series',
    cast.length ? cast.join('\n') : 'none yet: name characters only by the ids you would give them, and list each as `MISSING: cast <id>: <name>`',
    '',
    o.inventory.trim() || '# LIBRARY INVENTORY\n(unavailable: use built-ins only)',
    '',
    `## Narration of "${o.title}"`,
    '```text',
    ...narration(o.story),
    '```',
    '',
    '## Reply',
    'The whole story.md in one fenced `md` block, starting with `# ' + o.title + '`, then any MISSING lines. Nothing else.',
    '',
  ].join('\n')
}

/** the staged story.md out of the reply, plus what it says is missing and whether the narration changed */
export function parseStageReply(text: string, story: string): { md?: string; missing: string[]; changed: boolean; error?: string } {
  const t = text.replace(/\r/g, '')
  const fenced = t.match(/```(?:md|markdown)?\n([\s\S]*?)```/)
  const md = (fenced ? fenced[1] : t.slice(Math.max(0, t.indexOf('# ')))).trim()
  const missing = t.split('\n').map((l) => l.trim()).filter((l) => l.startsWith('MISSING:')).map((l) => l.slice(8).trim())
  if (!md.startsWith('# ')) return { missing, changed: false, error: 'No story.md found: expected a block starting with "# title".' }
  const body = fenced ? md : md.split('\n').filter((l) => !l.trim().startsWith('MISSING:')).join('\n').trim()
  if (!body.split('\n').some((l) => l.trim().startsWith('@'))) return { missing, changed: false, error: 'The script has no directives.' }
  return { md: body + '\n', missing, changed: narration(body).join('\n') !== narration(story).join('\n') }
}
