// Run: npm test (in engine/). Renders the pipeline's valid story fixture in a temp dir.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { setVariant } from "../page/rng.js";

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

// tests always force SwiftShader: identical bytes on any machine
const render = (...args) => spawnSync(process.execPath, [path.join(ENGINE, "render.mjs"), ...args, "--swiftshader"], { encoding: "utf8" });
const pngSize = (buf) => [buf.readUInt32BE(16), buf.readUInt32BE(20)]; // IHDR width, height

test("same frame twice gives identical PNG bytes, 1080x1920 (a talk frame, mouth open)", () => {
  const part = makePart();
  const a = path.join(part, "a.png"), b = path.join(part, "b.png");
  for (const out of [a, b]) {
    const r = render("--part", part, "--frame", "66", "--out", out); // s02 bob talks, mouth cycle open
    assert.equal(r.status, 0, r.stderr);
  }
  const A = fs.readFileSync(a), B = fs.readFileSync(b);
  assert.equal(A.subarray(1, 4).toString(), "PNG");
  assert.deepEqual(pngSize(A), [1080, 1920]);
  assert.ok(A.equals(B), "frame 66 rendered twice differs");
});

test("stills: one image per shot plus a manifest", () => {
  const part = makePart();
  const r = render("--part", part, "--stills");
  assert.equal(r.status, 0, r.stderr);
  const dir = path.join(part, "frames", "stills");
  const manifest = JSON.parse(fs.readFileSync(path.join(dir, "manifest.json"), "utf8"));
  assert.deepEqual(manifest.frames.map((m) => m.file), ["s01.png", "s02.png", "s03.png"]);
  assert.equal(manifest.renderer.renderer, "swiftshader");
  assert.match(manifest.renderer.gpu_name, /SwiftShader/);
  assert.ok(manifest.renderer.playwright && manifest.renderer.chromium);
  for (const m of manifest.frames) assert.deepEqual(pngSize(fs.readFileSync(path.join(dir, m.file))), [1080, 1920]);
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

const OUTDOOR = ["street", "dirt_road", "countryside", "orchard", "stadium"];

test("every set and variant builds inside stage clearance; outdoor props loop around the band without gaps", () => {
  // geometry only (no frames): --loop-check builds every set/variant for two seeds (buildSet throws on a clearance
  // break) and sweeps the travel shift across the whole band, comparing each row's widest gap around the band with
  // the widest gap inside the static layout
  const r = spawnSync(process.execPath, [path.join(ENGINE, "render.mjs"), "--loop-check", "--swiftshader"], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  const res = JSON.parse(r.stdout.trim().split(/\r?\n/).at(-1));
  assert.equal(res.length, 2 * (3 + 4 * 3)); // 2 seeds x (room, office, street + 4 sets x 3 variants)
  for (const x of res.filter((x) => OUTDOOR.includes(x.set))) {
    assert.ok(x.excess <= 1e-6, `${x.set}#${x.variant} seed ${x.seed}: row z ${x.row} opens a gap ${x.excess} at the seam`);
  }
});

test("frame range writes 6-digit names and renderer info", () => {
  const part = makePart(), out = path.join(part, "frames"), info = path.join(part, "info.json");
  const r = render("--part", part, "--frames", "8-10", "--out-dir", out, "--info-out", info);
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(fs.readdirSync(out).sort(), ["000008.png", "000009.png", "000010.png"]);
  assert.equal(JSON.parse(fs.readFileSync(info, "utf8")).renderer, "swiftshader");
});

// fixture: s01 0-60, s02 60-120, s03 120-180, all office. s03 -> street puts a wipe on frames 115..124.
const png = (dir, n) => fs.readFileSync(path.join(dir, `${String(n).padStart(6, "0")}.png`));

test("set change: marker wipe composites both sets, deterministic; one scene outside the wipe", () => {
  const wiped = makePart((s) => { s.shots[2].set = "street"; return s; });
  const office = makePart(), street = makePart((s) => { for (const sh of s.shots) sh.set = "street"; return s; });
  const out = (p, tag) => path.join(p, tag);
  const r = render("--part", wiped, "--frames", "114-117", "--out-dir", out(wiped, "a"));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /frame 117: .*\[wipe office->street 30%\]/);
  assert.doesNotMatch(r.stdout, /frame 114: .*wipe/);
  assert.equal(render("--part", wiped, "--frames", "117-117", "--out-dir", out(wiped, "b")).status, 0);
  for (const p of [office, street]) assert.equal(render("--part", p, "--frames", "114-117", "--out-dir", out(p, "a")).status, 0);
  assert.ok(png(out(wiped, "a"), 117).equals(png(out(wiped, "b"), 117)), "transition frame not deterministic");
  assert.ok(png(out(wiped, "a"), 114).equals(png(out(office, "a"), 114)), "frame outside the wipe changed");
  assert.ok(!png(out(wiped, "a"), 117).equals(png(out(office, "a"), 117)), "new set missing from the wipe frame");
  assert.ok(!png(out(wiped, "a"), 117).equals(png(out(street, "a"), 117)), "old set missing from the wipe frame");
});

test("set variant: stable per shot id, all variants reachable, and it changes the props", () => {
  const ids = Array.from({ length: 40 }, (_, i) => `s${String(i + 1).padStart(2, "0")}`);
  for (const id of ids) assert.equal(setVariant("orchard", id, 3), setVariant("orchard", id, 3));
  assert.deepEqual([...new Set(ids.map((id) => setVariant("orchard", id, 3)))].sort(), [0, 1, 2]);
  assert.equal(setVariant("room", "s07", 1), 0);
  // same story, only the shot ids differ -> a different variant of dirt_road -> a different picture
  const other = ids.find((id) => setVariant("dirt_road", id, 3) !== setVariant("dirt_road", "s01", 3));
  const parts = ["s01", other].map((id) => makePart((s) => {
    for (const sh of s.shots) sh.set = "dirt_road";
    s.shots[0].id = id; s.shots[1].id = `x${id}`; s.shots[2].id = `y${id}`;
    return s;
  }));
  for (const p of parts) assert.equal(render("--part", p, "--frame", "10", "--out", path.join(p, "f.png")).status, 0);
  assert.ok(!fs.readFileSync(path.join(parts[0], "f.png")).equals(fs.readFileSync(path.join(parts[1], "f.png"))));
});

// --- travel shots ---
/** s01 (frames 0-59) becomes a travel shot on `set`: bob walks in place facing `facing`, the world scrolls */
const travelPart = (set, speed = 1.2, facing = "right", id = "s01", extra = (s) => s) => makePart((s) => {
  const a = s.shots[0].actors[0];
  Object.assign(s.shots[0], { set, travel: { speed }, id });
  Object.assign(a, { start_pos: [0, 0.1], end_pos: [0, 0.1], facing });
  return extra(s);
});

test("travel shot: deterministic, the world scrolls, a wipe out of it still composites", () => {
  const part = travelPart("dirt_road", 1.2, "left", "s01", (s) => { s.shots[1].set = "orchard"; return s; });
  const still = makePart((s) => { s.shots[0].set = "dirt_road"; s.shots[0].actors[0].end_pos = [0, 0.1]; return s; });
  const r = render("--part", part, "--frames", "54-57", "--out-dir", path.join(part, "a"));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /frame 54: .*\[travel 1\.2 u\/s left, shift 2\.16, loop excess -?[\d.]+ \(row z -?\d+\)\]/);
  assert.match(r.stdout, /frame 57: .*\[wipe dirt_road->orchard 30%\]/);
  assert.equal(render("--part", part, "--frames", "54-54", "--out-dir", path.join(part, "b")).status, 0);
  assert.equal(render("--part", still, "--frames", "54-54", "--out-dir", path.join(still, "a")).status, 0);
  assert.ok(png(path.join(part, "a"), 54).equals(png(path.join(part, "b"), 54)), "travel frame not deterministic");
  assert.ok(!png(path.join(part, "a"), 54).equals(png(path.join(still, "a"), 54)), "world did not scroll");
});

test("travel smoke: one rendered travel frame per outdoor set", () => {
  // five 36-frame travel shots, one per outdoor set; --stills renders the middle of each in one browser
  const part = makePart((s) => {
    const base = s.shots[0];
    s.shots = OUTDOOR.map((set, i) => ({ ...structuredClone(base), id: `s0${i + 1}`, set, travel: { speed: 2.5 },
      start_frame: i * 36, end_frame: (i + 1) * 36, phrase_range: [0, 0], twist: false,
      actors: [{ ...base.actors[0], action: "run", start_pos: [0, 0.1], end_pos: [0, 0.1], facing: i % 2 ? "left" : "right" }] }));
    return s;
  });
  const r = render("--part", part, "--stills");
  assert.equal(r.status, 0, r.stderr);
  assert.equal([...r.stdout.matchAll(/\[travel 2\.5 u\/s (left|right)/g)].length, OUTDOOR.length, r.stdout);
});
