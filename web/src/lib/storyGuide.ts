// The story guide a chat AI gets: docs/STORY_GUIDE.md + what this library has right now (every id it may use) +
// the Story Package format (docs/story-package.md, the one source) + the library item schemas for new items.
// All bundled at build time and loaded on first use. Overview and Story Writer copy it.
import { api } from '../api/client'
import { SLOTS } from './wardrobe'

const ids = (xs: { id: string; name: string }[]) => xs.map((x) => `\`${x.id}\` (${x.name})`).join(', ')
type Weather = { kind: string; intensity: string } | null | undefined
const wx = (w: Weather) => (w ? `${w.kind} ${w.intensity}` : '')
/** custom sets with their default weather, e.g. `harbour` (Harbour, default weather fog light) */
const setIds = (xs: { id: string; name: string; default_weather?: Weather }[]) =>
  xs.map((x) => `\`${x.id}\` (${x.name}${x.default_weather ? `, default weather ${wx(x.default_weather)}` : ''})`).join(', ')
/** cast members with their named looks (@look), e.g. `mike` (Mike; looks: headless) */
const castIds = (xs: { id: string; name: string; looks?: Record<string, unknown> }[]) =>
  xs.map((x) => { const l = Object.keys(x.looks ?? {}); return `\`${x.id}\` (${x.name}${l.length ? `; looks: ${l.map((k) => `\`${k}\``).join(', ')}` : ''})` }).join(', ')

/** the "Available in this library" section, or '' when the API can't be reached (the static guide still works).
 * standalone: shared on its own (Overview's "Copy library list"), so the last line doesn't point into the guide */
export async function libraryRecords(standalone = false): Promise<string> {
  try {
    const [sets, props, creatures, actions, wardrobe, series, sfx] = await Promise.all([api.sets(), api.props(), api.creatures(), api.actions(), api.wardrobe(), api.series(), api.sfx()])
    const casts = await Promise.all(series.map((s) => api.seriesDetail(s.slug).then((d) => d.series, () => null)))
    const indoor = sets.custom.filter((s) => s.kind === 'indoor')
    const outdoor = sets.custom.filter((s) => s.kind === 'outdoor')
    const cast = casts.filter((s) => s?.cast.length).map((s) => `  - ${s!.title}: ${castIds(s!.cast)}`)
    return [
      '## Available in this library right now',
      '',
      `- **Sets** (${sets.builtin.length + sets.custom.length}): built in ${sets.builtin.map((s) => `\`${s.id}\``).join(', ')}` +
        (indoor.length ? `; custom indoor ${setIds(indoor)}` : '') +
        (outdoor.length ? `; custom outdoor ${setIds(outdoor)}` : ''),
      '- **Weather** for `@weather <type> [intensity]`: types `clear`, `rain`, `snow`, `fog`, `wind`, `storm`; intensities ' +
        '`light`, `medium` (default), `heavy`. Built-in sets start clear' +
        (sets.custom.some((s) => s.default_weather) ? '; custom sets with a default weather say so above' : '') +
        '. Mood: gods, sea battles, villains `storm`; sadness `rain`; mystery `fog`; calm `clear`.',
      '- **Lightning** `@fx lightning [target]`: at most 3 per part; target a cast id on stage or a prop someone on stage holds.',
      `- **Props** (${props.builtin.length + props.custom.length}): built in ${props.builtin.map((p) => `\`${p}\``).join(', ')}` +
        (props.custom.length ? `; custom ${ids(props.custom)}` : ''),
      `- **Creatures** (cast bodies, by rig; default \`human\`): ${[...creatures.builtin, ...creatures.custom]
        .map((c) => `\`${c.id}\` (${c.rig})`).join(', ')}`,
      `- **Actions** for \`@do <cast>: <action>\`: built in ${actions.do.map((a) => `\`${a}\``).join(', ')}` +
        (actions.custom.length ? `; custom (humanoids only) ${ids(actions.custom)}` : ''),
      `- **Wardrobe** (cast slots, by slot; worn by id, \`null\` for none): ${SLOTS.map((s) => {
        const xs = [...wardrobe.builtin.filter((w) => w.slot === s), ...wardrobe.custom.filter((w) => w.slot === s)]
        return `${s} ${xs.length ? xs.map((w) => `\`${w.id}\``).join(', ') : '(none yet)'}`
      }).join('; ')}`,
      `- **Sound effects** for \`@sfx <id> [volume 0-1]\` (at most 5 per part): ${sfx.sfx.length ? sfx.sfx.map((s) =>
        `\`${s.id}\` (${s.purpose || s.name}${s.anchor === 'end_on_line' ? '; ends as the line starts' : s.anchor === 'after_line' ? '; plays after the line is said' : ''})`).join(', ') : 'none yet'}`,
      `- **Cast** in your existing series (a new series designs its own CAST; reuse a look by copying it):${cast.length ? '' : ' none yet'}`,
      ...cast,
      '',
      standalone ? 'Use these by id; anything not listed does not exist yet and would have to be designed new.'
        : 'Use these by id; anything else is new and goes in the Story Package (section 6).',
      '',
      '',
    ].join('\n')
  } catch {
    return ''
  }
}

export async function storyGuide(): Promise<string> {
  const [guide, pkg, props, sets, creatures, actions, wardrobe, live] = await Promise.all([
    import('../../../docs/STORY_GUIDE.md?raw'), import('../../../docs/story-package.md?raw'),
    import('../../../docs/schemas/props.schema.json?raw'), import('../../../docs/schemas/sets.schema.json?raw'),
    import('../../../docs/schemas/creatures.schema.json?raw'), import('../../../docs/schemas/actions.schema.json?raw'),
    import('../../../docs/schemas/wardrobe.schema.json?raw'),
    libraryRecords(),
  ])
  const compact = (m: { default: string }) => JSON.stringify(JSON.parse(m.default))
  return [
    guide.default.replace('## Your series', `${live}## Your series`).trimEnd(),
    '---',
    pkg.default.replace(/^## /gm, '### ').replace(/^# Story Package v1/, '## Story Package format (v1)').trimEnd(),
    '---',
    '## Library item schemas (JSON Schema; one item of each list goes in the package section of the same name)',
    `PROPS: ${compact(props)}`,
    `SETS: ${compact(sets)}`,
    `CREATURES: ${compact(creatures)}`,
    `ACTIONS: ${compact(actions)}`,
    `WARDROBE: ${compact(wardrobe)}`,
    '',
  ].join('\n\n')
}
