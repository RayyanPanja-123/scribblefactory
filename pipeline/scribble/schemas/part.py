"""part.json and phrases.json: one part's stages, approvals and posts, and its timed words."""

from typing import Literal

from pydantic import ConfigDict, Field, model_serializer, model_validator

from .base import PartId, Strict, UtcDateTime


# --- part.json ---

class Stage(Strict):
    status: Literal["pending", "running", "done", "failed"] = "pending"
    started_at: UtcDateTime | None = None
    finished_at: UtcDateTime | None = None
    error: str | None = None
    inputs_hash: str | None = None  # sha256 of the stage's input files at the last successful run
    pid: int | None = Field(default=None, description="while running: the process running it (a running stage "
                                                      "whose process is gone was interrupted)")


class Stages(Strict):
    prep: Stage = Stage()
    tts: Stage | None = Field(default=None, description="voice_source tts only: voice.mp3 from the TTS server "
                                                        "(none: never run)")
    import_check: Stage = Stage()
    timing: Stage = Stage()
    shots: Stage = Stage()
    validate_: Stage = Field(default=Stage(), alias="validate")  # `validate` shadows a BaseModel method
    render: Stage = Stage()
    audio: Stage = Stage()
    finish: Stage = Stage()

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    @model_serializer(mode="wrap")
    def _no_null_tts(self, handler):
        d = handler(self)
        if d.get("tts") is None:
            d.pop("tts", None)  # a recorded-voice part never shows it
        return d


class Approval(Strict):
    approved_at: UtcDateTime | None = None


class Approvals(Strict):
    stills: Approval = Approval()
    final: Approval = Approval()


class Post(Strict):
    url: str
    posted_at: UtcDateTime


class Posted(Strict):
    youtube: Post | None = None
    instagram: Post | None = None


class PartModel(Strict):
    schema_version: Literal[1] = 1
    id: PartId
    number: int = Field(ge=1, le=99)
    title: str
    stages: Stages = Stages()
    approvals: Approvals = Approvals()
    posted: Posted = Posted()
    voice_source: Literal["recorded", "tts"] = Field(default="recorded", description="recorded: an uploaded voice.mp3; "
                                                     "tts: the tts stage makes voice.mp3 from the script")

    @model_serializer(mode="wrap")
    def _omit_recorded(self, handler):
        d = handler(self)
        if d.get("voice_source") == "recorded":
            d.pop("voice_source")  # part.json as before
        return d

    @model_validator(mode="before")
    @classmethod
    def _drop_removed(cls, d):
        """thumbnails and the test render were removed (2026-11-23): older part.json files still name them"""
        if isinstance(d, dict):
            d = {k: v for k, v in d.items() if k != "thumbnail_choice"}
            if isinstance(d.get("stages"), dict):
                d["stages"] = {k: v for k, v in d["stages"].items() if k != "thumbnails"}
            if isinstance(d.get("approvals"), dict):
                d["approvals"] = {k: v for k, v in d["approvals"].items() if k != "test_render"}
        return d

    @model_validator(mode="after")
    def _id_matches_number(self):
        if self.id != f"part-{self.number:02d}":
            raise ValueError(f"id {self.id!r} does not match number {self.number}")
        return self


# --- phrases.json ---

class Word(Strict):
    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class Phrase(Strict):
    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    word_start: int = Field(ge=0, description="index of the first word")
    word_end: int = Field(ge=0, description="index of the last word (inclusive)")


def _check_spans(items, duration: float, what: str) -> None:
    prev_end = 0.0
    for i, x in enumerate(items):
        if not (prev_end <= x.start <= x.end <= duration):
            raise ValueError(f"{what}[{i}] {x.start}-{x.end}: times must increase, not overlap, "
                             f"and stay within 0-{duration}")
        prev_end = x.end


class PhrasesModel(Strict):
    schema_version: Literal[1] = 1
    duration: float = Field(gt=0)
    words: list[Word]
    phrases: list[Phrase]

    @model_validator(mode="after")
    def _times(self):
        _check_spans(self.words, self.duration, "words")
        _check_spans(self.phrases, self.duration, "phrases")
        nxt = 0
        for i, p in enumerate(self.phrases):
            if p.word_start != nxt or p.word_end < p.word_start or p.word_end >= len(self.words):
                raise ValueError(f"phrases[{i}] word range {p.word_start}-{p.word_end} must continue at {nxt}")
            nxt = p.word_end + 1
        if nxt != len(self.words):
            raise ValueError("phrases must cover every word")
        return self
