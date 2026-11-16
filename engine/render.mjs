#!/usr/bin/env node
// Render frames of a part (or the cast sheet of a series) with headless Chromium.
//   node engine/render.mjs --part <dir> --frame N --out file.png
//   node engine/render.mjs --part <dir> --frames A-B --out-dir <dir>  -> <dir>/f00042.png (A..B inclusive)
//   add --gpu to any of these: hardware WebGL (benchmark only; default stays SwiftShader)
//   node engine/render.mjs --part <dir> --stills          -> <part>/frames/stills/<shot>.png + manifest.json
//   node engine/render.mjs --series <dir> --cast-sheet    -> <series>/cast-frames/<id>-<pose>.png + manifest.json
// Serves engine/page and three from node_modules on a localhost port (no extra deps). Exit 0 ok, 1 error.
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { chromium } from "playwright";

const ENGINE = path.dirname(fileURLToPath(import.meta.url));
const SERVED = [path.join(ENGINE, "page"), path.join(ENGINE, "node_modules", "three")];
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json" };
export const POSES = [["idle", "idle"], ["walk", "walk"], ["talk", "talk"],
  ...["neutral", "happy", "sad", "angry", "surprised", "sleepy"].map((e) => [e, "idle", e])];
// Software GL (SwiftShader) so output does not depend on the machine's GPU or driver.
const CHROME_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"];
// --gpu: Chromium's default ANGLE backend on the real GPU (D3D11 on Windows).
const GPU_ARGS = ["--use-angle=default", "--enable-gpu", "--ignore-gpu-blocklist"];

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

function writePng(file, dataUrl) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, Buffer.from(dataUrl.slice(dataUrl.indexOf(",") + 1), "base64"));
  fs.renameSync(tmp, file);
}

/** empty a generated frames folder so stale images never reach a sheet */
function freshDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
  for (const f of fs.readdirSync(dir)) if (f.endsWith(".png") || f === "manifest.json") fs.rmSync(path.join(dir, f));
}

async function main() {
  const { values: a } = parseArgs({
    options: {
      part: { type: "string" }, series: { type: "string" }, frame: { type: "string" }, out: { type: "string" },
      stills: { type: "boolean" }, "cast-sheet": { type: "boolean" },
      frames: { type: "string" }, "out-dir": { type: "string" }, gpu: { type: "boolean" },
    },
  });
  let data, jobs = [], manifestDir = null;
  if (a.part) {
    const part = path.resolve(a.part);
    data = { story: readJson(path.join(part, "story.json")), phrases: readJson(path.join(part, "phrases.json")),
      series: readJson(path.join(part, "..", "series.json")) };
    if (a.stills) {
      manifestDir = path.join(part, "frames", "stills");
      jobs = data.story.shots.map((s) => ({ label: s.id, file: path.join(manifestDir, `${s.id}.png`),
        call: ["renderFrame", Math.floor((s.start_frame + s.end_frame) / 2)] }));
    } else if (a.frames && a["out-dir"]) {
      const m = /^(\d+)-(\d+)$/.exec(a.frames);
      if (!m || Number(m[1]) > Number(m[2])) throw new Error(`--frames wants A-B with A <= B, got ${a.frames}`);
      for (let n = Number(m[1]); n <= Number(m[2]); n++) {
        jobs.push({ label: `frame ${n}`, file: path.join(path.resolve(a["out-dir"]), `f${String(n).padStart(5, "0")}.png`),
          call: ["renderFrame", n] });
      }
    } else if (a.frame !== undefined && a.out) {
      jobs = [{ label: `frame ${a.frame}`, file: path.resolve(a.out), call: ["renderFrame", Number(a.frame)] }];
    }
  } else if (a.series && a["cast-sheet"]) {
    const dir = path.resolve(a.series);
    data = { series: readJson(path.join(dir, "series.json")), story: { seed: 0 } };
    if (!data.series.cast.length) throw new Error("series.json has no cast");
    manifestDir = path.join(dir, "cast-frames");
    for (const c of data.series.cast) for (const [label, pose, expression] of POSES) {
      jobs.push({ label: `${c.id} ${label}`, file: path.join(manifestDir, `${c.id}-${label}.png`),
        call: ["renderCast", { castId: c.id, pose, expression }] });
    }
  }
  if (!jobs.length) {
    throw new Error("usage: --part <dir> (--frame N --out file.png | --frames A-B --out-dir <dir> | --stills) "
      + "| --series <dir> --cast-sheet  [--gpu]");
  }
  if (manifestDir) freshDir(manifestDir);

  const server = await serve();
  const browser = await chromium.launch({ args: a.gpu ? GPU_ARGS : CHROME_ARGS });
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
    let pageError = null;
    page.on("console", (m) => {
      if (["warning", "error"].includes(m.type()) && !m.text().includes("GL Driver Message")) {
        console.error(`[page ${m.type()}] ${m.text()}`); // SwiftShader perf notes are noise
      }
    });
    page.on("pageerror", (e) => { pageError = e; });
    await page.goto(`http://127.0.0.1:${server.address().port}/page/index.html`);
    await page.waitForFunction(() => window.engineReady === true, null, { timeout: 30000 });
    if (pageError) throw pageError;
    await page.evaluate((d) => window.setup(d), data);
    console.log(`webgl: ${await page.evaluate(() => window.glRenderer())}`);
    const times = [];
    for (const j of jobs) {
      const t0 = performance.now();
      const url = await page.evaluate(([fn, arg]) => window[fn](arg), j.call);
      writePng(j.file, url);
      times.push(performance.now() - t0);
      const info = j.call[0] === "renderFrame" ? await page.evaluate(() => window.lastInfo) : null;
      const wide = info?.angle === "wide"
        ? ` [wide: figure ${(info.figure * 100).toFixed(1)}% of frame height, ${info.inFrame ? "all in frame" : "CUT OFF"}]` : "";
      console.log(`${j.label}: ${times.at(-1).toFixed(0)} ms -> ${j.file}${wide}`);
    }
    if (manifestDir) {
      const rel = jobs.map((j) => ({ label: j.label, file: path.basename(j.file) }));
      fs.writeFileSync(path.join(manifestDir, "manifest.json"), JSON.stringify(rel, null, 2) + "\n");
    }
    const mean = (xs) => xs.reduce((s, x) => s + x, 0) / xs.length;
    const warm = times.length > 1 ? `, ${mean(times.slice(1)).toFixed(0)} ms without the first (warm)` : "";
    console.log(`rendered ${times.length} image(s), avg ${mean(times).toFixed(0)} ms per frame${warm}`);
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((e) => { console.error(`error: ${e.message}`); process.exit(1); });
