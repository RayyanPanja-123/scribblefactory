// The one thing to do next on a series page, from its state. Pure: the page renders it, the tests pin it.
// Order follows the pipeline: cast, cast sheet, cast approval, parts, then the first part needing attention.

export interface SeriesPartState {
  id: string
  number: number
  waiting: string[] // approvals with something ready to look at
  finished: boolean // final approved
  started: boolean // any stage done
}

export interface SeriesState {
  cast: number
  castApproved: number
  castCurrent: number // cast whose render shows their look now (approving needs it)
  sheetRendering: boolean
  parts: SeriesPartState[]
}

export type SeriesStep =
  | { kind: 'add-cast'; text: string }
  | { kind: 'add-part'; text: string }
  | { kind: 'render-sheet'; text: string }
  | { kind: 'wait'; text: string }
  | { kind: 'approve-cast'; text: string }
  | { kind: 'open-part'; text: string; part: string; action: string }
  | { kind: 'done'; text: string }

const APPROVAL = { stills: 'stills', test_render: 'test render', final: 'final video' } as Record<string, string>

export function seriesNext(s: SeriesState): SeriesStep {
  if (!s.cast) return { kind: 'add-cast', text: 'No cast yet. Add the characters with cast-add, or import cast JSON on a new series.' }
  if (s.castCurrent < s.cast || (s.castApproved < s.cast && s.sheetRendering)) {
    if (s.sheetRendering) return { kind: 'wait', text: 'The cast is rendering. Approve them once their poses show up.' }
    if (!s.parts.length) return { kind: 'add-part', text: 'Add the first part: the cast renders through a part.' }
    const n = s.cast - s.castCurrent
    return { kind: 'render-sheet', text: n === s.cast ? 'Render the cast to check every character before approving them.'
      : `${n} of ${s.cast} cast ${n === 1 ? 'is' : 'are'} new or changed. Render ${n === 1 ? 'it' : 'them'} before approving.` }
  }
  const left = s.cast - s.castApproved
  if (left) {
    const who = left === s.cast ? `None of the ${s.cast} cast are approved yet` : `${left} of ${s.cast} cast still ${left === 1 ? 'needs' : 'need'} approval`
    return { kind: 'approve-cast', text: `${who}. Check each row of the cast sheet, then approve them.` }
  }
  if (!s.parts.length) return { kind: 'add-part', text: 'The cast is ready. Add the first part and write its story.' }
  const waiting = s.parts.find((p) => p.waiting.length)
  if (waiting) {
    const what = waiting.waiting.map((w) => APPROVAL[w] ?? w).join(', ')
    return { kind: 'open-part', part: waiting.id, action: 'Review', text: `Part ${waiting.number} is waiting for you: ${what}.` }
  }
  const open = s.parts.find((p) => !p.finished)
  if (open) return { kind: 'open-part', part: open.id, action: open.started ? 'Continue' : 'Start', text: `Part ${open.number} is ${open.started ? 'in progress' : 'not started yet'}.` }
  return { kind: 'done', text: `All ${s.parts.length} part${s.parts.length === 1 ? '' : 's'} finished and approved.` }
}
