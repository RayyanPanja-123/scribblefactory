"""series.json: the series, its voice and style, and its cast with their wardrobe and props."""

from typing import Annotated, Literal, get_args

from pydantic import AfterValidator, Field, field_validator, model_serializer, model_validator

from .base import HexColor, PartId, Slug, Strict, UtcDateTime, WardrobeId


# --- series.json ---

class TtsVoice(Strict):
    """a voice on the Kokoro TTS server (settings tts_url): its id and speaking speed"""
    id: str = Field(min_length=1, max_length=60, description="Kokoro voice id, e.g. am_michael (settings tts_voices)")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class Voice(Strict):
    provider: str = "freetts.ai"
    voice_name: str
    notes: str = ""
    # word -> respelling for the voice only (script-for-tts.txt); captions keep the word. One token each, so the
    # voice keeps story.md's word count: e.g. {"Negro": "Neh-groh"}
    pronunciations: dict[str, str] = {}
    tts: TtsVoice | None = Field(default=None, description="the narrator's TTS voice for parts with voice_source "
                                                           "tts (none: settings tts_voice)")

    @model_serializer(mode="wrap")
    def _no_null_tts(self, handler):
        d = handler(self)
        if d.get("tts") is None:
            d.pop("tts", None)  # left out unset: series.json as before
        return d

    @field_validator("pronunciations")
    @classmethod
    def _one_token(cls, v):
        for word, say in v.items():
            if len(word.split()) != 1 or len(say.split()) != 1:
                raise ValueError(f"pronunciations {word!r}: {say!r}: word and respelling must be one token each "
                                 "(hyphens ok, no spaces)")
        return v


class Style(Strict):
    preset: str
    locked: bool = False
    captions: bool = True  # burned-in captions in final.mp4
    aspect: Literal["9:16", "16:9"] = "9:16"  # every part's frame: 9:16 = 1080x1920 (Shorts), 16:9 = 1920x1080


FRAME_SIZE = {"9:16": (1080, 1920), "16:9": (1920, 1080)}  # aspect -> (width, height) px


Expression = Literal["neutral", "happy", "cheer", "sad", "angry", "surprised", "sleepy", "cheeky", "exhausted", "worried", "dead",
                     "smug", "proud", "love", "excited", "relieved", "laughing", "wink", "furious", "annoyed", "disgusted", "crying", "scared", "embarrassed", "jealous", "guilty", "confused", "thinking", "suspicious", "shocked", "deadpan", "bored", "facepalm_ready", "dizzy", "drunk", "knocked_out", "evil", "crazy", "blank", "sick"]


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


Flame = Literal["off", "low", "high"]
FLAME_DESC = ("non-humanoid creatures only: fire on the mane, tail and hooves, eyes glowing (off | low | high). "
              "Left out of the saved file when unset, so older casts and their approvals stay as they were")


FLAME_COLOR_DESC = ("the flame's outer colour; the middle layer and the core (and the glowing eyes) are lighter mixes "
                    "of it. Unset: fire (red, orange, yellow core)")


def _drop_null_flame(d):
    for k in ("flame", "flame_color"):
        if isinstance(d, dict) and d.get(k) is None:
            d.pop(k, None)
    return d


def _drop_null_accent(self, nxt):
    """an unset accent is left out of the saved file, so casts saved before accents existed stay byte-identical"""
    d = nxt(self)
    if isinstance(d, dict) and d.get("accent") is None:
        d.pop("accent", None)
    return d


class WardrobeSlot(Strict):
    """one worn wardrobe item: an id (built in or library/wardrobe.json) and an optional colour for colorable items.
    A plain id string is accepted. "none": nothing (in a look: takes the cast member's item off)."""
    id: WardrobeId
    color: HexColor | None = None
    accent: HexColor | None = Field(default=None, description="the accent ($accent layers) of a recolourable library item")
    _ser = model_serializer(mode="wrap")(_drop_null_accent)

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
                                                                     "dress: the wide hat's ribbon and flower; "
                                                                     "a library top: its $accent layers")
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
    accent: HexColor | None = Field(default=None, description="the accent ($accent layers) of a recolourable library item")
    _ser = model_serializer(mode="wrap")(_drop_null_accent)
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
    accent: HexColor | None = Field(default=None, description="the accent ($accent layers) of a recolourable library item")
    _ser = model_serializer(mode="wrap")(_drop_null_accent)
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
    flame: Flame | None = Field(default=None, description="null: unchanged. " + FLAME_DESC)
    flame_color: HexColor | None = Field(default=None, description="null: unchanged. " + FLAME_COLOR_DESC)

    @model_serializer(mode="wrap")
    def _no_null_flame(self, nxt):
        return _drop_null_flame(nxt(self))

    @field_validator("props")
    @classmethod
    def _one_per_hand(cls, v):
        return _one_hand_each(v)

    @field_validator("accessory", "face", mode="before")
    @classmethod
    def _lists(cls, v):
        return None if v is None else _slot_list(v)


def worn(m) -> list[tuple[str, str]]:
    """(slot, id) of the wardrobe one CastMember or one CastLook puts on (unset and none left out)"""
    out = []
    for slot, key in (("top", "style"), ("headwear", "kind"), ("legwear", "kind")):
        if (v := getattr(m, slot)) is not None and getattr(v, key) != "none":
            out.append((slot, getattr(v, key)))
    for slot in ("hair", "facial_hair", "footwear", "back"):
        if (v := getattr(m, slot)) is not None and v.id != "none":
            out.append((slot, v.id))
    for slot in ("accessory", "face"):
        out += [(slot, v.id) for v in getattr(m, slot) or [] if v.id != "none"]
    return out


class CastMember(Strict):
    id: Slug
    name: str
    top: Top = Top()
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
    flame: Flame | None = Field(default=None, description="null: off. " + FLAME_DESC)
    flame_color: HexColor | None = Field(default=None, description=FLAME_COLOR_DESC)
    voice: TtsVoice | None = Field(default=None, description="the TTS voice of this member's spoken lines "
                                   "(`<id>: line` in story.md) in parts with voice_source tts. Left out of the saved "
                                   "file when unset; never part of the look (no new approval)")
    looks: dict[Slug, CastLook] = Field(default={}, description="named variants a story switches to with @look "
                                                               "<cast>: <name> (default: back to this entry's own)")
    approved_at: UtcDateTime | None = None

    @field_validator("props")
    @classmethod
    def _one_per_hand(cls, v):
        return _one_hand_each(v)

    @model_serializer(mode="wrap")
    def _no_null_flame(self, nxt):
        d = _drop_null_flame(nxt(self))
        if isinstance(d, dict) and d.get("voice") is None:
            d.pop("voice", None)
        return d

    @field_validator("flame")
    @classmethod
    def _flame_off(cls, v):
        return None if v == "off" else v  # off is the default: stored as unset, so the look key never changes

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
        return [x for m in [self, *self.looks.values()] for x in worn(m)]

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
        return self.model_dump_json(exclude={"id", "name", "approved_at", "voice"}).lower()


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
