// Borrowed from mromidev/claude-animated-shorts at commit e3b817b6afc6cd413466d43f11ba31209e034bbf,
// ported from TypeScript to plain JS and trimmed:
//   templates/bridge/toon.ts:  Pen (path, poly, stroke, dot), ellPts
//   templates/bridge/story.ts: glide (smootherstep), dolly
// Changes: no rotation transform in Pen, ink colour passed in, camera helpers return plain objects.
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
