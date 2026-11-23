"""Captions: Gemini, the one task an outside AI does here."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException, APIRouter
from pydantic import BaseModel, Field, ValidationError

from api.core import lib
from api.settings_routes import SettingsView, settings_view
from pipeline.scribble import db, settings

router = APIRouter()


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


@router.put("/api/settings/gemini-key", response_model=SettingsView)
def put_gemini_key(body: GeminiKey):
    """write-only: GET /api/settings shows only its last 4 characters"""
    key = body.key.strip()
    db.put_settings(lib(), {"gemini_key": key} if key else {}, drop=() if key else ("gemini_key",))
    return settings_view()


@router.post("/api/captions", response_model=Captions)
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
