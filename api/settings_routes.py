"""Settings (the setting table, pipeline/scribble/db.py): machine-level options (render workers, socials, folders, caption model)."""

from typing import Literal

from fastapi import HTTPException, APIRouter
from pydantic import BaseModel, Field

from api.core import lib
from pipeline.scribble import db, settings

router = APIRouter()


# settings held third-party AI provider settings and keys; AI help is copy/paste now, except captions
# (Gemini, keyed in Settings: write_captions)
OLD_AI_KEYS = {"provider", "base_url", "model", "omniroute_model", "gemini_model", "openrouter_model",
               "api_key", "gemini_api_key", "openrouter_api_key"}


def drop_ai_settings() -> list[str]:
    """remove the old provider keys from the settings"""
    if not OLD_AI_KEYS & db.get_settings(lib()).keys():
        return []
    db.put_settings(lib(), {}, drop=OLD_AI_KEYS)
    return ["settings: old AI provider settings and keys removed"]


class Socials(BaseModel):
    youtube: str = Field("", max_length=60)
    instagram: str = Field("", max_length=60)
    facebook: str = Field("", max_length=60)


class Settings(BaseModel):
    render_workers: Literal["auto"] | int = Field("auto", description="'auto' or 1..16 parallel browsers per render")
    force_software_gl: bool = False
    socials: Socials = Field(default_factory=Socials, description="handles on every part's closing 'Follow for more' "
                                                                  "screen (empty: left off)")
    caption_model: Literal[settings.FREE_GEMINI] = Field(settings.FREE_GEMINI[0], description=(
        "free Gemini model captions try first; busy or out of quota, the next free one answers"))
    export_directory: str = Field(settings.DEFAULTS["export_directory"], min_length=1, max_length=500,
                                  description="folder where the Export button copies approved final videos")
    audio_directory: str = Field(settings.DEFAULTS["audio_directory"], min_length=1, max_length=500,
                                 description="root folder where each new series gets an audio folder")


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


@router.get("/api/settings", response_model=SettingsView)
def get_settings():
    return settings_view()


@router.put("/api/settings", response_model=SettingsView)
def put_settings(body: Settings):
    """applies to the next render job; a running one keeps its workers. Handles: the next finish run."""
    w = body.render_workers
    if w != "auto" and not 1 <= w <= settings.MAX_WORKERS:
        raise HTTPException(422, f"render_workers must be 'auto' or 1 to {settings.MAX_WORKERS}")
    db.put_settings(lib(), body.model_dump())  # keys we don't know stay
    return settings_view()
