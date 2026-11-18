// The part's journey as 8 human-sized steps for the stepper: what is done, where it stands now, what is left.
// Pure: the page renders it, the tests pin it. The current step is the first one not done.

import type { PartState } from './partNext'

export type StepStatus = 'done' | 'current' | 'running' | 'failed' | 'review' | 'todo'

export interface PartStepView {
  key: string
  label: string
  href: string // the page section where the step happens ('' = none)
  status: StepStatus
  note: string // one short line under the label
}

type Def = { key: string; label: string; href: string; stages: string[]; done: (s: PartState) => boolean; review?: (s: PartState) => boolean }

const ok = (s: PartState, ...st: string[]) => st.every((x) => s.stages[x] === 'done')
const DEFS: Def[] = [
  { key: 'story', label: 'Story', href: '#story', stages: ['prep'], done: (s) => ok(s, 'prep') },
  { key: 'voice', label: 'Voice', href: '#voice', stages: ['import_check', 'timing'], done: (s) => s.files.voice && ok(s, 'import_check', 'timing') },
  { key: 'plan', label: 'Plan shots', href: '#run', stages: ['shots', 'validate'], done: (s) => ok(s, 'shots', 'validate') },
  { key: 'stills', label: 'Stills', href: '#review', stages: [], done: (s) => s.approvals.stills, review: (s) => s.files.stillsSheet },
  { key: 'test', label: 'Test render', href: '#video', stages: [], done: (s) => s.approvals.test_render, review: (s) => s.files.testRender },
  { key: 'final', label: 'Final', href: '#approvals', stages: ['render', 'audio', 'finish'], done: (s) => s.approvals.final,
    review: (s) => ok(s, 'render', 'audio', 'finish') },
  { key: 'thumbnail', label: 'Thumbnail', href: '#thumbnails', stages: ['thumbnails'], done: (s) => s.thumbnailPicked },
  { key: 'post', label: 'Post', href: '#posting', stages: [], done: (s) => s.posted.youtube || s.posted.instagram },
]

const NOTE: Record<StepStatus, string> = { done: 'done', current: 'up next', running: 'working…', failed: 'failed', review: 'approve it', todo: '' }

export function partSteps(s: PartState): PartStepView[] {
  const cur = DEFS.findIndex((d) => !d.done(s))
  return DEFS.map((d, i) => {
    let status: StepStatus = d.done(s) ? 'done' : i === cur ? 'current' : 'todo'
    if (status === 'current') {
      if (d.stages.some((st) => s.stages[st] === 'failed')) status = 'failed'
      else if (s.busy) status = 'running'
      else if (d.review?.(s)) status = 'review'
    }
    return { key: d.key, label: d.label, href: d.href, status, note: NOTE[status] }
  })
}
