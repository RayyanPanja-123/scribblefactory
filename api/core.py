"""Library paths and part/series JSON shared by every route module."""

import argparse
import os
import re
from pathlib import Path

from fastapi import HTTPException

from pipeline.scribble import cli
from pipeline.scribble.io import load_part, load_series, save_part, part_dir_of, part_folders_of, series_dirs, series_exists, storage_root
from pipeline.scribble.schemas import Stages

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "docs" / "openapi.json"
MEDIA_TYPES = {".mp4", ".png", ".jpg", ".mp3", ".md", ".json"}
PART_FILES = ["story.md", "voice.mp3", "final.mp4", "stills-sheet.png", "voice-recorded.mp3"]  # the last: a TTS part's kept recording
APPROVE_NEEDS = {"stills": "stills-sheet.png", "final": "final.mp4"}
JOB_COMMANDS = {"run", "render-stills", "render", "cast-sheet"}
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
    if not series_exists(d):
        raise HTTPException(404, f"series {slug!r} not found")
    return d


def part_path(slug: str, part: str) -> Path:
    series_path(slug)
    try:
        return cli.part_dir(argparse.Namespace(library=None, slug=slug, part=part))
    except cli.UserError as e:
        raise HTTPException(404, str(e))


def all_series() -> list[Path]:
    return series_dirs(lib())


def du(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def parts_of(d: Path):
    """(part id, PartModel) for each part of the series, by number"""
    for pid, folder in part_folders_of(d).items():
        yield pid, load_part(d / folder / "part.json")


def media_url(slug: str, rel: str) -> str:
    return f"/api/media/{slug}/{rel}"


def safe_folder_name(value: str, fallback: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]', "", value).strip(" .")
    return (value or fallback)[:120]


def posted_counts(d: Path) -> dict:
    out = {"youtube": 0, "instagram": 0}
    for _, p in parts_of(d):
        for k in out:
            out[k] += bool(p and getattr(p.posted, k))
    return out


def waiting_approvals(pdir: Path, p) -> list[str]:
    """approvals with something to look at but no approval yet"""
    return [n for n, f in APPROVE_NEEDS.items()
            if not getattr(p.approvals, n).approved_at and (pdir / f).is_file()
            and (n != "final" or p.stages.finish.status == "done")]


def part_summary(pdir: Path, p) -> dict:
    if p is None:
        return {"id": pdir.name, "missing": True}
    return {"id": p.id, "number": p.number, "title": p.title,
            "stages": {f.alias or name: s.status for name, f in Stages.model_fields.items()
                       if (s := getattr(p.stages, name)) is not None},
            "approvals": {n: getattr(p.approvals, n).model_dump(mode="json")["approved_at"] for n in APPROVE_NEEDS},
            "posted": p.posted.model_dump(mode="json"),
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
    # Run next plans from statuses, so a "done" prep would hide the edit: mark it pending and the chain after it
    # (shots, render, audio...) re-plans; stages whose inputs end up unchanged still skip
    model = load_part(pdir / "part.json")
    model.stages.prep.status = "pending"
    save_part(pdir / "part.json", model)
