"""TTS voices (the Kokoro server, pipeline/scribble/tts.py): the voice list, a preview, a cached line's clip, the
series' narrator voice and a part's voice source. Making a part's voice is a job step (run --stage tts)."""

import json
import re
import urllib.request
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.core import lib, part_path, series_json, series_path
from api.events import publish
from api.jobs import check_free
from pipeline.scribble import settings, tts
from pipeline.scribble.io import load_part, load_series, save_part, save_series
from pipeline.scribble.schemas import PartModel, SeriesModel, TtsVoice
from pipeline.scribble.stages.runner import StageError

router = APIRouter()
PREVIEW_TEXT = "Hi there. This is how I sound when I tell a story."


class Voice(BaseModel):
    id: str
    label: str
    lang: str | None = None
    gender: str | None = None


class Voices(BaseModel):
    online: bool  # false: the server did not answer; these are the ids it had last time, without labels
    voices: list[Voice]
    default: str  # settings tts_voice: the narrator when a series sets none


@router.get("/api/tts/voices", response_model=Voices)
def voices():
    s = settings.load(lib())
    url = str(s["tts_url"] or "").rstrip("/")
    if url:
        try:
            with urllib.request.urlopen(f"{url}/v1/voices", timeout=3) as r:
                got = json.loads(r.read())
            return {"online": True, "default": s["tts_voice"],
                    "voices": [{"id": v["id"], "label": v.get("label") or v["id"], "lang": v.get("lang"),
                                "gender": v.get("gender")} for v in got]}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return {"online": False, "default": s["tts_voice"], "voices": [{"id": v, "label": v} for v in s["tts_voices"]]}


@router.get("/api/tts/preview")
def preview(voice: str, speed: float = 1.0, text: str = ""):
    """a short line in this voice (WAV), cached like any other line"""
    if not 0.5 <= speed <= 2.0:
        raise HTTPException(422, "speed: 0.5..2.0")
    line = " ".join((text or PREVIEW_TEXT).split())[:200]
    try:
        cfg = tts.config(lib())
        path = tts.clips(lib(), [(line, voice, round(speed, 3))], cfg)[0]
    except StageError as e:
        raise HTTPException(503, str(e))
    return FileResponse(path, media_type="audio/wav")


@router.get("/api/tts/clip/{key}")
def clip(key: str):
    """one cached line (voice-tts.json lines[].clip)"""
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise HTTPException(404, "no such clip")
    f = tts.cache_dir(lib()) / f"{key}.wav"
    if not f.is_file():
        raise HTTPException(404, "clip not cached (run the tts step again)")
    return FileResponse(f, media_type="audio/wav")


class NarratorBody(BaseModel):
    tts: TtsVoice | None = Field(description="the narrator's voice; null: settings tts_voice")


@router.put("/api/series/{slug}/voice", response_model=SeriesModel)
def set_narrator(slug: str, body: NarratorBody):
    d = series_path(slug)
    s = load_series(d / "series.json")
    s.voice.tts = body.tts
    save_series(d / "series.json", s)
    publish("series-changed", {"slug": slug})
    return series_json(d)


class VoiceSourceBody(BaseModel):
    source: Literal["recorded", "tts"]


@router.put("/api/series/{slug}/parts/{part}/voice-source", response_model=PartModel)
def set_voice_source(slug: str, part: str, body: VoiceSourceBody):
    pdir = part_path(slug, part)
    check_free(slug, part)
    m = load_part(pdir / "part.json")
    m.voice_source = body.source
    save_part(pdir / "part.json", m)
    publish("part-changed", {"slug": slug, "part": part})
    return load_part(pdir / "part.json").model_dump(mode="json")
