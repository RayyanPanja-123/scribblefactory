// Borrowed from mromidev/claude-animated-shorts at commit e3b817b6afc6cd413466d43f11ba31209e034bbf,
// ported from TypeScript to plain JS and trimmed:
//   templates/bridge/toon.ts:  Pen (path, poly, stroke, dot), ellPts
//   templates/bridge/story.ts: glide (smootherstep), dolly
//   templates/bridge/paint.ts: cloudHD (as cloudCanvas)
// Changes: no rotation transform in Pen, ink colour passed in, camera helpers return plain objects; cloudCanvas takes
// a seeded rng and draws into a fresh canvas (no texture cache).
//
// MIT License
//
// Copyright (c) 2026 Mr omi
//
// Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
// documentation files (the "Software"), to deal in the Software without restriction, including without limitation
// the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
// to permit persons to whom the Software is furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all copies or substantial portions of
// the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
// THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
// TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

const rad = (d) => (d * Math.PI) / 180;

/** Canvas2D drawing helpers with a shared ink colour. */
export class Pen {
  constructor(g, ink) { this.g = g; this.ink = ink; }
  path(pts, close) {
    const g = this.g;
    g.beginPath();
    pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
    if (close) g.closePath();
  }
  /** filled shape with an ink outline; fill = null draws the outline only, ol = 0 no outline */
  poly(pts, fill, ol) {
    const g = this.g;
    this.path(pts, true);
    if (fill) { g.fillStyle = fill; g.fill(); }
    if (ol) { g.lineWidth = ol; g.strokeStyle = this.ink; g.lineJoin = "round"; g.stroke(); }
  }
  stroke(pts, w, col = this.ink) {
    const g = this.g;
    g.lineCap = "round"; g.lineJoin = "round";
    this.path(pts, false); g.strokeStyle = col; g.lineWidth = w; g.stroke();
  }
  dot(cx, cy, r, col = this.ink) {
    const g = this.g;
    g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.fillStyle = col; g.fill();
  }
}

export const ellPts = (cx, cy, rx, ry, a0 = 0, a1 = 360, rot = 0, n = 48) => {
  const r = rad(rot), pts = [];
  for (let i = 0; i <= n; i++) {
    const a = rad(a0 + ((a1 - a0) * i) / n), x = rx * Math.cos(a), y = ry * Math.sin(a);
    pts.push([cx + x * Math.cos(r) - y * Math.sin(r), cy + x * Math.sin(r) + y * Math.cos(r)]);
  }
  return pts;
};

/** symmetric smootherstep ease (attack = release) */
export const glide = (u) => { const x = Math.max(0, Math.min(1, u)); return x * x * x * (x * (6 * x - 15) + 10); };

/** dolly: camera slides toward the look point by factor k (k < 1 pushes in, k > 1 pulls out) */
export const dolly = (pos, look, k) => ({ pos: look.map((v, i) => v + (pos[i] - v) * k), look });

/** painted cloud sprite, 1024 x 512: a row of lobes plus a crown in three soft tones (pal: lit, mid, shade), lit
 *  side up-left, flat soft bottom, no outline. R: seeded rng. */
export function cloudCanvas(R, pal) {
  const W = 1024, H = 512, base = 400, TAU = Math.PI * 2, U = (a, b) => a + (b - a) * R();
  const c = Object.assign(document.createElement("canvas"), { width: W, height: H }), g = c.getContext("2d");
  const n = 6 + Math.floor(R() * 4), lobes = [];
  for (let i = 0; i < n; i++) { // main row, biggest in the middle
    const t = (i + 0.5) / n, rad = (60 + 110 * Math.sin(Math.PI * t) ** 0.8) * U(0.75, 1.15);
    lobes.push({ x: 150 + t * 724 + U(-30, 30), y: base - rad * U(0.35, 0.65), r: rad });
  }
  for (let i = 0; i < Math.floor(n / 2); i++) { // crown
    const t = U(0.25, 0.75), rad = U(60, 110);
    lobes.push({ x: 150 + t * 724, y: base - 150 - rad * U(0.3, 0.7), r: rad });
  }
  const layer = (dx, dy, k, col, blur) => {
    g.save(); g.filter = `blur(${blur}px)`; g.fillStyle = col; g.beginPath();
    for (const l of lobes) { const x = l.x + dx * l.r, y = l.y + dy * l.r; g.moveTo(x + l.r * k, y); g.arc(x, y, l.r * k, 0, TAU); }
    g.fill(); g.restore();
  };
  layer(0, 0, 1.0, pal.shade, 6);        // silhouette in the underside tone
  layer(-0.04, -0.12, 0.9, pal.mid, 8);  // mid band
  layer(-0.1, -0.26, 0.72, pal.lit, 10); // sunlit crown, offset up-left
  g.globalCompositeOperation = "destination-in"; // flat, soft bottom
  const m = g.createLinearGradient(0, base - 18, 0, base + 6);
  m.addColorStop(0, "rgba(0,0,0,1)"); m.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = m; g.fillRect(0, 0, W, H);
  g.globalCompositeOperation = "source-over";
  return c;
}
