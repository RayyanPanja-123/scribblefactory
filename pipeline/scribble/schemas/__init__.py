"""series.json / part.json / phrases.json / story.json / props.json / sets.json models. These are the source of truth; docs/schemas/ is generated."""

from datetime import datetime, timezone
from typing import Annotated, Literal, get_args

from pydantic import (AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer,
                      field_validator, model_serializer, model_validator)


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
# wardrobe ids: like a slug, underscores allowed too (the built-ins are flat_cap, ragged_shorts...)
WardrobeId = Annotated[str, Field(pattern=r"^[a-z0-9]+([_-][a-z0-9]+)*$")]


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


Expression = Literal["neutral", "happy", "sad", "angry", "surprised", "sleepy", "cheeky", "exhausted", "worried"]


# --- wardrobe: clothing, hair and cosmetics, one item per slot (engine/page/wardrobe.js) ---

WardrobeSlotName = Literal["hair", "facial_hair", "headwear", "top", "legwear", "footwear", "back", "accessory", "face"]
WARDROBE_SLOTS: list[str] = list(get_args(WardrobeSlotName))
DRAW_ORDER = ["back", "legwear", "footwear", "top", "accessory", "face", "facial_hair", "hair", "headwear"]  # back to front
LIST_SLOTS = {"accessory", "face"}  # up to 3 items each
# the original costume pieces, drawn by hand-written code in stickman.js: id -> (slot, name). Keep equal to
# engine/page/wardrobe.js BUILTIN_WARDROBE (a test checks)
BUILTIN_WARDROBE: dict[str, tuple[str, str]] = {
    "plain": ("top", "Plain top"), "suit": ("top", "Suit"), "tank": ("top", "Tank top"), "shirt": ("top", "Shirt"),
    "dress": ("top", "Dress"), "flat_cap": ("headwear", "Flat cap"), "postman_cap": ("headwear", "Postman cap"),
    "bowler": ("headwear", "Bowler"), "straw_hat": ("headwear", "Straw hat"), "wide_hat": ("headwear", "Wide hat"),
    "shorts": ("legwear", "Shorts"), "ragged_shorts": ("legwear", "Ragged shorts"), "trousers": ("legwear", "Trousers"),
}
# Used when an imported cast names a wardrobe item without its colour. The hand-drawn built-ins need a concrete
# colour to render, while a library item can use its own default_color. A top with no colour: the cast member's
# own top gets "top"; a look's top keeps the cast member's top colour (CastMember._default_top_colors).
BUILTIN_WARDROBE_DEFAULT_COLORS = {
    "top": "#4a6fa5",
    "headwear": "#2e3a59",
    "legwear": "#3a3a3a",
}
WardrobeAnchor = Literal["head", "head_top", "face", "eyes", "mouth", "neck", "shoulders", "chest", "waist", "hips",
                         "back", "arms", "hands", "legs", "feet"]


def _id_key(key: str):
    """before-validator: a plain id string, or {"id": ...}, -> {key: id}"""
    def f(v):
        if isinstance(v, str):
            return {key: v}
        if isinstance(v, dict) and "id" in v:
            v = {**v}
            v.setdefault(key, v.pop("id"))
            v.pop("id", None)
        return v
    return f


class WardrobeSlot(Strict):
    """one worn wardrobe item: an id (built in or library/wardrobe.json) and an optional colour for colorable items.
    A plain id string is accepted. "none": nothing (in a look: takes the cast member's item off)."""
    id: WardrobeId
    color: HexColor | None = None

    @model_validator(mode="before")
    @classmethod
    def _plain(cls, v):
        return {"id": v} if isinstance(v, str) else v


def _slot_list(v):
    """a list slot (accessory, face): one value or a list; null / "none": empty"""
    if v is None or v == "none":
        return []
    return v if isinstance(v, list) else [v]


class Top(Strict):
    style: WardrobeId = Field(default="plain", description="the top's wardrobe id (\"id\" accepted too): built in "
                                                         "plain, suit, tank, shirt, dress, or a library top")
    color: HexColor | None = Field(default=None, description="none: the cast member's own top colour in a look, "
                                                             "else the default top colour")
    accent_color: HexColor | None = Field(default=None, description="suit: the tie colour (no tie when null); "
                                                                     "dress: the wide hat's ribbon and flower")
    number: str | None = Field(default=None, pattern=r"^[0-9]{1,3}$", description="chest number on a white bib")
    _plain = model_validator(mode="before")(_id_key("style"))


def _needs_color(m):
    # the built-ins have no colour of their own; a library item falls back to its default_color
    if m.kind in BUILTIN_WARDROBE and m.color is None:
        raise ValueError(f"{m.kind} needs a color")
    return m


def _default_builtin_color(v, slot: str):
    """Fill the render colour for a built-in item when an import omits it."""
    if v is None or v == "none":
        return v
    kind = v if isinstance(v, str) else v.get("kind", v.get("id")) if isinstance(v, dict) else None
    if kind in BUILTIN_WARDROBE and isinstance(v, dict) and v.get("color") is None:
        return {**v, "kind": kind, "color": BUILTIN_WARDROBE_DEFAULT_COLORS[slot]}
    if kind in BUILTIN_WARDROBE and isinstance(v, str):
        return {"kind": v, "color": BUILTIN_WARDROBE_DEFAULT_COLORS[slot]}
    return v


class Headwear(Strict):
    kind: WardrobeId = Field(default="none", description="wardrobe id (\"id\" or a plain string accepted too): built "
                                                       "in flat_cap, postman_cap, bowler, straw_hat, wide_hat, or a "
                                                       "library headwear; none")
    color: HexColor | None = None
    _plain = model_validator(mode="before")(_id_key("kind"))
    @model_validator(mode="before")
    @classmethod
    def _default_color(cls, v):
        return _default_builtin_color(v, "headwear")
    _check = model_validator(mode="after")(_needs_color)


class Legwear(Strict):
    kind: WardrobeId = Field(default="none", description="wardrobe id: built in shorts, ragged_shorts, trousers, or a "
                                                       "library legwear; none")
    color: HexColor | None = None
    _plain = model_validator(mode="before")(_id_key("kind"))
    @model_validator(mode="before")
    @classmethod
    def _default_color(cls, v):
        return _default_builtin_color(v, "legwear")
    _check = model_validator(mode="after")(_needs_color)


BuiltinProp = Literal["clipboard", "stopwatch", "bottle", "syringe", "apple", "medal"]
# a built-in prop, or the id of a custom one in library/props.json (checked against the library where it is loaded);
# "none" stays reserved: v2's "no prop"
def _not_none(v):
    if v == "none":
        raise ValueError("none is not a prop (use [] for no props)")
    return v


PropKind = Annotated[Slug, AfterValidator(_not_none)]


PropAngle = Annotated[float, Field(ge=-180, le=180, description="degrees the held prop leans, like a clock hand with "
                                   "the top tipped away from the body: 0 upright, 90 level, 75 = half past two in the "
                                   "right hand")]


class Prop(Strict):
    kind: PropKind
    hand: Literal["left", "right"] = "right"
    angle: PropAngle | None = Field(default=None, description="this character's own angle; null: the prop's")

    @model_serializer(mode="wrap")
    def _no_null_angle(self, handler):
        """an unset angle is left out: series.json and every approved cast look (CastMember.look) stay as they were"""
        d = handler(self)
        if d.get("angle") is None:
            d.pop("angle", None)
        return d


def _one_hand_each(v):
    if v is not None and len({p.hand for p in v}) != len(v):
        raise ValueError("props: one per hand")
    return v


class CastLook(Strict):
    """a named variant of a cast member's look (story: @look <cast>: <name>). Only what it sets changes; everything
    else stays the cast member's own. The character keeps its id, name, approval and drawing seed."""
    top: Top | None = None
    headwear: Headwear | None = None
    legwear: Legwear | None = None
    hair: WardrobeSlot | None = Field(default=None, description="null: unchanged; \"none\": taken off")
    facial_hair: WardrobeSlot | None = None
    footwear: WardrobeSlot | None = None
    back: WardrobeSlot | None = None
    accessory: list[WardrobeSlot] | None = Field(default=None, max_length=3, description="null: unchanged; []: none")
    face: list[WardrobeSlot] | None = Field(default=None, max_length=3)
    props: list[Prop] | None = Field(default=None, max_length=2, description="held props, one per hand ([]: none)")
    default_expression: Expression | None = None
    eyes: Literal["dots", "half_closed"] | None = None
    headless: bool | None = Field(default=None, description="creatures with a stump only")
    @field_validator("props")
    @classmethod
    def _one_per_hand(cls, v):
        return _one_hand_each(v)

    @field_validator("accessory", "face", mode="before")
    @classmethod
    def _lists(cls, v):
        return None if v is None else _slot_list(v)


class CastMember(Strict):
    id: Slug
    name: str
    top: Top
    headwear: Headwear = Headwear()
    legwear: Legwear = Legwear()
    hair: WardrobeSlot | None = Field(default=None, description="wardrobe slots: an id, {\"id\", \"color\"} or null")
    facial_hair: WardrobeSlot | None = None
    footwear: WardrobeSlot | None = None
    back: WardrobeSlot | None = None
    accessory: list[WardrobeSlot] = Field(default=[], max_length=3)
    face: list[WardrobeSlot] = Field(default=[], max_length=3)
    props: list[Prop] = Field(default=[], max_length=2, description="held props, one per hand")
    default_expression: Expression = "neutral"
    eyes: Literal["dots", "half_closed"]
    body: Slug = Field(default="human", description="creature id (built in or library/creatures.json). human (default) "
                                                    "and other humanoids are stickmen: face, expressions, costume. "
                                                    "Other rigs are drawn in top.color ($main) and top.accent_color "
                                                    "($accent), eyes and mouth only, no costume")
    headless: bool = Field(default=False, description="creatures with a stump only: the stump instead of the head")
    looks: dict[Slug, CastLook] = Field(default={}, description="named variants a story switches to with @look "
                                                               "<cast>: <name> (default: back to this entry's own)")
    approved_at: UtcDateTime | None = None

    @field_validator("props")
    @classmethod
    def _one_per_hand(cls, v):
        return _one_hand_each(v)

    @field_validator("headwear", "legwear", mode="before")
    @classmethod
    def _none_wear(cls, v):
        return {"kind": "none"} if v is None else v

    @field_validator("hair", "facial_hair", "footwear", "back", mode="before")
    @classmethod
    def _none_slot(cls, v):
        return None if v == "none" or (isinstance(v, dict) and v.get("id") == "none") else v

    @field_validator("accessory", "face", mode="before")
    @classmethod
    def _lists(cls, v):
        return [x for x in _slot_list(v) if x != "none"]

    def wardrobe(self) -> list[tuple[str, str]]:
        """(slot, id) of everything this cast member wears in any of its looks (nothing for none)"""
        out = []
        for m in [self, *self.looks.values()]:
            for slot, key in (("top", "style"), ("headwear", "kind"), ("legwear", "kind")):
                if (v := getattr(m, slot)) is not None and getattr(v, key) != "none":
                    out.append((slot, getattr(v, key)))
            for slot in ("hair", "facial_hair", "footwear", "back"):
                if (v := getattr(m, slot)) is not None and v.id != "none":
                    out.append((slot, v.id))
            for slot in ("accessory", "face"):
                out += [(slot, v.id) for v in getattr(m, slot) or [] if v.id != "none"]
        return out

    @field_validator("body", mode="before")
    @classmethod
    def _legacy_stickman(cls, v):
        return "human" if v == "stickman" else v  # before every cast member had a creature type

    @model_validator(mode="after")
    def _default_top_colors(self):
        # a stored cast always has concrete top colours: the engine swaps a look's whole top in
        if self.top.color is None:
            self.top.color = BUILTIN_WARDROBE_DEFAULT_COLORS["top"]
        for look in self.looks.values():
            if look.top is not None and look.top.color is None:
                look.top.color = self.top.color
        return self

    @model_validator(mode="after")
    def _headless_creature(self):
        # whether the body has a stump needs the library: io.cast_body_problems. Built-in human never has one.
        if self.headless and self.body == "human":
            raise ValueError("headless: a human has no stump (set body to a creature with one)")
        if "default" in self.looks:
            raise ValueError("looks: default is reserved (it means the cast member's own look)")
        if bad := [k for k, v in self.looks.items() if v.headless and self.body == "human"]:
            raise ValueError(f"looks: {', '.join(bad)}: a human has no stump")
        return self

    def with_look(self, name: str | None) -> "CastMember":
        """this cast member as it looks in a named look (None / default: as is)"""
        if not name or name == "default":
            return self
        look = self.looks[name]
        return self.model_copy(update={k: v for k in look.model_fields_set if (v := getattr(look, k)) is not None})

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
    card is 1024 x 1024 with the figure in the middle 512, the built-in props span about -40..110). Drawn with the same wobbly ink as the built-ins."""
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
    use_for: str | None = Field(default=None, max_length=200, description="when a story should use it (shown to the "
                                                                       "story AI; never changes the drawing)")
    shapes: list[PropShape] = Field(min_length=1, max_length=40, description="drawn in order: later ones on top")
    angle: PropAngle = 0
    grip: tuple[float, float] | None = Field(default=None, description="the point of the shapes the hand holds "
                                             "(default 0,0), e.g. the middle of a staff's shaft")

    @field_validator("grip")
    @classmethod
    def _grip_near(cls, v):
        if v is not None and any(abs(x) > 300 for x in v):
            raise ValueError("grip must stay within 300 px of the hand")
        return v

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
WeatherKind = Literal["rain", "snow", "fog", "wind", "storm"]  # @weather; "clear" is no weather (None)
Intensity = Literal["light", "medium", "heavy"]


class Weather(Strict):
    """scene weather, drawn in ink by the engine (weather.js): fog behind the cast, the rest in front"""
    kind: WeatherKind
    intensity: Intensity = "medium"


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
    use_for: str | None = Field(default=None, max_length=200, description="when a story should use it (shown to the "
                                                                       "story AI; never changes the drawing)")
    kind: SetKind = Field(description="indoor: floor and back wall; outdoor: wide floor and sky, allows travel shots")
    floor: HexColor
    back: HexColor = Field(description="indoor: the back wall; outdoor: the sky")
    pieces: list[SetPiece] = Field(default=[], max_length=60, description="drawn in order")
    default_weather: Weather | None = Field(default=None, description="weather each @set of this set starts with "
                                                                      "(until an @weather); none: clear")

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

CreatureRig = Literal["humanoid", "bird", "quadruped", "biped", "crawler"]
# part -> required, per rig (keep equal to engine/page/creatures.js RIGS). A humanoid is a stickman: no shape parts,
# only its build (proportions + head colour)
RIG_PARTS: dict[str, dict[str, bool]] = {
    "humanoid": {},
    "bird": {"body": True, "head": True, "wing": True, "leg": True, "tail": False, "stump": False},
    "quadruped": {"body": True, "head": True, "leg_front": True, "leg_back": True, "tail": False, "stump": False},
    "biped": {"body": True, "head": True, "arm": True, "leg": True, "tail": False, "stump": False},
    "crawler": {"body": True, "head": False, "tail": False, "stump": False},
}
JOINT_OF = {"head": "neck", "stump": "neck", "wing": "wing", "tail": "tail", "leg": "hip", "leg_front": "shoulder",
            "leg_back": "hip", "arm": "shoulder"}
HAND_RIGS = {"humanoid", "biped"}  # the rigs that hold props, give, carry and support
# engine/page/creatures.js BUILTIN: id -> (rig, has a stump)
BUILTIN_CREATURES = {"human": ("humanoid", False), "chicken": ("bird", True), "cat": ("quadruped", True),
                     "horse": ("quadruped", True), "monkey": ("biped", True), "snake": ("crawler", True)}


class HumanoidBuild(Strict):
    """a humanoid's proportions as factors of the stickman's (1 = the default human), and its head colour"""
    head: float = Field(default=1, ge=0.7, le=1.3, description="head size")
    body_w: float = Field(default=1, ge=0.7, le=1.3, description="body width")
    body_h: float = Field(default=1, ge=0.7, le=1.3, description="body height")
    leg: float = Field(default=1, ge=0.7, le=1.3, description="leg length")
    arm: float = Field(default=1, ge=0.7, le=1.3, description="arm length")
    head_color: HexColor = Field(default="#ffffff", description="head fill (skin)")


# --- actions: built-in ones are code in the engine; custom ones (library/actions.json) are keyframes it plays ---

# every built-in actor action and what it is (keep the names equal to engine/page/actions.js BUILTIN_ACTIONS):
# do: @do can ask for it; hands: needs a body with hands; moving: walks across the stage; partner: has a target
# actor; prop: names a prop; mood: a crowd mood too
ACTIONS: dict[str, frozenset[str]] = {k: frozenset(v) for k, v in {
    "idle": {"do"}, "walk": {"do", "moving"}, "run": {"do", "moving"}, "talk": {"do"}, "point": {"do"},
    "react": {"do"}, "wave": {"do"}, "ride": set(), "stagger": {"do", "moving"}, "lie": {"do"}, "collapse": {"do"},
    "eat": {"do", "prop"}, "give": {"do", "hands", "partner", "prop"}, "receive": {"partner"},
    "carry": {"do", "hands", "partner", "moving"}, "carried": {"partner"},
    "support": {"do", "hands", "partner", "moving"}, "supported": {"partner"},
    "cheer": {"do", "mood"}, "angry": {"do", "mood"}, "gasp": {"do", "mood"},
}.items()}
actions_with = lambda trait: {a for a, t in ACTIONS.items() if trait in t}  # noqa: E731


class ActionKey(Strict):
    """one pose of a custom action. Angles in degrees from straight down, + toward +x: on the front view screen right
    (the left arm hangs out at about -16, the right at +16); on a side action FORWARD, the way the figure faces
    (arms[0] is then the back arm, arms[1] the front arm, and + lean bends forward)"""
    t: float = Field(ge=0, le=1, description="when, as a share of the action's duration")
    arms: tuple[tuple[float, float], tuple[float, float]] | None = Field(
        default=None, description="[[upper arm, forearm bend] left, [upper arm, forearm bend] right]; none: at rest")
    legs: tuple[float, float] | None = Field(default=None, description="[left, right] thigh angles, -90..90 (rest -6, 6); the "
                                                                       "feet stay on the ground; none: at rest")
    knees: tuple[float, float] | None = Field(default=None, description="[left, right] knee bends, 0 (straight) to 170: "
                                                                          "on a side action the shin folds back, behind "
                                                                          "the figure; facing the camera the knees bend "
                                                                          "outward (a front squat); none: straight")
    lean: float = Field(default=0, ge=-60, le=60, description="whole figure, about the feet; + leans toward +x. With "
                                                             "bent knees it bends at the hips instead (legs stay put)")

    @model_validator(mode="after")
    def _ranges(self):
        if self.arms and any(not -180 <= v <= 180 for arm in self.arms for v in arm):
            raise ValueError("arms: angles -180..180")
        if self.legs and any(not -90 <= v <= 90 for v in self.legs):
            raise ValueError("legs: angles -90..90")
        if self.knees and any(not 0 <= v <= 170 for v in self.knees):
            raise ValueError("knees: bends 0..170")
        return self


class CustomAction(Strict):
    """an in-place move for humanoids (salute, bow, dance...): keyframes the engine blends between. @do <cast>:
    <id> plays it; other creatures stand idle through it."""
    id: Slug
    name: str = Field(min_length=1, max_length=40)
    use_for: str | None = Field(default=None, max_length=200, description="when a story should use it (shown to the "
                                                                       "story AI; never changes the drawing)")
    duration: float = Field(ge=0.2, le=10, description="seconds for one pass through the keys")
    loop: bool = Field(default=True, description="repeat for the whole shot; false: play once and hold the last key")
    facing: Literal["camera", "side"] = Field(default="camera", description="camera: front view; side: the figure "
                                                                            "turns to face left or right")
    move: float = Field(default=0, ge=-2.5, le=2.5, description="side only: units/s across the stage while it plays; "
                                                                "+ forward, - backward (a moonwalk), 0 in place")
    keys: list[ActionKey] = Field(min_length=1, max_length=40, description="in time order")

    @field_validator("id")
    @classmethod
    def _not_builtin(cls, v):
        if v in ACTIONS:
            raise ValueError(f"{v} is a built-in action")
        return v

    @model_validator(mode="after")
    def _moves_sideways(self):
        if self.move and self.facing != "side":
            raise ValueError("move: only a side action crosses the stage (set facing to side)")
        if self.move and abs(self.move) < 0.3:
            raise ValueError("move: at least 0.3 units/s, or 0 to stay in place")
        if self.facing == "side" and any(k.arms and min(k.arms[0][1], k.arms[1][1]) < 0 for k in self.keys):
            raise ValueError("arms: on a side action both arms are in profile and an elbow only bends forward: "
                             "bends 0..180 (the - mirror bend is for the left arm of a camera action)")
        return self

    @field_validator("keys")
    @classmethod
    def _in_order(cls, v):
        if any(b.t < a.t for a, b in zip(v, v[1:])):
            raise ValueError("keys must be in time order (t ascending)")
        return v


class ActionLibrary(Strict):
    schema_version: Literal[1] = 1
    actions: list[CustomAction] = []

    @field_validator("actions")
    @classmethod
    def _unique(cls, v):
        ids = [a.id for a in v]
        if dupes := sorted({i for i in ids if ids.count(i) > 1}):
            raise ValueError(f"duplicate action id: {', '.join(dupes)}")
        return v


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
    use_for: str | None = Field(default=None, max_length=200, description="when a story should use it (shown to the "
                                                                       "story AI; never changes the drawing)")
    rig: CreatureRig = Field(description="how it moves: humanoid (a stickman: face, costume, hands), bird, quadruped, "
                                         "biped (has hands), crawler")
    accent: HexColor = Field(default="#3a2a1e", description="$accent when the cast member has no accent colour")
    joints: dict[str, Point] = Field(default={}, description="where each part attaches, ground space: hip, shoulder, "
                                                             "neck, wing, tail (not for a humanoid)")
    face: CreatureFace = CreatureFace()
    parts: dict[str, list[CreatureShape]] = Field(default={}, description="part -> shapes, drawn in order (later on "
                                                                          "top; not for a humanoid)")
    build: HumanoidBuild | None = Field(default=None, description="humanoid only: proportions and head colour")

    @field_validator("id")
    @classmethod
    def _not_builtin(cls, v):
        if v in BUILTIN_CREATURES or v == "stickman":
            raise ValueError(f"{v} is a built-in body")
        return v

    @model_validator(mode="after")
    def _fits_rig(self):
        if self.rig == "humanoid":
            if self.parts or self.joints or self.face != CreatureFace():
                raise ValueError("a humanoid is a stickman: no parts, joints or face, only a build")
            if self.build is None:
                self.build = HumanoidBuild()
            return self
        if self.build is not None:
            raise ValueError("build is for a humanoid only")
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


# --- library/wardrobe.json (custom clothing, hair and cosmetics, shared by every series) ---

class WardrobeLayer(Strict):
    """one ink shape of a wardrobe item, in canvas px around its anchor (the default human: head radius 150, body 184
    wide and 300 tall, legs 220, arms 175). x: across (+ outward on the paired anchors shoulders / arms / hands / legs /
    feet, drawn on both sides, mirrored on the left); y: down (arms and legs: along the limb from the shoulder / hip).
    Torso anchors scale with body_w x body_h, arms and hands with arm, legs and feet with leg; head anchors (head,
    head_top, face, eyes, mouth) are in head space: they scale with the head and turn with the face."""
    shape: Literal["rect", "circle", "ellipse", "line", "poly"]
    anchor: WardrobeAnchor
    pts: list[Point] = Field(min_length=1, max_length=40, description="rect: 2 corners; circle / ellipse: the centre; "
                                                                      "line: 2+ points; poly: 3+ points (closed)")
    r: float | None = Field(default=None, gt=0, le=400, description="circle: radius; ellipse: x radius")
    ry: float | None = Field(default=None, gt=0, le=400, description="ellipse: y radius")
    rot: float = Field(default=0, ge=-180, le=180, description="ellipse: turn in degrees, clockwise")
    fill: HexColor | Literal["$color"] | None = Field(
        default=None, description="$color: the worn colour (the cast member's for a colorable item, else the item's "
                                  "default_color); none: outline only. For a line: its colour (default ink)")
    width: float = Field(default=8, ge=0, le=40, description="outline / line width; 0: no outline")
    behind: bool = Field(default=False, description="drawn behind the head and body (long hair, a cape)")
    when: list[Expression] | None = Field(default=None, description="only with these expressions (blush: happy)")

    @model_validator(mode="after")
    def _fits(self):
        need = {"rect": (2, 2), "circle": (1, 1), "ellipse": (1, 1), "line": (2, 40), "poly": (3, 40)}[self.shape]
        if not need[0] <= len(self.pts) <= need[1]:
            raise ValueError(f"{self.shape} takes {need[0] if need[0] == need[1] else f'{need[0]}+'} points")
        if (self.shape in ("circle", "ellipse")) != (self.r is not None):
            raise ValueError("r is for circles and ellipses, and each needs one")
        if (self.shape == "ellipse") != (self.ry is not None):
            raise ValueError("ry is for ellipses, and every ellipse needs one")
        if any(abs(v) > 600 for p in self.pts for v in p):
            raise ValueError("points must stay within 600 px of the anchor")
        return self


class WardrobeItem(Strict):
    id: WardrobeId = Field(description="the id a cast slot uses")  # checked: _not_builtin
    name: str = Field(min_length=1, max_length=40)
    slot: WardrobeSlotName
    layers: list[WardrobeLayer] = Field(default=[], max_length=60, description="drawn in order: later ones on top")
    colorable: bool = Field(default=True, description="the cast member's colour replaces default_color in $color")
    default_color: HexColor = "#6b4f3a"

    @field_validator("id")
    @classmethod
    def _not_builtin(cls, v):
        if v in BUILTIN_WARDROBE or v == "none":
            raise ValueError(f"{v} is a built-in wardrobe item" if v != "none" else "none is reserved")
        return v


class WardrobeLibrary(Strict):
    schema_version: Literal[1] = 1
    wardrobe: list[WardrobeItem] = []

    @field_validator("wardrobe")
    @classmethod
    def _unique(cls, v):
        ids = [x.id for x in v]
        if dupes := sorted({i for i in ids if ids.count(i) > 1}):
            raise ValueError(f"wardrobe ids must be unique: {', '.join(dupes)}")
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


class FaceChange(Strict):
    frame: int = Field(ge=0, description="the face changes from this video frame on (the word that names the mood)")
    expression: Expression


class Actor(Strict):
    cast_id: str
    # partner roles: give <-> receive, carry (2 carriers) <-> carried, support (1-2) <-> supported
    action: Slug = Field(description="a built-in action (ACTIONS: idle, walk, run, talk, point, react, wave, ride, "
                                     "stagger, lie, collapse, eat, give, receive, carry, carried, support, supported, "
                                     "cheer, angry, gasp) or a custom one from library/actions.json")
    start_pos: Pos
    end_pos: Pos | None = None
    facing: Literal["left", "right", "camera"]
    expression: Expression = Field(description="neutral: the cast member's default_expression")
    target: str | None = Field(default=None, description="give / receive: the other actor; carry / support: the "
                                                         "actor carried / supported")
    prop: PropKind | None = Field(default=None, description="eat / give: the prop eaten / handed over")
    look: Slug | None = Field(default=None, description="the cast member's named look (@look), none: its own")
    faces: list[FaceChange] = Field(default=[], description="face changes inside the shot, in frame order: expression "
                                                            "until the first, then each from its frame")


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
    weather: Weather | None = Field(default=None, description="@weather (or the set's default_weather); none: clear")


class Cue(Strict):
    frame: int
    kind: Literal["music_stop", "music_start", "low_hit", "whoosh", "pop", "bark"]


class Strike(Strict):
    """@fx lightning: one bolt + a brief flash, at the first word of the line after the directive"""
    frame: int = Field(ge=0)
    target: str | None = Field(default=None, description="cast id the bolt lands near; none: behind the stage")


class EndCard(Strict):
    start_frame: int = Field(ge=0, description="a black card shown from this frame to the end: non-final parts cut to it after the line before the sign-off (validate.end_card_start)")
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
    lightning: list[Strike] = Field(default=[], max_length=3, description="@fx lightning strikes, by frame")
    end_card: EndCard | None = Field(default=None, description="non-final parts only; the final part has none")
