"""series.json / part.json / phrases.json / story.json models. These are the source of truth; docs/schemas/ is generated."""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer,
                      field_validator, model_validator)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Naive datetimes are rejected; aware ones are normalised to UTC and written as ...Z.
UtcDateTime = Annotated[
    AwareDatetime,
    AfterValidator(lambda d: d.astimezone(timezone.utc)),
    PlainSerializer(lambda d: d.isoformat().replace("+00:00", "Z"), return_type=str, when_used="json"),
]

# [0-9] not \d: pydantic's regex engine treats \d as any Unicode digit.
Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
PartId = Annotated[str, Field(pattern=r"^part-[0-9]{2}$")]
HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- series.json ---

class Voice(Strict):
    provider: str = "freetts.ai"
    voice_name: str
    notes: str = ""


class Style(Strict):
    preset: str
    locked: bool = False
    captions: bool = True  # burned-in captions in final.mp4


class CastMember(Strict):
    id: Slug
    name: str
    outfit_color: HexColor
    eyes: Literal["dots", "half_closed"]
    approved_at: UtcDateTime | None = None


class SeriesModel(Strict):
    schema_version: Literal[1] = 1
    slug: Slug
    title: str
    created_at: UtcDateTime
    status: Literal["draft", "active", "complete", "archived"] = "draft"
    parts: list[PartId] = []
    voice: Voice
    style: Style
    cast: list[CastMember] = []

    @field_validator("parts")
    @classmethod
    def _unique_parts(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("parts contains duplicates")
        return v

    @field_validator("cast")
    @classmethod
    def _unique_cast(cls, v):
        # approvals are merged by cast id on save, so ids must be unique
        if len({c.id for c in v}) != len(v):
            raise ValueError("cast contains duplicate ids")
        return v


# --- part.json ---

class Stage(Strict):
    status: Literal["pending", "running", "done", "failed"] = "pending"
    started_at: UtcDateTime | None = None
    finished_at: UtcDateTime | None = None
    error: str | None = None
    inputs_hash: str | None = None  # sha256 of the stage's input files at the last successful run


class Stages(Strict):
    prep: Stage = Stage()
    import_check: Stage = Stage()
    timing: Stage = Stage()
    shots: Stage = Stage()
    validate_: Stage = Field(default=Stage(), alias="validate")  # `validate` shadows a BaseModel method
    render: Stage = Stage()
    audio: Stage = Stage()
    finish: Stage = Stage()
    thumbnails: Stage = Stage()

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)


class Approval(Strict):
    approved_at: UtcDateTime | None = None


class Approvals(Strict):
    stills: Approval = Approval()
    test_render: Approval = Approval()
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
    thumbnail_choice: str | None = None
    posted: Posted = Posted()

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


# --- story.json (shot plan) ---
# No "static" move on purpose: the camera always creeps.

Pos = tuple[float, float]  # [x, z] on the ground plane


class Camera(Strict):
    angle: Literal["wide", "medium", "close", "low", "high", "over_shoulder"]
    move: Literal["push_in", "pull_out", "truck_left", "truck_right", "crane_up", "crane_down"]
    speed: float = Field(ge=0.05, le=1.0)
    roll_deg: float = 0


class Actor(Strict):
    cast_id: str
    action: Literal["idle", "walk", "run", "talk", "point", "react", "wave", "ride"]
    start_pos: Pos
    end_pos: Pos | None = None
    facing: Literal["left", "right", "camera"]
    expression: Literal["neutral", "happy", "sad", "angry", "surprised", "sleepy"]


class Travel(Strict):
    speed: float = Field(gt=0, description="world scroll speed, units/s; actors run in place against it")


class Animal(Strict):
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    kind: Literal["dog"]
    action: Literal["run", "idle", "bark"]
    start_pos: Pos
    end_pos: Pos | None = None
    facing: Literal["left", "right"]  # side-view card: no camera facing
    variant: Literal["brown", "black", "tan", "white_patches"]


class Vehicle(Strict):
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    kind: Literal["car"]
    action: Literal["arrive", "drive", "leave", "idle"]  # arrive eases to a stop, leave eases out from one
    start_pos: Pos
    end_pos: Pos | None = None
    facing: Literal["left", "right"]  # side-view card: no camera facing
    riders: list[str] = Field(default=[], max_length=3, description="cast ids seated (actors with action ride, "
                                                                    "or wave/talk while riding)")
    variant: Literal["red", "green", "navy", "yellow"]


class Shot(Strict):
    id: str = Field(pattern=r"^s[0-9]{2,}$")
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0, description="exclusive")
    set: str = Field(description="set preset name, e.g. office, street, room")
    phrase_range: tuple[int, int] = Field(description="[first, last] phrase indices into phrases.json, inclusive")
    camera: Camera
    actors: list[Actor] = []
    animals: list[Animal] = []
    vehicles: list[Vehicle] = []
    twist: bool = False
    travel: Travel | None = Field(default=None, description="travel shot: the world scrolls past the actors")


class Cue(Strict):
    frame: int
    kind: Literal["music_stop", "music_start", "low_hit", "whoosh", "pop", "bark"]


class StoryModel(Strict):
    schema_version: Literal[1] = 1
    fps: Literal[30] = 30
    width: Literal[1080] = 1080
    height: Literal[1920] = 1920
    duration_frames: int = Field(ge=1)
    seed: int
    shots: list[Shot]
    cues: list[Cue] = []
