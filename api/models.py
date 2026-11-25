"""Response models (docs/openapi.json -> web/src/api/types.ts)."""

from typing import Literal

from pydantic import BaseModel

from pipeline.scribble.schemas import PartModel, Posted, SeriesModel, Stage

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
    waiting: list[str]  # "stills" | "final" | "cast:<id>"


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
    disk_usage: int
    posted: PostedCounts


class StoredFile(BaseModel):
    """a file of a series folder (frames aside): what it is and how big, for the Overview"""
    slug: str
    part: str | None  # part-01, or None for a series-level file (cast sheets)
    path: str  # its folder under library/database/storage
    filename: str
    size_bytes: int
    content_type: str
    duration_s: float | None  # audio and video
    sha256: str
    created_at: str  # first seen
    updated_at: str  # the file's modified time


class Notification(BaseModel):
    id: str
    title: str
    message: str
    slug: str
    series_title: str
    href: str


class PartSummary(BaseModel):
    id: str
    missing: bool = False  # listed in series.json but no part.json: only id is set
    number: int | None = None
    title: str | None = None
    stages: dict[str, StageStatus] = {}
    approvals: dict[str, str | None] = {}  # stills/final -> approved_at (ISO) or None
    posted: Posted | None = None
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
    versions: dict[str, int]  # file -> modified time: the ?v of its media url, new per re-render
    qa: dict | None
    upload_md: str | None
    story_md: str | None
    tts_script: str | None  # script-for-tts.txt: what the voice reads (prep writes it; a story package too)
    voice_duration: float | None
    frames_bytes: int
    part_bytes: int  # the whole part folder, frames included
    busy: str | None
    audio_notice: str | None = None
    tts_lines: list["TtsLine"] | None = None  # a TTS part's voice, line by line (voice-tts.json)


class TtsLine(BaseModel):
    line: int  # story.md line
    speaker: str | None  # cast id; None: the narrator
    voice: str
    speed: float
    text: str
    clip: str  # the cached clip: /api/tts/clip/<clip>
    start: float
    end: float
    pause: float | None = None  # @pause before it
    pace: float | None = None  # @pace speed factor


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
