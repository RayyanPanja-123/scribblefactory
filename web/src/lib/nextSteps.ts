// "Run next": the CLI steps from the current stage statuses up to the next human gate.
// Steps are job step strings (see api/main.py JOB_COMMANDS). Re-queuing an up-to-date stage is safe:
// run_stage skips it when its inputs hash the same, so once one step is planned, every later automatic step
// in the same stretch is planned too (its inputs may have changed).

export type StageStatus = 'pending' | 'running' | 'done' | 'failed'

export interface PipelineState {
  stages: Partial<Record<string, StageStatus>>
  approvals: { stills: boolean; test_render: boolean; final: boolean }
  files: { voice: boolean; stillsSheet: boolean; testRender: boolean }
  castApproved: boolean // every series cast member approved (the stills render refuses otherwise)
}

export interface Plan {
  steps: string[]
  stop: string | null // the human gate the plan stops before; null = nothing left to do
}

const PREP_STRETCH = ['import_check', 'timing', 'shots', 'validate']
const FINISH_STRETCH = ['audio', 'finish', 'thumbnails']

export function nextSteps(s: PipelineState): Plan {
  if (Object.values(s.stages).includes('running')) return { steps: [], stop: 'a stage is running' }
  const done = (st: string) => s.stages[st] === 'done'
  const steps: string[] = []

  if (!done('prep')) steps.push('run --stage prep')
  if (!s.files.voice) return { steps, stop: 'voice.mp3: make it on freetts.ai and upload it in the Voice card' }

  for (const st of PREP_STRETCH) if (steps.length || !done(st)) steps.push(`run --stage ${st}`)

  if (!s.approvals.stills) {
    if (!s.castApproved) return { steps, stop: 'cast approval: check the cast sheet' }
    if (steps.length || !s.files.stillsSheet) steps.push('render-stills')
    return { steps, stop: 'stills approval' }
  }
  if (!s.approvals.test_render) {
    if (steps.length || !s.files.testRender) steps.push('test-render')
    return { steps, stop: 'test render approval' }
  }

  if (steps.length || !done('render')) steps.push('render')
  for (const st of FINISH_STRETCH) if (steps.length || !done(st)) steps.push(`run --stage ${st}`)
  return { steps, stop: s.approvals.final ? null : 'final approval' }
}
