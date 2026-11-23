"""story.json: the shot plan the engine renders."""

from typing import Literal

from pydantic import Field, model_validator

from .base import Slug, Strict
from .library import Weather
from .series import Expression, FRAME_SIZE, Headwear, Legwear, Prop, PropKind, Top


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
    props: list[Prop] | None = Field(default=None, max_length=2, description="@hold: the props held from this shot on "
                                                                            "(the look's, with held hands replaced); "
                                                                            "none: the look's own")
    faces: list[FaceChange] = Field(default=[], description="face changes inside the shot, in frame order: expression "
                                                            "until the first, then each from its frame")
    mount: str | None = Field(default=None, description="@ride: the actor (a creature in this shot) this one rides; it "
                                                        "is drawn in the saddle and goes where its mount goes")


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
    end_card: EndCard | None = Field(default=None, description="every part's closing screen (older story.json files "
                                                               "may have none)")

    @model_validator(mode="after")
    def _known_size(self):
        if (self.width, self.height) not in FRAME_SIZE.values():
            raise ValueError(f"{self.width}x{self.height} is not a known frame size ({FRAME_SIZE})")
        return self
