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
import time
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Literal, get_args

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, TypeAdapter, ValidationError
from sse_starlette import EventSourceResponse

from pipeline.scribble import cli, storycheck
from pipeline.scribble.io import (atomic_write_bytes, atomic_write_json, atomic_write_text, delete_prop, delete_set, load_part, load_props,
                                  load_series, load_sets, prop_kinds, save_prop, save_series, save_set, unknown_cast_props,
                                  cast_body_problems, delete_creature, load_creatures, save_creature, delete_action,
                                  load_actions, save_action)
from pipeline.scribble.schemas import (ACTIONS, BUILTIN_CREATURES, BUILTIN_SETS, BuiltinProp, CastMember, CreatureRig,
                                       CustomAction, CustomCreature, actions_with,
                                       CustomProp, CustomSet, PartModel, Posted, SeriesModel, SetKind, Slug,
                                       Stage, Stages,
                                       utcnow)
from pipeline.scribble.stages import render as render_stage
from pipeline.scribble.stages.import_check import probe_duration
from pipeline.scribble.stages.runner import StageError, recover_stuck

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "docs" / "openapi.json"
MEDIA_TYPES = {".mp4", ".png", ".jpg", ".mp3", ".md", ".json"}
COVER_W = 360  # dashboard cover width (px): a small cached JPEG instead of the 1080x1920 thumbnail PNG
PART_FILES = ["story.md", "voice.mp3", "preview.mp4", "test-render.mp4", "final.mp4", "stills-sheet.png", "cast-sheet.png"]
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
    """approvals with something to look at but no approval yet"""
    return [n for n, f in APPROVE_NEEDS.items()
            if not getattr(p.approvals, n).approved_at and (pdir / f).is_file()
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


class SeriesDetail(BaseModel):
    series: SeriesModel
    parts: list[PartSummary]
    cast_sheet: str | None


class PartDetail(BaseModel):
    part: PartModel
    files: dict[str, bool]
    thumbs: list[str]
    qa: dict | None
    upload_md: str | None
    story_md: str | None
    voice_duration: float | None
    frames_bytes: int
    part_bytes: int  # the whole part folder, frames included
    busy: str | None


class Job(BaseModel):
    id: int
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
SHEET_STEPS = ["Story", "Voice", "Plan", "Stills", "Test", "Final", "Thumb", "Post"]


def sheet_cells(slug: str, pdir: Path, p) -> list[str]:
    st = {f.alias or n: getattr(p.stages, n).status for n, f in Stages.model_fields.items()}
    ok = lambda *xs: all(st.get(x) == "done" for x in xs)  # noqa: E731
    steps = [  # (done, stages that can fail it, ready for review)
        (ok("prep"), ["prep"], False),
        ((pdir / "voice.mp3").is_file() and ok("import_check", "timing"), ["import_check", "timing"], False),
        (ok("shots", "validate"), ["shots", "validate"], False),
        (bool(p.approvals.stills.approved_at), [], (pdir / "stills-sheet.png").is_file()),
        (bool(p.approvals.test_render.approved_at), [], (pdir / "test-render.mp4").is_file()),
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
        cast = [f"cast:{c.id}" for c in s.cast if not c.approved_at]
        if cast and (d / "cast-sheet.png").is_file():
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
    return [{"slug": s.slug, "title": s.title, "status": s.status, "part_count": len(s.parts), "cover": cover(d),
             "disk_usage": du(d), "posted": posted_counts(d)}
            for d in all_series() for s in [load_series(d / "series.json")]]


@app.get("/api/series/{slug}", response_model=SeriesDetail)
def series_detail(slug: str):
    d = series_path(slug)
    return {"series": series_json(d), "parts": [part_summary(d / pid, p) for pid, p in parts_of(d)],
            "cast_sheet": media_url(slug, "cast-sheet.png") if (d / "cast-sheet.png").is_file() else None}


@app.get("/api/series/{slug}/parts/{part}", response_model=PartDetail)
def part_detail(slug: str, part: str):
    pdir = part_path(slug, part)
    files = {f: (pdir / f).is_file() for f in PART_FILES}
    files["cast-sheet.png"] = (pdir.parent / "cast-sheet.png").is_file()  # series level
    try:
        voice = probe_duration(pdir / "voice.mp3") if files["voice.mp3"] else None
    except StageError:
        voice = None
    qa, upload, story = pdir / "qa.json", pdir / "upload.md", pdir / "story.md"
    return {"part": part_json(pdir), "files": files,
            "thumbs": sorted(f.name for f in (pdir / "thumbs").glob("thumb-*.png")),
            "qa": json.loads(qa.read_bytes()) if qa.is_file() else None,
            "upload_md": upload.read_text(encoding="utf-8") if upload.is_file() else None,
            "story_md": story.read_text(encoding="utf-8") if story.is_file() else None,
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
    return FileResponse(f)  # Starlette answers Range requests with 206


# ---------------- actions ----------------

def busy(slug: str, part: str | None = None) -> str | None:
    """why this part (or, part None, any part of the series) can't be touched now, else None"""
    for j in list(JOBS):
        if j["status"] == "running" and j["slug"] == slug and part in (None, j["part"]):
            return f"job {j['id']} is running on {slug} {j['part']}"
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
    if not (d / "cast-sheet.png").is_file():
        raise HTTPException(409, f"no cast sheet yet: run cast-sheet {slug} first")
    cli_call("approve-cast", slug, body.cast_id)
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
    c = {k: v for k, v in c.items() if k != "approved_at"}
    if "color" in c:
        c.setdefault("top", {})
        c["top"] = {**c["top"], "color": c.pop("color")} if isinstance(c["top"], dict) else c["top"]
    c.setdefault("eyes", "dots")
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
        raise HTTPException(409, f"cast body: {problems[0]}")
    cli_call("new-series", body.slug, f"--title={body.title}")
    d = series_path(body.slug)
    if cast:
        series = load_series(d / "series.json")
        series.cast = cast
        save_series(d / "series.json", series)
    publish("series-changed", {"slug": body.slug})
    return series_json(d)


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
        raise HTTPException(409, f"job {run['id']} is running on {run['slug']} {run['part']}; wait for it or cancel it")


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


def startup() -> None:
    """API start: jobs from .jobs.json, then every part's stuck stages and stale render locks (orphan workers)."""
    notes = load_jobs()
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
    job = {"id": next(_ids), "slug": body.slug, "part": body.part, "steps": body.steps, "argv": argv,
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
        publish("part-changed", {"slug": job["slug"], "part": job["part"]})
        publish("series-changed", {"slug": job["slug"]})
        if job["status"] == "cancelled":
            return
        if proc.returncode != 0:
            job["status"] = "failed"
            return
    job["status"] = "done"


# ---------------- AI settings (library/settings.json): provider keys make "Build with AI" one click ----------------

DEFAULT_AI_URL = "http://localhost:20128/v1"
DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1"
AI_TIMEOUT_S = 180


class AiSettings(BaseModel):
    provider: Literal["omniroute", "gemini", "openrouter"]
    base_url: str
    model: str
    omniroute_model: str
    gemini_model: str
    openrouter_model: str
    has_key: bool
    key_hint: str
    has_omniroute_key: bool
    omniroute_key_hint: str
    has_gemini_key: bool
    gemini_key_hint: str
    has_openrouter_key: bool
    openrouter_key_hint: str


class AiSettingsIn(BaseModel):
    provider: Literal["omniroute", "gemini", "openrouter"] = "omniroute"
    base_url: str = DEFAULT_AI_URL
    model: str = ""
    omniroute_model: str | None = None
    gemini_model: str | None = None
    openrouter_model: str | None = None
    api_key: str | None = None  # None keeps the saved key, "" clears it
    gemini_api_key: str | None = None  # None keeps the saved key, "" clears it
    openrouter_api_key: str | None = None  # None keeps the saved key, "" clears it


class AiPrompt(BaseModel):
    prompt: str


class AiReply(BaseModel):
    text: str


class GeminiModelsIn(BaseModel):
    api_key: str | None = None  # optional typed key; otherwise use the saved Gemini key


class GeminiModels(BaseModel):
    models: list[str]
    recommended: str


def settings_file() -> Path:
    return lib() / "settings.json"


def load_settings() -> dict:
    f = settings_file()
    s = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    provider = s.get("provider") if s.get("provider") in ("omniroute", "gemini", "openrouter") else "omniroute"
    legacy_model = s.get("model", "")
    omniroute_model = s.get("omniroute_model", legacy_model if provider == "omniroute" else "")
    gemini_model = s.get("gemini_model", legacy_model if provider == "gemini" else "")
    openrouter_model = s.get("openrouter_model", legacy_model if provider == "openrouter" else "")
    return {
        "provider": provider,
        "base_url": s.get("base_url") or DEFAULT_AI_URL,
        "model": {"omniroute": omniroute_model, "gemini": gemini_model, "openrouter": openrouter_model}[provider],
        "omniroute_model": omniroute_model,
        "gemini_model": gemini_model,
        "openrouter_model": openrouter_model,
        "api_key": s.get("api_key", ""),
        "gemini_api_key": s.get("gemini_api_key", ""),
        "openrouter_api_key": s.get("openrouter_api_key", ""),
    }


def public_settings(s: dict) -> AiSettings:
    active_key = {"omniroute": s["api_key"], "gemini": s["gemini_api_key"], "openrouter": s["openrouter_api_key"]}[s["provider"]]
    return AiSettings(provider=s["provider"], base_url=s["base_url"], model=s["model"],
                      omniroute_model=s["omniroute_model"], gemini_model=s["gemini_model"],
                      openrouter_model=s["openrouter_model"],
                      has_key=bool(active_key), key_hint=active_key[-4:],
                      has_omniroute_key=bool(s["api_key"]), omniroute_key_hint=s["api_key"][-4:],
                      has_gemini_key=bool(s["gemini_api_key"]), gemini_key_hint=s["gemini_api_key"][-4:],
                      has_openrouter_key=bool(s["openrouter_api_key"]), openrouter_key_hint=s["openrouter_api_key"][-4:])


@app.get("/api/settings", response_model=AiSettings)
def get_settings():
    return public_settings(load_settings())


@app.put("/api/settings", response_model=AiSettings)
def put_settings(body: AiSettingsIn):
    if not body.base_url.startswith(("http://", "https://")):
        raise HTTPException(422, "base URL must start with http:// or https://")
    s = load_settings()
    s.update(provider=body.provider, base_url=body.base_url.strip().rstrip("/"))
    if body.omniroute_model is not None:
        s["omniroute_model"] = body.omniroute_model.strip()
    elif body.provider == "omniroute":
        s["omniroute_model"] = body.model.strip()
    if body.gemini_model is not None:
        s["gemini_model"] = body.gemini_model.strip()
    elif body.provider == "gemini":
        s["gemini_model"] = body.model.strip()
    if body.openrouter_model is not None:
        s["openrouter_model"] = body.openrouter_model.strip()
    elif body.provider == "openrouter":
        s["openrouter_model"] = body.model.strip()
    s["model"] = {"omniroute": s["omniroute_model"], "gemini": s["gemini_model"], "openrouter": s["openrouter_model"]}[body.provider]
    if body.api_key is not None:
        s["api_key"] = body.api_key.strip()
    if body.gemini_api_key is not None:
        s["gemini_api_key"] = body.gemini_api_key.strip()
    if body.openrouter_api_key is not None:
        s["openrouter_api_key"] = body.openrouter_api_key.strip()
    lib().mkdir(parents=True, exist_ok=True)
    atomic_write_json(settings_file(), s)
    return public_settings(s)


@app.post("/api/ai/gemini-models", response_model=GeminiModels)
def gemini_models(body: GeminiModelsIn):
    """List text-generation Gemini models available to the supplied or saved key."""
    import urllib.error
    import urllib.request
    key = (body.api_key or "").strip() or load_settings()["gemini_api_key"]
    if not key:
        raise HTTPException(400, "Enter a Gemini API key first")
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
        headers={"x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        names = [m["name"].removeprefix("models/") for m in data.get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        models = sorted((n for n in names if n.startswith("gemini") and not re.search(r"tts|image|live|embed|audio", n)), reverse=True)
        if not models:
            raise HTTPException(502, "That key works but cannot use any Gemini text model")
        stable = [m for m in models if "flash" in m and not re.search(r"lite|preview|exp", m)]
        return GeminiModels(models=models, recommended=(stable or models)[0])
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"Gemini said {e.code}: {e.read().decode(errors='replace')[:500]}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise HTTPException(502, f"Gemini not reachable: {getattr(e, 'reason', e)}")
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, "Gemini returned an unexpected model list")


class Gateway(BaseModel):
    running: bool


class GatewayIn(BaseModel):
    on: bool


class OmniRouteModel(BaseModel):
    id: str
    owned_by: str | None = None
    is_free: bool | None = None
    context_window: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None


class OmniRouteModels(BaseModel):
    models: list[OmniRouteModel]
    checked_at: datetime


def gateway_port() -> int | None:
    """Port of the gateway in Settings when it's on this machine (the only kind we can start); None otherwise."""
    from urllib.parse import urlsplit
    s = load_settings()
    if s["provider"] != "omniroute":
        return None
    u = urlsplit(s["base_url"])
    if u.hostname not in ("localhost", "127.0.0.1", "::1"):
        return None
    return u.port or (443 if u.scheme == "https" else 80)


def gateway_up(port: int | None) -> bool:
    if port is None:
        return False
    with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), timeout=0.5):
        return True
    return False


# Windows: a launcher starts argv and exits at once, so argv is orphaned: outside the API's process tree (an API
# reload, or dev.sh's taskkill /T, can't reach it) and, where the job allows breakaway, outside its job object.
# CREATE_NO_WINDOW gives it a hidden console that the CLIs it spawns inherit.
_LAUNCHER = """import subprocess, sys
flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
for f in (flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, flags):
    try:
        subprocess.Popen(sys.argv[1:], creationflags=f, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        break
    except OSError:  # the job doesn't allow breakaway
        pass
"""


def spawn_detached(argv: list[str]) -> None:
    """Start argv so it outlives this process (and its reloads), with no visible window."""
    if os.name != "nt":
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return
    subprocess.run([sys.executable, "-c", _LAUNCHER, *argv], timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)


@app.get("/api/gateway", response_model=Gateway)
def get_gateway():
    return Gateway(running=gateway_up(gateway_port()))


@app.put("/api/gateway", response_model=Gateway)
def put_gateway(body: GatewayIn):
    """Start (daemon, no browser) or stop the local OmniRoute through its own CLI."""
    import shutil
    port = gateway_port()
    if port is None:
        raise HTTPException(409, "the AI gateway in Settings isn't on this machine: start it where it runs")
    if gateway_up(port) == body.on:
        return Gateway(running=body.on)
    exe = shutil.which("omniroute")
    if not exe:
        raise HTTPException(409, "OmniRoute isn't installed: npm install -g omniroute")
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if body.on:
        # Not --daemon: that detaches the server from any console, so on Windows every CLI provider it runs
        # (claude, codex, ...) pops its own console window. In a hidden console, they inherit it instead.
        # `omniroute stop` still finds it (PID file, else the port).
        spawn_detached([exe, "serve", "--no-open", "--port", str(port)])
        deadline = time.monotonic() + 60
        while not gateway_up(port) and time.monotonic() < deadline:
            time.sleep(0.5)
        if not gateway_up(port):
            raise HTTPException(502, "omniroute serve didn't start listening within 60 s: run it in a terminal to see why")
        return Gateway(running=True)
    try:
        r = subprocess.run([exe, "stop", "--port", str(port)], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=90, creationflags=no_window)
    except subprocess.TimeoutExpired:
        raise HTTPException(502, "omniroute stop took over 90 s")
    deadline = time.monotonic() + 30  # the CLI can return before the port is released
    while gateway_up(port) and time.monotonic() < deadline:
        time.sleep(0.5)
    if gateway_up(port):
        raise HTTPException(502, f"omniroute stop failed: {(r.stderr or r.stdout).strip()[-500:] or f'exit {r.returncode}'}")
    return Gateway(running=False)


@app.get("/api/ai/omniroute-models", response_model=OmniRouteModels)
def omniroute_models():
    """Discover models exposed by the configured OmniRoute gateway."""
    import urllib.error
    import urllib.request
    s = load_settings()
    if s["provider"] != "omniroute":
        raise HTTPException(409, "OmniRoute is not the active AI provider")
    if not s["api_key"]:
        raise HTTPException(400, "no OmniRoute API key: add one in Settings")
    url = f"{s['base_url'].rstrip('/')}/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {s['api_key']}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            payload = json.loads(r.read())
        models = []
        for item in payload.get("data", []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            models.append(OmniRouteModel(
                id=str(item["id"]),
                owned_by=item.get("owned_by"),
                is_free=item.get("is_free", item.get("isFree")),
                context_window=item.get("context_window", item.get("contextWindow")),
                max_input_tokens=item.get("max_input_tokens", item.get("maxInputTokens")),
                max_output_tokens=item.get("max_output_tokens", item.get("maxOutputTokens")),
            ))
        return OmniRouteModels(models=sorted(models, key=lambda m: m.id.lower()), checked_at=datetime.now().astimezone())
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"OmniRoute said {e.code}: {e.read().decode(errors='replace')[:500]}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise HTTPException(502, f"OmniRoute not reachable: {getattr(e, 'reason', e)}")
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, "OmniRoute returned an unexpected model list")


@app.post("/api/ai/complete", response_model=AiReply)
def ai_complete(body: AiPrompt):
    """One completion through the selected provider. Keys stay server-side."""
    import urllib.error
    import urllib.parse
    import urllib.request
    s = load_settings()
    key = {"omniroute": s["api_key"], "gemini": s["gemini_api_key"], "openrouter": s["openrouter_api_key"]}[s["provider"]]
    if not key:
        raise HTTPException(400, "no API key: add one in Settings")
    if not s["model"]:
        raise HTTPException(400, "no model: set one in Settings")
    if s["provider"] == "gemini":
        model = s["model"].removeprefix("models/")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model, safe='')}:generateContent"
        payload = {"contents": [{"role": "user", "parts": [{"text": body.prompt}]}]}
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    else:
        url = f"{s['base_url']}/chat/completions"
        payload = {"model": s["model"], "messages": [{"role": "user", "content": body.prompt}]}
        if s["provider"] == "openrouter":
            # OpenRouter may reject its 16k default when a free key has only a smaller remaining limit.
            payload["max_tokens"] = 4000
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT_S) as r:
            data = json.loads(r.read())
        if s["provider"] == "gemini":
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
            return AiReply(text=text)
        return AiReply(text=data["choices"][0]["message"]["content"] or "")
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"{s['provider']} said {e.code}: {e.read().decode(errors='replace')[:500]}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise HTTPException(502, f"{s['provider']} not reachable: {getattr(e, 'reason', e)}")
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(502, f"{s['provider']} sent an unexpected reply")


@app.post("/api/ai/story-writer", response_model=AiReply)
def ai_story_writer(body: AiPrompt):
    """Story Writer is intentionally restricted to the dedicated Gemini provider, never OmniRoute."""
    if load_settings()["provider"] == "omniroute":
        raise HTTPException(409, "Story Writer requires Gemini or OpenRouter as the active provider")
    return ai_complete(body)


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


if __name__ == "__main__":
    OPENAPI.write_text(openapi_text(), encoding="utf-8", newline="\n")
    print(f"wrote {OPENAPI}")
