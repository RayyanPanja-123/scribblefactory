// Run: npm test (in engine/). Renders the pipeline's valid story fixture in temp dirs. Every frame of this file is
// rendered by one browser (render.mjs --batch, started in `before`), overlapped with the geometry-only loop check and
// one plain call that covers the non-batch CLI path and determinism across separate processes.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { after, before, test } from "node:test";
import { setVariant } from "../page/rng.js";
import { fixturePart, frames, jobOk, png, render, renderNamed } from "./batch.mjs";

const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });
const makePart = (mutate) => fixturePart(temps, mutate);
const pngSize = (buf) => [buf.readUInt32BE(16), buf.readUInt32BE(20)]; // IHDR width, height
const OUTDOOR = ["street", "dirt_road", "countryside", "orchard", "stadium"];

// --- parts (built once) ---
// fixture: s01 0-60, s02 60-120, s03 120-180, all office. base: s01 in the room (the unknown-set fallback target).
const base = makePart((s) => { s.shots[0].set = "room"; return s; });
const moon = makePart((s) => { s.shots[0].set = "moon"; return s; });
const stills = makePart();
// s03 -> street puts a wipe on frames 115..124
const wiped = makePart((s) => { s.shots[2].set = "street"; return s; });
const street = makePart((s) => { for (const sh of s.shots) sh.set = "street"; return s; });
// set variant: same story, only the shot ids differ -> a different variant of dirt_road -> a different picture
const IDS = Array.from({ length: 40 }, (_, i) => `s${String(i + 1).padStart(2, "0")}`);
const otherId = IDS.find((id) => setVariant("dirt_road", id, 3) !== setVariant("dirt_road", "s01", 3));
const variants = ["s01", otherId].map((id) => makePart((s) => {
  for (const sh of s.shots) sh.set = "dirt_road";
  s.shots[0].id = id; s.shots[1].id = `x${id}`; s.shots[2].id = `y${id}`;
  return s;
}));
// s01 (frames 0-59) becomes a travel shot: bob walks in place facing left, the world scrolls; s02 on another set
const travel = makePart((s) => {
  Object.assign(s.shots[0], { set: "dirt_road", travel: { speed: 1.2 } });
  Object.assign(s.shots[0].actors[0], { start_pos: [0, 0.1], end_pos: [0, 0.1], facing: "left" });
  s.shots[1].set = "orchard";
  return s;
});
const still = makePart((s) => { s.shots[0].set = "dirt_road"; s.shots[0].actors[0].end_pos = [0, 0.1]; return s; });
// five 36-frame travel shots, one per outdoor set; --stills renders the middle of each
const smoke = makePart((s) => {
  const b = s.shots[0];
  s.shots = OUTDOOR.map((set, i) => ({ ...structuredClone(b), id: `s0${i + 1}`, set, travel: { speed: 2.5 },
    start_frame: i * 36, end_frame: (i + 1) * 36, phrase_range: [0, 0], twist: false,
    actors: [{ ...b.actors[0], action: "run", start_pos: [0, 0.1], end_pos: [0, 0.1], facing: i % 2 ? "left" : "right" }] }));
  return s;
});

// custom sets (library/sets.json): a part in its own library. s01 on an indoor custom set, s02 a travel shot on an
// outdoor one; `blocked` puts a piece on the stage (clearance break)
const KITCHEN = { id: "kitchen", name: "Kitchen", kind: "indoor", floor: "#d9c7a3", back: "#f6e7c8", pieces: [
  { shape: "box", at: [-1.8, 0.45, -2.2], size: [1.6, 0.9, 0.6], color: "#8a5a32" },
  { shape: "ball", at: [2.5, 1.2, -2.3], size: [0.3], color: "#43aa8b", backdrop: true }] };
const BEACH = { id: "beach", name: "Beach", kind: "outdoor", floor: "#f2d8a0", back: "#8fd0f0", pieces: [
  { shape: "cyl", at: [-3, 1.5, -3], size: [0.1, 0.15, 3], color: "#7b5132" },
  { shape: "mound", at: [6, -1, -40], size: [12, 0.3], color: "#3a8fb7", backdrop: true }] };
function inLibrary(sets, mutate) {
  const lib = fs.mkdtempSync(path.join(path.dirname(path.dirname(base)), "scribble-lib-"));
  temps.push(lib);
  fs.cpSync(path.dirname(makePart(mutate)), path.join(lib, "demo"), { recursive: true });
  fs.writeFileSync(path.join(lib, "sets.json"), JSON.stringify({ schema_version: 1, sets }));
  return path.join(lib, "demo", "part-01");
}
const custom = inLibrary([KITCHEN, BEACH], (s) => {
  s.shots[0].set = "kitchen";
  Object.assign(s.shots[1], { set: "beach", travel: { speed: 1.2 } });
  Object.assign(s.shots[1].actors[0], { start_pos: [0, 0.1], end_pos: [0, 0.1], facing: "left" });
  return s;
});
const blocked = inLibrary([{ ...KITCHEN, pieces: [{ shape: "box", at: [0, 0.5, 0], size: [1, 1, 1], color: "#ff0000" }] }],
  (s) => { s.shots[0].set = "kitchen"; return s; });

const JOBS = {
  talk: ["--part", base, "--frame", "66", "--out", path.join(base, "a.png")], // s02 bob talks, mouth cycle open
  room: frames(base, "9-10", "range"),                                          // also the 6-digit range check
  moon: frames(moon, "10-10", "a"),
  badFrame: ["--part", base, "--frame", "999", "--out", path.join(base, "x.png")],
  stills: ["--part", stills, "--stills"],
  wipe114: frames(wiped, "114-114", "a"), wipe117: frames(wiped, "117-117", "a"), wipe117b: frames(wiped, "117-117", "b"),
  office: frames(base, "114-114", "o"), office117: frames(base, "117-117", "o"), street117: frames(street, "117-117", "a"),
  variant0: frames(variants[0], "10-10", "a"), variant1: frames(variants[1], "10-10", "a"),
  travel54: frames(travel, "54-54", "a"), travel57: frames(travel, "57-57", "a"), travel54b: frames(travel, "54-54", "b"),
  still54: frames(still, "54-54", "a"),
  smoke: ["--part", smoke, "--stills"],
  kitchen: frames(custom, "10-10", "a"), beach: frames(custom, "90-90", "a"), blocked: frames(blocked, "10-10", "a"),
};
let R, plain, loop;
before(async () => {
  [R, plain, loop] = await Promise.all([
    renderNamed(JOBS),
    render("--part", base, "--frame", "66", "--out", path.join(base, "c.png"), "--info-out", path.join(base, "info.json")),
    render("--loop-check"),
  ]);
});
const ok = (name) => jobOk(R, name);

test("same frame gives identical PNG bytes, 1080x1920 (a talk frame, mouth open), across processes", () => {
  ok("talk");
  assert.equal(plain.status, 0, plain.stderr);
  assert.equal(JSON.parse(fs.readFileSync(path.join(base, "info.json"), "utf8")).renderer, "swiftshader");
  const [A, C] = ["a.png", "c.png"].map((f) => fs.readFileSync(path.join(base, f)));
  assert.equal(A.subarray(1, 4).toString(), "PNG");
  assert.deepEqual(pngSize(A), [1080, 1920]);
  assert.ok(A.equals(C), "frame 66 differs between the batch and a separate process");
});

test("stills: one image per shot plus a manifest", () => {
  ok("stills");
  const dir = path.join(stills, "frames", "stills");
  const manifest = JSON.parse(fs.readFileSync(path.join(dir, "manifest.json"), "utf8"));
  assert.deepEqual(manifest.frames.map((m) => m.file), ["s01.png", "s02.png", "s03.png"]);
  assert.equal(manifest.renderer.renderer, "swiftshader");
  assert.match(manifest.renderer.gpu_name, /SwiftShader/);
  assert.ok(manifest.renderer.playwright && manifest.renderer.chromium);
  for (const m of manifest.frames) assert.deepEqual(pngSize(fs.readFileSync(path.join(dir, m.file))), [1080, 1920]);
});

test("unknown set falls back to room with a warning", () => {
  ok("moon"); ok("room");
  assert.match(R.stderr, /unknown set "moon", using "room"/);
  assert.ok(png(path.join(moon, "a"), 10).equals(png(path.join(base, "range"), 10)));
});

test("custom sets (library/sets.json): indoor and outdoor build and travel; a piece on the stage fails", () => {
  ok("kitchen"); ok("beach");
  assert.doesNotMatch(R.stderr, /unknown set "(kitchen|beach)"/);
  assert.ok(!png(path.join(custom, "a"), 10).equals(png(path.join(base, "range"), 10)), "kitchen drew the room");
  assert.match(R.beach.out, /frame 90: .*\[travel 1\.2 u\/s left/);
  assert.equal(R.blocked.ok, false);
  assert.match(R.blocked.error, /breaks stage clearance/);
});

test("bad frame number fails that job with the range in the message", () => {
  assert.equal(R.badFrame.ok, false);
  assert.match(R.badFrame.error, /outside 0\.\.179/);
});

test("every set and variant builds inside stage clearance; outdoor props loop around the band without gaps", () => {
  // geometry only (no frames): --loop-check builds every set/variant for two seeds (buildSet throws on a clearance
  // break) and sweeps the travel shift across the whole band, comparing each row's widest gap around the band with
  // the widest gap inside the static layout
  assert.equal(loop.status, 0, loop.stderr);
  const res = JSON.parse(loop.stdout.trim().split(/\r?\n/).at(-1));
  assert.equal(res.length, 2 * (3 + 4 * 3)); // 2 seeds x (room, office, street + 4 sets x 3 variants)
  for (const x of res.filter((x) => OUTDOOR.includes(x.set))) {
    assert.ok(x.excess <= 1e-6, `${x.set}#${x.variant} seed ${x.seed}: row z ${x.row} opens a gap ${x.excess} at the seam`);
  }
});

test("frame range writes 6-digit names", () => {
  ok("room");
  assert.deepEqual(fs.readdirSync(path.join(base, "range")).sort(), ["000009.png", "000010.png"]);
});

test("set change: marker wipe composites both sets, deterministic; one scene outside the wipe", () => {
  for (const n of ["wipe114", "wipe117", "wipe117b", "office", "office117", "street117"]) ok(n);
  assert.match(R.wipe117.out, /frame 117: .*\[wipe office->street 30%\]/);
  assert.doesNotMatch(R.wipe114.out, /wipe/);
  const W = path.join(wiped, "a");
  assert.ok(png(W, 117).equals(png(path.join(wiped, "b"), 117)), "transition frame not deterministic");
  assert.ok(png(W, 114).equals(png(path.join(base, "o"), 114)), "frame outside the wipe changed");
  assert.ok(!png(W, 117).equals(png(path.join(base, "o"), 117)), "new set missing from the wipe frame");
  assert.ok(!png(W, 117).equals(png(path.join(street, "a"), 117)), "old set missing from the wipe frame");
});

test("set variant: stable per shot id, all variants reachable, and it changes the props", () => {
  for (const id of IDS) assert.equal(setVariant("orchard", id, 3), setVariant("orchard", id, 3));
  assert.deepEqual([...new Set(IDS.map((id) => setVariant("orchard", id, 3)))].sort(), [0, 1, 2]);
  assert.equal(setVariant("room", "s07", 1), 0);
  ok("variant0"); ok("variant1");
  assert.ok(!png(path.join(variants[0], "a"), 10).equals(png(path.join(variants[1], "a"), 10)));
});

test("travel shot: deterministic, the world scrolls, a wipe out of it still composites", () => {
  for (const n of ["travel54", "travel57", "travel54b", "still54"]) ok(n);
  assert.match(R.travel54.out, /frame 54: .*\[travel 1\.2 u\/s left, shift 2\.16, loop excess -?[\d.]+ \(row z -?\d+\)\]/);
  assert.match(R.travel57.out, /frame 57: .*\[wipe dirt_road->orchard 30%\]/);
  assert.ok(png(path.join(travel, "a"), 54).equals(png(path.join(travel, "b"), 54)), "travel frame not deterministic");
  assert.ok(!png(path.join(travel, "a"), 54).equals(png(path.join(still, "a"), 54)), "world did not scroll");
});

test("travel smoke: one rendered travel frame per outdoor set", () => {
  ok("smoke");
  assert.equal([...R.smoke.out.matchAll(/\[travel 2\.5 u\/s (left|right)/g)].length, OUTDOOR.length, R.smoke.out);
});

test("render.mjs without a job prints usage and exits 1", async () => {
  const r = await render();
  assert.equal(r.status, 1);
  assert.match(r.stderr, /usage:/);
});
