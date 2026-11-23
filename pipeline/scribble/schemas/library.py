"""The shared library catalogs: props, sets, world objects, creatures, actions and wardrobe (library/<kind>.json)."""

from typing import Literal, get_args

from pydantic import Field, field_validator, model_validator

from .base import HexColor, Slug, Strict, WardrobeId
from .series import BUILTIN_WARDROBE, BuiltinProp, Expression, PropAngle, WardrobeAnchor, WardrobeSlotName


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


WorldObjectCategory = Literal["vehicle", "container", "furniture", "equipment", "debris", "other"]
WorldObjectCapability = Literal["move", "carry", "enter", "ride", "open", "close", "break", "steal", "remove"]
WorldObjectCarryMode = Literal["none", "one-hand", "two-hand", "vehicle"]


class WorldObject(Strict):
    """Reusable geometry and interaction capabilities for a large scene object.

    Unlike a Prop, a WorldObject is not owned by a cast member and is not attached to a hand. Its state belongs to
    the scene and can persist across shots. The renderer currently accepts the same primitives as set pieces so the
    asset can be introduced without adding a second drawing language.
    """
    id: Slug
    name: str = Field(min_length=1, max_length=40)
    category: WorldObjectCategory = "other"
    capabilities: list[WorldObjectCapability] = Field(default_factory=list, max_length=9)
    carry_mode: WorldObjectCarryMode = "none"
    pieces: list[SetPiece] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _capabilities(self):
        caps = set(self.capabilities)
        if "carry" in caps and self.carry_mode == "none":
            raise ValueError("a carryable world object needs carry_mode")
        if self.carry_mode != "none" and "carry" not in caps:
            raise ValueError("a world object's carry_mode requires the carry capability")
        if self.carry_mode == "two-hand" and "carry" not in caps:
            raise ValueError("two-hand objects must be carryable")
        return self


class WorldObjectInstance(Strict):
    """A named placement of a WorldObject in a set; its id is the story target."""
    id: Slug
    object: Slug
    at: Point3
    visible: bool = True


class CustomSet(Strict):
    id: Slug = Field(description="the name used in @set")  # checked: _not_builtin
    name: str = Field(min_length=1, max_length=40)
    use_for: str | None = Field(default=None, max_length=200, description="when a story should use it (shown to the "
                                                                       "story AI; never changes the drawing)")
    kind: SetKind = Field(description="indoor: floor and back wall; outdoor: wide floor and sky, allows travel shots")
    floor: HexColor
    back: HexColor = Field(description="indoor: the back wall; outdoor: the sky")
    pieces: list[SetPiece] = Field(default=[], max_length=60, description="drawn in order")
    objects: list[WorldObjectInstance] = Field(default=[], max_length=60,
                                                description="placed World Objects, targetable by staged interactions")
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


class WorldObjectLibrary(Strict):
    schema_version: Literal[1] = 1
    objects: list[WorldObject] = []

    @field_validator("objects")
    @classmethod
    def _unique(cls, v):
        if dupes := sorted({o.id for o in v if sum(q.id == o.id for q in v) > 1}):
            raise ValueError(f"world object ids must be unique: {', '.join(dupes)}")
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
    ease: Literal["linear", "in-out", "back-out"] = Field(
        default="in-out", description="how the pose moves into this key from the one before: in-out (eases both ends), "
                                      "linear (steady), back-out (overshoots a little, then settles)")

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
    fill: HexColor | Literal["$color", "$accent"] | None = Field(
        default=None, description="$color: the worn colour (the cast member's for a colorable item, else the item's "
                                  "default_color); $accent: the worn accent (else default_accent); none: outline "
                                  "only. For a line: its colour (default ink)")
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
    default_accent: HexColor = Field(default="#3a2a1e", description="$accent when the cast member sets no accent")

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
