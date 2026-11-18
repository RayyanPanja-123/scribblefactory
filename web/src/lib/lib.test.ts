import { describe, expect, it } from 'vitest'
import { backoff, connectStream, type EventSourceLike } from './events'
import { nextSteps, type PipelineState } from './nextSteps'
import { jobFraction, parseProgress } from './progress'
import { buildPrompt, importProp } from './propPrompt'
import { seriesNext, type SeriesState } from './seriesNext'

const ALL = ['prep', 'import_check', 'timing', 'shots', 'validate', 'render', 'audio', 'finish', 'thumbnails']
const NONE = { stills: false, test_render: false, final: false }
function state(doneUpto: number, over: Partial<PipelineState> = {}): PipelineState {
  return {
    stages: Object.fromEntries(ALL.map((s, i) => [s, i < doneUpto ? 'done' : 'pending'])),
    approvals: NONE,
    files: { voice: true, stillsSheet: false, testRender: false },
    castApproved: true,
    ...over,
  }
}

describe('nextSteps', () => {
  it('fresh part with voice: prep stretch, then stills, stops at the stills gate', () => {
    expect(nextSteps(state(0))).toEqual({
      steps: ['run --stage prep', 'run --stage import_check', 'run --stage timing', 'run --stage shots',
        'run --stage validate', 'render-stills'],
      stop: 'stills approval',
    })
  })
  it('no voice yet: only prep, then stops for the voice', () => {
    const p = nextSteps(state(0, { files: { voice: false, stillsSheet: false, testRender: false } }))
    expect(p.steps).toEqual(['run --stage prep'])
    expect(p.stop).toMatch(/voice\.mp3/)
  })
  it('a failed stage restarts there and re-plans everything after it', () => {
    const s = state(5)
    s.stages.timing = 'failed'
    expect(nextSteps(s).steps.slice(0, 3)).toEqual(['run --stage timing', 'run --stage shots', 'run --stage validate'])
  })
  it('unapproved cast stops before the stills render', () => {
    expect(nextSteps(state(5, { castApproved: false }))).toEqual({ steps: [], stop: 'cast approval: check the cast sheet' })
  })
  it('stills sheet waiting: nothing to run, stops at the gate', () => {
    const files = { voice: true, stillsSheet: true, testRender: false }
    expect(nextSteps(state(5, { files }))).toEqual({ steps: [], stop: 'stills approval' })
  })
  it('stills approved: test render, stops at its gate', () => {
    const p = nextSteps(state(5, { approvals: { ...NONE, stills: true } }))
    expect(p).toEqual({ steps: ['test-render'], stop: 'test render approval' })
  })
  it('both approved: full render to thumbnails, stops at final approval', () => {
    const p = nextSteps(state(5, { approvals: { ...NONE, stills: true, test_render: true } }))
    expect(p).toEqual({
      steps: ['render', 'run --stage audio', 'run --stage finish', 'run --stage thumbnails'], stop: 'final approval',
    })
  })
  it('render done, audio failed: resumes at audio', () => {
    const s = state(6, { approvals: { ...NONE, stills: true, test_render: true } })
    s.stages.audio = 'failed'
    expect(nextSteps(s).steps).toEqual(['run --stage audio', 'run --stage finish', 'run --stage thumbnails'])
  })
  it('everything done and approved: nothing left', () => {
    expect(nextSteps(state(9, { approvals: { stills: true, test_render: true, final: true } }))).toEqual({ steps: [], stop: null })
  })
  it('a running stage blocks planning', () => {
    const s = state(3)
    s.stages.shots = 'running'
    expect(nextSteps(s).steps).toEqual([])
  })
})

describe('parseProgress', () => {
  it('reads the last chunk line', () => {
    expect(parseProgress(['webgl: x', 'chunk 1/4 done (frames 0-149, 30 fps)', 'chunk 3/4 done (frames 300-449)'])).toBe(0.75)
  })
  it('reads resume and frame counters', () => {
    expect(parseProgress(['resuming: 2/8 chunk(s) already done'])).toBe(0.25)
    expect(parseProgress(['frame 45/90'])).toBe(0.5)
  })
  it('null without countable progress, and ignores zero totals', () => {
    expect(parseProgress(['prep: running', 'prep: done'])).toBeNull()
    expect(parseProgress(['chunk 0/0'])).toBeNull()
    expect(parseProgress([])).toBeNull()
  })
  it('job fraction combines finished steps and the current one', () => {
    expect(jobFraction(1, 4, 0.5)).toBe(0.375)
    expect(jobFraction(0, 2, null)).toBe(0)
    expect(jobFraction(null, 2, 0.5)).toBe(0)
  })
})

class FakeES implements EventSourceLike {
  static all: FakeES[] = []
  onopen: ((e: Event) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  listeners: Record<string, (e: MessageEvent) => void> = {}
  closed = false
  constructor(public url: string) {
    FakeES.all.push(this)
  }
  addEventListener(t: string, fn: (e: MessageEvent) => void) {
    this.listeners[t] = fn
  }
  close() {
    this.closed = true
  }
  emit(t: string, data: string) {
    this.listeners[t]?.({ data } as MessageEvent)
  }
}

describe('connectStream', () => {
  it('backoff doubles from 1 s and caps at 30 s', () => {
    expect([0, 1, 2, 3, 4, 5, 10].map(backoff)).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000])
  })
  it('delivers parsed events, reconnects with backoff, resets after a good open', () => {
    FakeES.all = []
    const timers: [() => void, number][] = []
    const got: unknown[] = []
    const opens: boolean[] = []
    const stop = connectStream({
      url: '/api/events', types: ['job-output'], create: (u) => new FakeES(u),
      setTimer: (fn, ms) => timers.push([fn, ms]),
      onEvent: (t, d) => got.push([t, d]), onOpen: (r) => opens.push(r),
    })
    const first = FakeES.all[0]
    first.onopen!(new Event('open'))
    first.emit('job-output', '{"line":"hi"}')
    first.emit('job-output', 'not json')
    expect(got).toEqual([['job-output', { line: 'hi' }]])

    first.onerror!(new Event('error'))
    expect(first.closed).toBe(true)
    expect(timers.map((t) => t[1])).toEqual([1000])
    timers[0][0]() // retry 1 fails too
    FakeES.all[1].onerror!(new Event('error'))
    expect(timers.map((t) => t[1])).toEqual([1000, 2000])
    timers[1][0]() // retry 2 opens: reported as a reconnect, backoff resets
    FakeES.all[2].onopen!(new Event('open'))
    expect(opens).toEqual([false, true])
    FakeES.all[2].onerror!(new Event('error'))
    expect(timers.at(-1)![1]).toBe(1000)

    stop()
    timers.at(-1)![0]() // a retry due after stop does nothing
    expect(FakeES.all).toHaveLength(3)
  })
})

import { shortPaths } from './paths'

describe('shortPaths', () => {
  it('shortens Windows and POSIX library paths to …/<series>/<part>/…', () => {
    const win = String.raw`s33: 82 ms -> C:\Users\me\AppData\Local\Temp\scribble-demo-x1\great-emu-war\part-07\frames\stills\s33.png [travel]`
    expect(shortPaths(win)).toBe('s33: 82 ms -> …/great-emu-war/part-07/frames/stills/s33.png [travel]')
    expect(shortPaths('stills sheet: /home/me/library/marathon-1904/part-01/stills-sheet.png'))
      .toBe('stills sheet: …/marathon-1904/part-01/stills-sheet.png')
    expect(shortPaths(String.raw`preview: D:\lib\cat\part-12`)).toBe('preview: …/cat/part-12')
  })
  it('leaves other text alone', () => {
    for (const s of ['prep: done', 'chunk 3/4 done (frames 300-449)', 'words: 2, estimated duration: 0.8 s'])
      expect(shortPaths(s)).toBe(s)
  })
})

describe('build with AI', () => {
  it('prompt names the thing, a suggested id, the taken ids and the format', () => {
    const p = buildPrompt('Water Gun', ['apple', 'torch'])
    expect(p).toContain('**Water Gun**')
    expect(p).toContain('"id": "water-gun"')
    expect(p).toContain('NOT be one of: apple, torch')
    expect(p).toContain('"shape": "circle"')
  })
  it('imports a fenced reply, a props file, and rejects junk', () => {
    const reply = 'Sure!\n```json\n{"id": "Gun!", "name": "Gun", "shapes": [{"shape": "rect", "pts": [[0,-10],[80,10]], "fill": "#333333"}, {"shape": "circle", "pts": [[0,0]], "r": 5}]}\n```\nEnjoy.'
    const { prop } = importProp(reply)
    expect(prop?.id).toBe('gun')
    expect(prop?.shapes).toEqual([
      { shape: 'rect', pts: [[0, -10], [80, 10]], r: null, fill: '#333333', width: 8 },
      { shape: 'circle', pts: [[0, 0]], r: 5, fill: null, width: 8 },
    ])
    expect(importProp('{"props": [{"name": "Flag", "shapes": [{"shape": "line", "pts": [[0,0],[0,-90]]}]}]}').prop?.id).toBe('flag')
    expect(importProp('no json here').error).toMatch(/Not valid JSON/)
    expect(importProp('{"shapes": [{"shape": "star", "pts": [[0,0]]}]}').error).toMatch(/Shape #1/)
  })
})

describe('seriesNext', () => {
  const part = (n: number, over = {}) => ({ id: `part-0${n}`, number: n, waiting: [], finished: false, started: false, ...over })
  const s = (over: Partial<SeriesState> = {}): SeriesState =>
    ({ cast: 3, castApproved: 3, castSheet: true, sheetRendering: false, parts: [part(1)], ...over })

  it('walks the series pipeline in order', () => {
    expect(seriesNext(s({ cast: 0 })).kind).toBe('add-cast')
    expect(seriesNext(s({ castSheet: false, parts: [] })).kind).toBe('add-part') // the sheet needs a part
    expect(seriesNext(s({ castSheet: false })).kind).toBe('render-sheet')
    expect(seriesNext(s({ castSheet: false, sheetRendering: true })).kind).toBe('wait')
    expect(seriesNext(s({ castApproved: 0 })).text).toMatch(/^None of the 3 cast are approved yet\./)
    expect(seriesNext(s({ castApproved: 1 })).text).toMatch(/^2 of 3 cast still need approval/)
    expect(seriesNext(s({ castApproved: 2 })).text).toMatch(/^1 of 3 cast still needs approval/)
    expect(seriesNext(s({ parts: [] })).kind).toBe('add-part')
  })

  it('points at the first part that waits, else the first unfinished one', () => {
    const parts = [part(1, { finished: true, started: true }), part(2, { started: true }), part(3, { waiting: ['stills', 'test_render'] })]
    expect(seriesNext(s({ parts }))).toEqual({ kind: 'open-part', part: 'part-03', action: 'Review', text: 'Part 3 is waiting for you: stills, test render.' })
    expect(seriesNext(s({ parts: parts.slice(0, 2) }))).toMatchObject({ part: 'part-02', action: 'Continue' })
    expect(seriesNext(s({ parts: [part(1)] }))).toMatchObject({ action: 'Start' })
    expect(seriesNext(s({ parts: [parts[0]] })).kind).toBe('done')
  })
})

import { partNext, type PartState } from './partNext'

describe('partNext', () => {
  const ALL_OK = { stills: true, test_render: true, final: true }
  const p = (doneUpto: number, over: Partial<PartState> = {}): PartState => ({
    ...state(doneUpto), busy: null, failed: null, thumbs: true, thumbnailPicked: false, posted: { youtube: false, instagram: false }, ...over,
  })
  it('walks the part from story to posted', () => {
    expect(partNext(p(0, { busy: 'job 3 is running' })).kind).toBe('wait')
    expect(partNext(p(0))).toMatchObject({ kind: 'run', steps: ['run --stage prep', 'run --stage import_check', 'run --stage timing', 'run --stage shots', 'run --stage validate', 'render-stills'] })
    expect(partNext(p(1, { files: { voice: false, stillsSheet: false, testRender: false } })).kind).toBe('voice')
    expect(partNext(p(5, { castApproved: false })).kind).toBe('cast')
    expect(partNext(p(5, { files: { voice: true, stillsSheet: true, testRender: false } }))).toMatchObject({ kind: 'approve', approval: 'stills' })
    expect(partNext(p(5, { approvals: { ...NONE, stills: true }, files: { voice: true, stillsSheet: true, testRender: true } }))).toMatchObject({ approval: 'test_render' })
    expect(partNext(p(9, { approvals: { ...ALL_OK, final: false } }))).toMatchObject({ approval: 'final' })
    expect(partNext(p(9, { approvals: ALL_OK })).kind).toBe('thumbnail')
    expect(partNext(p(9, { approvals: ALL_OK, thumbnailPicked: true })).kind).toBe('post')
    expect(partNext(p(9, { approvals: ALL_OK, thumbnailPicked: true, posted: { youtube: true, instagram: false } })))
      .toEqual({ kind: 'done', text: 'Posted. Add the Instagram link if it goes up there too.' })
  })
  it('a failed stage says so and offers the re-run', () => {
    const s = p(2, { failed: { stage: 'timing', error: 'no phrases' } })
    expect(partNext(s)).toMatchObject({ kind: 'run', text: expect.stringMatching(/^timing failed: no phrases\./) })
  })
  it('stepper: done steps, one current step, the rest to do', () => {
    const at = (s: PartState) => partSteps(s).map((x) => `${x.key}:${x.status}`).join(' ')
    expect(at(p(0))).toMatch(/^story:current voice:todo/)
    expect(at(p(5))).toMatch(/^story:done voice:done plan:done stills:current test:todo/)
    expect(at(p(5, { files: { voice: true, stillsSheet: true, testRender: false } }))).toContain('stills:review')
    expect(at(p(5, { busy: 'job 1' }))).toContain('stills:running')
    expect(at(p(2, { stages: { ...state(2).stages, timing: 'failed' } }))).toContain('voice:failed')
    expect(at(p(9, { approvals: ALL_OK, thumbnailPicked: true, posted: { youtube: true, instagram: false } })))
      .not.toMatch(/current|todo/)
  })
})

import { partSteps } from './partSteps'

import { buildSetPrompt, importSet } from './setPrompt'

describe('build a set with AI', () => {
  it('prompt names the thing, a suggested id, the taken ids and the stage rule', () => {
    const p = buildSetPrompt('Beach Bar', ['room', 'kitchen'])
    expect(p).toContain('**Beach Bar**')
    expect(p).toContain('"id": "beach-bar"')
    expect(p).toContain('NOT be one of: room, kitchen')
    expect(p).toContain('STAGE CLEARANCE')
  })
  it('prompt takes the name, the details and a story id separately', () => {
    const p = buildSetPrompt('Corner Bakery', ['room'], 'glass counter, bread shelves', 'bakery')
    expect(p).toContain('"id": "bakery", "name": "Corner Bakery"')
    expect(p).toContain('What it should look like: glass counter, bread shelves')
    expect(buildPrompt('Baguette', []).includes('What it should look like')).toBe(false)
  })
  it('imports a fenced reply, a sets file, and rejects junk', () => {
    const reply = 'Here:\n```json\n{"id": "Beach!", "name": "Beach", "kind": "outdoor", "floor": "#f2d8a0", "back": "nope", "pieces": [{"shape": "ball", "at": [3, 1, -3], "size": [0.5], "color": "#43aa8b", "backdrop": true}]}\n```'
    const { set } = importSet(reply)
    expect(set).toEqual({ id: 'beach', name: 'Beach', kind: 'outdoor', floor: '#f2d8a0', back: '#f6e7c8',
      pieces: [{ shape: 'ball', at: [3, 1, -3], size: [0.5], color: '#43aa8b', backdrop: true }] })
    expect(importSet('{"sets": [{"name": "Den", "pieces": []}]}').set).toMatchObject({ id: 'den', kind: 'indoor' })
    expect(importSet('no json here').error).toMatch(/Not valid JSON/)
    expect(importSet('{"pieces": [{"shape": "box", "at": [0, 0, -2], "size": [1, 1]}]}').error).toMatch(/Piece #1/)
  })
})

describe('creature prompt', () => {
  it('teaches the chosen rig with its parts and a built-in example, and avoids taken ids', async () => {
    const { buildCreaturePrompt } = await import('./creatures')
    const p = buildCreaturePrompt('Dog', 'quadruped', ['cat', 'horse'], 'floppy ears')
    expect(p).toContain('"id": "dog"')
    expect(p).toContain('leg_front (required)')
    expect(p).toContain('must NOT be one of: cat, horse')
    expect(p).toContain('floppy ears')
    expect(p).toContain('"id":"cat"') // the built-in quadruped as the example
  })
  it('imports a fenced reply, a {"creatures": [...]} file, and refuses a bad rig', async () => {
    const { importCreature } = await import('./creatures')
    const body = '"parts": {"body": [{"shape": "circle", "pts": [[0, -50]], "r": 40, "fill": "$main"}]}'
    const { creature } = importCreature(`Here:\n\`\`\`json\n{"id": "Blob Fish", "name": "Blob", "rig": "crawler", ${body}}\n\`\`\``)
    expect(creature?.id).toBe('blob-fish')
    expect(creature?.accent).toBe('#3a2a1e')
    expect(importCreature(`{"creatures": [{"name": "Worm", "rig": "crawler", ${body}}]}`).creature?.id).toBe('worm')
    expect(importCreature(`{"name": "X", "rig": "fish", ${body}}`).error).toMatch(/rig/)
    expect(importCreature('{"name": "X", "rig": "bird"}').error).toMatch(/body/)
  })
})
