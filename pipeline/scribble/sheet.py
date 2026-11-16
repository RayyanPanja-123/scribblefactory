"""Contact sheets: a labelled grid of frames from a render manifest.

Run: python -m pipeline.scribble.sheet <frames-dir> <out.png> [--cols N]
<frames-dir>/manifest.json is written by engine/render.mjs: {"renderer": {...}, "frames": [{"label", "file"}, ...]}
(a bare list of frames is accepted too).
"""

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

THUMB_W, THUMB_H = 216, 384   # 1080x1920 / 5
LABEL_H = 30
PAD = 8


def sheet_size(n: int, cols: int) -> tuple[int, int]:
    rows = math.ceil(n / cols)
    return cols * (THUMB_W + PAD) + PAD, rows * (THUMB_H + LABEL_H + PAD) + PAD


def build_sheet(items: list[tuple[str, Path]], out: Path, cols: int) -> Path:
    """items: (label, image path) in reading order. Writes out atomically and returns it."""
    if not items:
        raise ValueError("no frames to put on a sheet")
    cols = max(1, min(cols, len(items)))
    sheet = Image.new("RGB", sheet_size(len(items), cols), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=20)
    for i, (label, path) in enumerate(items):
        x = PAD + (i % cols) * (THUMB_W + PAD)
        y = PAD + (i // cols) * (THUMB_H + LABEL_H + PAD)
        with Image.open(path) as im:
            sheet.paste(im.convert("RGB").resize((THUMB_W, THUMB_H), Image.LANCZOS), (x, y))
        draw.text((x + 2, y + THUMB_H + 4), label, fill="black", font=font)
    out = Path(out)
    tmp = out.with_name(f".{out.name}.tmp.png")
    sheet.save(tmp)
    tmp.replace(out)
    return out


def from_manifest(frames_dir: Path, out: Path, cols: int) -> Path:
    frames_dir = Path(frames_dir)
    manifest = json.loads((frames_dir / "manifest.json").read_text(encoding="utf-8"))
    frames = manifest["frames"] if isinstance(manifest, dict) else manifest
    return build_sheet([(m["label"], frames_dir / m["file"]) for m in frames], out, cols)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m pipeline.scribble.sheet")
    p.add_argument("frames_dir")
    p.add_argument("out")
    p.add_argument("--cols", type=int, default=6)
    a = p.parse_args(argv)
    print(f"wrote {from_manifest(Path(a.frames_dir), Path(a.out), a.cols)}")


if __name__ == "__main__":
    main()
