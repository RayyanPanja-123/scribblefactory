"""scribblefactory web API. Run from the repo root: uvicorn api.main:app --host 127.0.0.1 --port 8765

Localhost only, no auth. Files on disk are the source of truth: every read goes to the library, every write
goes through the CLI commands / pipeline io helpers, and long work runs as CLI subprocesses on one worker thread.
Write docs/openapi.json: python -m api.main
"""

import contextlib
import json
import os
import re
import shutil
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, TypeAdapter, ValidationError

from api.core import (APPROVE_NEEDS, MEDIA_TYPES, OPENAPI, PART_FILES, ROOT, all_series, du, lib, media_url,
                      part_json, part_path, part_summary, parts_of, posted_counts, safe_folder_name, series_json,
                      series_path, waiting_approvals, write_story)
from api.events import publish
from api.jobs import JOBS, busy, check_free, check_no_jobs, load_jobs
from api.models import Health, Notification, Overview, PartDetail, SeriesCard, SeriesDetail, StoredFile
from api.settings_routes import drop_ai_settings
from pipeline.scribble import cli, db, gallery, package, settings, storycheck
from pipeline.scribble.io import (atomic_write_json, part_dir_of, sync_files, storage_root, write_series, atomic_write_text, load_part, load_series, prop_kinds, save_part,
                                  save_series, unknown_cast_props, cast_body_problems, cast_files,
                                  cast_render_current)
from pipeline.scribble.schemas import CastMember, PartModel, SeriesModel, Slug, Stages, utcnow
from pipeline.scribble.stages import render as render_stage
from pipeline.scribble.stages.import_check import probe_duration
from pipeline.scribble.stages.runner import StageError, recover_stuck


@contextlib.asynccontextmanager
async def lifespan(_app):
    startup()
    yield


app = FastAPI(title="scribblefactory", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


# ---------------- read endpoints ----------------

@app.get("/api/health", response_model=Health)
def health():
    return {"ok": True}


# the exposure sheet's columns: the same journey as web/src/lib/partSteps.ts, coarse (from files on disk + jobs)
SHEET_STEPS = ["Story", "Voice", "Plan", "Stills", "Final", "Post"]


def sheet_cells(slug: str, pdir: Path, p) -> list[str]:
    st = {f.alias or n: s.status for n, f in Stages.model_fields.items() if (s := getattr(p.stages, n)) is not None}
    ok = lambda *xs: all(st.get(x) == "done" for x in xs)  # noqa: E731
    steps = [  # (done, stages that can fail it, ready for review)
        (ok("prep"), ["prep"], False),
        ((pdir / "voice.mp3").is_file() and ok("import_check", "timing"), ["import_check", "timing"], False),
        (ok("shots", "validate"), ["shots", "validate"], False),
        (bool(p.approvals.stills.approved_at), [], (pdir / "stills-sheet.png").is_file()),
        (bool(p.approvals.final.approved_at), ["render", "audio", "finish"], ok("render", "audio", "finish")),
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
        elif busy(slug, p.id):
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
            if w := waiting_approvals(part_dir_of(d, pid), p):
                waiting.append({"slug": d.name, "part": pid, "waiting": w})
            if not (p.posted.youtube or p.posted.instagram) and s.status != "archived":
                sheet.append({"slug": d.name, "series_title": s.title, "part": pid, "number": p.number,
                              "title": p.title, "cells": sheet_cells(d.name, part_dir_of(d, pid), p)})
            for platform in ("youtube", "instagram"):
                post = getattr(p.posted, platform)
                if post and (m := post.posted_at.strftime("%Y-%m")) in per_month:
                    per_month[m][platform] += 1
    for gp in (gp for e in gallery.entries(lib()) for gp in e.parts):  # posts of series moved to the gallery count too
        for platform in ("youtube", "instagram"):
            if (m := getattr(gp, platform).posted_at.strftime("%Y-%m")) in per_month:
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
              "part_count": len(s.parts),
              "disk_usage": du(d), "posted": posted_counts(d)}
             for d in all_series() for s in [load_series(d / "series.json")]]
    return sorted(cards, key=lambda card: card["created_at"], reverse=True)


@app.get("/api/storage", response_model=list[StoredFile])
def storage(slug: str | None = None):
    """every stored file of the library (or one series), frames aside, with size, type, duration and sha256;
    brought up to date first (only new or changed files are measured)"""
    for d in ([series_path(slug)] if slug else all_series()):
        sync_files(d)
    return db.get_files(lib(), slug)


@app.get("/api/notifications", response_model=list[Notification])
def notifications():
    """Library information that is useful to review but does not belong in a part's story warnings."""
    unused = storycheck.unused_custom_actions(lib())
    if not unused:
        return []
    return [Notification(
        id=f"unused-actions:{','.join(unused)}",
        title="Custom actions not used",
        message=f"{', '.join(unused[:8])}{'…' if len(unused) > 8 else ''} are in the shared library but no story uses them.",
        slug="",
        series_title="Shared library",
        href="/actions",
    )]


@app.get("/api/series/{slug}", response_model=SeriesDetail)
def series_detail(slug: str):
    d = series_path(slug)
    s = load_series(d / "series.json")
    return {"series": s.model_dump(mode="json"), "parts": [part_summary(part_dir_of(d, pid), p) for pid, p in parts_of(d)],
            "cast": {c.id: cast_render(d, c) for c in s.cast}}


def cast_render(d: Path, c) -> dict:
    def url(f: Path):  # ?v: a re-render is a new url, not a cached old picture
        return f"{media_url(d.name, f.relative_to(d).as_posix())}?v={f.stat().st_mtime_ns}" if f.is_file() else None
    files = cast_files(d, c.id)
    return {"sheet": url(files["sheet"]), "idle": url(files["idle"]), "current": cast_render_current(d, c)}


@app.get("/api/series/{slug}/parts/{part}", response_model=PartDetail)
def part_detail(slug: str, part: str, audio_notice: str | None = None):
    pdir = part_path(slug, part)
    files = {f: (pdir / f).is_file() for f in PART_FILES}
    try:
        voice = probe_duration(pdir / "voice.mp3") if files["voice.mp3"] else None
    except StageError:
        voice = None
    qa, upload, story, tts = pdir / "qa.json", pdir / "upload.md", pdir / "story.md", pdir / "script-for-tts.txt"
    versions = {rel: (pdir / rel).stat().st_mtime_ns for rel in PART_FILES if files[rel]}
    return {"part": part_json(pdir), "files": files, "versions": versions,
            "qa": json.loads(qa.read_bytes()) if qa.is_file() else None,
            "upload_md": upload.read_text(encoding="utf-8") if upload.is_file() else None,
            "story_md": story.read_text(encoding="utf-8") if story.is_file() else None,
            "tts_script": tts.read_text(encoding="utf-8") if tts.is_file() else None,
            "voice_duration": voice, "frames_bytes": du(pdir / "frames"), "part_bytes": du(pdir),
            "busy": busy(slug, part), "audio_notice": audio_notice}


class MissingItem(BaseModel):
    kind: Literal["cast", "set", "prop", "action", "look", "sound", "wardrobe", "unapproved"]
    ids: list[str]
    owner: str | None = None  # a look: the cast member who lacks it


class StoryIssue(BaseModel):
    line: int | None  # story.md line, None: the whole story
    message: str
    missing: MissingItem | None = None  # names something that does not exist yet (storycheck.MISSING)


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
    root = (storage_root(lib()) / slug).resolve()
    first, _, rest = path.partition("/")  # web urls name a part by its id (part-01/final.mp4): its folder on disk
    if rest and first.startswith("part-"):
        path = f"{part_dir_of(root, first).name}/{rest}"
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


@app.post("/api/series/{slug}/parts/{part}/export")
def export_final(slug: str, part: str):
    """Copy a completed final video into the user's reels export library."""
    check_free(slug, part)
    series_dir = series_path(slug)
    part_dir = part_path(slug, part)
    source = part_dir / "final.mp4"
    if not source.is_file():
        raise HTTPException(409, "final.mp4 is not ready to export")
    series = load_series(series_dir / "series.json")
    model = load_part(part_dir / "part.json")

    export_root = Path(settings.load(lib())["export_directory"])
    destination_dir = export_root / safe_folder_name(series.title, slug)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"Part {model.number:02d} - {safe_folder_name(model.title, part)}.mp4"
    shutil.copy2(source, destination)
    return {"path": str(destination), "filename": destination.name}


# ---------------- actions ----------------

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
def approve(slug: str, part: str, what: Literal["stills", "final"]):
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


@app.post("/api/series/{slug}/parts/{part}/reopen", response_model=PartModel)
def reopen(slug: str, part: str):
    """start a part over (taken down, or redone): clear its posts, approvals and stages; files stay"""
    return part_action(slug, part, "reopen", slug, part)


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
    aspect: Literal["9:16", "16:9"] = "9:16"  # the frame shape of every part


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
    Path(settings.load(lib())["audio_directory"]).joinpath(safe_folder_name(body.title, body.slug)).mkdir(parents=True, exist_ok=True)
    if cast or body.aspect != "9:16":
        series = load_series(d / "series.json")
        series.cast, series.style.aspect = cast, body.aspect
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
    write_series(d / "series.json", series)
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


@app.delete("/api/series/{slug}/cast/{cast_id}", response_model=SeriesModel)
def delete_cast(slug: str, cast_id: str, force: bool = False):
    """remove one cast member. A 409 names the parts whose directives still use the id, unless force (their
    check-story then flags it). Its render files stay on disk."""
    d = series_path(slug)
    check_free(slug)
    series = load_series(d / "series.json")
    if not any(c.id == cast_id for c in series.cast):
        raise HTTPException(404, f"cast id {cast_id!r} not in {slug}")
    word = re.compile(rf"(?<![\w-]){re.escape(cast_id)}(?![\w-])")
    used = [pid for pid, _ in parts_of(d) if (f := part_dir_of(d, pid) / "story.md").is_file()
            and any(l.lstrip().startswith("@") and word.search(l) for l in f.read_text(encoding="utf-8").splitlines())]
    if used and not force:
        raise HTTPException(409, f"used in {', '.join(used)}")
    series.cast = [c for c in series.cast if c.id != cast_id]
    write_series(d / "series.json", series)
    publish("series-changed", {"slug": slug})
    return series_json(d)


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


def auto_pick_part_audio(slug: str, part: str, title: str, number: int) -> str:
    """Copy an unambiguous mp3 from the series audio folder into a new part, or explain what is missing."""
    series_dir = series_path(slug)
    series = load_series(series_dir / "series.json")
    audio_dir = Path(settings.load(lib())["audio_directory"]) / safe_folder_name(series.title, slug)
    if not audio_dir.is_dir():
        return f"No audio folder found yet: {audio_dir}. Add an mp3 there and upload it in Voice."

    def key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    wanted = {key(part), key(f"part-{number:02d}"), key(f"part {number}"), key(f"{number:02d}"), key(title)}
    matches = sorted(f for f in audio_dir.iterdir() if f.is_file() and f.suffix.lower() == ".mp3" and key(f.stem) in wanted)
    if not matches:
        return f"No matching mp3 found in {audio_dir}. Expected a file named {part}.mp3 or {title or f'Part {number}'}.mp3."
    source = matches[0]
    data = source.read_bytes()
    if len(data) > MAX_VOICE_BYTES:
        return f"Audio found ({source.name}) but it is over {MAX_VOICE_BYTES // 2**20} MB; upload it in Voice."
    if not (data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)):
        return f"Audio found ({source.name}) but it is not a valid mp3; upload it in Voice."
    destination = part_dir_of(series_dir, part) / "voice.mp3"
    destination.write_bytes(data)
    return f"Audio auto-selected: {source.name}"


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
    model = load_part(part_dir_of(d, part) / "part.json")
    audio_notice = auto_pick_part_audio(slug, part, model.title, model.number)
    if body.story is not None:
        write_story(part_dir_of(d, part), body.story)
    publish("series-changed", {"slug": slug})
    return part_detail(slug, part, audio_notice)


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


@app.post("/api/series/{slug}/gallery", response_model=gallery.GalleryEntry)
def move_to_gallery(slug: str):
    """keep the titles and links of a series posted everywhere, delete its folder (cli to-gallery)"""
    series_path(slug)
    check_free(slug)
    if any(j["status"] == "queued" and j["slug"] == slug for j in list(JOBS)):
        raise HTTPException(409, f"a job is queued on {slug}; cancel it first")
    before = {e.slug for e in gallery.entries(lib())}
    cli_call("to-gallery", slug, "--yes")
    publish("series-changed", {"slug": slug})
    return next(e for e in gallery.entries(lib()) if e.slug not in before)


@app.get("/api/gallery", response_model=list[gallery.GalleryEntry])
def gallery_list():
    return gallery.entries(lib())


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
    # a new voice: Run next must redo import_check onward (it plans from statuses; Re-render alone keeps the old
    # voice-tight.wav, so the old audio). Its later steps re-plan themselves once one step runs.
    model = load_part(pdir / "part.json")
    model.stages.import_check.status = "pending"
    save_part(pdir / "part.json", model)
    publish("part-changed", {"slug": slug, "part": part})
    return part_detail(slug, part)


@app.post("/api/series/{slug}/parts/{part}/clean-frames", response_model=PartModel)
def clean_frames(slug: str, part: str):
    return part_action(slug, part, "clean-frames", slug, part)


def startup() -> None:
    """API start: jobs from .jobs.json, then every part's stuck stages and stale render locks (orphan workers)."""
    notes = load_jobs() + drop_ai_settings()
    for d in all_series():
        for pid, p in parts_of(d):
            pdir = part_dir_of(d, pid)
            notes += [f"{d.name} {pid}: {n}" for n in render_stage.clear_stale_lock(pdir)]
            notes += [f"{d.name} {pid}: {n} was left running: marked failed (interrupted)" for n in recover_stuck(pdir)]
    for n in notes:
        print(f"startup: {n}", flush=True)


from api import captions, catalogs, events, jobs, settings_routes, sounds

for _module in (catalogs, sounds, settings_routes, captions, jobs, events):
    app.include_router(_module.router)


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
