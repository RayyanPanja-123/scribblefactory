// Test helper: run many render jobs in one browser (render.mjs --batch), always SwiftShader (identical bytes on any
// machine). render.mjs calls are queued: one browser at a time per process (and `npm test` runs files one at a time),
// so the suite never has more than one render running. Not a test file itself.
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ENGINE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const FIX = path.join(ENGINE, "..", "pipeline", "tests", "fixtures", "story");

let queue = Promise.resolve();

/** render.mjs call in its own browser, after any earlier call finishes -> Promise<{ status, stdout, stderr }> */
export function render(...args) {
  const run = queue.then(() => spawnRender(args));
  queue = run.catch(() => {});
  return run;
}

function spawnRender(args) {
  return new Promise((ok, fail) => {
    const p = spawn(process.execPath, [path.join(ENGINE, "render.mjs"), ...args, "--swiftshader"]);
    // SwiftShader takes every core: below-normal priority (Chromium inherits it) keeps the PC usable meanwhile
    try { os.setPriority(p.pid, os.constants.priority.PRIORITY_BELOW_NORMAL); } catch {}
    let stdout = "", stderr = "";
    p.stdout.on("data", (d) => { stdout += d; });
    p.stderr.on("data", (d) => { stderr += d; });
    p.on("error", fail);
    p.on("close", (status) => ok({ status, stdout, stderr }));
  });
}

/** jobs: [[...render.mjs args], ...] -> [{ ok, out (that job's stdout), error }] in job order; .stderr: all jobs' */
export async function renderBatch(jobs) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scribble-batch-"));
  try {
    fs.writeFileSync(path.join(dir, "jobs.json"), JSON.stringify(jobs));
    const r = await render("--batch", path.join(dir, "jobs.json"));
    const res = jobs.map(() => ({ ok: false, out: "", error: `no output (exit ${r.status}): ${r.stderr}` }));
    let cur = null;
    for (const line of r.stdout.split(/\r?\n/)) {
      const m = /^== job (\d+)(?: (ok)| error: (.*))?$/.exec(line);
      if (m && !m[2] && m[3] === undefined) { cur = res[Number(m[1])]; cur.error = null; continue; }
      if (m) { res[Number(m[1])].ok = !!m[2]; res[Number(m[1])].error = m[3] ?? null; cur = null; continue; }
      if (cur) cur.out += line + "\n";
    }
    res.stderr = r.stderr;
    return res;
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/** named jobs { name: args } -> { name: result } plus .stderr */
export async function renderNamed(jobs) {
  const names = Object.keys(jobs), res = await renderBatch(Object.values(jobs));
  return Object.assign(Object.fromEntries(names.map((n, i) => [n, res[i]])), { stderr: res.stderr });
}

/** assert a named batch job succeeded */
export const jobOk = (R, name) => { if (!R[name]?.ok) throw new Error(`${name}: ${R[name]?.error}`); };

/** temp series folder with the fixture series.json (or `series`), phrases.json and story.json (mutated) in part-01 */
export function fixturePart(temps, mutate = (s) => s, series = null) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scribble-engine-"));
  temps.push(dir);
  const part = path.join(dir, "part-01");
  fs.mkdirSync(part);
  if (series) fs.writeFileSync(path.join(dir, "series.json"), JSON.stringify(series));
  else fs.copyFileSync(path.join(FIX, "series.json"), path.join(dir, "series.json"));
  fs.copyFileSync(path.join(FIX, "phrases.json"), path.join(part, "phrases.json"));
  const story = mutate(JSON.parse(fs.readFileSync(path.join(FIX, "story.json"), "utf8")));
  fs.writeFileSync(path.join(part, "story.json"), JSON.stringify(story));
  return part;
}

export const png = (dir, n) => fs.readFileSync(path.join(dir, `${String(n).padStart(6, "0")}.png`));
export const frames = (part, range, dir) => ["--part", part, "--frames", range, "--out-dir", path.join(part, dir)];
