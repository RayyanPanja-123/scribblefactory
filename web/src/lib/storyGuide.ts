// The story guide a chat AI gets: docs/STORY_GUIDE.md (contract + workflow) + the step rules in docs/ai/ (tts,
// library, cast, script: each also usable alone as one step's prompt) + the Story Package format (docs/story-package.md, the one
// source) + the library item schemas for new items. All bundled at build time and loaded on first use. Overview and
// Story Writer copy it. The live library list is separate (libraryRecords): the user shares it alongside the guide.
import { api } from '../api/client'
import { toast } from '../composables/feedback'
import { SLOTS } from './wardrobe'

/** a custom item's "use for" note (when a story should use it), e.g. "; use for: Neptune's weapon" */
const use = (x: { use_for?: string | null }) => (x.use_for ? `; use for: ${x.use_for}` : '')
const ids = (xs: { id: string; name: string; use_for?: string | null }[]) => xs.map((x) => `\`${x.id}\` (${x.name}${use(x)})`).join(', ')
type Weather = { kind: string; intensity: string } | null | undefined
const wx = (w: Weather) => (w ? `${w.kind} ${w.intensity}` : '')
/** custom sets with their default weather, e.g. `harbour` (Harbour, default weather fog light) */
const setIds = (xs: { id: string; name: string; default_weather?: Weather; use_for?: string | null }[]) =>
  xs.map((x) => `\`${x.id}\` (${x.name}${x.default_weather ? `, default weather ${wx(x.default_weather)}` : ''}${use(x)})`).join(', ')
/** cast members with their named looks (@look), e.g. `mike` (Mike; looks: headless) */
const castIds = (xs: { id: string; name: string; looks?: Record<string, unknown> }[]) =>
  xs.map((x) => { const l = Object.keys(x.looks ?? {}); return `\`${x.id}\` (${x.name}${l.length ? `; looks: ${l.map((k) => `\`${k}\``).join(', ')}` : ''})` }).join(', ')

/** the server's voices for the library list: English first, as `id` (label); the rest as plain ids */
export const ttsVoiceList = (vs: { id: string; label: string; lang?: string | null }[]) => {
  const en = vs.filter((v) => !v.lang || v.lang.startsWith('en'))
  const other = vs.filter((v) => v.lang && !v.lang.startsWith('en'))
  return [en.map((v) => `\`${v.id}\`${v.label !== v.id ? ` (${v.label})` : ''}`).join(', '),
    other.length ? `other languages: ${other.map((v) => v.id).join(', ')}` : ''].filter(Boolean).join(' | ')
}

/** the "Available in this library" section, or '' when the API can't be reached (the static guide still works).
 * standalone: shared on its own (Overview's "Copy library list"), so the last line doesn't point into the guide */
export async function libraryRecords(standalone = false): Promise<string> {
  try {
    const [sets, props, objects, creatures, actions, wardrobe, series, sfx] = await Promise.all([api.sets(), api.props(), api.objects(), api.creatures(), api.actions(), api.wardrobe(), api.series(), api.sfx()])
    const casts = await Promise.all(series.map((s) => api.seriesDetail(s.slug).then((d) => d.series, () => null)))
    const tts = await api.ttsVoices().catch(() => null) // the TTS server's voices: cast voice acting picks from them
    const indoor = sets.custom.filter((s) => s.kind === 'indoor')
    const outdoor = sets.custom.filter((s) => s.kind === 'outdoor')
    const cast = casts.filter((s) => s?.cast.length).map((s) => `  - ${s!.title}: ${castIds(s!.cast)}`)
    return [
      '# LIBRARY INVENTORY',
      `SETS (${sets.builtin.length + sets.custom.length})`,
      `built-in: ${sets.builtin.map((s) => s.id).join(', ')}${indoor.length ? ` | indoor: ${setIds(indoor)}` : ''}${outdoor.length ? ` | outdoor: ${setIds(outdoor)}` : ''}`,
      'weather: clear, rain, snow, fog, wind, storm; intensity light, medium, heavy',
      `PROPS (${props.builtin.length + props.custom.length})`,
      `built-in: ${props.builtin.join(', ')}${props.custom.length ? ` | custom: ${ids(props.custom)}` : ''}`,
      `WORLD ITEMS (${objects.objects.length}; drawn ones go on stage with @item <tag>: <id>)`,
      objects.objects.length ? objects.objects.map((o) => o.look === 'card'
        ? `${o.id} [drawn; ${o.layer ?? 'mid'}${o.states?.length ? `; states ${o.states.join('/')}` : ''}]`
        : `${o.id} [built, set only; ${o.category}; ${o.capabilities.join(', ') || 'static'}; carry=${o.carry_mode}]`).join(' | ') : 'none yet',
      `CREATURES (${creatures.builtin.length + creatures.custom.length})`,
      [...creatures.builtin, ...creatures.custom].map((c) => `${c.id} (${c.rig}${use(c as { use_for?: string | null })})`).join(', '),
      `ACTIONS (@do; ${actions.do.length + actions.custom.length})`,
      `built-in: ${actions.do.join(', ')}${actions.custom.length ? ` | custom: ${ids(actions.custom)}` : ''}`,
      'WARDROBE',
      SLOTS.map((s) => {
        const xs = [...wardrobe.builtin.filter((w) => w.slot === s), ...wardrobe.custom.filter((w) => w.slot === s)]
        return `${s} ${xs.length ? xs.map((w) => `\`${w.id}\``).join(', ') : '(none yet)'}`
      }).join(' | '),
      `SOUNDS (@sfx; ${sfx.sfx.length}): ${sfx.sfx.length ? sfx.sfx.map((s) =>
        `\`${s.id}\` (${s.purpose || s.name}${s.anchor === 'end_on_line' ? '; ends as the line starts' : s.anchor === 'after_line' ? '; plays after the line is said' : ''})`).join(', ') : 'none yet'}`,
      `CAST${cast.length ? '' : ': none yet'}`,
      ...cast,
      ...(tts?.voices.length ? [`TTS VOICES (cast voice acting: a cast member's "voice"; narrator default \`${tts.default}\`)`,
        ttsVoiceList(tts.voices)] : []),
      '',
      standalone ? 'Use ids exactly as listed. Unlisted items must be designed new.' : 'Use ids exactly as listed. Unlisted items go in the Story Package.',
    ].join('\n')
  } catch {
    return ''
  }
}

/** copy the library list for a chat AI to share alongside the story guide; true when copied */
export async function copyLibraryList(): Promise<boolean> {
  const list = await libraryRecords(true)
  try {
    if (!list) throw new Error('empty')
    await navigator.clipboard.writeText(list.trim() + '\n')
    toast('Library list copied: paste it into your AI alongside the story guide', 'ok')
    return true
  } catch {
    toast(list ? 'Could not copy to the clipboard.' : 'Could not load the library: is the API running?', 'error')
    return false
  }
}

export async function storyGuide(): Promise<string> {
  const [guide, tts, library, cast, script, pkg, props, sets, creatures, actions, wardrobe, objects] = await Promise.all([
    import('../../../docs/STORY_GUIDE.md?raw'), import('../../../docs/ai/tts.md?raw'), import('../../../docs/ai/library.md?raw'),
    import('../../../docs/ai/cast.md?raw'), import('../../../docs/ai/script.md?raw'), import('../../../docs/story-package.md?raw'),
    import('../../../docs/schemas/props.schema.json?raw'), import('../../../docs/schemas/sets.schema.json?raw'),
    import('../../../docs/schemas/creatures.schema.json?raw'), import('../../../docs/schemas/actions.schema.json?raw'),
    import('../../../docs/schemas/wardrobe.schema.json?raw'), import('../../../docs/schemas/objects.schema.json?raw'),
  ])
  const compact = (m: { default: string }) => JSON.stringify(JSON.parse(m.default))
  return [
    ...[guide, tts, library, cast, script].map((m) => m.default.trimEnd()),
    '---',
    pkg.default.replace(/^## /gm, '### ').replace(/^# Story Package v1/, '## Story Package format (v1)').trimEnd(),
    '---',
    '## Library item schemas (JSON Schema; one item of each list goes in the package section of the same name)',
    `PROPS: ${compact(props)}`,
    `SETS: ${compact(sets)}`,
    `CREATURES: ${compact(creatures)}`,
    `ACTIONS: ${compact(actions)}`,
    `WARDROBE: ${compact(wardrobe)}`,
    `OBJECTS: ${compact(objects)}`,
    '',
  ].join('\n\n')
}

type Issue = { section?: string; line?: number | null; message: string }
/** a prompt asking the chat AI to fix the checker's issues. body: a part's story.md (answer = that script only);
 * none: a Story Package still open in the chat (answer = the whole package again) */
export function fixPrompt(issues: Issue[], body?: string): string {
  const list = issues.map((i) => `- ${[i.section, i.line ? `line ${i.line}` : ''].filter(Boolean).join(', ') || 'whole script'}: ${i.message}`)
  return body
    ? ['The scribblefactory checker found these issues in this part script. Fix every problem, and every warning that fits the story. Follow the story guide. Reply with only the whole corrected script in one fenced `md` block.',
      '', ...list, '', '```md', body.trimEnd(), '```', ''].join('\n')
    : ['The scribblefactory checker found these issues in your Story Package (line numbers are in the package as pasted). Fix every error, and every warning that fits the story. Reply with only the whole corrected Story Package: same markers, one `text` block, never a partial one.',
      '', ...list, ''].join('\n')
}
