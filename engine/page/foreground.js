// Foreground silhouettes: an out-of-focus ink shape near the camera, at the frame's outer edge (main.js
// foregroundFor places it). Drawn for the right edge: the outer side is the canvas's right, the top its top; main.js
// mirrors it for the left. Every shape comes from a seeded rng: same set, same silhouette.
import { INK } from "./style.js";

export const FG_KINDS = { outdoor: ["leaves", "vine"], indoor: ["plant", "curtain"] };
const FW = 256, FH = 1024; // a tall strip: the outer ~20% of the frame, top to just above the captions

/** canvas FW x FH with the silhouette `kind`, ink on transparent, softened by blur px, fading out at the bottom */
export function foregroundCanvas(kind, R, blur) {
  const c = Object.assign(document.createElement("canvas"), { width: FW, height: FH }), g = c.getContext("2d");
  const U = (a, b) => a + (b - a) * R();
  g.filter = `blur(${blur}px)`;
  g.fillStyle = g.strokeStyle = INK;
  g.lineCap = "round";
  const leaf = (x, y, len, ang) => {
    g.save(); g.translate(x, y); g.rotate(ang);
    g.beginPath(); g.ellipse(len / 2, 0, len / 2, len * 0.2, 0, 0, Math.PI * 2); g.fill();
    g.restore();
  };
  if (kind === "leaves") { // a branch reaching in from the top corner, leaves hanging off it
    const end = [FW * U(0.1, 0.3), FH * U(0.3, 0.5)], ctl = [FW * 0.7, FH * 0.02];
    g.lineWidth = FW * 0.07;
    g.beginPath(); g.moveTo(FW * 1.1, -10); g.quadraticCurveTo(...ctl, ...end); g.stroke();
    for (let i = 0, n = 10 + Math.floor(R() * 6); i < n; i++) {
      const p = (i + R()) / n, q = 1 - p; // point on the branch's curve
      const x = q * q * FW * 1.1 + 2 * q * p * ctl[0] + p * p * end[0], y = q * q * -10 + 2 * q * p * ctl[1] + p * p * end[1];
      leaf(x, y, FW * U(0.25, 0.42), U(0.6, 2.4));
    }
  } else if (kind === "vine") { // strands hanging from the top, leaves on alternate sides
    for (let s = 0, n = 3 + Math.floor(R() * 2); s < n; s++) {
      const x0 = FW * U(0.4, 1), len = FH * U(0.5, 0.95), ph = U(0, 6), amp = FW * U(0.03, 0.08);
      g.lineWidth = FW * 0.025;
      g.beginPath(); g.moveTo(x0, 0);
      for (let y = 0; y <= len; y += 16) g.lineTo(x0 + amp * Math.sin(y / 90 + ph), y);
      g.stroke();
      for (let y = 30, k = 0; y < len; y += FH * U(0.05, 0.08), k++) {
        leaf(x0 + amp * Math.sin(y / 90 + ph), y, FW * U(0.18, 0.3), (k % 2 ? 0.5 : Math.PI - 0.5) + U(-0.3, 0.3));
      }
    }
  } else if (kind === "plant") { // a hanging plant: long fronds falling from the top corner
    for (let i = 0, n = 7 + Math.floor(R() * 4); i < n; i++) {
      const a = U(1.75, 2.9), len = FH * U(0.3, 0.6), x0 = FW * 1.05, y0 = -FH * 0.02;
      const x1 = x0 + Math.cos(a) * len * 0.35, y1 = y0 + Math.sin(a) * len, w = FW * U(0.06, 0.1);
      g.beginPath(); g.moveTo(x0, y0);
      g.quadraticCurveTo(x1 - w * 3, (y0 + y1) / 2, x1, y1);
      g.quadraticCurveTo(x1 + w * 3, (y0 + y1) / 2, x0 + w, y0);
      g.fill();
    }
  } else { // curtain: a drape on the outer edge, its inner edge in soft folds
    const x = FW * U(0.35, 0.55);
    g.beginPath(); g.moveTo(FW + 20, 0); g.lineTo(x, 0);
    for (let y = 0; y <= FH; y += 16) g.lineTo(x + FW * 0.06 * Math.sin(y / 70 + 1.3) + (y / FH) * FW * 0.1, y);
    g.lineTo(FW + 20, FH); g.closePath(); g.fill();
    g.globalCompositeOperation = "destination-out"; // folds: lighter streaks
    g.globalAlpha = 0.35; g.lineWidth = FW * 0.04;
    for (let k = 1; k <= 3; k++) { const fx = x + (FW - x) * (k / 4); g.beginPath(); g.moveTo(fx, 0); g.lineTo(fx + FW * 0.05, FH); g.stroke(); }
    g.globalAlpha = 1; g.globalCompositeOperation = "source-over";
  }
  g.filter = "none"; // fade the strip's bottom: its cut edge never shows above the captions
  g.globalCompositeOperation = "destination-in";
  const fade = g.createLinearGradient(0, FH * 0.75, 0, FH);
  fade.addColorStop(0, "#000"); fade.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = fade; g.fillRect(0, 0, FW, FH);
  return c;
}
