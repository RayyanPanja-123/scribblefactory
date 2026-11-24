"""story.json: the shot plan the engine renders."""

from typing import Literal

from pydantic import Field, model_serializer, model_validator

from .base import Slug, Strict
from .library import ItemLayer, Weather, omit_defaults
from .series import Expression, FRAME_SIZE, Headwear, Legwear, Prop, PropKind, Top


# --- story.json (shot plan) ---
# No "static" move on purpose: the camera always creeps.

Pos = tuple[float, float]  # [x, z] on the ground plane


CamAngle = Literal["wide", "medium", "close", "low", "high", "over_shoulder"]
CamMove = Literal["push_in", "pull_out", "truck_left", "truck_right", "crane_up", "crane_down"]


class Camera(Strict):
    angle: CamAngle
    move: CamMove | Literal["hold"] = Field(description="hold: no move (only from @cam; the planner always creeps)")
    speed: float = Field(ge=0.05, le=1.0)
    roll_deg: float = 0
    # @cam only (left out of story.json at their defaults, so plans without @cam stay as they were)
    dutch_deg: float = Field(default=0, ge=-25, le=25, description="@cam dutch: a tilted horizon (degrees, + rolls "
                                                                     "clockwise); glides in on a twist shot")
    shake: bool = Field(default=False, description="@cam shake: a camera shake at the shot's first frame")
    forced: bool = Field(default=False, description="set by @cam: the validator lets its angle repeat the previous "
                                                     "shot's and a twist keep @cam's move / dutch")

    @model_serializer(mode="wrap")
    def _omit_cam_defaults(self, handler):
        d = handler(self)
        for k, v in (("dutch_deg", 0), ("shake", False), ("forced", False)):
            if d.get(k) == v:
                d.pop(k, None)
        return d


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
    props: list[Prop] | None = Field(default=None, max_length=2, description="@hold: the props held from this shot on "
                                                                            "(the look's, with held hands replaced); "
                                                                            "none: the look's own")
    faces: list[FaceChange] = Field(default=[], description="face changes inside the shot, in frame order: expression "
                                                            "until the first, then each from its frame")
    mount: str | None = Field(default=None, description="@ride: the actor (a creature in this shot) this one rides; it "
                                                        "is drawn in the saddle and goes where its mount goes")
    item: str | None = Field(default=None, description="pickup / drop / open / close / push / sit / stand / enter / "
                                                       "exit: the @item tag acted on (left out when none)")
    approach: float | None = Field(default=None, gt=0, lt=1, description="an item action after a walk to the item: "
                                                                         "the share of the shot the walk (start_pos "
                                                                         "to end_pos) takes; the action plays after")

    behind: list[float] = Field(default=[], description="an approach walk passes behind the actors standing at these x "
                                                         "(a dip in z around each; engine actions.js passBehind)")

    @model_serializer(mode="wrap")
    def _omit_item(self, handler):
        return omit_defaults(handler(self), type(self), ("item", "approach", "behind"))


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


class ShotItem(Strict):
    """@item: a World Item (library/objects.json card) on stage for this shot, flying a path when start and end
    differ (@do <tag>: fly left | right)"""
    id: Slug = Field(description="the @item tag")
    object: Slug = Field(description="the World Item it draws")
    layer: ItemLayer
    start_pos: Pos
    end_pos: Pos | None = None
    y: float = Field(description="height of its base (a sky / back card: its middle) in world units")
    facing: Literal["left", "right"] = "right"
    state: Slug | None = Field(default=None, description="none: the item's first state")
    switch: "ItemSwitch | None" = Field(default=None, description="open / close: the state it turns to, and when")
    riders: list[str] = Field(default=[], description="cast ids seated inside it (enter) for the whole shot, its "
                                                      "seats in order")

    @model_serializer(mode="wrap")
    def _omit_defaults(self, handler):
        return omit_defaults(handler(self), type(self), ("switch", "riders"))


class ItemSwitch(Strict):
    frame: int = Field(ge=0, description="the state flips here (a short tween either side)")
    to: Slug


ShotItem.model_rebuild()


class Extra(Strict):
    """non-cast stickman: a seeded runner or a crowd member with optional team costume/prop."""
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    kind: Literal["crowd", "runner"]
    action: Literal["cheer", "angry", "gasp", "neutral", "fight", "run"]  # crowd: a mood; runner: run
    group: str | None = Field(default=None, pattern=r"^[a-z0-9_-]+$")
    target_group: str | None = Field(default=None, pattern=r"^[a-z0-9_-]+$")
    start_pos: Pos
    end_pos: Pos | None = None
    facing: Literal["left", "right", "camera"]
    variant: int = Field(ge=0, description="seeds the extra's look (top, hat, colours, runner number)")
    top: Top | None = None
    headwear: Headwear | None = None
    legwear: Legwear | None = None
    props: list[Prop] = Field(default_factory=list, max_length=2)


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
    items: list[ShotItem] = Field(default=[], description="@item World Items on stage (left out of story.json when "
                                                          "there are none, so older plans keep their bytes)")

    @model_serializer(mode="wrap")
    def _omit_items(self, handler):
        return omit_defaults(handler(self), type(self), ("items",))


class Cue(Strict):
    frame: int
    kind: Literal["music_stop", "music_start", "background_music", "low_hit", "whoosh", "pop", "bark"]
    track: str | None = None
    volume: float | None = Field(default=None, ge=0, le=1)


class Strike(Strict):
    """@fx lightning: one bolt + a brief flash, at the first word of the line after the directive"""
    frame: int = Field(ge=0)
    target: str | None = Field(default=None, description="cast id the bolt lands near; none: behind the stage")


class EndCard(Strict):
    start_frame: int = Field(ge=0, description="where the story ends (duration_frames): finish appends the silent end "
                                                "screen there for validate.END_SCREEN_S")
    text: str = Field(description='its headline, "Follow for more" (finish adds the handles from library/settings.json)')


class StoryModel(Strict):
    schema_version: Literal[1] = 1
    fps: Literal[30] = 30
    width: Literal[1080, 1920] = 1080
    height: Literal[1920, 1080] = 1920
    duration_frames: int = Field(ge=1)
    seed: int
    shots: list[Shot]
    cues: list[Cue] = []
    lightning: list[Strike] = Field(default=[], max_length=3, description="@fx lightning strikes, by frame")
    shakes: list[int] = Field(default=[], description="@fx shake: frames the camera (engine) and the captions (finish) "
                                                      "shake on; older story.json files have none")
    end_card: EndCard | None = Field(default=None, description="every part's closing screen (older story.json files "
                                                               "may have none)")

    @model_validator(mode="after")
    def _known_size(self):
        if (self.width, self.height) not in FRAME_SIZE.values():
            raise ValueError(f"{self.width}x{self.height} is not a known frame size ({FRAME_SIZE})")
        return self
