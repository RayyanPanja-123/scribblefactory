// Run: npm test (in engine/). Renders the pipeline's valid story fixture in a temp dir.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";

const ENGINE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FIX = path.join(ENGINE, "..", "pipeline", "tests", "fixtures", "story");

const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });

function makePart(mutate = (s) => s) {
  const series = fs.mkdtempSync(path.join(os.tmpdir(), "scribble-engine-"));
  temps.push(series);
  const part = path.join(series, "part-01");
  fs.mkdirSync(part);
  fs.copyFileSync(path.join(FIX, "series.json"), path.join(series, "series.json"));
  fs.copyFileSync(path.join(FIX, "phrases.json"), path.join(part, "phrases.json"));
  const story = mutate(JSON.parse(fs.readFileSync(path.join(FIX, "story.json"), "utf8")));
  fs.writeFileSync(path.join(part, "story.json"), JSON.stringify(story));
  return part;
}

const render = (...args) => spawnSync(process.execPath, [path.join(ENGINE, "render.mjs"), ...args], { encoding: "utf8" });
const pngSize = (buf) => [buf.readUInt32BE(16), buf.readUInt32BE(20)]; // IHDR width, height

test("same frame twice gives identical PNG bytes, 1080x1920", () => {
  const part = makePart();
  const a = path.join(part, "a.png"), b = path.join(part, "b.png");
  for (const out of [a, b]) {
    const r = render("--part", part, "--frame", "40", "--out", out);
    assert.equal(r.status, 0, r.stderr);
  }
  const A = fs.readFileSync(a), B = fs.readFileSync(b);
  assert.equal(A.subarray(1, 4).toString(), "PNG");
  assert.deepEqual(pngSize(A), [1080, 1920]);
  assert.ok(A.equals(B), "frame 40 rendered twice differs");
});

test("stills: one image per shot plus a manifest", () => {
  const part = makePart();
  const r = render("--part", part, "--stills");
  assert.equal(r.status, 0, r.stderr);
  const dir = path.join(part, "frames", "stills");
  const manifest = JSON.parse(fs.readFileSync(path.join(dir, "manifest.json"), "utf8"));
  assert.deepEqual(manifest.map((m) => m.file), ["s01.png", "s02.png", "s03.png"]);
  for (const m of manifest) assert.deepEqual(pngSize(fs.readFileSync(path.join(dir, m.file))), [1080, 1920]);
});

test("unknown set falls back to room with a warning", () => {
  const moon = makePart((s) => { s.shots[0].set = "moon"; return s; });
  const room = makePart((s) => { s.shots[0].set = "room"; return s; });
  const r = render("--part", moon, "--frame", "10", "--out", path.join(moon, "f.png"));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stderr, /unknown set "moon", using "room"/);
  assert.equal(render("--part", room, "--frame", "10", "--out", path.join(room, "f.png")).status, 0);
  assert.ok(fs.readFileSync(path.join(moon, "f.png")).equals(fs.readFileSync(path.join(room, "f.png"))));
});

test("bad frame number fails with exit 1", () => {
  const part = makePart();
  const r = render("--part", part, "--frame", "999", "--out", path.join(part, "x.png"));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /outside 0\.\.179/);
});
