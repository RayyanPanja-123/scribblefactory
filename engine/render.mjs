#!/usr/bin/env node
// Render frames of a part (or the cast sheet of a series) with headless Chromium.
//   node engine/render.mjs --part <dir> --frame N --out file.png
//   node engine/render.mjs --part <dir> --frames A-B --out-dir <dir>   -> <dir>/000042.png (A..B inclusive)
//   node engine/render.mjs --part <dir> --stills          -> <part>/frames/stills/<shot>.png + manifest.json
//   node engine/render.mjs --series <dir> --cast-sheet    -> <series>/cast-frames/<id>-<pose>.png + manifest.json
//   node engine/render.mjs --probe                        -> print the renderer it would use
//   node engine/render.mjs --loop-check                   -> JSON: every set/variant built, travel loop excess
//   node engine/render.mjs --batch jobs.json              -> [[args of one --part/--series job], ...] in one browser
//   node engine/render.mjs --part <dir> --worker --out-dir <dir>
//       long-lived worker: one browser, page built once. Prints "READY <renderer info json>", then reads
//       "A B" lines on stdin and answers "DONE A B" once frames A..B are written. Exits when stdin closes.
//       stdout carries only that protocol; logs go to stderr.
// Renderer: the GPU by default; falls back to SwiftShader (with a note) when WebGL reports a software renderer.
// --swiftshader forces software. --info-out <file> writes the renderer info as JSON (any mode).
// Serves engine/page and three from node_modules on a localhost port (no extra deps). Exit 0 ok, 1 error.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import readline from "node:readline";
import { parseArgs } from "node:util";
import { chromium } from "playwright";

const ENGINE = path.dirname(fileURLToPath(import.meta.url));
const WARDROBE_SEED = path.join(ENGINE, "..", "pipeline", "scribble", "seed", "wardrobe.json");
const SERVED = [path.join(ENGINE, "page"), path.join(ENGINE, "node_modules", "three")];
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json" };
const PLAYWRIGHT = JSON.parse(fs.readFileSync(path.join(ENGINE, "node_modules", "playwright", "package.json"), "utf8")).version;
export const POSES = [["idle", "idle"], ["walk", "walk"], ["talk", "talk"],
  ...["neutral", "happy", "sad", "angry", "surprised", "sleepy", "cheeky", "exhausted"].map((e) => [e, "idle", e]),
  ...["stagger", "lie", "eat", "give", "carried"].map((a) => [a, a]),
  ["cheer", "cheer", "happy"], ["angry mood", "angry", "angry"]]; // crowd moods (label: "angry" is an expression column)
export const LOOK_POSES = ["idle", "walk", "talk", "stagger"]; // cast sheet: per named look
// Software GL (SwiftShader): output does not depend on the machine's GPU or driver.
const SWIFTSHADER_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"];
// Chromium's default ANGLE backend on the real GPU (D3D11 on Windows).
const GPU_ARGS = ["--use-angle=default", "--enable-gpu", "--ignore-gpu-blocklist"];
const SOFTWARE_GL = /swiftshader|llvmpipe|softpipe|software|basic render/i;

function serve() {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const file = path.resolve(ENGINE, "." + rel);
    if (!SERVED.some((d) => file.startsWith(d + path.sep)) || !fs.existsSync(file)) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

const readJson = (f) => {
  if (!fs.existsSync(f)) throw new Error(`${f} not found`);
  return JSON.parse(fs.readFileSync(f, "utf8"));
};
/** every custom item of the library (library/<kind>.json, none yet: []), handed to the page once (library.js) */
const loadLibrary = (library) => Object.fromEntries(["props", "sets", "creatures", "actions", "wardrobe"].map((k) => {
  const f = path.join(library, `${k}.json`);
  if (!fs.existsSync(f) && k === "wardrobe") return [k, readJson(WARDROBE_SEED)[k]]; // the starter wardrobe (io.py)
  return [k, fs.existsSync(f) ? readJson(f)[k] : []];
}));

function writeFileAtomic(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, data);
  fs.renameSync(tmp, file);
}
const writePng = (file, dataUrl) => writeFileAtomic(file, Buffer.from(dataUrl.slice(dataUrl.indexOf(",") + 1), "base64"));

/** empty a generated frames folder so stale images never reach a sheet */
function freshDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
  for (const f of fs.readdirSync(dir)) if (f.endsWith(".png") || f === "manifest.json") fs.rmSync(path.join(dir, f));
}

/** GPU driver version for the adapter WebGL names. WebGL hides it and headless Chromium blocks chrome://gpu,
 *  so on Windows ask WMI (~1 s); elsewhere null. */
function driverFor(gpuName) {
  if (process.platform !== "win32") return null;
  try {
    const out = execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command",
      "Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion | ConvertTo-Json -Compress"],
    { encoding: "utf8", timeout: 15000 });
    const list = [].concat(JSON.parse(out));
    return list.find((g) => g.Name && gpuName.includes(g.Name))?.DriverVersion ?? null;
  } catch {
    return null;
  }
}

/** launch Chromium, load the engine page. GPU unless forced or unavailable. Returns { browser, page, info }. */
async function openPage(port, swiftshader) {
  const launch = async (soft) => {
    const browser = await chromium.launch({ args: soft ? SWIFTSHADER_ARGS : GPU_ARGS });
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    let pageError = null;
    page.on("console", (m) => {
      if (["warning", "error"].includes(m.type()) && !m.text().includes("GL Driver Message")) {
        console.error(`[page ${m.type()}] ${m.text()}`); // SwiftShader perf notes are noise
      }
    });
    page.on("pageerror", (e) => { pageError = e; });
    await page.goto(`http://127.0.0.1:${port}/page/index.html`);
    await page.waitForFunction(() => window.engineReady === true, null, { timeout: 30000 });
    if (pageError) throw pageError;
    const gl = await page.evaluate(() => window.glInfo());
    const info = { renderer: soft ? "swiftshader" : "gpu", gpu_name: gl.renderer, gl_vendor: gl.vendor,
      gl_version: gl.version, driver: null, chromium: browser.version(), playwright: PLAYWRIGHT };
    return { browser, page, info, getError: () => pageError, clearError: () => { pageError = null; } };
  };
  if (swiftshader) return launch(true);
  const gpu = await launch(false);
  if (!SOFTWARE_GL.test(gpu.info.gpu_name)) {
    gpu.info.driver = driverFor(gpu.info.gpu_name);
    return gpu;
  }
  console.log(`note: no hardware WebGL (got "${gpu.info.gpu_name}"), using SwiftShader`);
  await gpu.browser.close();
  return launch(true);
}

function frameJobs(a) {
  const part = path.resolve(a.part);
  const data = { story: readJson(path.join(part, "story.json")), phrases: readJson(path.join(part, "phrases.json")),
    series: readJson(path.join(part, "..", "series.json")), ...loadLibrary(path.join(part, "..", "..")) };
  if (a.stills) {
    const dir = path.join(part, "frames", "stills");
    return { data, manifestDir: dir, jobs: data.story.shots.map((s) => ({ label: s.id, file: path.join(dir, `${s.id}.png`),
      call: ["renderFrame", Math.floor((s.start_frame + s.end_frame) / 2)] })) };
  }
  if (a.frames && a["out-dir"]) {
    const m = /^(\d+)-(\d+)$/.exec(a.frames);
    if (!m || Number(m[1]) > Number(m[2])) throw new Error(`--frames wants A-B with A <= B, got ${a.frames}`);
    const jobs = [];
    for (let n = Number(m[1]); n <= Number(m[2]); n++) {
      jobs.push({ label: `frame ${n}`, file: framePng(path.resolve(a["out-dir"]), n), call: ["renderFrame", n] });
    }
    return { data, jobs };
  }
  if (a.frame !== undefined && a.out) {
    return { data, jobs: [{ label: `frame ${a.frame}`, file: path.resolve(a.out), call: ["renderFrame", Number(a.frame)] }] };
  }
  return { data, jobs: [] };
}

function castJobs(a) {
  const dir = path.resolve(a.series);
  const data = { series: readJson(path.join(dir, "series.json")), story: { seed: 0 }, ...loadLibrary(path.join(dir, "..")) };
  if (!data.series.cast.length) throw new Error("series.json has no cast");
  const manifestDir = path.join(dir, "cast-frames"), jobs = [];
  for (const c of data.series.cast) for (const [label, pose, expression] of POSES) {
    jobs.push({ label: `${c.id} ${label}`, file: path.join(manifestDir, `${c.id}-${label}.png`),
      call: ["renderCast", { castId: c.id, pose, expression }] });
  }
  // named looks (@look) after everyone's full rows, so those rows stay aligned: a few poses each
  for (const c of data.series.cast) for (const look of Object.keys(c.looks || {})) for (const pose of LOOK_POSES) {
    jobs.push({ label: `${c.id} ${look} ${pose}`, file: path.join(manifestDir, `${c.id}-${look}-${pose}.png`),
      call: ["renderCast", { castId: c.id, pose, look }] });
  }
  return { data, jobs, manifestDir };
}

const framePng = (dir, n) => path.join(dir, `${String(n).padStart(6, "0")}.png`);

/** long-lived worker: see the header. One browser + one page build for every chunk it is given. */
async function runWorker(a) {
  if (!a.part || !a["out-dir"]) throw new Error("--worker needs --part <dir> --out-dir <dir>");
  const { data } = frameJobs({ part: a.part });
  const outDir = path.resolve(a["out-dir"]);
  const server = await serve();
  let browser = null;
  try {
    const opened = await openPage(server.address().port, a.swiftshader);
    browser = opened.browser;
    await opened.page.evaluate((d) => window.setup(d), data);
    process.stdout.write(`READY ${JSON.stringify(opened.info)}\n`);
    for await (const line of readline.createInterface({ input: process.stdin })) {
      if (!line.trim()) continue;
      const [first, last] = line.trim().split(/\s+/).map(Number);
      if (!Number.isInteger(first) || !Number.isInteger(last) || first > last) throw new Error(`bad job line: ${line}`);
      const t0 = performance.now();
      for (let n = first; n <= last; n++) {
        writePng(framePng(outDir, n), await opened.page.evaluate((f) => window.renderFrame(f), n));
      }
      if (opened.getError()) throw opened.getError();
      console.error(`frames ${first}-${last}: ${((performance.now() - t0) / (last - first + 1)).toFixed(0)} ms per frame`);
      process.stdout.write(`DONE ${first} ${last}\n`);
    }
  } finally {
    if (browser) await browser.close();
    server.close();
  }
}

const OPTIONS = {
  part: { type: "string" }, series: { type: "string" }, frame: { type: "string" }, out: { type: "string" },
  stills: { type: "boolean" }, "cast-sheet": { type: "boolean" },
  frames: { type: "string" }, "out-dir": { type: "string" },
  swiftshader: { type: "boolean" }, probe: { type: "boolean" }, "info-out": { type: "string" },
  worker: { type: "boolean" }, "loop-check": { type: "boolean" }, batch: { type: "string" },
};
const USAGE = "usage: --part <dir> (--frame N --out file.png | --frames A-B --out-dir <dir> | --stills) "
  + "| --series <dir> --cast-sheet | --probe | --loop-check | --batch jobs.json   [--swiftshader] [--info-out file.json]";

/** one render job (--part ... or --series ... --cast-sheet) on an open page: setup, frames, manifest */
async function renderJobs(opened, a) {
  const { data, jobs, manifestDir = null } = a.part ? frameJobs(a) : a.series && a["cast-sheet"] ? castJobs(a) : { jobs: [] };
  if (!jobs.length) throw new Error(USAGE);
  if (manifestDir) freshDir(manifestDir);
  const { page, info } = opened;
  await page.evaluate((d) => window.setup(d), data);
  const times = [];
  for (const j of jobs) {
    const t0 = performance.now();
    const url = await page.evaluate(([fn, arg]) => window[fn](arg), j.call);
    writePng(j.file, url);
    times.push(performance.now() - t0);
    const fi = j.call[0] === "renderFrame" ? await page.evaluate(() => window.lastInfo) : null;
    const note = fi?.angle === "wide"
      ? ` [wide: figure ${(fi.figure * 100).toFixed(1)}% of frame height, ${fi.inFrame ? "all in frame" : "CUT OFF"}]`
      : fi?.hidden ? ` [${fi.hidden} prop(s) hidden behind the subject]` : "";
    const gest = fi?.gestures?.length ? ` [gesture: ${fi.gestures.join(", ")}]` : "";
    const wipe = (fi?.wipe ? ` [wipe ${fi.wipe}]` : "") + (fi?.travel ? ` [travel ${fi.travel}]` : "")
      + (fi?.dogs ? ` [dogs ${fi.dogs}]` : "") + (fi?.cars ? ` [car ${fi.cars}]` : "")
      + (fi?.extrasDropped != null ? ` [extras dropped: ${fi.extrasDropped}]` : "")
      + (fi?.extrasOut ? ` [extras OUT OF FRAME: ${fi.extrasOut}]` : "")
      + (fi?.weather && fi.weather !== "clear" ? ` [weather ${fi.weather}]` : "")
      + (fi?.strike != null ? ` [lightning ${fi.strike}]` : "") + (fi?.flash ? ` [flash ${fi.flash}]` : "");
    console.log(`${j.label}: ${times.at(-1).toFixed(0)} ms -> ${j.file}${note}${gest}${wipe}`);
  }
  if (opened.getError()) throw opened.getError();
  if (manifestDir) {
    const frames = jobs.map((j) => ({ label: j.label, file: path.basename(j.file) }));
    writeFileAtomic(path.join(manifestDir, "manifest.json"), JSON.stringify({ renderer: info, frames }, null, 2) + "\n");
  }
  const mean = (xs) => xs.reduce((s, x) => s + x, 0) / xs.length;
  const warm = times.length > 1 ? `, ${mean(times.slice(1)).toFixed(0)} ms without the first (warm)` : "";
  console.log(`rendered ${times.length} image(s), avg ${mean(times).toFixed(0)} ms per frame${warm}`);
}

async function main() {
  const { values: a } = parseArgs({ options: OPTIONS });
  if (a.worker) return runWorker(a);
  // --batch jobs.json: [[...args], ...] -- every job in one browser. Each job's output starts with "== job N" and
  // ends with "== job N ok" or "== job N error: <message>"; exit 1 if any job failed.
  const batch = a.batch ? readJson(path.resolve(a.batch)) : null;
  const check = a.probe || a["loop-check"];
  if (!batch && !check && !a.part && !(a.series && a["cast-sheet"])) throw new Error(USAGE);
  if (a.part && !batch) frameJobs(a); // bad paths fail before a browser starts

  const server = await serve();
  let browser = null;
  try {
    const opened = await openPage(server.address().port, a.swiftshader);
    browser = opened.browser;
    const { page, info } = opened;
    console.log(`webgl: ${info.renderer} (${info.gpu_name})`);
    if (a["info-out"]) writeFileAtomic(path.resolve(a["info-out"]), JSON.stringify(info, null, 2) + "\n");
    if (a.probe) return;
    if (a["loop-check"]) {
      const res = await page.evaluate(() => window.loopCheck());
      if (opened.getError()) throw opened.getError();
      console.log(JSON.stringify(res));
      return;
    }
    if (!batch) return await renderJobs(opened, a);
    let failed = 0;
    for (const [i, args] of batch.entries()) {
      console.log(`== job ${i}`);
      try {
        await renderJobs(opened, parseArgs({ args, options: OPTIONS }).values);
        console.log(`== job ${i} ok`);
      } catch (e) {
        failed++;
        opened.clearError();
        console.log(`== job ${i} error: ${e.message}`);
      }
    }
    if (failed) process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    server.close();
  }
}

main().catch((e) => { console.error(`error: ${e.message}`); process.exit(1); });
