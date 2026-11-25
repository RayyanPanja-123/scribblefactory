// Progress of the current job step from its output lines (render: "chunk 3/12 done ...", "resuming: 2/12 chunk(s)
// already done"; anything printing "frame N/M"). null = no countable progress: show an indeterminate bar.

const PATTERNS = [/\bchunk (\d+)\/(\d+)/i, /resuming: (\d+)\/(\d+) chunk/i, /\bframes? (\d+)\s*\/\s*(\d+)/i,
  /^line (\d+)\/(\d+)$/] // tts: "line 3/10" as each line's voice arrives

export function parseProgress(lines: readonly string[]): number | null {
  for (let i = lines.length - 1; i >= 0; i--) {
    for (const re of PATTERNS) {
      const m = lines[i].match(re)
      if (m && +m[2] > 0) return Math.min(1, Math.max(0, +m[1] / +m[2]))
    }
  }
  return null
}

/** Whole-job fraction: finished steps plus the current one's progress (0 when unknown). */
export function jobFraction(step: number | null, steps: number, current: number | null): number {
  if (step === null || steps <= 0) return 0
  return Math.min(1, (step + (current ?? 0)) / steps)
}
