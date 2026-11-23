"""Library paths and part/series JSON shared by every route module."""

import argparse
import io
import os
import re
from pathlib import Path

from PIL import Image
from fastapi import HTTPException

from pipeline.scribble import cli
from pipeline.scribble.io import atomic_write_bytes, load_part, load_series
from pipeline.scribble.schemas import Stages

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "docs" / "openapi.json"
MEDIA_TYPES = {".mp4", ".png", ".jpg", ".mp3", ".md", ".json"}
COVER_W = 360  # dashboard cover width (px): a small cached JPEG instead of the 1080x1920 thumbnail PNG
PART_FILES = ["story.md", "voice.mp3", "preview.mp4", "test-render.mp4", "final.mp4", "stills-sheet.png"]
APPROVE_NEEDS = {"stills": "stills-sheet.png", "test_render": "test-render.mp4", "final": "final.mp4"}
JOB_COMMANDS = {"run", "render-stills", "test-render", "render", "cast-sheet"}
KEEP_JOBS = 500  # finished jobs kept as history (oldest dropped first); the History page cleans up sooner
OUTPUT_LINES = 200
HEARTBEAT_S = 15
# ---------------- library ----------------

def lib() -> Path:
    return cli.library_root(argparse.Namespace(library=None))


def series_path(slug: str) -> Path:
    try:
        d = cli.series_dir(argparse.Namespace(library=None, slug=slug))
    except cli.UserError as e:
        raise HTTPException(404, str(e))
    if not (d / "series.json").exists():
        raise HTTPException(404, f"series {slug!r} not found")
    return d


def part_path(slug: str, part: str) -> Path:
    series_path(slug)
    try:
        return cli.part_dir(argparse.Namespace(library=None, slug=slug, part=part))
    except cli.UserError as e:
        raise HTTPException(404, str(e))


def all_series() -> list[Path]:
    root = lib()
    return sorted(d for d in root.iterdir() if (d / "series.json").is_file()) if root.is_dir() else []


def du(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def parts_of(d: Path):
    """(part id, PartModel or None) for each part listed in series.json"""
    for pid in load_series(d / "series.json").parts:
        f = d / pid / "part.json"
        yield pid, (load_part(f) if f.exists() else None)


def media_url(slug: str, rel: str) -> str:
    return f"/api/media/{slug}/{rel}"


def safe_folder_name(value: str, fallback: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]', "", value).strip(" .")
    return (value or fallback)[:120]


def cover(d: Path) -> str | None:
    parts = load_series(d / "series.json").parts
    if not parts:
        return None
    pdir = d / parts[0]
    choice = load_part(pdir / "part.json").thumbnail_choice if (pdir / "part.json").exists() else None
    for rel in filter(None, (choice, "thumbs/thumb-1.png")):
        if (pdir / rel).is_file():
            small = small_cover(pdir / rel)
            return media_url(d.name, f"{parts[0]}/{small.relative_to(pdir).as_posix() if small else rel}")
    return None


def small_cover(src: Path) -> Path | None:
    """<thumb>-360.jpg beside the thumbnail, made once and again only when the thumbnail is newer; None if the
    thumbnail can't be read (then the PNG is served as it is)"""
    out = src.with_name(f"{src.stem}-{COVER_W}.jpg")
    if out.is_file() and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    try:
        with Image.open(src) as im:
            im = im.convert("RGB")
            buf = io.BytesIO()
            im.resize((COVER_W, round(im.height * COVER_W / im.width)), Image.LANCZOS).save(buf, "JPEG", quality=82)
    except (OSError, ValueError):
        return None
    atomic_write_bytes(out, buf.getvalue())
    return out


def posted_counts(d: Path) -> dict:
    out = {"youtube": 0, "instagram": 0}
    for _, p in parts_of(d):
        for k in out:
            out[k] += bool(p and getattr(p.posted, k))
    return out


def waiting_approvals(pdir: Path, p) -> list[str]:
    """approvals with something to look at but no approval yet (not the test render: optional, never waited on)"""
    return [n for n, f in APPROVE_NEEDS.items()
            if n != "test_render" and not getattr(p.approvals, n).approved_at and (pdir / f).is_file()
            and (n != "final" or p.stages.finish.status == "done")]


def part_summary(pdir: Path, p) -> dict:
    if p is None:
        return {"id": pdir.name, "missing": True}
    return {"id": p.id, "number": p.number, "title": p.title,
            "stages": {f.alias or name: getattr(p.stages, name).status for name, f in Stages.model_fields.items()},
            "approvals": {n: getattr(p.approvals, n).model_dump(mode="json")["approved_at"] for n in APPROVE_NEEDS},
            "posted": p.posted.model_dump(mode="json"), "thumbnail_choice": p.thumbnail_choice,
            "waiting": waiting_approvals(pdir, p)}


def part_json(pdir: Path) -> dict:
    return load_part(pdir / "part.json").model_dump(mode="json")


def series_json(d: Path) -> dict:
    return load_series(d / "series.json").model_dump(mode="json")


def write_story(pdir: Path, text: str) -> None:
    """story.md is user-owned, so not via io.atomic_write_text (it refuses PROTECTED names on purpose)"""
    tmp = pdir / ".story.md.upload.tmp"
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, pdir / "story.md")
