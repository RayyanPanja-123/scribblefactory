// Job log display: absolute library paths shortened to "…/<series>/<part>/…" (the copied log keeps them whole).
// A path counts when it runs through a <slug>/part-NN folder; everything before the slug becomes "…".
const PART_PATH = /(?:[A-Za-z]:)?[\\/](?:[^\s\\/"']+[\\/])*?([a-z0-9]+(?:-[a-z0-9]+)*)[\\/](part-\d{2})((?:[\\/][^\s"')\]]*)?)/g

export function shortPaths(line: string): string {
  return line.replace(PART_PATH, (_, series: string, part: string, rest: string) =>
    `…/${series}/${part}${rest.replace(/\\/g, '/')}`)
}
