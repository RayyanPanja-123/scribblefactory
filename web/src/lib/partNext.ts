// The one thing to do next on a part page, from its state. Pure: the page renders it, the tests pin it.
// Machine work comes from nextSteps (run up to the next human gate); this adds the human gates and the
// after-final steps (thumbnail, posting) so the page always names a single next action.

import { nextSteps, type PipelineState } from './nextSteps'

export interface PartState extends PipelineState {
  busy: string | null // a job is queued/running on this part
  failed: { stage: string; error: string | null } | null
  thumbs: boolean // thumbnail candidates exist
  thumbnailPicked: boolean
  posted: { youtube: boolean; instagram: boolean }
}

export type Approval = 'stills' | 'test_render' | 'final'

export type PartStep =
  | { kind: 'wait'; text: string }
  | { kind: 'run'; text: string; steps: string[]; stop: string | null }
  | { kind: 'voice'; text: string }
  | { kind: 'cast'; text: string }
  | { kind: 'approve'; text: string; approval: Approval }
  | { kind: 'thumbnail'; text: string }
  | { kind: 'post'; text: string }
  | { kind: 'done'; text: string }

const APPROVE: Record<Approval, string> = {
  stills: 'The stills sheet is ready. Zoom in and check every shot, then approve the stills.',
  test_render: 'The 5 s test render is ready. Watch it in the player, then approve it.',
  final: 'final.mp4 is ready. Watch it to the end and check QA, then approve the final.',
}

export function partNext(s: PartState): PartStep {
  if (s.busy) return { kind: 'wait', text: `Working: ${s.busy}. This page updates when it finishes.` }
  const plan = nextSteps(s)
  if (plan.steps.length) {
    const n = plan.steps.length
    const lead = s.failed ? `${s.failed.stage} failed${s.failed.error ? `: ${s.failed.error}` : ''}. Fix the cause, then run again.`
      : `${n} automatic step${n === 1 ? '' : 's'} to run.`
    return { kind: 'run', steps: plan.steps, stop: plan.stop, text: plan.stop ? `${lead} Stops before ${plan.stop.split(':')[0]}.` : lead }
  }
  if (plan.stop?.startsWith('voice')) return { kind: 'voice', text: 'Record the voice: paste script-for-tts.txt into freetts.ai, download the mp3 and upload it here.' }
  if (plan.stop?.startsWith('cast')) return { kind: 'cast', text: 'The series cast is not approved yet. Approve it on the series page before stills can render.' }
  if (plan.stop === 'stills approval') return { kind: 'approve', approval: 'stills', text: APPROVE.stills }
  if (plan.stop === 'final approval') return { kind: 'approve', approval: 'final', text: APPROVE.final }
  if (plan.stop) return { kind: 'wait', text: plan.stop } // 'a stage is running'
  if (s.thumbs && !s.thumbnailPicked) return { kind: 'thumbnail', text: 'Pick one of the thumbnail candidates on the light table.' }
  if (!s.posted.youtube && !s.posted.instagram) return { kind: 'post', text: 'Copy the title and description from upload.md, post the video, then paste the links here.' }
  const missing = !s.posted.youtube ? 'YouTube' : !s.posted.instagram ? 'Instagram' : null
  return { kind: 'done', text: missing ? `Posted. Add the ${missing} link if it goes up there too.` : 'Finished and posted everywhere.' }
}
