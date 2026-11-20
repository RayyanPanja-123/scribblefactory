"""scribblefactory web API. Run from the repo root: uvicorn api.main:app --host 127.0.0.1 --port 8765

Localhost only, no auth. Files on disk are the source of truth: every read goes to the library, every write
goes through the CLI commands / pipeline io helpers, and long work runs as CLI subprocesses on one worker thread.
Write docs/openapi.json: python -m api.main
"""

import argparse
import asyncio
import contextlib
import io
import itertools
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Literal, get_args

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sse_starlette import EventSourceResponse

from pipeline.scribble import cli, package, settings, storycheck
from pipeline.scribble import sfx as sfx_lib
from pipeline.scribble.io import (atomic_write_bytes, atomic_write_json, atomic_write_text, delete_prop, delete_set, delete_object, load_part, load_props,
                                  load_series, load_sets, prop_kinds, save_prop, save_series, save_set, unknown_cast_props,
                                  cast_body_problems, cast_files, cast_render_current, delete_creature, load_creatures, save_creature, delete_action,
                                  load_actions, save_action, delete_wardrobe_item, load_wardrobe, save_wardrobe_item, load_objects, save_object)
from pipeline.scribble.schemas import (ACTIONS, BUILTIN_CREATURES, BUILTIN_SETS, BuiltinProp, CastMember, CreatureRig,
                                       CustomAction, CustomCreature, actions_with,
                                       CustomProp, CustomSet, PartModel, Posted, SeriesModel, SetKind, Slug, WorldObject,
                                       Stage, Stages,
                                       BUILTIN_WARDROBE, WardrobeId, WardrobeItem, WardrobeSlotName, utcnow)
from pipeline.scribble.stages import render as render_stage
from pipeline.scribble.stages.import_check import probe_duration
from pipeline.scribble.stages.runner import StageError, recover_stuck

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

@contextlib.asynccontextmanager
async def lifespan(_app):
    startup()
    yield


app = FastAPI(title="scribblefactory", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


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


# ---------------- response models (docs/openapi.json -> web/src/api/types.ts) ----------------

StageStatus = Stage.model_fields["status"].annotation


class Health(BaseModel):
    ok: bool


class Kpi(BaseModel):
    series: int
    parts_in_progress: int
    waiting_for_approval: int
    posted_this_month: int


class Waiting(BaseModel):
    slug: str
    part: str | None  # None: series-level (cast)
    waiting: list[str]  # "stills" | "test_render" | "final" | "cast:<id>"


class MonthPosts(BaseModel):
    month: str  # YYYY-MM
    youtube: int
    instagram: int


SheetCell = Literal["done", "current", "review", "running", "failed", "todo"]


class SheetRow(BaseModel):
    slug: str
    series_title: str
    part: str
    number: int
    title: str
    cells: list[SheetCell]  # one per SHEET_STEPS column


class Overview(BaseModel):
    kpi: Kpi
    waiting: list[Waiting]
    sheet_steps: list[str]
    sheet: list[SheetRow]  # every unposted part of every series, the exposure sheet
    posts_per_month: list[MonthPosts]
    disk_usage: dict[str, int]  # slug -> bytes


class PostedCounts(BaseModel):
    youtube: int
    instagram: int


class SeriesCard(BaseModel):
    slug: str
    title: str
    created_at: str
    status: str
    part_count: int
    cover: str | None
    disk_usage: int
    posted: PostedCounts


class PartSummary(BaseModel):
    id: str
    missing: bool = False  # listed in series.json but no part.json: only id is set
    number: int | None = None
    title: str | None = None
    stages: dict[str, StageStatus] = {}
    approvals: dict[str, str | None] = {}  # stills/test_render/final -> approved_at (ISO) or None
    posted: Posted | None = None
    thumbnail_choice: str | None = None
    waiting: list[str] = []


class CastRender(BaseModel):
    sheet: str | None  # every pose in one row (plus a row per named look); None: never rendered
    idle: str | None  # the idle pose alone: the card picture
    current: bool  # drawn from the look it has now; approving needs it


class SeriesDetail(BaseModel):
    series: SeriesModel
    parts: list[PartSummary]
    cast: dict[str, CastRender]  # cast id -> its render


class PartDetail(BaseModel):
    part: PartModel
    files: dict[str, bool]
    versions: dict[str, int]  # file (thumbs/<name> too) -> modified time: the ?v of its media url, new per re-render
    thumbs: list[str]
    qa: dict | None
    upload_md: str | None
    story_md: str | None
    tts_script: str | None  # script-for-tts.txt: what the voice reads (prep writes it; a story package too)
    voice_duration: float | None
    frames_bytes: int
    part_bytes: int  # the whole part folder, frames included
    busy: str | None


class Job(BaseModel):
    id: int
    tag: str
    slug: str
    part: str
    steps: list[str]
    current_step: int | None
    status: Literal["queued", "running", "done", "failed", "cancelled"]
    queued_at: str
    started_at: str | None
    finished_at: str | None
    returncode: int | None
    output: list[str]
    error: str | None = None  # why it failed without a return code, e.g. "interrupted by restart"


# ---------------- read endpoints ----------------

@app.get("/api/health", response_model=Health)
def health():
    return {"ok": True}


# the exposure sheet's columns: the same journey as web/src/lib/partSteps.ts, coarse (from files on disk + jobs)
SHEET_STEPS = ["Story", "Voice", "Plan", "Stills", "Final", "Thumb", "Post"]


def sheet_cells(slug: str, pdir: Path, p) -> list[str]:
    st = {f.alias or n: getattr(p.stages, n).status for n, f in Stages.model_fields.items()}
    ok = lambda *xs: all(st.get(x) == "done" for x in xs)  # noqa: E731
    steps = [  # (done, stages that can fail it, ready for review)
        (ok("prep"), ["prep"], False),
        ((pdir / "voice.mp3").is_file() and ok("import_check", "timing"), ["import_check", "timing"], False),
        (ok("shots", "validate"), ["shots", "validate"], False),
        (bool(p.approvals.stills.approved_at), [], (pdir / "stills-sheet.png").is_file()),
        (bool(p.approvals.final.approved_at), ["render", "audio", "finish"], ok("render", "audio", "finish")),
        (bool(p.thumbnail_choice), ["thumbnails"], False),
        (bool(p.posted.youtube or p.posted.instagram), [], False),
    ]
    cur = next((i for i, (done, _, _) in enumerate(steps) if not done), len(steps))
    out = []
    for i, (done, stages, review) in enumerate(steps):
        if done:
            out.append("done")
        elif i != cur:
            out.append("todo")
        elif any(st.get(x) == "failed" for x in stages):
            out.append("failed")
        elif busy(slug, pdir.name):
            out.append("running")
        else:
            out.append("review" if review else "current")
    return out


@app.get("/api/overview", response_model=Overview)
def overview():
    now = utcnow()
    months = [f"{now.year - (now.month - 1 - i < 0)}-{(now.month - 1 - i) % 12 + 1:02d}" for i in range(11, -1, -1)]
    per_month = {m: {"youtube": 0, "instagram": 0} for m in months}
    in_progress, waiting, disk, sheet = 0, [], {}, []
    for d in all_series():
        s = load_series(d / "series.json")
        disk[d.name] = du(d)
        cast = [f"cast:{c.id}" for c in s.cast if not c.approved_at and cast_render_current(d, c)]
        if cast:
            waiting.append({"slug": d.name, "part": None, "waiting": cast})
        for pid, p in parts_of(d):
            if p is None:
                continue
            in_progress += p.stages.finish.status != "done"
            if w := waiting_approvals(d / pid, p):
                waiting.append({"slug": d.name, "part": pid, "waiting": w})
            if not (p.posted.youtube or p.posted.instagram) and s.status != "archived":
                sheet.append({"slug": d.name, "series_title": s.title, "part": pid, "number": p.number,
                              "title": p.title, "cells": sheet_cells(d.name, d / pid, p)})
            for platform in ("youtube", "instagram"):
                post = getattr(p.posted, platform)
                if post and (m := post.posted_at.strftime("%Y-%m")) in per_month:
                    per_month[m][platform] += 1
    this = per_month[months[-1]]
    return {"kpi": {"series": len(disk), "parts_in_progress": in_progress, "waiting_for_approval": len(waiting),
                    "posted_this_month": this["youtube"] + this["instagram"]},
            "waiting": waiting,
            "sheet_steps": SHEET_STEPS,
            "sheet": sheet,
            "posts_per_month": [{"month": m, **per_month[m]} for m in months],
            "disk_usage": disk}


@app.get("/api/series", response_model=list[SeriesCard])
def series_list():
    cards = [{"slug": s.slug, "title": s.title, "created_at": s.created_at.isoformat(), "status": s.status,
              "part_count": len(s.parts), "cover": cover(d),
              "disk_usage": du(d), "posted": posted_counts(d)}
             for d in all_series() for s in [load_series(d / "series.json")]]
    return sorted(cards, key=lambda card: card["created_at"], reverse=True)


@app.get("/api/series/{slug}", response_model=SeriesDetail)
def series_detail(slug: str):
    d = series_path(slug)
    s = load_series(d / "series.json")
    return {"series": s.model_dump(mode="json"), "parts": [part_summary(d / pid, p) for pid, p in parts_of(d)],
            "cast": {c.id: cast_render(d, c) for c in s.cast}}


def cast_render(d: Path, c) -> dict:
    def url(f: Path):  # ?v: a re-render is a new url, not a cached old picture
        return f"{media_url(d.name, f.relative_to(d).as_posix())}?v={f.stat().st_mtime_ns}" if f.is_file() else None
    files = cast_files(d, c.id)
    return {"sheet": url(files["sheet"]), "idle": url(files["idle"]), "current": cast_render_current(d, c)}


@app.get("/api/series/{slug}/parts/{part}", response_model=PartDetail)
def part_detail(slug: str, part: str):
    pdir = part_path(slug, part)
    files = {f: (pdir / f).is_file() for f in PART_FILES}
    try:
        voice = probe_duration(pdir / "voice.mp3") if files["voice.mp3"] else None
    except StageError:
        voice = None
    qa, upload, story, tts = pdir / "qa.json", pdir / "upload.md", pdir / "story.md", pdir / "script-for-tts.txt"
    thumbs = sorted(f.name for f in (pdir / "thumbs").glob("thumb-*.png"))
    versions = {rel: (pdir / rel).stat().st_mtime_ns for rel in [*(f for f in PART_FILES if files[f]),
                                                                  *(f"thumbs/{t}" for t in thumbs)]}
    return {"part": part_json(pdir), "files": files, "versions": versions, "thumbs": thumbs,
            "qa": json.loads(qa.read_bytes()) if qa.is_file() else None,
            "upload_md": upload.read_text(encoding="utf-8") if upload.is_file() else None,
            "story_md": story.read_text(encoding="utf-8") if story.is_file() else None,
            "tts_script": tts.read_text(encoding="utf-8") if tts.is_file() else None,
            "voice_duration": voice, "frames_bytes": du(pdir / "frames"), "part_bytes": du(pdir),
            "busy": busy(slug, part)}


class StoryIssue(BaseModel):
    line: int | None  # story.md line, None: the whole story
    message: str


class StoryCheck(BaseModel):
    ok: bool  # no problems: ready for voice and the pipeline
    problems: list[StoryIssue]
    warnings: list[StoryIssue]
    words: int
    seconds: float  # estimated video duration (speech at the measured words/s + end card)


@app.get("/api/series/{slug}/parts/{part}/check-story", response_model=StoryCheck)
def check_story(slug: str, part: str):
    return storycheck.check_story(part_path(slug, part))


@app.get("/api/media/{slug}/{path:path}")
def media(slug: str, path: str):
    try:
        TypeAdapter(Slug).validate_python(slug)
    except ValidationError:
        raise HTTPException(404, "not found")
    root = (lib() / slug).resolve()
    f = (root / path).resolve()
    if not f.is_relative_to(root) or f.suffix.lower() not in MEDIA_TYPES or not f.is_file():
        raise HTTPException(404, "not found")
    # no-cache: the browser may keep a copy but checks it first, so a re-rendered file never shows stale
    return FileResponse(f, headers={"Cache-Control": "no-cache"})  # Starlette answers Range requests with 206


@app.get("/api/download/{slug}/{part}/final.mp4")
def download_final(slug: str, part: str):
    """Download endpoint used by the mobile QR handoff for an approved/final render."""
    pdir = part_path(slug, part)
    f = pdir / "final.mp4"
    if not f.is_file():
        raise HTTPException(404, "final video not found")
    filename = f"{slug}-{part}-instagram.mp4"
    return FileResponse(f, filename=filename, media_type="video/mp4", headers={"Cache-Control": "no-cache"})


@app.get("/api/mobile-download-url/{slug}/{part}")
def mobile_download_url(slug: str, part: str, request: Request):
    """Return a phone-reachable URL even when the desktop app was opened as localhost."""
    part_path(slug, part)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("192.0.2.1", 1))  # no packets are sent; this asks Windows for the LAN interface
        lan_ip = sock.getsockname()[0]
    except OSError:
        lan_ip = request.url.hostname or "127.0.0.1"
    finally:
        try:
            sock.close()
        except UnboundLocalError:
            pass
    port = request.url.port or int(os.environ.get("PORT", "8765"))
    host = f"{lan_ip}:{port}" if port not in (80, 443) else lan_ip
    return {"url": f"http://{host}/api/download/{urllib.parse.quote(slug)}/{urllib.parse.quote(part)}/final.mp4"}


# ---------------- actions ----------------

def busy(slug: str, part: str | None = None) -> str | None:
    """why this part (or, part None, any part of the series) can't be touched now, else None"""
    for j in list(JOBS):
        if j["status"] == "running" and j["slug"] == slug and part in (None, j["part"]):
            return f"job {j.get('tag', j['id'])} is running on {slug} {j['part']}"
    if part:
        pid = render_stage.lock_owner(lib() / slug / part)
        if pid:
            return f"a render is running on {slug} {part} (pid {pid})"
    return None


def check_free(slug: str, part: str | None = None) -> None:
    if why := busy(slug, part):
        raise HTTPException(409, f"{why}; wait for it or cancel it")


def cli_call(*argv: str) -> None:
    """Run one CLI command in-process: its gates and validation become 409s."""
    try:
        args = cli.build_parser().parse_args(argv)
        args.func(args)
    except (cli.UserError, ValidationError) as e:
        raise HTTPException(409, str(e))
    except SystemExit:  # argparse rejected an argument (already validated by the request model; defensive)
        raise HTTPException(409, f"invalid arguments: {' '.join(argv)}")


def part_action(slug: str, part: str, *argv: str) -> dict:
    pdir = part_path(slug, part)
    check_free(slug, part)
    cli_call(*argv)
    publish("part-changed", {"slug": slug, "part": part})
    return part_json(pdir)


@app.post("/api/series/{slug}/parts/{part}/approve/{what}", response_model=PartModel)
def approve(slug: str, part: str, what: Literal["stills", "test_render", "final"]):
    pdir = part_path(slug, part)
    if what not in waiting_approvals(pdir, load_part(pdir / "part.json")) \
            and not getattr(load_part(pdir / "part.json").approvals, what).approved_at:
        raise HTTPException(409, f"nothing to approve: {APPROVE_NEEDS[what]} not ready yet"
                                 + (" (finish not done)" if what == "final" else ""))
    return part_action(slug, part, "approve", slug, part, what)


class CastApproval(BaseModel):
    cast_id: str


@app.post("/api/series/{slug}/approve-cast", response_model=SeriesModel)
def approve_cast(slug: str, body: CastApproval):
    d = series_path(slug)
    check_free(slug)
    cli_call("approve-cast", slug, body.cast_id)  # refused until that member's render shows its current look
    publish("series-changed", {"slug": slug})
    return series_json(d)


class Thumbnail(BaseModel):
    n: Literal[1, 2, 3]


@app.post("/api/series/{slug}/parts/{part}/pick-thumbnail", response_model=PartModel)
def pick_thumbnail(slug: str, part: str, body: Thumbnail):
    return part_action(slug, part, "pick-thumbnail", slug, part, str(body.n))


class Posting(BaseModel):
    platform: Literal["youtube", "instagram"]
    url: str
    date: str | None = None  # YYYY-MM-DD, default today (UTC)
    force: bool = False


@app.post("/api/series/{slug}/parts/{part}/mark-posted", response_model=PartModel)
def mark_posted(slug: str, part: str, body: Posting):
    argv = ["mark-posted", slug, part, body.platform, f"--url={body.url}"]
    argv += [f"--date={body.date}"] * bool(body.date) + ["--force"] * body.force
    return part_action(slug, part, *argv)


class UploadText(BaseModel):
    text: str


@app.put("/api/series/{slug}/parts/{part}/upload.md", response_model=PartDetail)
def put_upload_md(slug: str, part: str, body: UploadText):
    pdir = part_path(slug, part)
    check_free(slug, part)
    atomic_write_text(pdir / "upload.md", body.text)
    publish("part-changed", {"slug": slug, "part": part})
    return part_detail(slug, part)


class NewSeries(BaseModel):
    slug: str
    title: str
    # same shape as series.json "cast" (approved_at is dropped: an imported look still needs approval);
    # shorthand: {"id", "name", "color"} for a plain top. Reference: web/public/cast-reference.json
    cast: list[dict] = []


def cast_member(i: int, c: dict) -> CastMember:
    """one imported cast entry -> CastMember, or a 409 naming the entry and the field"""
    c = package.cast_dict(c)
    try:
        return CastMember.model_validate(c)
    except ValidationError as e:
        err = e.errors()[0]
        where = ".".join(map(str, err["loc"])) or "entry"
        raise HTTPException(409, f"cast #{i + 1} ({c.get('id', 'no id')}): {where}: {err['msg']}")


@app.post("/api/series", response_model=SeriesModel)
def create_series(body: NewSeries):
    cast = [cast_member(i, c) for i, c in enumerate(body.cast)]  # all checked before anything is written
    if dupes := sorted({c.id for c in cast if sum(d.id == c.id for d in cast) > 1}):
        raise HTTPException(409, f"cast ids must be unique: {', '.join(dupes)}")
    if unknown := unknown_cast_props(cast, lib()):
        raise HTTPException(409, f"unknown prop {unknown[0]} (props: {', '.join(prop_kinds(lib()))})")
    if problems := cast_body_problems(cast, lib()):
        raise HTTPException(409, f"cast: {problems[0]}")
    cli_call("new-series", body.slug, f"--title={body.title}")
    d = series_path(body.slug)
    if cast:
        series = load_series(d / "series.json")
        series.cast = cast
        save_series(d / "series.json", series)
    publish("series-changed", {"slug": body.slug})
    return series_json(d)


class NewCast(BaseModel):
    cast: list[dict]  # same entries as NewSeries.cast


@app.post("/api/series/{slug}/cast", response_model=SeriesModel)
def add_cast(slug: str, body: NewCast):
    """append cast members to a series; never replaces one (an id already in the series is a 409)"""
    d = series_path(slug)
    check_free(slug)
    new = [cast_member(i, c) for i, c in enumerate(body.cast)]
    series = load_series(d / "series.json")
    ids = [c.id for c in series.cast + new]
    if dupes := sorted({i for i in ids if ids.count(i) > 1}):
        raise HTTPException(409, f"cast ids must be unique: {', '.join(dupes)}")
    if unknown := unknown_cast_props(new, lib()):
        raise HTTPException(409, f"unknown prop {unknown[0]} (props: {', '.join(prop_kinds(lib()))})")
    if problems := cast_body_problems(new, lib()):
        raise HTTPException(409, f"cast: {problems[0]}")
    series.cast = series.cast + new
    save_series(d / "series.json", series)
    publish("series-changed", {"slug": slug})
    return series_json(d)


def merge_cast(slug: str, entries: list[dict]) -> dict:
    """all or nothing: each entry replaces the member with its id (a new look clears that approval and makes its
    render stale until cast-sheet <slug> <id> runs again) or, a new id, is appended. Members not listed stay."""
    d = series_path(slug)
    check_free(slug)
    new = [cast_member(i, c) for i, c in enumerate(entries)]  # all checked before anything is written
    ids = [c.id for c in new]
    if dupes := sorted({i for i in ids if ids.count(i) > 1}):
        raise HTTPException(409, f"cast ids must be unique: {', '.join(dupes)}")
    if unknown := unknown_cast_props(new, lib()):
        raise HTTPException(409, f"unknown prop {unknown[0]} (props: {', '.join(prop_kinds(lib()))})")
    if problems := cast_body_problems(new, lib()):
        raise HTTPException(409, f"cast: {problems[0]}")
    series = load_series(d / "series.json")
    at = {c.id: i for i, c in enumerate(series.cast)}
    for c in new:
        if c.id in at:
            old = series.cast[at[c.id]]
            c.approved_at = old.approved_at if c.look() == old.look() else None
            series.cast[at[c.id]] = c
        else:
            series.cast.append(c)
    # written directly: save_series would restore a cleared approval (it only ever adds approvals)
    atomic_write_json(d / "series.json", series.model_dump(mode="json"))
    publish("series-changed", {"slug": slug})
    return series_json(d)


@app.put("/api/series/{slug}/cast", response_model=SeriesModel)
def import_cast(slug: str, body: NewCast):
    """mass edit (the cast panel's JSON import): update members by id, append new ids; see merge_cast"""
    return merge_cast(slug, body.cast)


@app.put("/api/series/{slug}/cast/{cast_id}", response_model=SeriesModel)
def edit_cast(slug: str, cast_id: str, body: dict):
    """replace one cast member (same entry shape as NewCast; the id stays); see merge_cast"""
    if not any(c.id == cast_id for c in load_series(series_path(slug) / "series.json").cast):
        raise HTTPException(404, f"cast id {cast_id!r} not in {slug}")
    return merge_cast(slug, [{**body, "id": cast_id}])


# ---------------- props (library/props.json, shared by every series) ----------------

class PropCatalog(BaseModel):
    builtin: list[BuiltinProp]
    custom: list[CustomProp]
    cleared: list[str] = []  # after a save: "<slug>/<cast id>" approvals cleared because the drawing changed


def prop_catalog(cleared=()) -> PropCatalog:
    return PropCatalog(builtin=list(get_args(BuiltinProp)), custom=load_props(lib()).props, cleared=list(cleared))


def check_no_jobs() -> None:
    """props.json feeds every render: no changes while one runs (its chunks would mix two drawings)"""
    if run := next((j for j in list(JOBS) if j["status"] == "running"), None):
        raise HTTPException(409, f"job {run.get('tag', run['id'])} is running on {run['slug']} {run['part']}; wait for it or cancel it")


@app.get("/api/props", response_model=PropCatalog)
def get_props():
    return prop_catalog()


@app.put("/api/props/{prop_id}", response_model=PropCatalog)
def put_prop(prop_id: Slug, body: CustomProp):
    if body.id != prop_id:
        raise HTTPException(409, f"body id {body.id!r} does not match {prop_id!r}")
    check_no_jobs()
    lib().mkdir(parents=True, exist_ok=True)
    cleared = save_prop(lib(), body)
    publish("props-changed", {"id": prop_id})
    for slug in {c.split("/")[0] for c in cleared}:
        publish("series-changed", {"slug": slug})
    return prop_catalog(cleared)


@app.delete("/api/props/{prop_id}", response_model=PropCatalog)
def remove_prop(prop_id: Slug):
    check_no_jobs()
    try:
        delete_prop(lib(), prop_id)
    except KeyError:
        raise HTTPException(404, f"no custom prop {prop_id!r}")
    except ValueError as e:
        raise HTTPException(409, str(e))
    publish("props-changed", {"id": prop_id})
    return prop_catalog()



# ---------------- creatures (library/creatures.json, shared by every series) ----------------

class BuiltinCreature(BaseModel):
    id: str
    rig: CreatureRig


class CreatureCatalog(BaseModel):
    builtin: list[BuiltinCreature]  # drawn by engine/page/creatures.js BUILTIN (the editor previews them from there)
    custom: list[CustomCreature]
    cleared: list[str] = []  # after a save: "<slug>/<cast id>" approvals cleared because the drawing changed


def creature_catalog(cleared=()) -> CreatureCatalog:
    return CreatureCatalog(builtin=[BuiltinCreature(id=k, rig=v[0]) for k, v in BUILTIN_CREATURES.items()],
                           custom=load_creatures(lib()).creatures, cleared=list(cleared))


@app.get("/api/creatures", response_model=CreatureCatalog)
def get_creatures():
    return creature_catalog()


@app.put("/api/creatures/{creature_id}", response_model=CreatureCatalog)
def put_creature(creature_id: Slug, body: CustomCreature):
    if body.id != creature_id:
        raise HTTPException(409, f"body id {body.id!r} does not match {creature_id!r}")
    check_no_jobs()  # creatures.json feeds every render, like props.json
    lib().mkdir(parents=True, exist_ok=True)
    cleared = save_creature(lib(), body)
    publish("creatures-changed", {"id": creature_id})
    for slug in {c.split("/")[0] for c in cleared}:
        publish("series-changed", {"slug": slug})
    return creature_catalog(cleared)


@app.delete("/api/creatures/{creature_id}", response_model=CreatureCatalog)
def remove_creature(creature_id: Slug):
    check_no_jobs()
    try:
        delete_creature(lib(), creature_id)
    except KeyError:
        raise HTTPException(404, f"no custom creature {creature_id!r}")
    except ValueError as e:
        raise HTTPException(409, str(e))
    publish("creatures-changed", {"id": creature_id})
    return creature_catalog()


# ---------------- wardrobe (library/wardrobe.json: clothing, hair, cosmetics, shared by every series) ----------------

class BuiltinWardrobeItem(BaseModel):
    id: str
    name: str
    slot: WardrobeSlotName


class WardrobeCatalog(BaseModel):
    builtin: list[BuiltinWardrobeItem]  # hand-drawn by engine/page/stickman.js: read only
    custom: list[WardrobeItem]
    cleared: list[str] = []  # after a save: "<slug>/<cast id>" approvals cleared because the drawing changed


def wardrobe_catalog(cleared=()) -> WardrobeCatalog:
    return WardrobeCatalog(builtin=[BuiltinWardrobeItem(id=k, slot=v[0], name=v[1]) for k, v in BUILTIN_WARDROBE.items()],
                           custom=load_wardrobe(lib()).wardrobe, cleared=list(cleared))


@app.get("/api/wardrobe", response_model=WardrobeCatalog)
def get_wardrobe():
    return wardrobe_catalog()


@app.put("/api/wardrobe/{item_id}", response_model=WardrobeCatalog)
def put_wardrobe_item(item_id: WardrobeId, body: WardrobeItem):
    if body.id != item_id:
        raise HTTPException(409, f"body id {body.id!r} does not match {item_id!r}")
    check_no_jobs()  # wardrobe.json feeds every render, like props.json
    lib().mkdir(parents=True, exist_ok=True)
    try:
        cleared = save_wardrobe_item(lib(), body)
    except ValueError as e:
        raise HTTPException(409, str(e))
    publish("wardrobe-changed", {"id": item_id})
    for slug in {c.split("/")[0] for c in cleared}:
        publish("series-changed", {"slug": slug})
    return wardrobe_catalog(cleared)


@app.delete("/api/wardrobe/{item_id}", response_model=WardrobeCatalog)
def remove_wardrobe_item(item_id: WardrobeId):
    check_no_jobs()
    try:
        delete_wardrobe_item(lib(), item_id)
    except KeyError:
        raise HTTPException(404, f"no custom wardrobe item {item_id!r}")
    except ValueError as e:
        raise HTTPException(409, str(e))
    publish("wardrobe-changed", {"id": item_id})
    return wardrobe_catalog()


# ---------------- actions (library/actions.json: custom moves, shared by every series) ----------------

class ActionCatalog(BaseModel):
    builtin: list[str]  # code in the engine (schemas ACTIONS); @do may ask for those with the "do" trait
    do: list[str]       # the built-ins @do accepts
    custom: list[CustomAction]


def action_catalog() -> ActionCatalog:
    return ActionCatalog(builtin=list(ACTIONS), do=sorted(actions_with("do")), custom=load_actions(lib()).actions)


@app.get("/api/actions", response_model=ActionCatalog)
def get_actions():
    return action_catalog()


@app.put("/api/actions/{action_id}", response_model=ActionCatalog)
def put_action(action_id: Slug, body: CustomAction):
    if body.id != action_id:
        raise HTTPException(409, f"body id {body.id!r} does not match {action_id!r}")
    check_no_jobs()  # actions.json feeds every render, like props.json
    lib().mkdir(parents=True, exist_ok=True)
    save_action(lib(), body)
    publish("actions-changed", {"id": action_id})
    return action_catalog()


@app.delete("/api/actions/{action_id}", response_model=ActionCatalog)
def remove_action(action_id: Slug):
    check_no_jobs()
    try:
        delete_action(lib(), action_id)
    except KeyError:
        raise HTTPException(404, f"no custom action {action_id!r}")
    except ValueError as e:
        raise HTTPException(409, str(e))
    publish("actions-changed", {"id": action_id})
    return action_catalog()


# ---------------- sets (library/sets.json, shared by every series) ----------------

class BuiltinSet(BaseModel):
    id: str
    kind: SetKind


class SetCatalog(BaseModel):
    builtin: list[BuiltinSet]
    custom: list[CustomSet]


def set_catalog() -> SetCatalog:
    return SetCatalog(builtin=[BuiltinSet(id=k, kind=v) for k, v in BUILTIN_SETS.items()], custom=load_sets(lib()).sets)


@app.get("/api/sets", response_model=SetCatalog)
def get_sets():
    return set_catalog()


@app.put("/api/sets/{set_id}", response_model=SetCatalog)
def put_set(set_id: Slug, body: CustomSet):
    if body.id != set_id:
        raise HTTPException(409, f"body id {body.id!r} does not match {set_id!r}")
    check_no_jobs()  # sets.json feeds every render, like props.json
    lib().mkdir(parents=True, exist_ok=True)
    save_set(lib(), body)
    publish("sets-changed", {"id": set_id})
    return set_catalog()


@app.delete("/api/sets/{set_id}", response_model=SetCatalog)
def remove_set(set_id: Slug):
    check_no_jobs()
    try:
        delete_set(lib(), set_id)
    except KeyError:
        raise HTTPException(404, f"no custom set {set_id!r}")
    except ValueError as e:
        raise HTTPException(409, str(e))
    publish("sets-changed", {"id": set_id})
    return set_catalog()


# ---------------- world objects (library/objects.json, shared by every series) ----------------

class WorldObjectCatalog(BaseModel):
    objects: list[WorldObject]


def object_catalog() -> WorldObjectCatalog:
    return WorldObjectCatalog(objects=load_objects(lib()).objects)


@app.get("/api/objects", response_model=WorldObjectCatalog)
def get_objects():
    return object_catalog()


@app.put("/api/objects/{object_id}", response_model=WorldObjectCatalog)
def put_object(object_id: Slug, body: WorldObject):
    if body.id != object_id:
        raise HTTPException(409, f"body id {body.id!r} does not match {object_id!r}")
    check_no_jobs()
    lib().mkdir(parents=True, exist_ok=True)
    save_object(lib(), body)
    publish("objects-changed", {"id": object_id})
    return object_catalog()


@app.delete("/api/objects/{object_id}", response_model=WorldObjectCatalog)
def remove_object(object_id: Slug):
    check_no_jobs()
    try:
        delete_object(lib(), object_id)
    except KeyError:
        raise HTTPException(404, f"no world object {object_id!r}")
    publish("objects-changed", {"id": object_id})
    return object_catalog()

# ---------------- sounds (library/sfx/: audio files + sfx.json, the @sfx directive) ----------------

MAX_SFX_BYTES = 20 * 2**20


class SfxView(sfx_lib.SfxEntry):
    missing: bool = False       # the file is not in library/sfx/
    users: list[str] = []       # "<slug>/<part>" whose story.md uses it


class SfxCatalog(BaseModel):
    sfx: list[SfxView]
    warnings: list[str]


def sfx_catalog() -> SfxCatalog:
    d = sfx_lib.sfx_dir(lib())
    return SfxCatalog(sfx=[SfxView(**x.model_dump(), missing=not (d / x.file).is_file(), users=sfx_lib.sfx_users(lib(), x.id))
                           for x in sfx_lib.load_sfx(lib()).sfx], warnings=sfx_lib.missing_files(lib()))


def sfx_entry(sfx_id: str) -> sfx_lib.SfxEntry:
    if not (e := sfx_lib.by_id(lib()).get(sfx_id)):
        raise HTTPException(404, f"no sound {sfx_id!r}")
    return e


@app.get("/api/sfx", response_model=SfxCatalog)
def get_sfx():
    return sfx_catalog()


@app.put("/api/sfx/{sfx_id}", response_model=SfxCatalog)
def put_sfx(sfx_id: str, body: sfx_lib.SfxEntry):
    """add or change a sound's entry (name, purpose, tags, anchor, volume, file name)"""
    if body.id != sfx_id:
        raise HTTPException(409, f"body id {body.id!r} does not match {sfx_id!r}")
    check_no_jobs()  # sfx.json feeds the audio stage
    cur = sfx_lib.load_sfx(lib())
    sfx_lib.save_sfx(lib(), sfx_lib.SfxLibrary(sfx=[body if x.id == sfx_id else x for x in cur.sfx]
                                               + ([] if any(x.id == sfx_id for x in cur.sfx) else [body])))
    publish("sfx-changed", {"id": sfx_id})
    return sfx_catalog()


@app.put("/api/sfx/{sfx_id}/audio", response_model=SfxCatalog)
async def put_sfx_audio(sfx_id: str, request: Request, name: str):
    """Raw audio body (mp3 / wav / ogg / m4a) saved as library/sfx/<name>; a new id gets an entry with defaults
    (anchor start, volume 0.8) to edit after."""
    try:
        TypeAdapter(sfx_lib.SfxId).validate_python(sfx_id)
        new = sfx_lib.SfxEntry(id=sfx_id, file=Path(name).name, name=Path(name).stem[:60] or sfx_id)
    except ValidationError as e:
        raise HTTPException(409, f"bad id or file name: {e.errors()[0]['msg']}")
    if Path(new.file).suffix.lower() not in sfx_lib.AUDIO_TYPES:
        raise HTTPException(415, f"not a sound file ({', '.join(sorted(sfx_lib.AUDIO_TYPES))})")
    check_no_jobs()
    data = await request.body()
    if len(data) > MAX_SFX_BYTES:
        raise HTTPException(413, f"over {MAX_SFX_BYTES // 2**20} MB")
    d = sfx_lib.sfx_dir(lib())
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".upload{Path(new.file).suffix}"
    tmp.write_bytes(data)
    try:
        probe_duration(tmp)  # ffprobe must read it as audio
    except StageError:
        tmp.unlink(missing_ok=True)
        raise HTTPException(415, "ffprobe could not read it as audio")
    os.replace(tmp, d / new.file)
    cur = sfx_lib.load_sfx(lib())
    old = next((x for x in cur.sfx if x.id == sfx_id), None)
    entry = old.model_copy(update={"file": new.file}) if old else new
    sfx_lib.save_sfx(lib(), sfx_lib.SfxLibrary(sfx=[entry if x.id == sfx_id else x for x in cur.sfx] + ([] if old else [entry])))
    publish("sfx-changed", {"id": sfx_id})
    return sfx_catalog()


@app.delete("/api/sfx/{sfx_id}", response_model=SfxCatalog)
def remove_sfx(sfx_id: str):
    """the entry and its file; refused while any story.md uses it"""
    e = sfx_entry(sfx_id)
    check_no_jobs()
    if users := sfx_lib.sfx_users(lib(), sfx_id):
        raise HTTPException(409, f"{sfx_id} is used by {', '.join(users)}: take its @sfx lines out first")
    cur = sfx_lib.load_sfx(lib())
    sfx_lib.save_sfx(lib(), sfx_lib.SfxLibrary(sfx=[x for x in cur.sfx if x.id != sfx_id]))
    if not any(x.file == e.file for x in cur.sfx if x.id != sfx_id):
        (sfx_lib.sfx_dir(lib()) / e.file).unlink(missing_ok=True)
    publish("sfx-changed", {"id": sfx_id})
    return sfx_catalog()


@app.get("/api/sfx/{sfx_id}/audio")
def sfx_audio(sfx_id: str):
    f = sfx_lib.sfx_dir(lib()) / sfx_entry(sfx_id).file
    if not f.is_file():
        raise HTTPException(404, f"{f.name} is missing from library/sfx/")
    return FileResponse(f, headers={"Cache-Control": "no-cache"})


class SfxSuggestion(BaseModel):
    line: int       # the narration line "@sfx <id>" goes above
    text: str       # that line, to check it has not moved
    id: str
    reason: str = ""
    at: float = 0.0  # seconds: when the sound starts


class SfxSuggestions(BaseModel):
    suggestions: list[SfxSuggestion]
    written: int    # @sfx lines already in story.md
    max: int
    timed: bool     # line times from the recorded voice (else estimated from the word count)


class SfxDecision(SfxSuggestion):
    accept: bool


def rejected_file(pdir: Path) -> Path:
    return pdir / "sfx-rejected.json"


@app.get("/api/series/{slug}/parts/{part}/sfx-suggestions", response_model=SfxSuggestions)
def sfx_suggestions(slug: str, part: str):
    pdir = part_path(slug, part)
    md = (pdir / "story.md").read_text(encoding="utf-8") if (pdir / "story.md").is_file() else ""
    ph = pdir / "phrases.json"
    times = sfx_lib.line_times(md, json.loads(ph.read_bytes())["words"]) if ph.is_file() else None
    rej = set(json.loads(rejected_file(pdir).read_bytes())) if rejected_file(pdir).is_file() else set()
    entries = sfx_lib.by_id(lib())
    out = sfx_lib.suggest(md, entries, times or sfx_lib.estimated_times(md), load_part(pdir / "part.json").number == 1,
                          rej, lambda e: sfx_lib.clip_seconds(lib(), e))
    return SfxSuggestions(suggestions=out, written=len(sfx_lib.directives(md)), max=sfx_lib.MAX_PER_PART, timed=times is not None)


@app.post("/api/series/{slug}/parts/{part}/sfx-suggestions", response_model=SfxSuggestions)
def decide_sfx(slug: str, part: str, body: SfxDecision):
    """accept: "@sfx <id>" is written into story.md above the line; reject: never suggested again for that line"""
    pdir = part_path(slug, part)
    check_free(slug, part)
    if body.accept:
        sfx_entry(body.id)
        try:
            write_story(pdir, sfx_lib.insert((pdir / "story.md").read_text(encoding="utf-8"), body.line, body.text, body.id))
        except ValueError as e:
            raise HTTPException(409, str(e))
    else:
        f = rejected_file(pdir)
        rej = json.loads(f.read_bytes()) if f.is_file() else []
        atomic_write_json(f, sorted({*rej, f"{body.id}|{body.text.strip()}"}))
    publish("part-changed", {"slug": slug, "part": part})
    return sfx_suggestions(slug, part)


# ---------------- story packages (docs/story-package.md): one paste -> assets, cast, series, parts ----------------

class PackageText(BaseModel):
    text: str


class PackageIssue(BaseModel):
    section: str  # META, PROPS ... CAST, "PART 2 SCRIPT", "PART 2 VOICE", START, END
    line: int | None  # in the pasted text
    message: str


class PackageItem(BaseModel):
    id: str
    name: str
    data: dict  # the item as it will be saved (props.json ... series.json cast entry): the review page previews it


class PackagePart(BaseModel):
    number: int
    title: str
    words: int
    story: str  # story.md
    voice: str  # script-for-tts.txt


class PackageSeries(BaseModel):
    title: str
    slug: str
    was: str | None  # the slug it asked for, when that was taken


class PackageResult(BaseModel):
    ok: bool
    series: PackageSeries | None
    props: list[PackageItem]
    sets: list[PackageItem]
    creatures: list[PackageItem]
    actions: list[PackageItem]
    wardrobe: list[PackageItem] = []
    cast: list[PackageItem]
    renames: dict[str, dict[str, str]]  # props / sets / creatures / actions: package id -> imported id
    parts: list[PackagePart]
    warnings: list[PackageIssue]
    errors: list[PackageIssue]


@app.post("/api/packages/validate", response_model=PackageResult)
def validate_package(body: PackageText):
    """dry run: what the package would create, its warnings and errors (section + pasted-text line). Writes nothing."""
    return package.summary(package.parse(body.text, lib()))


@app.post("/api/packages/import", response_model=PackageResult)
def import_package(body: PackageText):
    """all or nothing: new assets, then the series with its cast and parts (story.md + script-for-tts.txt).
    Never overwrites: a clashing id or slug gets a suffix. 409 when the package has errors (validate lists them)."""
    check_no_jobs()  # it writes the library's item files, which feed every render
    try:
        r = package.import_package(body.text, lib())
    except package.PackageError as e:
        raise HTTPException(409, f"package has errors, nothing was written: {e}")
    for kind in ("props", "sets", "creatures", "actions", "wardrobe"):
        publish(f"{kind}-changed", {"id": None})
    publish("series-changed", {"slug": r["series"]["slug"]})
    return package.summary(r)


class NewPart(BaseModel):
    title: str | None = None
    story: str | None = None  # story.md body; default: the CLI's "# <title>" stub


def write_story(pdir: Path, text: str) -> None:
    """story.md is user-owned, so not via io.atomic_write_text (it refuses PROTECTED names on purpose)"""
    tmp = pdir / ".story.md.upload.tmp"
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, pdir / "story.md")


@app.put("/api/series/{slug}/parts/{part}/story.md", response_model=PartDetail)
def put_story_md(slug: str, part: str, body: UploadText):
    """replace story.md; the stages after it see the change on their next run (their inputs hash differently)"""
    pdir = part_path(slug, part)
    check_free(slug, part)
    write_story(pdir, body.text)
    publish("part-changed", {"slug": slug, "part": part})
    return part_detail(slug, part)


@app.post("/api/series/{slug}/parts", response_model=PartDetail)
def create_part(slug: str, body: NewPart):
    d = series_path(slug)
    check_free(slug)
    cli_call("new-part", slug, *([f"--title={body.title}"] if body.title else []))
    part = load_series(d / "series.json").parts[-1]
    if body.story is not None:
        write_story(d / part, body.story)
    publish("series-changed", {"slug": slug})
    return part_detail(slug, part)


@app.delete("/api/series/{slug}", response_model=Health)
def delete_series(slug: str):
    """the whole series folder; refused while a job is queued or running on any of its parts, or a render runs"""
    series_path(slug)
    check_free(slug)
    if any(j["status"] == "queued" and j["slug"] == slug for j in list(JOBS)):
        raise HTTPException(409, f"a job is queued on {slug}; cancel it first")
    cli_call("delete-series", slug, "--yes")
    publish("series-changed", {"slug": slug})
    return {"ok": True}


@app.delete("/api/series/{slug}/parts/{part}", response_model=SeriesModel)
def delete_part(slug: str, part: str):
    """the whole part folder and its series.json entry; refused while a job or render runs on it"""
    d = series_path(slug)
    part_path(slug, part)
    check_free(slug, part)
    if any(j["status"] == "queued" and j["slug"] == slug and j["part"] == part for j in list(JOBS)):
        raise HTTPException(409, f"a job is queued on {slug} {part}; cancel it first")
    cli_call("delete-part", slug, part, "--yes")
    publish("series-changed", {"slug": slug})
    return series_json(d)


MAX_VOICE_BYTES = 100 * 2**20


@app.put("/api/series/{slug}/parts/{part}/voice.mp3", response_model=PartDetail)
async def put_voice(slug: str, part: str, request: Request, replace: bool = False):
    """Raw mp3 body (no multipart dep). voice.mp3 is protected: replacing it needs ?replace=true."""
    pdir = part_path(slug, part)
    check_free(slug, part)
    if (pdir / "voice.mp3").exists() and not replace:
        raise HTTPException(409, "voice.mp3 already exists; pass replace=true to overwrite it")
    data = await request.body()
    if len(data) > MAX_VOICE_BYTES:
        raise HTTPException(413, f"voice.mp3 is over {MAX_VOICE_BYTES // 2**20} MB")
    if not (data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)):
        raise HTTPException(415, "not an mp3 file (no ID3 tag or MPEG frame header)")
    # user-owned file, so not via io.atomic_write_bytes (it refuses PROTECTED names on purpose)
    tmp = pdir / ".voice.mp3.upload.tmp"
    tmp.write_bytes(data)
    os.replace(tmp, pdir / "voice.mp3")
    publish("part-changed", {"slug": slug, "part": part})
    return part_detail(slug, part)


@app.post("/api/series/{slug}/parts/{part}/clean-frames", response_model=PartModel)
def clean_frames(slug: str, part: str):
    return part_action(slug, part, "clean-frames", slug, part)


# ---------------- jobs ----------------
# One in-process worker. Jobs persist to library/.jobs.json (atomic) on every state change, so a restart resumes the
# queue (see startup). Output lines are saved with them, not streamed to disk line by line.

JOBS: list[dict] = []
_procs: dict[int, subprocess.Popen] = {}
_cv = threading.Condition()
_ids = itertools.count(1)
_worker: threading.Thread | None = None


def series_code(title: str, fallback: str = "series") -> str:
    """A readable uppercase code from a series title, e.g. TRWDWOTO."""
    words = re.findall(r"[A-Za-z]+", title)
    code = "".join(word[0] for word in words).upper()
    if not code:
        code = "".join(re.findall(r"[A-Za-z]", fallback)).upper()
    return code or "SERIES"


def job_tag(slug: str, part: str) -> str:
    """Stable human-facing tag: series initials + three-digit part number."""
    d = series_path(slug)
    title = load_series(d / "series.json").title
    number = load_part(d / part / "part.json").number
    return f"{series_code(title, slug)}{number:03d}"


class JobRequest(BaseModel):
    slug: str
    part: str
    steps: list[str]  # CLI commands without slug/part, e.g. "run --stage audio", "render-stills", "render --force"


def step_argv(slug: str, part: str, step: str) -> list[str]:
    """CLI subprocess for one step. Raises ValueError for anything but the job commands."""
    words = shlex.split(step)
    if not words or words[0] not in JOB_COMMANDS:
        raise ValueError(f"step {step!r}: must start with one of {', '.join(sorted(JOB_COMMANDS))}")
    argv = [words[0], slug] + ([part] if words[0] != "cast-sheet" else []) + words[1:]
    try:
        cli.build_parser().parse_args(argv)  # validate stage names and flags now, not halfway through the job
    except SystemExit:
        raise ValueError(f"step {step!r}: invalid arguments")
    return [sys.executable, "-m", "pipeline.scribble.cli", *argv, f"--library={lib().resolve()}"]


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def public(job: dict) -> dict:
    return {**{k: v for k, v in job.items() if k not in ("argv", "pid")}, "output": list(job["output"])}


_save_lock = threading.Lock()


def jobs_file() -> Path:
    return lib() / ".jobs.json"


def save_jobs() -> None:
    with _save_lock:
        jobs = [{**public(j), "argv": j["argv"], "pid": j.get("pid")} for j in list(JOBS)]
        jobs_file().parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(jobs_file(), jobs)


def load_jobs() -> list[str]:
    """library/.jobs.json -> JOBS. A job left running by the last API process failed ("interrupted by restart"); its
    process, if it still runs (job steps start in their own process group, so they can outlive the API), is stopped:
    no one follows its output any more. Queued jobs stay queued and the worker picks them up. Returns notes."""
    global _ids
    f, notes = jobs_file(), []
    try:
        saved = json.loads(f.read_bytes()) if f.is_file() else []
    except (OSError, ValueError) as e:
        return [f"ignoring unreadable {f.name}: {e}"]
    for j in saved:
        # Jobs written before tags were introduced are still valid history. Derive their tag once
        # from the current series title and keep it in the persisted record from then on.
        if "tag" not in j:
            try:
                j["tag"] = job_tag(j["slug"], j["part"])
            except (HTTPException, OSError, ValueError, KeyError):
                # A finished job can outlive a deleted series; preserve that history with a
                # deterministic slug-based fallback rather than failing API startup.
                number = int(j["part"].removeprefix("part-"))
                j["tag"] = f"{series_code(j['slug'])}{number:03d}"
        j["output"] = deque(j.get("output", []), maxlen=OUTPUT_LINES)
        if j["status"] == "running":
            pid = j.get("pid")
            if pid and render_stage.pid_alive(pid) and render_stage.RUNNER_PROCESS.match(
                    render_stage.process_name(pid) or ""):
                render_stage.kill_pid_tree(pid)
                notes.append(f"job {j['id']}: stopped its orphaned process {pid}")
            j.update(status="failed", error="interrupted by restart", finished_at=_iso(utcnow()), pid=None)
            notes.append(f"job {j['id']} ({j['slug']} {j['part']}) was running: marked failed (interrupted by restart)")
    with _cv:
        JOBS[:] = saved
        _ids = itertools.count(max((j["id"] for j in saved), default=0) + 1)
        if any(j["status"] == "queued" for j in saved):
            notes.append(f"resuming {sum(j['status'] == 'queued' for j in saved)} queued job(s)")
            _start_worker()
            _cv.notify()
    if saved:
        save_jobs()
    return notes


# library/settings.json held third-party AI provider settings and keys; AI help is copy/paste now, except captions
# (Gemini, keyed in Settings: write_captions)
OLD_AI_KEYS = {"provider", "base_url", "model", "omniroute_model", "gemini_model", "openrouter_model",
               "api_key", "gemini_api_key", "openrouter_api_key"}


def drop_ai_settings() -> list[str]:
    """remove the old provider keys from settings.json (the file too, when nothing else is left); never fails startup"""
    f = lib() / "settings.json"
    try:
        s = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(s, dict) or not OLD_AI_KEYS & s.keys():
            return []
        rest = {k: v for k, v in s.items() if k not in OLD_AI_KEYS}
        atomic_write_json(f, rest) if rest else f.unlink()
        return ["settings.json: old AI provider settings and keys removed"]
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        return [f"settings.json: could not clean up old AI settings ({e})"]


class Socials(BaseModel):
    youtube: str = Field("", max_length=60)
    instagram: str = Field("", max_length=60)
    facebook: str = Field("", max_length=60)


class Settings(BaseModel):
    render_workers: Literal["auto"] | int = Field("auto", description="'auto' or 1..16 parallel browsers per render")
    force_software_gl: bool = False
    socials: Socials = Field(default_factory=Socials, description="handles on every part's closing 'Follow for more' "
                                                                  "screen (empty: left off)")
    brand_tags: str = Field("", max_length=300, description="hashtags every caption carries, e.g. #scribblefactory")
    caption_model: Literal[settings.FREE_GEMINI] = Field(settings.FREE_GEMINI[0], description=(
        "free Gemini model captions try first; busy or out of quota, the next free one answers"))


class Machine(BaseModel):
    cpu_threads: int
    ram_gb: float | None
    gpu: str | None  # from the newest rendered chunk; None before any render
    recommended_workers: int


class PcExample(BaseModel):
    pc: str
    workers: int


class SettingsView(BaseModel):
    settings: Settings
    workers_now: int  # what the next render uses
    machine: Machine
    examples: list[PcExample]
    gemini_key_last4: str  # '' when none is set; the key itself never leaves the server
    caption_models: list[str]  # the free Gemini models, in fallback order


# typical machines -> what auto picks on them (same formula as this PC's recommendation)
PC_EXAMPLES = [("Laptop, 4 cores, 8 GB, Intel UHD", 8, 8, "Intel(R) UHD Graphics"),
               ("Desktop, 6 cores, 16 GB, GTX 1660", 12, 16, "NVIDIA GeForce GTX 1660"),
               ("Desktop, 8 cores, 32 GB, RTX 3070", 16, 32, "NVIDIA GeForce RTX 3070"),
               ("Workstation, 16 cores, 64 GB, RTX 4090", 32, 64, "NVIDIA GeForce RTX 4090")]


def settings_view() -> dict:
    return {"settings": settings.load(lib()), "workers_now": settings.render_workers(lib()),
            "machine": settings.machine(lib()),
            "examples": [{"pc": pc, "workers": settings.recommend(t, r, g)} for pc, t, r, g in PC_EXAMPLES],
            "gemini_key_last4": settings.gemini_key(lib())[-4:], "caption_models": list(settings.FREE_GEMINI)}


@app.get("/api/settings", response_model=SettingsView)
def get_settings():
    return settings_view()


@app.put("/api/settings", response_model=SettingsView)
def put_settings(body: Settings):
    """applies to the next render job; a running one keeps its workers. Handles: the next finish run."""
    w = body.render_workers
    if w != "auto" and not 1 <= w <= settings.MAX_WORKERS:
        raise HTTPException(422, f"render_workers must be 'auto' or 1 to {settings.MAX_WORKERS}")
    f = settings.path(lib())
    try:
        old = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    atomic_write_json(f, {**(old if isinstance(old, dict) else {}), **body.model_dump()})  # keep keys we don't know
    return settings_view()


# ---------------- captions: Gemini, the one task an outside AI does here ----------------
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
GEMINI_NEXT = {404, 429, 503}  # gone, out of quota, high demand: the next free model tries


class CaptionRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=30000)


class Captions(BaseModel):
    youtube_title: str
    youtube_description: str  # with its hashtags
    youtube_pinned_comment: str
    instagram_caption: str  # the whole post: hook, story, question, hashtags


class GeminiKey(BaseModel):
    key: str = Field("", max_length=200)  # empty: remove it


@app.put("/api/settings/gemini-key", response_model=SettingsView)
def put_gemini_key(body: GeminiKey):
    """write-only: GET /api/settings shows only its last 4 characters"""
    f = settings.path(lib())
    try:
        old = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    s = {k: v for k, v in (old if isinstance(old, dict) else {}).items() if k != "gemini_key"}
    atomic_write_json(f, {**s, "gemini_key": body.key.strip()} if body.key.strip() else s)
    return settings_view()


@app.post("/api/captions", response_model=Captions)
def write_captions(body: CaptionRequest):
    """YouTube and Instagram captions from Gemini: the key from Settings (else $GEMINI_API_KEY). The model chosen in
    Settings first (else $GEMINI_MODEL); busy, out of quota or gone, the other free models in turn"""
    key = settings.gemini_key(lib()) or os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(409, "No Gemini API key: add it in Settings")
    first = os.environ.get("GEMINI_MODEL", "").strip() or settings.load(lib())["caption_model"]
    schema = {"type": "OBJECT", "properties": {k: {"type": "STRING"} for k in Captions.model_fields},
              "required": list(Captions.model_fields), "propertyOrdering": list(Captions.model_fields)}
    data = json.dumps({"contents": [{"role": "user", "parts": [{"text": body.prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema}}).encode()
    for model in dict.fromkeys([first, *settings.FREE_GEMINI]):
        req = urllib.request.Request(GEMINI_URL.format(urllib.parse.quote(model, safe="")), method="POST", data=data,
                                     headers={"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out = json.load(r)
            break
        except urllib.error.HTTPError as e:
            try:
                msg = json.load(e)["error"]["message"]
            except (ValueError, KeyError, TypeError, OSError):
                msg = f"HTTP {e.code}"
            if e.code not in GEMINI_NEXT:
                raise HTTPException(502, f"Gemini ({model}): {msg}")
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise HTTPException(502, f"Gemini ({model}) did not answer: {e}")
    else:
        raise HTTPException(502, f"Gemini: every free model is busy or out of quota, try again later ({model}: {msg})")
    try:
        parts = out["candidates"][0]["content"]["parts"]
        return Captions.model_validate_json("".join(p.get("text", "") for p in parts if not p.get("thought")))
    except (KeyError, IndexError, TypeError, AttributeError, ValidationError):
        raise HTTPException(502, f"Gemini ({model}) sent no usable captions: try again")


def startup() -> None:
    """API start: jobs from .jobs.json, then every part's stuck stages and stale render locks (orphan workers)."""
    notes = load_jobs() + drop_ai_settings()
    for d in all_series():
        for pid, p in parts_of(d):
            if p is None:
                continue
            notes += [f"{d.name} {pid}: {n}" for n in render_stage.clear_stale_lock(d / pid)]
            notes += [f"{d.name} {pid}: {n} was left running: marked failed (interrupted)" for n in recover_stuck(d / pid)]
    for n in notes:
        print(f"startup: {n}", flush=True)


@app.post("/api/jobs", response_model=Job)
def submit_job(body: JobRequest):
    part_path(body.slug, body.part)
    if not body.steps:
        raise HTTPException(409, "steps is empty")
    try:
        argv = [step_argv(body.slug, body.part, s) for s in body.steps]
    except ValueError as e:
        raise HTTPException(409, str(e))
    job = {"id": next(_ids), "tag": job_tag(body.slug, body.part), "slug": body.slug, "part": body.part,
           "steps": body.steps, "argv": argv,
           "current_step": None, "status": "queued", "queued_at": _iso(utcnow()), "started_at": None,
           "finished_at": None, "returncode": None, "output": deque(maxlen=OUTPUT_LINES), "error": None, "pid": None}
    with _cv:
        JOBS.append(job)
        _start_worker()
        _cv.notify()
    save_jobs()
    publish("job-queued", public(job))
    return public(job)


@app.get("/api/jobs", response_model=list[Job])
def list_jobs():
    return [public(j) for j in list(JOBS)]


class JobCleanup(BaseModel):
    before: date | None = None  # delete finished jobs that finished before this day (UTC); None: every finished job


@app.post("/api/jobs/cleanup", response_model=list[Job])
def cleanup_jobs(body: JobCleanup):
    """delete job history; queued and running jobs are never touched. Returns the jobs that are left."""
    cut = body.before.isoformat() if body.before else None
    with _cv:
        gone = [j for j in JOBS if j["status"] not in ("queued", "running")
                and (cut is None or (j["finished_at"] or j["queued_at"])[:10] < cut)]
        for j in gone:
            JOBS.remove(j)
    save_jobs()
    publish("jobs-cleaned", {"removed": len(gone)})
    return list_jobs()


@app.delete("/api/jobs/{job_id}", response_model=Job)
def cancel_job(job_id: int):
    with _cv:
        job = next((j for j in JOBS if j["id"] == job_id), None)
        if job is None:
            raise HTTPException(404, f"job {job_id} not found")
        if job["status"] not in ("queued", "running"):
            raise HTTPException(409, f"job {job_id} already {job['status']}")
        was_queued = job["status"] == "queued"
        job["status"] = "cancelled"
        proc = _procs.get(job_id)
    if proc:
        render_stage.kill_tree(proc)  # the worker sees the exit and finishes the job as cancelled
    elif was_queued:
        job["finished_at"] = _iso(utcnow())
        publish("job-finished", _brief(job))
    save_jobs()
    return public(job)


def _brief(job: dict) -> dict:
    return {k: job[k] for k in ("id", "slug", "part", "status", "current_step", "returncode", "finished_at")}


def _start_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_work, name="jobs", daemon=True)
        _worker.start()


def _work() -> None:
    while True:
        with _cv:
            while not (job := next((j for j in JOBS if j["status"] == "queued"), None)):
                _cv.wait()
            job["status"], job["started_at"] = "running", _iso(utcnow())
        save_jobs()
        publish("job-started", _brief(job))
        _run(job)
        job["finished_at"], job["pid"] = _iso(utcnow()), None
        publish("job-finished", _brief(job))
        with _cv:  # keep the last KEEP_JOBS finished jobs
            done = [j for j in JOBS if j["status"] not in ("queued", "running")]
            for j in done[:-KEEP_JOBS]:
                JOBS.remove(j)
        save_jobs()


def _run(job: dict) -> None:
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    for i, argv in enumerate(job["argv"]):
        job["current_step"] = i
        publish("job-step", {"id": job["id"], "step": i, "command": job["steps"][i]})
        with _cv:
            if job["status"] == "cancelled":
                return
            proc = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", **render_stage.GROUP)
            _procs[job["id"]] = proc
            job["pid"] = proc.pid
        save_jobs()
        for line in proc.stdout:
            line = line.rstrip("\r\n")
            job["output"].append(line)
            publish("job-output", {"id": job["id"], "step": i, "line": line})
        proc.wait()
        with _cv:
            _procs.pop(job["id"], None)
        job["returncode"] = proc.returncode
        if job["status"] == "cancelled" and job["part"]:  # killed: its stage never got to say so, nor drop its lock
            d = lib() / job["slug"] / job["part"]
            notes = render_stage.clear_stale_lock(d) + [f"{n}: cancelled, marked failed" for n in recover_stuck(d)]
            job["output"] += notes
        publish("part-changed", {"slug": job["slug"], "part": job["part"]})
        publish("series-changed", {"slug": job["slug"]})
        if job["status"] == "cancelled":
            return
        if proc.returncode != 0:
            job["status"] = "failed"
            return
    job["status"] = "done"


# ---------------- live events ----------------

_subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()


def publish(event: str, data: dict) -> None:
    """Send to every SSE client. Safe from any thread."""
    msg = {"event": event, "data": json.dumps(data)}
    for loop, q in list(_subscribers):
        with contextlib.suppress(RuntimeError):  # that client's loop is gone
            loop.call_soon_threadsafe(q.put_nowait, msg)


@app.get("/api/events")
async def events():
    sub = (asyncio.get_running_loop(), asyncio.Queue())

    async def stream():
        _subscribers.add(sub)
        try:
            yield {"event": "hello", "data": "{}"}
            while True:
                yield await sub[1].get()
        finally:
            _subscribers.discard(sub)

    return EventSourceResponse(stream(), ping=HEARTBEAT_S)


# ---------------- web app (production: scripts/serve.sh builds web/dist and sets SCRIBBLE_SERVE_WEB=1) ----------------

DIST = ROOT / "web" / "dist"


@app.get("/{path:path}", include_in_schema=False)
def web_app(path: str):
    """web/dist files, and index.html for every other non-API path (the Vue router uses HTML5 history)"""
    if os.environ.get("SCRIBBLE_SERVE_WEB") != "1" or path.split("/")[0] == "api" or not (DIST / "index.html").is_file():
        raise HTTPException(404, "not found")
    f = (DIST / path).resolve()
    if path and f.is_relative_to(DIST.resolve()) and f.is_file():
        return FileResponse(f)
    return FileResponse(DIST / "index.html")


# ---------------- openapi ----------------

def openapi_text() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def dev() -> None:
    """npm run dev's backend: scripts/dev.sh runs this under watchfiles, which restarts it on code changes. Not
    uvicorn --reload: on Windows that restarts its worker with a console-wide Ctrl+C, which stops Vite and npm too."""
    import uvicorn
    # LAN binding is intentional: the Instagram QR handoff is scanned by a phone on the same network.
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8765")))


if __name__ == "__main__":
    OPENAPI.write_text(openapi_text(), encoding="utf-8", newline="\n")
    print(f"wrote {OPENAPI}")
