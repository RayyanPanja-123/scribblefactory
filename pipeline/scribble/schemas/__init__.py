"""series.json / part.json / phrases.json / story.json / props.json / sets.json models. These are the source of truth; docs/schemas/ is generated."""

from datetime import datetime, timezone
from typing import Annotated, Literal, get_args

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


Expression = Literal["neutral", "happy", "sad", "angry", "surprised", "sleepy", "cheeky", "exhausted"]


class Top(Strict):
    style: Literal["plain", "suit", "tank", "shirt", "dress"] = "plain"
    color: HexColor
    accent_color: HexColor | None = Field(default=None, description="suit: the tie colour (no tie when null); "
                                                                     "dress: the wide hat's ribbon and flower")
    number: str | None = Field(default=None, pattern=r"^[0-9]{1,3}$", description="chest number on a white bib")


def _needs_color(m):
    if m.kind != "none" and m.color is None:
        raise ValueError(f"{m.kind} needs a color")
    return m


class Headwear(Strict):
    kind: Literal["none", "flat_cap", "postman_cap", "bowler", "straw_hat", "wide_hat"] = "none"
    color: HexColor | None = None
    _check = model_validator(mode="after")(_needs_color)


class Legwear(Strict):
    kind: Literal["none", "shorts", "ragged_shorts", "trousers"] = "none"
    color: HexColor | None = None
    _check = model_validator(mode="after")(_needs_color)


BuiltinProp = Literal["clipboard", "stopwatch", "bottle", "syringe", "apple", "medal"]
# a built-in prop, or the id of a custom one in library/props.json (checked against the library where it is loaded);
# "none" stays reserved: v2's "no prop"
def _not_none(v):
    if v == "none":
        raise ValueError("none is not a prop (use [] for no props)")
    return v


PropKind = Annotated[Slug, AfterValidator(_not_none)]


class Prop(Strict):
    kind: PropKind
    hand: Literal["left", "right"] = "right"


class CastMember(Strict):
    id: Slug
    name: str
    top: Top
    headwear: Headwear = Headwear()
    legwear: Legwear = Legwear()
    props: list[Prop] = Field(default=[], max_length=2, description="held props, one per hand")
    default_expression: Expression = "neutral"
    eyes: Literal["dots", "half_closed"]
    body: Slug = Field(default="stickman", description="stickman, or a creature id (built in or library/creatures.json):"
                                                       " drawn in top.color ($main) and top.accent_color ($accent); "
                                                       "eyes and mouth only, no costume")
    headless: bool = Field(default=False, description="creatures with a stump only: the stump instead of the head")
    approved_at: UtcDateTime | None = None

    @field_validator("props")
    @classmethod
    def _one_per_hand(cls, v):
        if len({p.hand for p in v}) != len(v):
            raise ValueError("props: one per hand")
        return v

    @model_validator(mode="after")
    def _headless_creature(self):
        if self.headless and self.body == "stickman":
            raise ValueError("headless: only a creature can be headless (set body to a creature id)")
        return self

    def look(self) -> str:
        """everything the cast sheet shows (hex case ignored): a change here needs a new approval"""
        return self.model_dump_json(exclude={"id", "name", "approved_at"}).lower()


def _cast_upgrade(c):
    """older cast entry -> v3, same look. v1: outfit_color becomes a plain top, everything else none/neutral.
    v2: the single prop becomes the props list (empty for kind none)."""
    if not isinstance(c, dict):
        return c
    c = dict(c)
    if "outfit_color" in c:
        c["top"] = {"style": "plain", "color": c.pop("outfit_color")}
    if "prop" in c:
        prop = c.pop("prop") or {}
        c["props"] = [prop] if prop.get("kind", "none") != "none" else []
    return c


class SeriesModel(Strict):
    schema_version: Literal[3] = 3
    slug: Slug
    title: str
    created_at: UtcDateTime
    status: Literal["draft", "active", "complete", "archived"] = "draft"
    parts: list[PartId] = []
    voice: Voice
    style: Style
    cast: list[CastMember] = []

    @model_validator(mode="before")
    @classmethod
    def _migrate_v1(cls, data):
        # v1 / v2 files are upgraded on load (approvals kept: the look is unchanged); saving writes v3
        if isinstance(data, dict) and data.get("schema_version", 1) in (1, 2):
            data = {**data, "schema_version": 3, "cast": [_cast_upgrade(c) for c in data.get("cast", [])]}
        return data

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


# --- library/props.json (custom props, shared by every series) ---

Point = tuple[float, float]


class PropShape(Strict):
    """one piece of a custom prop, in hand space: the hand at (0, 0), y down, x away from the body (canvas px; the
    figure is 512 x 1024, the built-in props span about -40..110). Drawn with the same wobbly ink as the built-ins."""
    shape: Literal["rect", "circle", "line", "poly"]
    pts: list[Point] = Field(min_length=1, max_length=24, description="rect: 2 corners; circle: the centre; "
                                                                      "line: 2+ points; poly: 3+ points (closed)")
    r: float | None = Field(default=None, gt=0, le=200, description="circle: the radius")
    fill: HexColor | None = Field(default=None, description="no fill: outline only (ignored for line)")
    width: float = Field(default=8, ge=0, le=24, description="outline / line width; 0: no outline")

    @model_validator(mode="after")
    def _fits(self):
        need = {"rect": (2, 2), "circle": (1, 1), "line": (2, 24), "poly": (3, 24)}[self.shape]
        if not need[0] <= len(self.pts) <= need[1]:
            raise ValueError(f"{self.shape} takes {need[0] if need[0] == need[1] else f'{need[0]}+'} points")
        if (self.shape == "circle") != (self.r is not None):
            raise ValueError("r is for circles, and every circle needs one")
        if any(abs(v) > 300 for p in self.pts for v in p):
            raise ValueError("points must stay within 300 px of the hand")
        return self


class CustomProp(Strict):
    id: Slug = Field(description="the prop kind used in cast props and @do eat / give")  # checked: _not_builtin
    name: str = Field(min_length=1, max_length=40)
    shapes: list[PropShape] = Field(min_length=1, max_length=40, description="drawn in order: later ones on top")

    @field_validator("id")
    @classmethod
    def _not_builtin(cls, v):
        if v in get_args(BuiltinProp) or v == "none":
            raise ValueError(f"{v} is a built-in prop" if v != "none" else "none is reserved")
        return v


class PropLibrary(Strict):
    schema_version: Literal[1] = 1
    props: list[CustomProp] = []

    @field_validator("props")
    @classmethod
    def _unique(cls, v):
        if dupes := sorted({p.id for p in v if sum(q.id == p.id for q in v) > 1}):
            raise ValueError(f"prop ids must be unique: {', '.join(dupes)}")
        return v


# --- library/sets.json (custom sets, shared by every series) ---

# the engine's hand-built sets (engine/page/world.js SETS) and whether they are indoor (back wall) or outdoor (can
# scroll: travel shots). The one Python list of them; a test keeps it in step with world.js.
BUILTIN_SETS = {"room": "indoor", "office": "indoor", "street": "outdoor", "dirt_road": "outdoor",
                "countryside": "outdoor", "orchard": "outdoor", "stadium": "outdoor"}
SetKind = Literal["indoor", "outdoor"]
Point3 = tuple[float, float, float]


class SetPiece(Strict):
    """one primitive of a custom set, in world units: actors stand on y = 0, z = 0, x in -2..2; the back wall of an
    indoor set is at z -2.6. Anything across the stage (|x| < 2.2) must sit behind z -1, nothing forward of z 0.6
    (the engine checks this stage clearance when it builds the set)."""
    shape: Literal["box", "cyl", "ball", "mound"]
    at: Point3 = Field(description="the centre")
    size: list[float] = Field(min_length=1, max_length=3, description="box: width, height, depth; cyl: top radius, "
                                                                      "bottom radius, height; ball: radius; "
                                                                      "mound: radius, height factor")
    color: HexColor
    backdrop: bool = Field(default=False, description="scenery that is never hidden behind an actor (walls, far hills)")
    outline: bool = True

    @model_validator(mode="after")
    def _fits(self):
        need = {"box": 3, "cyl": 3, "ball": 1, "mound": 2}[self.shape]
        if len(self.size) != need:
            raise ValueError(f"{self.shape} takes {need} size value{'s' if need > 1 else ''}")
        if any(not 0 <= v <= 80 for v in self.size) or not any(self.size):
            raise ValueError("sizes must be 0..80 and not all 0")
        if any(abs(v) > 80 for v in self.at):
            raise ValueError("pieces must stay within 80 units of the stage")
        return self


class CustomSet(Strict):
    id: Slug = Field(description="the name used in @set")  # checked: _not_builtin
    name: str = Field(min_length=1, max_length=40)
    kind: SetKind = Field(description="indoor: floor and back wall; outdoor: wide floor and sky, allows travel shots")
    floor: HexColor
    back: HexColor = Field(description="indoor: the back wall; outdoor: the sky")
    pieces: list[SetPiece] = Field(default=[], max_length=60, description="drawn in order")

    @field_validator("id")
    @classmethod
    def _not_builtin(cls, v):
        if v in BUILTIN_SETS:
            raise ValueError(f"{v} is a built-in set")
        return v


class SetLibrary(Strict):
    schema_version: Literal[1] = 1
    sets: list[CustomSet] = []

    @field_validator("sets")
    @classmethod
    def _unique(cls, v):
        if dupes := sorted({p.id for p in v if sum(q.id == p.id for q in v) > 1}):
            raise ValueError(f"set ids must be unique: {', '.join(dupes)}")
        return v


# --- library/creatures.json (non-human cast bodies, shared by every series) ---

CreatureRig = Literal["bird", "quadruped", "biped", "crawler"]
# part -> required, per rig (keep equal to engine/page/creatures.js RIGS)
RIG_PARTS: dict[str, dict[str, bool]] = {
    "bird": {"body": True, "head": True, "wing": True, "leg": True, "tail": False, "stump": False},
    "quadruped": {"body": True, "head": True, "leg_front": True, "leg_back": True, "tail": False, "stump": False},
    "biped": {"body": True, "head": True, "arm": True, "leg": True, "tail": False, "stump": False},
    "crawler": {"body": True, "head": False, "tail": False, "stump": False},
}
JOINT_OF = {"head": "neck", "stump": "neck", "wing": "wing", "tail": "tail", "leg": "hip", "leg_front": "shoulder",
            "leg_back": "hip", "arm": "shoulder"}
HAND_RIGS = {"biped"}  # the only rig that holds props, gives, carries and supports
# engine/page/creatures.js BUILTIN: id -> (rig, has a stump)
BUILTIN_CREATURES = {"chicken": ("bird", True), "cat": ("quadruped", True), "horse": ("quadruped", True),
                     "monkey": ("biped", True), "snake": ("crawler", True)}


class CreatureShape(Strict):
    """one piece of a creature part, in canvas px, facing right, y down: the body around the ground point under the
    creature, every other part around its joint, at rest (legs and arms hang down from it). A stickman stands about
    950 px tall; the card is 1024 px wide (x -512..512) and tall (y -1000..24 for the body)."""
    shape: Literal["rect", "circle", "ellipse", "line", "poly"]
    pts: list[Point] = Field(min_length=1, max_length=40, description="rect: 2 corners; circle / ellipse: the centre; "
                                                                      "line: 2+ points; poly: 3+ points (closed)")
    r: float | None = Field(default=None, gt=0, le=600, description="circle: radius; ellipse: x radius")
    ry: float | None = Field(default=None, gt=0, le=600, description="ellipse: y radius")
    rot: float = Field(default=0, ge=-180, le=180, description="ellipse: turn in degrees, clockwise")
    fill: HexColor | Literal["$main", "$accent"] | None = Field(
        default=None, description="$main: the cast member's top colour; $accent: its accent colour (else the "
                                  "creature's); none: outline only. For a line: its colour (default ink)")
    width: float = Field(default=8, ge=0, le=40, description="outline / line width; 0: no outline")

    @model_validator(mode="after")
    def _fits(self):
        need = {"rect": (2, 2), "circle": (1, 1), "ellipse": (1, 1), "line": (2, 40), "poly": (3, 40)}[self.shape]
        if not need[0] <= len(self.pts) <= need[1]:
            raise ValueError(f"{self.shape} takes {need[0] if need[0] == need[1] else f'{need[0]}+'} points")
        if (self.shape in ("circle", "ellipse")) != (self.r is not None):
            raise ValueError("r is for circles and ellipses, and each needs one")
        if (self.shape == "ellipse") != (self.ry is not None):
            raise ValueError("ry is for ellipses, and every ellipse needs one")
        if any(abs(v) > 1024 for p in self.pts for v in p):
            raise ValueError("points must stay within 1024 px")
        return self


class CreatureFace(Strict):
    eye: Point | None = Field(default=None, description="eye centre (head space; body space without a head): a dot "
                                                        "that blinks")
    mouth: Point | None = Field(default=None, description="mouth centre: opens while talking, hidden when shut")


class CustomCreature(Strict):
    id: Slug = Field(description="the body name used in series.json cast")  # checked: _not_builtin
    name: str = Field(min_length=1, max_length=40)
    rig: CreatureRig = Field(description="how it moves: bird, quadruped, biped (has hands), crawler")
    accent: HexColor = Field(default="#3a2a1e", description="$accent when the cast member has no accent colour")
    joints: dict[str, Point] = Field(description="where each part attaches, ground space: hip, shoulder, neck, wing, tail")
    face: CreatureFace = CreatureFace()
    parts: dict[str, list[CreatureShape]] = Field(description="part -> shapes, drawn in order (later on top)")

    @field_validator("id")
    @classmethod
    def _not_builtin(cls, v):
        if v in BUILTIN_CREATURES or v == "stickman":
            raise ValueError(f"{v} is a built-in body")
        return v

    @model_validator(mode="after")
    def _fits_rig(self):
        spec = RIG_PARTS[self.rig]
        if bad := sorted(set(self.parts) - set(spec)):
            raise ValueError(f"{', '.join(bad)}: not a {self.rig} part (parts: {', '.join(spec)})")
        if missing := [p for p, need in spec.items() if need and not self.parts.get(p)]:
            raise ValueError(f"a {self.rig} needs {', '.join(missing)}")
        if too_big := [p for p, shapes in self.parts.items() if not 1 <= len(shapes) <= 60]:
            raise ValueError(f"{', '.join(too_big)}: 1 to 60 shapes per part")
        need = {JOINT_OF[p] for p in self.parts if p != "body"} | ({"hip"} if self.rig != "crawler" else set())
        if missing := sorted(need - set(self.joints)):
            raise ValueError(f"joints: {', '.join(missing)} missing")
        if extra := sorted(set(self.joints) - need):
            raise ValueError(f"joints: {', '.join(extra)} not used by any part")
        return self


class CreatureLibrary(Strict):
    schema_version: Literal[1] = 1
    creatures: list[CustomCreature] = []

    @field_validator("creatures")
    @classmethod
    def _unique(cls, v):
        if dupes := sorted({p.id for p in v if sum(q.id == p.id for q in v) > 1}):
            raise ValueError(f"creature ids must be unique: {', '.join(dupes)}")
        return v


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
    # partner roles: give <-> receive, carry (2 carriers) <-> carried, support (1-2) <-> supported
    action: Literal["idle", "walk", "run", "talk", "point", "react", "wave", "ride",
                    "stagger", "lie", "collapse", "eat", "give", "receive", "carry", "carried", "support", "supported",
                    "cheer", "angry", "gasp"]
    start_pos: Pos
    end_pos: Pos | None = None
    facing: Literal["left", "right", "camera"]
    expression: Expression = Field(description="neutral: the cast member's default_expression")
    target: str | None = Field(default=None, description="give / receive: the other actor; carry / support: the "
                                                         "actor carried / supported")
    prop: PropKind | None = Field(default=None, description="eat / give: the prop eaten / handed over")


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
    # arrive eases to a stop, leave eases out from one; broken: parked, smoking, shaking
    action: Literal["arrive", "drive", "leave", "idle", "broken"]
    start_pos: Pos
    end_pos: Pos | None = None
    facing: Literal["left", "right"]  # side-view card: no camera facing
    riders: list[str] = Field(default=[], max_length=3, description="cast ids seated (actors with action ride, "
                                                                    "or wave/talk while riding)")
    variant: Literal["red", "green", "navy", "yellow"]


class Extra(Strict):
    """non-cast stickman: crowd (stands behind the stage in a mood) or runner (background runner); seeded look"""
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    kind: Literal["crowd", "runner"]
    action: Literal["cheer", "angry", "gasp", "neutral", "run"]  # crowd: a mood; runner: run
    start_pos: Pos
    end_pos: Pos | None = None
    facing: Literal["left", "right", "camera"]
    variant: int = Field(ge=0, description="seeds the extra's look (top, hat, colours, runner number)")


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
    extras: list[Extra] = []
    twist: bool = False
    travel: Travel | None = Field(default=None, description="travel shot: the world scrolls past the actors")


class Cue(Strict):
    frame: int
    kind: Literal["music_stop", "music_start", "low_hit", "whoosh", "pop", "bark"]


class EndCard(Strict):
    start_frame: int = Field(ge=0, description="shown from this frame to the end, over the last shot")
    text: str = Field(description='e.g. "Part 2 on my profile 👆"')


class StoryModel(Strict):
    schema_version: Literal[1] = 1
    fps: Literal[30] = 30
    width: Literal[1080] = 1080
    height: Literal[1920] = 1920
    duration_frames: int = Field(ge=1)
    seed: int
    shots: list[Shot]
    cues: list[Cue] = []
    end_card: EndCard | None = Field(default=None, description="non-final parts only; the final part has none")
