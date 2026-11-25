"""Sounds: library/sfx/ audio files + sfx.json (the @sfx directive), and sound suggestions."""

import json
import os
from pathlib import Path

from fastapi import HTTPException, Request, APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, TypeAdapter, ValidationError

from api.core import lib, part_path, write_story
from api.events import publish
from api.jobs import check_free, check_no_jobs
from pipeline.scribble import background_music, sfx as sfx_lib
from pipeline.scribble.io import atomic_write_json, load_part
from pipeline.scribble.stages.import_check import probe_duration
from pipeline.scribble.stages.runner import StageError

router = APIRouter()


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


@router.get("/api/sfx", response_model=SfxCatalog)
def get_sfx():
    return sfx_catalog()


@router.put("/api/sfx/{sfx_id}", response_model=SfxCatalog)
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


@router.put("/api/sfx/{sfx_id}/audio", response_model=SfxCatalog)
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


@router.delete("/api/sfx/{sfx_id}", response_model=SfxCatalog)
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


@router.get("/api/sfx/{sfx_id}/audio")
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


@router.get("/api/series/{slug}/parts/{part}/sfx-suggestions", response_model=SfxSuggestions)
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


@router.post("/api/series/{slug}/parts/{part}/sfx-suggestions", response_model=SfxSuggestions)
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


@router.post("/api/series/{slug}/parts/{part}/background-music")
def attach_background_music(slug: str, part: str):
    """the "Attach Background Music" button: story.md's @background-music lines replaced by mood cues
    (background_music.score); the next run re-mixes the audio and re-encodes, reusing the rendered frames"""
    pdir = part_path(slug, part)
    check_free(slug, part)
    if not (pdir / "story.md").is_file():
        raise HTTPException(404, "no story.md")
    md = background_music.score((pdir / "story.md").read_text(encoding="utf-8"))
    write_story(pdir, md)
    publish("part-changed", {"slug": slug, "part": part})
    return {"cues": md.count("\n@background-music ") + md.startswith("@background-music ")}
