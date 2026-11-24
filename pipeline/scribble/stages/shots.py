"""shots: story.md directives + phrases.json + series cast -> story.json. Rule-based and seeded, no AI.

Each phrase gets a shot starting at its first word (pauses stay with the earlier shot); shots over
MAX_SHOT_FRAMES split into equal parts. Directive state (@set, @cast, @dogs, @car, @do, !!) is read at a phrase's first
word. @do overrides the named actors (and the car) for every shot of the one line after it.
The output must pass the validator, otherwise nothing is written.
"""

import math
import random
import re
import zlib
from pathlib import Path
from typing import NamedTuple

from ..io import (LIBRARY_FILES, atomic_write_json, library_of, load_part, load_series, cast_body_problems, creature_bodies, creature_halves, creature_wardrobe, custom_actions,
                  custom_moves,
                  outdoor_sets,
                  prop_kinds, set_kinds, set_weather, wardrobe_slots,
                  unknown_cast_props)
from ..schemas import (FRAME_SIZE, BUILTIN_CREATURES, BUILTIN_SETS, BUILTIN_WARDROBE, HAND_RIGS, Prop, Top, Headwear, Legwear,
                       actions_with, Actor, FaceChange, Animal, Camera, Cue, EndCard, Extra, PhrasesModel, SeriesModel,
                       Shot, StoryModel, Strike, Travel, Vehicle)
from ..validate import (CAR_SPEED, CROWD_Z, DOG_RUN_SPEED, MAX_SHOT_FRAMES, MOODS, OUTDOOR_SETS, SPEEDS,
                        custom_speeds, end_frame, validate)
from .prep import (BUILTIN_PROPS, DO_CAR, FX_LIGHTNING, FX_MODES, MARKER_RE, clean_markdown, mark_directives, parse_do,
                   parse_face, parse_hold, parse_lightning, parse_look, parse_ride, parse_weather, ride, RIDE_ACTIONS)
from .. import background_music
from .runner import StageError
from .validate import load_model

INPUTS = ["story.md", "phrases.json", "../series.json", *(f"../../{f}" for f in LIBRARY_FILES)]
OUTPUTS = ["story.json"]

FPS = 30
END_TEXT = "Follow for more"  # the end screen's headline; finish adds the handles from library/settings.json
DEFAULT_SET = "room"
DEFAULT_CAST_SIZE = 2      # first N series cast members when story.md has no @cast
ANGLES = ["wide", "medium", "close", "low", "high", "over_shoulder"]
ESTABLISHING = "wide"      # first shot of the part and after each set change; if the previous shot was already
                           # wide, the first other angle in ANGLES (no-repeat wins)
MOVES = ["push_in", "pull_out", "truck_left", "truck_right", "crane_up", "crane_down"]
SPEED = (0.15, 0.35)
TWIST_ROLL = (6.0, 10.0)   # degrees, sign seeded
STAGE_X = 1.0              # starting cast spread across -STAGE_X..STAGE_X, z = 0
BOUNDS = (-2.0, 2.0)       # x range a walk/run must end inside
MOVE_SPEED = {"walk": 1.2, "run": 2.5, "stagger": 0.6}  # units/s
MIN_SPEED = {a: SPEEDS[a][0] for a in MOVE_SPEED}  # shortened moves never go slower than the validator allows
NEEDS_HANDS = actions_with("hands")  # creatures without hands can still be carried or supported
GROUP_SPEED = {"carry": 0.9, "support": 0.8}  # @do carry / support: the group walks toward the stage centre
HOLD_GAP = 0.42            # carry / support: a holder stands this far (x) beside the held actor (engine actions.js)
MIN_GAP = 0.8              # actors at least this far apart in x at the start and end of every shot
HUMAN_HALF = MIN_GAP / 2   # half a stickman's width: two of them MIN_GAP apart touch; wider bodies keep their half
MAX_ON_STAGE = round((BOUNDS[1] - BOUNDS[0]) / MIN_GAP) + 1  # 6: that many fit side by side MIN_GAP apart
# A crowded scene (more @cast than MAX_ON_STAGE) gets a second row: whoever the scene features (named in its lines
# or in an @do) stands in front, the rest stand behind in the gaps between them, idle, smaller by perspective.
BACK_Z = -0.9              # just inside the stage clearance line (set props sit behind z -1.0)
MAX_CAST = 2 * MAX_ON_STAGE  # front row + back row
TRAVEL_Z = 0.3             # travel shots: each actor seeded in z -0.3..0.3 so a pack reads as a group
# dogs (@dogs N): ids dog1..dogN; colours from a seeded order of the variants, unique until all are used
MAX_DOGS = 6
DOG_VARIANTS = ["brown", "black", "tan", "white_patches"]
DOG_GAP = 0.6              # travel: a dog never gets closer than this to the rearmost actor (x, so also 2D)
DOG_STEP = 0.35            # x stagger between dogs on one stage edge
CHASE_STEP = 0.5           # travel: x spacing between neighbouring dogs in a chase pack (min) ...
CHASE_JITTER = 0.05        # ... plus up to this, seeded
DOG_Z = 0.45               # travel: dogs alternate z bands 0.1..0.45 / -0.45..-0.1
DOG_CLOSE = (0.15, 0.35)   # travel: units/s the pack gains on the actors (on top of the scroll), one rate per shot
# car (@car arrive | ride | leave | off): one car "car1", colour seeded per part
CAR_MODES = ("arrive", "ride", "leave", "off")
CAR_VARIANTS = ["red", "green", "navy", "yellow"]
CAR_SEATS = 3              # riders per car
CAR_HALF = 1.4             # half the car's length (world units), for spacing
CAR_BESIDE = 1.9           # arrive: car centre stops this far (x) from the subject, on the subject's outer side
CAR_Z = -0.6               # arrive / leave: the car stays a little behind the actors' line
CAR_RUN_D = 5.0            # arrive / leave: distance driven (from / to off-screen), shortened for short shots
CAR_TRAVEL_SPEED = 4.0     # ride: travel-shot scroll speed (units/s)
# extras (@crowd <mood> [N], named teams, and crowd wardrobe/props; all reset on a set change unless repeated)
CROWD_DEFAULT, CROWD_MAX = 8, 12
CROWD_W = 2.8              # crowd spread across x -2.8..2.8
CROWD_GAP = 0.55           # min x between neighbours in a crowd row
CROWD_ONE_ROW = 7          # more than this: a second row behind, offset half a step
CROWD_FRONT = (-1.3, -1.7)  # front row z (stadium: STADIUM_FRONT, behind the rail at z -1.6)
STADIUM_FRONT = (-1.85, -2.1)
CROWD_BACK = (-2.2, -2.8)   # second row z (indoors: no further back than INDOOR_BACK, the wall is at -2.6)
INDOOR_BACK = -2.5
MAX_RUNNERS = 6
RUNNER_SPEED = 2.6         # background runners' leg speed, units/s (inside RUN_SPEED)
RUNNER_GAP = 0.6           # min x between runners, and (travel) from the cast
RUNNER_Z = {"travel": (-1.6, -0.8), "cross": (-2.6, -2.0)}  # crossers run behind the crowd's front row
DOG_EDGE_X = 1.8           # non-travel: dogs stand at |x| >= this ...
DOG_EDGE_GAP = 0.9         # ... and at least this far (x) outside every actor's start/end, so cards never overlap

# Lexicons match lowercase words with punctuation and a trailing 's stripped. First match in the phrase wins.
ACTIONS = {
    **dict.fromkeys(["walk", "walks", "walked", "walking", "went", "came", "left"], "walk"),
    **dict.fromkeys(["run", "runs", "ran", "running", "rushed", "chased", "sprint", "sprinted", "sprinting", "dodging"],
                    "run"),
    # no "showed": it fires on "showed up"
    **dict.fromkeys(["point", "points", "pointed", "pointing", "shows"], "point"),
    **dict.fromkeys(["wave", "waves", "waved", "waving"], "wave"),
    **dict.fromkeys(["gasped", "froze", "frozen", "shocked", "collapsed", "collapse", "dizzy", "cramps", "hopped"],
                    "react"),
    **dict.fromkeys(["stagger", "staggers", "staggered", "staggering", "stumbled", "stumbling", "wobbled"], "stagger"),
    **dict.fromkeys(["lay", "lying", "napped"], "lie"),
    **dict.fromkeys(["fainted", "faints"], "collapse"),
    **dict.fromkeys(["eat", "eats", "ate", "eating"], "eat"),
}
EXPRESSIONS = {
    **dict.fromkeys(["happy", "glad", "smiled", "smiles", "laughed", "laughs", "laughing", "grinned", "joy",
                     "cheerfully", "comfortably", "giggled", "giggles", "cheered", "proudly", "delighted"], "happy"),
    **dict.fromkeys(["sad", "cried", "cries", "sighed", "tears", "lonely", "upset", "cramps", "collapsed", "sobbed",
                     "wept", "weeping", "miserable"], "sad"),
    **dict.fromkeys(["angry", "mad", "furious", "furiously", "yelled", "shouted", "screamed", "stomped", "stomps",
                     "fuming", "raged", "rage", "glared", "scowled", "snapped", "gritted", "grumbled", "annoyed",
                     "tomato"], "angry"),
    **dict.fromkeys(["surprised", "shocked", "gasped", "wow", "stunned", "chased", "astonished", "amazed"], "surprised"),
    **dict.fromkeys(["worried", "nervous", "scared", "afraid", "terrified", "panicked", "trembled"], "worried"),
    **dict.fromkeys(["sleepy", "tired", "yawned", "yawns", "asleep", "nap", "napped", "slept", "dizzy", "exhaustion",
                     "exhausted"], "sleepy"),
}
DIRECTIONS = {"left": -1, "right": 1}
# an @do action that is an emotion sets the face when the line names no mood (a "neutral" face shows the cast's
# default_expression, e.g. a cheeky smirk on someone stomping in rage)
ACTION_FACE = {"angry": "angry", "gasp": "surprised", "react": "surprised", "cheer": "happy"}


def token(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"['’]s\W*$", "", word.lower()))


def seed_for(slug: str, part_number: int) -> int:
    return zlib.crc32(slug.encode()) + part_number  # stable across runs (unlike hash())


class Tag(NamedTuple):
    """the staging state of one spoken word (read by field name: a new field can't shift the others)"""
    set: str
    cast: tuple
    twist: bool  # a twist starts here
    dogs: int
    car: str
    do: "tuple | None"
    crowd: dict
    crowd_wardrobe: dict
    runners: int
    looks: dict
    holds: dict  # @hold: {cast id: {hand: prop kind, or None for an empty hand}}
    weather: "Weather | None"
    strike: "tuple | None"
    face: "dict | None"
    bg_music: "tuple | None"
    rides: dict = {}  # @ride: {rider cast id: mount cast id}, kept across @set changes until "@ride <rider>: none"
    shake: bool = False  # @fx shake: the first word of the line after it (camera shake, story.shakes)


def tag_words(md: str, cast_ids: list[str], default_cast: list[str], props=BUILTIN_PROPS, looks_of=None, actions=(),
              weather_of=None, wardrobe=None, creatures=None, handless=None):
    """Return (words, [Tag]) from
    story.md, words as prep's script has them. do: (story.md line, @do clauses) for the words of the line after an
    @do, else None. crowd: (mood, N) or None. A set change resets crowd and runners. looks: {cast id: look name} set
    by @look, kept for the rest of the part (default drops it). looks_of: cast id -> its look names. weather: Weather
    or None (clear), from @weather until the next @weather or @set; @set starts weather_of[set] (custom sets'
    default_weather), else clear. strike: (story.md line, target) on the first word after an @fx lightning, else None.
    face: {cast id: expression} for the words of the line after an @face, else None. holds: @hold, kept like looks.
    handless: cast id -> "a <rig>" for creatures without hands (they cannot @hold)."""
    text, directives = mark_directives(md)
    set_, cast, twist_next, dogs, car, do = DEFAULT_SET, tuple(default_cast), False, 0, "off", None
    bg_music = None
    crowd, crowd_wardrobe, runners, looks, strike, face = {}, {}, 0, {}, None, None
    holds, rides, shake_next = {}, {}, False
    weather_of = weather_of or {}
    weather = weather_of.get(set_)
    looks_of = looks_of if looks_of is not None else {c: [] for c in cast_ids}
    words, tags = [], []
    for tok in clean_markdown(text).split():
        m = MARKER_RE.match(tok)
        if not m:
            words.append(tok)
            tags.append(Tag(set=set_, cast=cast, twist=twist_next, dogs=dogs, car=car, do=do,
                            crowd={k: dict(v) for k, v in crowd.items()},
                            crowd_wardrobe={k: dict(v) for k, v in crowd_wardrobe.items()}, runners=runners,
                            looks=dict(looks), holds={k: dict(v) for k, v in holds.items()}, weather=weather, strike=strike, face=face, bg_music=bg_music,
                            rides=dict(rides), shake=shake_next))
            twist_next, strike, shake_next = False, None, False
        elif m[1] == "!":
            twist_next = True
        elif m[1] == "/":
            do = face = None  # the @do / @face line is over
        else:
            line, d = directives[int(m[1])]
            name, _, arg = d.strip().partition(" ")
            arg = arg.strip()
            if name == "set" and arg:
                if arg != set_:
                    crowd, crowd_wardrobe, runners = {}, {}, 0  # extras belong to a set
                set_, weather = arg, weather_of.get(arg)
            elif name == "weather":
                weather = parse_weather(arg, line)
            elif name == "cast":
                ids = [x.strip() for x in arg.split(",") if x.strip()]
                if not ids:
                    raise StageError(f"story.md line {line}: @cast needs at least one cast id")
                unknown = [x for x in ids if x not in cast_ids]
                if unknown:
                    raise StageError(f"story.md line {line}: @cast: unknown cast id {', '.join(unknown)} "
                                     f"(series cast: {', '.join(cast_ids)}; add with cast-add)")
                if len(ids) > MAX_CAST:
                    raise StageError(f"story.md line {line}: @cast: {len(ids)} on stage, at most {MAX_CAST} fit "
                                     f"({MAX_ON_STAGE} in front, {MAX_ON_STAGE} behind); split the scene, or use "
                                     f"@crowd for a group in the background")
                cast = tuple(ids)
            elif name == "dogs" and arg.isdigit() and int(arg) <= MAX_DOGS:
                dogs = int(arg)
            elif name == "car" and arg in CAR_MODES:
                car = arg
            elif name == "fx" and arg in FX_MODES:
                shake_next = arg == "shake"  # caption effect (finish); a shake also shakes the camera (engine)
            elif name == "fx" and arg.split()[:1] == [FX_LIGHTNING]:
                strike = (line, parse_lightning(arg, line, cast_ids, props))
            elif name == "do":
                do = (line, tuple(parse_do(arg, line, cast_ids, props, actions)))
            elif name == "crowd":
                group, spec = parse_crowd(arg, line)
                if spec is None:
                    crowd.pop(group, None)
                else:
                    if spec["mood"] == "fight" and group in crowd:
                        spec["n"] = crowd[group]["n"]
                    crowd[group] = spec
            elif name == "crowd-look":
                group, costume = parse_crowd_look(arg, line, wardrobe or set())
                crowd_wardrobe[group] = {**crowd_wardrobe.get(group, {}), **costume}
            elif name == "crowd-weapon":
                group, weapon = parse_crowd_weapon(arg, line, props)
                crowd_wardrobe[group] = {**crowd_wardrobe.get(group, {}), "props": [Prop(kind=weapon, hand="right")]}
            elif name == "runners" and arg.isdigit() and int(arg) <= MAX_RUNNERS:
                runners = int(arg)
            elif name == "face":
                face = {**(face or {}), **parse_face(arg, line, cast_ids)}
            elif name == "sfx":
                pass  # sound effect: the audio stage reads it
            elif name == "background-music":
                bg_music = background_music.parse(arg, line)
            elif name == "look":
                who, look = parse_look(arg, line, looks_of, creatures)
                looks = {**{k: v for k, v in looks.items() if k not in who}, **({w: look for w in who} if look != "default" else {})}
            elif name == "hold":
                who, hand, kind = parse_hold(arg, line, cast_ids, props, handless)
                for w in who:
                    holds[w] = {**holds.get(w, {}), **dict.fromkeys(["left", "right"] if hand == "both" else [hand], kind)}
            elif name == "ride":  # lasts until "none" or the part's end; a @set keeps it (the horse goes along)
                rides = ride(rides, *parse_ride(arg, line, cast_ids, creatures), line)
            else:
                raise StageError(f"story.md line {line}: bad directive @{d.strip()} (use @set <name>, @cast a, b, "
                                 f"@dogs 0-{MAX_DOGS}, @car {' | '.join(CAR_MODES)}, @fx {' | '.join(FX_MODES)} | lightning [target], "
                                 f"@weather <type> [intensity], "
                                 f"@do <cast>: <action>, @look <cast>: <look>, @hold <cast>: <prop> [hand], @ride <cast>: <creature>, @face <cast>: <expression>, @sfx <id>, "
                                 f"@crowd <mood> [N] | <group> <mood> [N] | off, @crowd-look <group>: <wardrobe ids>, "
                                 f"@crowd-weapon <group>: <prop>, or @runners 0-{MAX_RUNNERS})")
    return words, tags


def parse_crowd(arg: str, line: int):
    """Return (group, spec). Legacy syntax uses the implicit default group."""
    words = arg.split()
    if words == ["off"]:
        return "default", None
    group, rest = "default", words
    if words and words[0] not in MOODS and words[0] not in {"off"}:
        group, rest = words[0], words[1:]
    if rest == ["off"]:
        if not re.fullmatch(r"[a-z0-9_-]+", group):
            raise StageError(f"story.md line {line}: bad directive @crowd {arg.strip()}")
        return group, None
    valid_tail = rest[1].isdigit() and 1 <= int(rest[1]) <= CROWD_MAX if len(rest) == 2 and rest[0] != "fight" else \
        bool(len(rest) == 2 and re.fullmatch(r"[a-z0-9_-]+", rest[1])) if rest and rest[0] == "fight" else len(rest) == 1
    if not re.fullmatch(r"[a-z0-9_-]+", group) or not 1 <= len(rest) <= 2 or rest[0] not in (*MOODS, "fight") or not valid_tail:
        raise StageError(f"story.md line {line}: bad directive @crowd {arg.strip()} (use @crowd "
                         f"{' | '.join(sorted(MOODS | {'fight'}))} [1-{CROWD_MAX}, default {CROWD_DEFAULT}], "
                         f"@crowd <group> <mood> [N], or @crowd off)")
    return group, {"mood": rest[0], "n": CROWD_DEFAULT if rest[0] == "fight" or not len(rest) == 2 or not rest[1].isdigit() else int(rest[1]),
                   "target": rest[1] if rest[0] == "fight" and len(rest) == 2 else None}


def parse_crowd_look(arg: str, line: int, wardrobe):
    group, sep, ids = arg.partition(":")
    ids = [x.strip() for x in ids.split(",") if x.strip()]
    if not sep or not re.fullmatch(r"[a-z0-9_-]+", group.strip()) or not ids or len(ids) > 3:
        raise StageError(f"story.md line {line}: bad directive @crowd-look {arg.strip()} (use @crowd-look <group>: top, headwear, legwear)")
    slots = {**{k: v[0] for k, v in BUILTIN_WARDROBE.items()}, **(wardrobe or {})}
    costume = {}
    for wid in ids:
        slot = slots.get(wid)
        if not slot or slot not in {"top", "headwear", "legwear"}:
            raise StageError(f"story.md line {line}: bad directive @crowd-look {arg.strip()} (unknown or unsupported wardrobe item {wid})")
        value = {"style": wid, "color": "#536b82"} if slot == "top" else {"kind": wid, "color": "#334455"}
        costume[slot] = value
    return group.strip(), costume


def parse_crowd_weapon(arg: str, line: int, props):
    group, sep, weapon = arg.partition(":")
    group, weapon = group.strip(), weapon.strip()
    if not sep or not re.fullmatch(r"[a-z0-9_-]+", group) or not re.fullmatch(r"[a-z0-9_-]+", weapon) or weapon not in set(props):
        raise StageError(f"story.md line {line}: bad directive @crowd-weapon {arg.strip()} (use @crowd-weapon <group>: <prop>)")
    return group, weapon


def crowd_extras(group: str, spec: dict, seed: int, set_: str, indoor: bool = False, group_index: int = 0, group_count: int = 1,
                 costume: dict | None = None) -> list[Extra]:
    """n crowd extras facing the camera: one row (n <= CROWD_ONE_ROW), else a front row of ceil(n/2) and a back row
    offset half a step. Neighbours in a row stay CROWD_GAP+ apart in x. Spots and looks are seeded per part, set and
    crowd size: the same people stand in the same places across cuts. (The engine then moves or drops, per shot,
    any extra whose head would overlap a cast member's head on screen.)"""
    mood, n, target = spec["mood"], spec["n"], spec.get("target")
    R = random.Random(f"{seed}:crowd:{set_}:{group}:{n}")
    # two rows: the front row takes one more than the back, so every back extra fits in a gap between two front ones
    n1 = math.ceil((n + 1) / 2) if n > CROWD_ONE_ROW else n
    n2 = n - n1
    step = 2 * CROWD_W / n1
    jit = max(0.0, min(0.1, (step - CROWD_GAP) / 2 - 0.001))
    front = STADIUM_FRONT if set_ == "stadium" else CROWD_FRONT
    back = (CROWD_BACK[0], max(CROWD_BACK[1], INDOOR_BACK) if indoor else CROWD_BACK[1])
    gap0 = (n1 - 1 - n2) // 2  # the back row sits in the middle gaps
    out = []
    # Named teams face each other: the first two teams occupy opposite halves. The legacy default remains wide.
    side = -1 if group_count > 1 and group_index == 0 else 1 if group_count > 1 else 0
    lo, hi = (-CROWD_W, 0.0) if side < 0 else (0.0, CROWD_W) if side > 0 else (-CROWD_W, CROWD_W)
    for row, (count, zr, off) in enumerate(((n1, front, 0.5), (n2, back, 1.0 + gap0))):
        for i in range(count):
            x = lo + (hi - lo) * ((i + off) / max(n1, 1)) + R.uniform(-jit, jit)
            out.append(Extra(id=f"{group}-{len(out) + 1}", kind="crowd", action=mood,
                             group=group, target_group=target,
                             start_pos=(round(x, 3), round(R.uniform(*zr), 2)),
                             facing="right" if side < 0 else "left" if side > 0 else "camera",
                             variant=R.randrange(1000), **(costume or {})))
    return out


def _clear(a: float, b: float, c: float, gap: float) -> bool:
    """the run from x a to x b stays at least gap from x c the whole way"""
    lo, hi = min(a, b), max(a, b)
    return (c - hi if c > hi else lo - c if c < lo else 0.0) >= gap - 1e-9


def _runner_spot(cast_x, taken, gain, way, jitter) -> float:
    """travel: start x for the next runner. Nearest the frame centre first (so they're seen), over a 0.1 grid in
    -2.2..2.2: the whole run (x0 .. x0 + gain) keeps RUNNER_GAP from every cast x, and from the runners already
    placed (same gain, so their gap holds). Nothing fits: ahead of everyone, pulling away."""
    grid = sorted((round(k / 10 + jitter, 3) for k in range(-22, 23)), key=lambda x: (abs(x), -way * x))
    for x0 in grid:
        if all(_clear(x0, x0 + gain, c, RUNNER_GAP) for c in cast_x) and all(abs(x0 - t) >= RUNNER_GAP for t in taken):
            return x0
    edge = max(cast_x + taken) if way > 0 else min(cast_x + taken)
    return edge + way * RUNNER_GAP


def runner_extras(n, seed, sid, seconds, actors, travel_dir=0, travel_speed=0.0, indoor=False) -> list[Extra]:
    """n background runners, RUNNER_GAP+ apart in x. Travel shot: they run the travel way in the background, legs at
    RUNNER_SPEED (the scroll plus their own gain), each on a spot whose whole run stays RUNNER_GAP+ clear of the cast
    (see _runner_spot). Otherwise they cross the background from off-screen, all one way (seeded per shot), so they
    never pass each other."""
    R, out = random.Random(f"{seed}:runners:{sid}"), []
    d = R.choice((-1, 1))
    lo, hi = RUNNER_Z["cross"]  # (-2.6, -2.0): indoors no further back than INDOOR_BACK (the wall)
    cross_z = (max(lo, INDOOR_BACK) if indoor else lo, hi)
    for i in range(n):
        variant = R.randrange(1000)
        if travel_dir:
            xs = [x for a in actors for x in (a.start_pos[0], (a.end_pos or a.start_pos)[0])] or [0.0]
            gain = travel_dir * max(0.0, RUNNER_SPEED - travel_speed) * seconds
            x0 = _runner_spot(xs, [e.start_pos[0] for e in out], gain, travel_dir, R.uniform(0, 0.1))
            z = R.uniform(*RUNNER_Z["travel"])
            out.append(Extra(id=f"runner{i + 1}", kind="runner", action="run", start_pos=(round(x0, 3), round(z, 2)),
                             end_pos=(round(x0 + gain, 3), round(z, 2)),
                             facing="right" if travel_dir > 0 else "left", variant=variant))
        else:
            x0, z = -d * (3.0 + 0.9 * i + R.uniform(0, 0.25)), R.uniform(*cross_z)
            out.append(Extra(id=f"runner{i + 1}", kind="runner", action="run", start_pos=(round(x0, 3), round(z, 2)),
                             end_pos=(round(x0 + d * RUNNER_SPEED * seconds, 3), round(z, 2)),
                             facing="right" if d > 0 else "left", variant=variant))
    return out


def spread(cast) -> dict[str, float]:
    """even spots across -STAGE_X..STAGE_X, widened for big casts so neighbours stay MIN_GAP apart"""
    n = len(cast)
    gap = max(2 * STAGE_X / (n - 1), MIN_GAP) if n > 1 else 0
    return {cid: round((i - (n - 1) / 2) * gap, 3) for i, cid in enumerate(cast)}


def split_rows(cast: tuple, featured: set) -> tuple[tuple, tuple]:
    """(front, back) for one scene, each in @cast order. Up to MAX_ON_STAGE everyone stands in front. Beyond that the
    featured stand in front and the rest behind; a full back row sends its first listed forward."""
    if len(cast) <= MAX_ON_STAGE:
        return tuple(cast), ()
    front = {c for c in cast if c in featured} or {cast[0]}
    if len(front) > MAX_ON_STAGE:
        raise StageError(f"@cast {', '.join(cast)}: {len(front)} of them are named or directed in one scene, at most "
                         f"{MAX_ON_STAGE} fit in front; split the scene")
    back = [c for c in cast if c not in front]
    while len(back) > MAX_ON_STAGE:
        front.add(back.pop(0))
    return tuple(c for c in cast if c in front), tuple(back)


def back_spots(back: tuple, front_xs: list[float]) -> dict[str, float]:
    """x for each back-row actor: in the widest gaps of the front row (heads show between front heads), MIN_GAP
    apart, inside the bounds; nearer the centre on ties. Greedy, so it can paint itself into a corner: then the even
    spread (always fits MAX_ON_STAGE)."""
    grid = [round(k / 10, 1) for k in range(int(BOUNDS[0] * 10), int(BOUNDS[1] * 10) + 1)]
    out: dict[str, float] = {}
    for cid in back:
        free = [x for x in grid if all(abs(x - t) >= MIN_GAP - 1e-9 for t in out.values())]
        if not free:
            return spread(back)
        out[cid] = max(free, key=lambda x: (min((abs(x - f) for f in front_xs), default=0.0), -abs(x)))
    return out


def _free(x: float, others, h: float = HUMAN_HALF) -> bool:
    """x inside the bounds and clear of others: each an x (a stickman) or (x, half width); two bodies stay MIN_GAP
    apart, wider ones (a horse) their half widths apart, so a stage of stickmen spaces exactly as before"""
    return BOUNDS[0] <= x <= BOUNDS[1] and all(
        abs(x - ox) >= max(MIN_GAP, h + oh) - 1e-9 for ox, oh in (o if isinstance(o, tuple) else (o, HUMAN_HALF) for o in others))


def place(want: float, others, h: float = HUMAN_HALF) -> float:
    """nearest x to want (0.1 steps, right first on ties) clear of others (_free), inside the bounds"""
    for k in range(int((BOUNDS[1] - BOUNDS[0]) * 10) + 1):
        for x in (round(want + k / 10, 3), round(want - k / 10, 3)):
            if _free(x, others, h):
                return x
    raise StageError(f"no room on stage for {len(others) + 1} actors {MIN_GAP} units apart")


def fit_move(x: float, d: int, action: str, seconds: float, others=(), speeds=None,
             h: float = HUMAN_HALF) -> tuple[str, int, float] | None:
    """(action, direction, distance) for a walk/run from x that ends inside the stage bounds and at least MIN_GAP
    from every other actor's x, or None (go idle).

    Full distance in direction d; else flipped; else the free distance nearest the full one (roomier side first,
    0.01 steps; may pass another actor), never slower than the validator's minimum speed (plus a mm of rounding
    margin) and never past the stage edge. A run that can't fit is tried as a walk.
    speeds: (full, min, max) units/s for a moving custom action (else the built-in walk / run / stagger ones).
    """
    full, lo_speed, hi = speeds or (MOVE_SPEED[action], MIN_SPEED[action], SPEEDS[action][1])
    dist = full * seconds
    for dd in (d, -d):
        if _free(round(x + dd * dist, 3), others, h):
            return action, dd, dist
    lo = lo_speed * seconds + 0.001
    hi_speed = hi * seconds
    room = {dd: math.floor(((BOUNDS[1] - x) if dd > 0 else (x - BOUNDS[0])) * 1000) / 1000 for dd in (1, -1)}
    cands = []
    for dd in (1, -1):
        top = min(room[dd], math.floor(hi_speed * 1000) / 1000)
        cands += [(dd, r) for r in [top] + [round(top - k / 100, 3) for k in range(1, int((top - lo) * 100) + 1)]
                  if r >= lo]
    # nearest the full distance; ties: roomier side, then right, then the longer move
    for dd, r in sorted(cands, key=lambda c: (abs(c[1] - dist), -room[c[0]], -c[0], -c[1])):
        if _free(round(x + dd * r, 3), others, h):
            return action, dd, r
    return fit_move(x, d, "walk", seconds, others, h=h) if action == "run" else None


def line_moods(md: str, words: list[str]) -> list[str | None]:
    """per script word: the mood (EXPRESSIONS) in effect there. A line opens with its first mood word's mood (so every
    shot of a line split over several phrases has it) and each later mood word switches it from that word on ("Bob
    grinned, then screamed": happy, then angry at "screamed"). All None when story.md and the words disagree."""
    from ..sfx import line_words
    out = [None] * len(words)
    spans = line_words(md)
    if sum(b - a + 1 for a, b in spans.values()) != len(words):
        return out
    for a, b in spans.values():
        toks = [token(w) for w in words[a:b + 1]]
        mood = next((EXPRESSIONS[t] for t in toks if t in EXPRESSIONS), None)
        for j, t in enumerate(toks):
            mood = EXPRESSIONS.get(t, mood)
            out[a + j] = mood
    return out


def _actors(cast, pos, subject, words, seconds, travel_dir=0, zs=None, mood=None, halves=None):
    """Actors for one shot, starting at pos[cid]. Updates pos to where each one ends.
    travel_dir (+1 right / -1 left): travel shot, every actor does the subject's walk/run in place at z zs[cid].
    mood: the line's mood (line_moods), else the shot's own words decide. halves: cast id -> half width (_free)."""
    action = next((ACTIONS[w] for w in words if w in ACTIONS), "talk")
    expression = mood or next((EXPRESSIONS[w] for w in words if w in EXPRESSIONS), "neutral")
    if travel_dir:
        facing = "left" if travel_dir < 0 else "right"
        return [Actor(cast_id=cid, action=action, start_pos=(pos[cid], zs[cid]), end_pos=(pos[cid], zs[cid]),
                      facing=facing, expression=expression if cid == subject else "neutral") for cid in cast]
    sx = pos[subject]
    out = []
    for cid in cast:
        x = pos[cid]
        if cid != subject:
            facing = "camera" if x == sx else "left" if sx < x else "right"  # look at the subject
            out.append(Actor(cast_id=cid, action="idle", start_pos=(x, 0.0), facing=facing, expression="neutral"))
            continue
        move = None
        if action in MOVE_SPEED:
            d = next((DIRECTIONS[w] for w in words if w in DIRECTIONS), 1 if x <= 0 else -1)  # else to centre
            hw = halves or {}
            move = fit_move(x, d, action, seconds, [(pos[c], hw.get(c, HUMAN_HALF)) for c in cast if c != cid],
                            h=hw.get(cid, HUMAN_HALF))
        if move:
            act, d, dist = move
            pos[cid] = round(x + d * dist, 3)
            out.append(Actor(cast_id=cid, action=act, start_pos=(x, 0.0), end_pos=(pos[cid], 0.0),
                             facing="left" if d < 0 else "right", expression=expression))
        else:
            act = "idle" if action in MOVE_SPEED else action  # a walk/run that can't fit on stage
            out.append(Actor(cast_id=cid, action=act, start_pos=(x, 0.0), facing="camera", expression=expression,
                             prop="apple" if act == "eat" else None))  # "Bob ate.": an apple unless @do says
    return out


def _group_move(xs: list[float], role: str, seconds: float) -> float:
    """signed x distance a carry / support group walks (toward the stage centre, else away), keeping every member
    inside the bounds and at least the validator's minimum speed; 0 = it stands"""
    mid = sum(xs) / len(xs)
    d = 1 if mid <= 0 else -1
    want, lo = GROUP_SPEED[role] * seconds, SPEEDS[role][0] * seconds + 0.001
    for dd in (d, -d):
        room = (BOUNDS[1] - max(xs)) if dd > 0 else (min(xs) - BOUNDS[0])
        dist = math.floor(min(want, room) * 1000) / 1000
        if dist >= lo:
            return dd * dist
    return 0.0


def _apply_do(clauses, line, cast, pos, actors, vehicles, seconds, fallen, handless=None, actions=None,
              halves=None) -> list[Actor]:
    """@do for one shot: the named actors get the given action (others keep the planner's choice); "car: broken"
    stops the car on stage. pos is updated to where everyone ends. fallen: (line, cast id) already collapsed or
    gave on this line: a collapse or a give happens once, in the line's first shot; later shots lie / carry on.
    handless: cast id -> "a <rig>" for creatures without hands (no give, receive, carry or support).
    actions: the library's custom actions by id (side ones turn to face a side, moving ones cross like a walk)."""
    handless = handless or {}
    def bad(msg):
        raise StageError(f"story.md line {line}: @do: {msg}")
    by = {a.cast_id: a for a in actors}
    named = {w for c in clauses for w in c.who}
    for c in clauses:
        if c.who == (DO_CAR,):
            if not vehicles:
                bad("car: broken, but there is no car on stage here (bring one with @car arrive)")
            for v in vehicles:
                v.action, v.start_pos, v.end_pos = "broken", v.end_pos or v.start_pos, None  # stops where it stands
            continue
        for w in c.who + ((c.target,) if c.target else ()):
            if w not in by:
                bad(f"{w} is not on stage on this line (@cast {', '.join(cast)})")
        if c.target in named:
            bad(f"{c.target} is the target of {c.action} and has its own action too")
        if c.action in NEEDS_HANDS:
            hands = c.who + ((c.target,) if c.action == "give" else ())
            for w in (w for w in hands if w in handless):
                bad(f"{w} is {handless[w]} (no hands) and cannot {c.action}" + (" or be given things" if c.action == "give" else ""))
    for cid in named & set(by):  # undo the planner's move for every actor @do takes over
        pos[cid] = by[cid].start_pos[0]
    face = lambda d: "left" if d < 0 else "right"
    for c in clauses:
        if c.who == (DO_CAR,):
            continue
        if c.action == "give":
            g, t = c.who[0], c.target
            if (line, g) in fallen:  # handed over in the line's first shot; the receiver keeps it (engine propsByShot)
                continue
            fallen.add((line, g))
            dg = 1 if pos[t] >= pos[g] else -1
            by[g] = Actor(cast_id=g, action="give", target=t, prop=c.prop, start_pos=(pos[g], 0.0), facing=face(dg),
                          expression=by[g].expression)
            by[t] = Actor(cast_id=t, action="receive", target=g, start_pos=(pos[t], 0.0), facing=face(-dg),
                          expression=by[t].expression)
        elif c.action in GROUP_SPEED:
            held, holders = c.target, list(c.who)
            mid = pos[held]
            if len(holders) == 2:
                spots = [round(mid - HOLD_GAP, 3), round(mid + HOLD_GAP, 3)]
            else:
                spots = [round(mid + (HOLD_GAP if mid <= 0 else -HOLD_GAP), 3)]
            dx = _group_move(spots + [mid], c.action, seconds)
            facing = face(dx) if dx else "camera"
            for h, x in zip(holders, spots):
                end = (round(x + dx, 3), 0.0) if dx else None
                by[h] = Actor(cast_id=h, action=c.action, target=held, start_pos=(x, 0.0), end_pos=end, facing=facing,
                              expression=by[h].expression)
                pos[h] = end[0] if end else x
            by[held] = Actor(cast_id=held, action="carried" if c.action == "carry" else "supported",
                             start_pos=(mid, 0.0), facing=facing, expression=by[held].expression)
            pos[held] = round(mid + dx, 3)
        else:
            custom = (actions or {}).get(c.action)  # a library action (CustomAction), else None
            for cid in c.who:
                x, old = pos[cid], by[cid]
                toward = (1 if pos[c.target] >= x else -1) if c.target else 0  # a custom action's target
                if c.action in MOVE_SPEED or (custom and custom.move):
                    d = toward or (1 if x <= 0 else -1)
                    speeds = (abs(custom.move), *custom_speeds(custom.move)) if custom else None
                    hw = halves or {}
                    move = fit_move(x, d, c.action, seconds, [(pos[o], hw.get(o, HUMAN_HALF)) for o in cast if o != cid],
                                    speeds, hw.get(cid, HUMAN_HALF))
                    if move and toward and (move[1] != toward or (x + move[1] * move[2] - pos[c.target]) * toward > 0):
                        move = None  # aimed: never away from the target or past it; plays in place facing it
                    if move:
                        act, dd, dist = move
                        pos[cid] = round(x + dd * dist, 3)
                        back = custom is not None and custom.move < 0  # a moonwalk faces away from where it goes
                        by[cid] = Actor(cast_id=cid, action=act, start_pos=(x, 0.0), end_pos=(pos[cid], 0.0),
                                        facing=face(-dd if back else dd), expression=old.expression)
                        continue
                    action = c.action if custom else "idle"  # no room to move: a custom move plays in place
                else:
                    action = c.action
                facing = old.facing
                if custom and custom.facing == "side" and (toward or facing == "camera"):
                    facing = face(toward or (1 if x <= 0 else -1))  # side on, toward the target, else the middle
                if action == "collapse":
                    action = "lie" if (line, cid) in fallen else action
                    fallen.add((line, cid))
                by[cid] = Actor(cast_id=cid, action=action, start_pos=(x, 0.0), facing=facing,
                                expression=old.expression if old.expression != "neutral"
                                else ACTION_FACE.get(action, "neutral"),  # a mood word in the line wins
                                prop=c.prop if action == "eat" else None)
    return [by[a.cast_id] for a in actors]


def _seat_riders(actors, rides, pos, subject=None, action=None) -> list[Actor]:
    """@ride: each rider (rides: rider -> mount, both on stage) sits on its mount: the mount's spot (the engine draws
    it wherever the mount goes), facing the mount's side, mount set; RIDE_ACTIONS only, else idle. subject / action:
    the shot's subject and its keyword action (planner shots): a mounted subject gets the action (talk by default)
    unless it is a move, and its mount stands still unless it moves."""
    by = {a.cast_id: a for a in actors}
    for r, m in rides.items():
        h = by[m]
        if h.facing == "camera":  # a mounted pair is seen side on
            h.facing = "right"
        a = by.get(r) or Actor(cast_id=r, action="idle", start_pos=h.start_pos, facing="right", expression="neutral")
        if r == subject:
            a.expression = h.expression
            act = action or "talk"
            if act in RIDE_ACTIONS:
                a.action = act
            if h.action not in MOVE_SPEED:
                h.action, h.expression, h.prop = "idle", "neutral", None
        if a.action not in RIDE_ACTIONS:
            a.action = "idle"
        a.start_pos, a.end_pos, a.mount = h.start_pos, None, m
        if a.action not in ("give", "receive"):  # a hand-off keeps its partner and prop (arms only, fine in the saddle)
            a.target, a.prop = None, None
        a.facing = "left" if h.facing == "left" else "right"
        by[r], pos[r] = a, pos[m]
    return [by[a.cast_id] for a in actors] + [by[r] for r in rides if r not in {a.cast_id for a in actors}]


def dog_variant(seed: int, dog_id: str) -> str:
    """dogN takes the N-th colour of a per-part seeded order: unique until every variant is used"""
    order = random.Random(f"{seed}:dog-colours").sample(DOG_VARIANTS, len(DOG_VARIANTS))
    return order[(int(dog_id.removeprefix("dog")) - 1) % len(order)]


def car_variant(seed: int, car_id: str) -> str:
    return random.Random(f"{seed}:car:{car_id}").choice(CAR_VARIANTS)


def _dogs(n, xs, way, s0, s1, seed, sid, travel_speed=None):
    """(animals, bark cue or None) for a shot with n dogs. xs: x of everything on stage (actors, car ends).
    Travel (way +1 right / -1 left): the pack runs behind (the side they run away from), CHASE_STEP+ apart in x and
    in alternating z bands, closing in together at one seeded rate and ending >= DOG_GAP behind the rearmost x.
    Otherwise: dogs idle or bark at the stage edges, alternating sides, outside every actor's path; one bark cue."""
    R, seconds = random.Random(f"{seed}:dogs:{sid}"), (s1 - s0) / FPS
    ids = [f"dog{j + 1}" for j in range(n)]
    out = []
    if travel_speed:
        facing = "right" if way > 0 else "left"
        rear = min(xs) if way > 0 else max(xs)
        min_close = DOG_RUN_SPEED[0] - travel_speed + 0.01  # a walk-speed scroll alone is too slow for a gallop
        close = math.ceil(max(R.uniform(*DOG_CLOSE), min_close) * seconds * 1000) / 1000
        gap = DOG_GAP + 0.15
        for j, did in enumerate(ids):
            gap += (CHASE_STEP + R.uniform(0, CHASE_JITTER)) if j else 0
            end = round(rear - way * gap, 3)
            z = round(R.uniform(0.1, DOG_Z) * (1 if j % 2 == 0 else -1), 2)
            out.append(Animal(id=did, kind="dog", action="run", start_pos=(round(end - way * close, 3), z),
                              end_pos=(end, z), facing=facing, variant=dog_variant(seed, did)))
        return out, None
    xs = xs or [0.0]
    side, used = R.choice((-1, 1)), {1: 0, -1: 0}
    for j, did in enumerate(ids):
        sd = side if j % 2 == 0 else -side
        edge = max(DOG_EDGE_X, (max(xs) if sd > 0 else -min(xs)) + DOG_EDGE_GAP)
        x = round(sd * (edge + used[sd] * DOG_STEP), 3)
        used[sd] += 1
        out.append(Animal(id=did, kind="dog", action=R.choice(("idle", "bark")),
                          start_pos=(x, round(R.uniform(-0.4, 0.2), 2)),
                          facing="left" if sd > 0 else "right", variant=dog_variant(seed, did)))
    if out and all(a.action != "bark" for a in out):
        out[0].action = "bark"
    return out, Cue(frame=s0 + R.randrange(max(1, (s1 - s0) * 2 // 3)), kind="bark") if out else None


def car_dist(seconds: float) -> float:
    """arrive / leave distance: CAR_RUN_D, shortened so the peak speed (2x average) stays under CAR_SPEED's top"""
    return round(min(CAR_RUN_D, (CAR_SPEED[1] - 0.5) / 2 * seconds), 3)


def _car_move(mode, park, actors, subject, seconds, seed) -> Vehicle:
    """arrive: from off-screen to a stop beside the subject (outer side); parked (idle) once arrived.
    leave: from where it is parked (else beside the subject) off-screen the way it faces (else outward)."""
    subj = next(a for a in actors if a.cast_id == subject)
    sx = (subj.end_pos or subj.start_pos)[0]
    side = -1 if sx < 0 else 1
    d = car_dist(seconds)
    car = dict(id="car1", kind="car", variant=car_variant(seed, "car1"))
    if mode == "arrive" and park:
        return Vehicle(**car, action="idle", start_pos=(park[0], CAR_Z), facing=park[1])
    if mode == "arrive":
        stop = round(sx + side * CAR_BESIDE, 3)
        return Vehicle(**car, action="arrive", start_pos=(round(stop + side * d, 3), CAR_Z), end_pos=(stop, CAR_Z),
                       facing="left" if side > 0 else "right")
    x0, facing = park or (round(sx + side * CAR_BESIDE, 3), "right" if side > 0 else "left")
    way = 1 if facing == "right" else -1
    return Vehicle(**car, action="leave", start_pos=(x0, CAR_Z), end_pos=(round(x0 + way * d, 3), CAR_Z),
                   facing=facing)


def plan(md: str, phrases: PhrasesModel, series: SeriesModel, part_number: int, props=BUILTIN_PROPS,
         outdoor=OUTDOOR_SETS, bodies=BUILTIN_CREATURES, actions=(), weather_of=None, wardrobe=None,
         widths=None) -> StoryModel:
    """bodies: creature id -> (rig, has a stump), io.creature_bodies (built-ins + library/creatures.json).
    actions: the library's custom actions (io.custom_actions), which @do may ask for. weather_of: custom set id ->
    its default_weather (io.set_weather). widths: creature id -> half width in world units (io.creature_halves; none:
    every body spaces like a stickman)"""
    if not series.cast:
        raise StageError("series.json has no cast: add some with cast-add")
    ids = [c.id for c in series.cast]
    handless = {c.id: f"a {bodies[c.body][0]}" for c in series.cast
                if c.body in bodies and bodies[c.body][0] not in HAND_RIGS}
    by_id = {c.id: c for c in series.cast}
    halves = {c.id: max(HUMAN_HALF, (widths or {}).get(c.body, 0.0)) for c in series.cast}
    words, tags = tag_words(md, ids, ids[:DEFAULT_CAST_SIZE], props, {c.id: list(c.looks) for c in series.cast}, actions,
                            weather_of, wardrobe, creature_wardrobe(series.cast, bodies), handless)
    heard = [w.text for w in phrases.words]
    moods = line_moods(md, words)
    if words != heard:
        i = next((i for i, (a, b) in enumerate(zip(words, heard)) if a != b), min(len(words), len(heard)))
        at = lambda ws: repr(ws[i]) if i < len(ws) else "(end)"
        raise StageError(f"story.md and phrases.json differ at word {i + 1}: story {at(words)}, phrases {at(heard)} "
                         f"({len(words)} vs {len(heard)} words). Re-run prep and timing after editing story.md.")

    seed = seed_for(series.slug, part_number)
    rng = random.Random(seed)
    total = end_frame(phrases, FPS)
    end_card = EndCard(start_frame=total, text=END_TEXT)  # every part: finish appends the silent end screen after it
    starts = []
    for i, p in enumerate(phrases.phrases):  # strictly increasing so every phrase keeps >= 1 frame
        starts.append(0 if i == 0 else max(round(p.start * FPS), starts[-1] + 1))
    if starts[-1] >= total:
        raise StageError("phrases are too close together to give each one a frame")
    ends = starts[1:] + [total]
    names = {}
    for c in series.cast:
        names.setdefault(token(c.name), c.id)
        names[token(c.id)] = c.id
        names.setdefault(token(c.id) + "s", c.id)  # plural: "the runners" -> runner

    # scenes: runs of phrases on one set with one @cast. Each scene's rows are fixed for all its shots.
    rows, scene, featured, key = {}, [], set(), None
    for i, p in enumerate(phrases.phrases + [None]):
        t = tags[p.word_start] if p else None
        if scene and (p is None or (t.set, t.cast) != key):
            for j in scene:
                rows[j] = split_rows(key[1], featured)
            scene, featured = [], set()
        if p is None:
            break
        key = (t.set, t.cast)
        scene.append(i)
        featured |= {names[w] for w in (token(x) for x in heard[p.word_start:p.word_end + 1]) if names.get(w) in key[1]}
        if t.do:  # @do: everyone named in it, actors and targets
            featured |= {w for c in t.do[1] for w in c.who + ((c.target,) if c.target else ()) if w in key[1]}

    shots, cues = [], [Cue(frame=0, kind="music_start")]
    prev_angle = prev_set = subject = None
    back_pos: dict[str, float] = {}  # back row of the current scene (a scene's first shot places it)
    scene_key = None
    car_mode, car_left, park = "off", False, None  # park: (x, facing) where an arrived car stands
    prev_cast, travel_run = (), None  # travel_run: first shot id of the current run of travel shots on one set
    pos: dict[str, float] = {}  # where each actor stands now; reset on a set change
    prev_rides: dict[str, str] = {}  # @ride pairs on stage in the last shot's phrase
    fallen: set = set()  # (@do line, cast id) that already collapsed
    for i, p in enumerate(phrases.phrases):
        t = tags[p.word_start]
        set_, cast, dogs, mode, do, crowd, crowd_wardrobe, runners, looks, holds, weather, face = (
            t.set, t.cast, t.dogs, t.car, t.do, t.crowd, t.crowd_wardrobe, t.runners, t.looks, t.holds, t.weather, t.face)
        if (set_, cast) != scene_key:
            scene_key, back_pos = (set_, cast), {}
        cast, back = rows[i]  # from here on, cast is the front row
        if set_ != prev_set:
            pos, park = {}, None
        if mode != car_mode:
            car_mode, car_left = mode, False
            if mode == "arrive":
                park = None
        if mode == "ride" and len(cast) > CAR_SEATS:
            raise StageError(f"@car ride: {len(cast)} riders in @cast, the car seats {CAR_SEATS}")
        # @ride: a rider whose mount is on stage with it is part of the mount's spot (one wider actor); in the car
        # (@car ride) everyone is seated instead
        rides = {r: m for r, m in t.rides.items() if r in cast and m in cast} if mode != "ride" else {}
        spacers = tuple(c for c in cast if c not in rides)
        home, placed = spread(spacers), []
        # actors on stage last shot stay put; newcomers (start, set change, @cast change) and returners take the
        # free spot nearest their even-spread one, clear of everyone already placed (_free: by body width)
        try:
            # a rider who just got off steps down last, beside its mount (the mount keeps its spot)
            off = {r for r, m in prev_rides.items() if r not in rides and r in pos}
            for cid in sorted(spacers, key=lambda c: (c in off, c not in prev_cast or c not in pos)):
                if cid in off or cid not in pos or cid not in prev_cast or not _free(pos[cid], placed, halves[cid]):
                    pos[cid] = place(pos[cid] if cid in off else home[cid], placed, halves[cid])
                placed.append((pos[cid], halves[cid]))
        except StageError:  # where earlier moves left people splits the free room into gaps too small for a
            pos.update(home)  # newcomer: everyone takes their even-spread spot (fits up to MAX_ON_STAGE)
        for r, m in rides.items():
            pos[r] = pos[m]
        prev_rides = rides
        if back and not back_pos:
            back_pos = back_spots(back, [pos[c] for c in cast])
        prev_cast = cast
        twist = any(x.twist for x in tags[p.word_start:p.word_end + 1])
        pw = [token(w) for w in heard[p.word_start:p.word_end + 1]]
        mentioned = next((names[w] for w in pw if names.get(w) in cast), None)
        subject = mentioned or (subject if subject in cast else cast[0])
        action = next((ACTIONS[w] for w in pw if w in ACTIONS), None)
        mood = moods[p.word_start] if p.word_start < len(moods) else None
        expression = mood or next((EXPRESSIONS[w] for w in pw if w in EXPRESSIONS), "neutral")
        a, b = starts[i], ends[i]
        parts = math.ceil((b - a) / MAX_SHOT_FRAMES)
        for k in range(parts):
            s0, s1 = a + (b - a) * k // parts, a + (b - a) * (k + 1) // parts
            angle = rng.choice([x for x in ANGLES if x != prev_angle])
            if set_ != prev_set:  # first shot of the part or of a new set: establish it
                angle = ESTABLISHING if prev_angle != ESTABLISHING else next(x for x in ANGLES if x != prev_angle)
            move, speed, roll = rng.choice(MOVES), round(rng.uniform(*SPEED), 3), 0.0
            is_twist = twist and k == 0
            if is_twist:
                move = "push_in"
                roll = round(rng.uniform(*TWIST_ROLL), 2) * rng.choice((-1, 1))
                cues += [Cue(frame=s0, kind="music_stop"), Cue(frame=s0, kind="low_hit")]
            if prev_set is not None and set_ != prev_set:
                cues.append(Cue(frame=s0, kind="whoosh"))
            sid, tdir, zs = f"s{len(shots) + 1:02d}", 0, None
            ride = car_mode == "ride"
            # a ride takes one @do: "car: broken" (stops with the cast still seated); people's actions need them out
            stalled = ride and bool(do) and all(c.who == (DO_CAR,) for c in do[1])
            if ride and do and not stalled:
                raise StageError(f"story.md line {do[0]}: @do: not while @car ride, except \"car: broken\" "
                                 "(the cast is seated in the car)")
            car_here = ride or car_mode == "arrive" or (car_mode == "leave" and not car_left)
            travel = set_ in outdoor and ((ride and not stalled) or (action in MOVE_SPEED and not car_here and not do))
            tspeed = CAR_TRAVEL_SPEED if ride else MOVE_SPEED.get(action)
            if travel:  # direction and z stagger seeded once per run of travel shots, so the run keeps them
                if travel_run is None or set_ != prev_set:
                    travel_run = sid
                tdir = random.Random(f"{seed}:travel:{travel_run}").choice((-1, 1))
                zs = {c: round(random.Random(f"{seed}:travel:{travel_run}:{c}").uniform(-TRAVEL_Z, TRAVEL_Z), 2)
                      for c in cast}
            else:
                travel_run = None
            seconds, vehicles = (s1 - s0) / FPS, []
            if ride:  # the whole @cast sits in the car; a travel shot outdoors, parked indoors
                facing = "left" if tdir < 0 else "right"
                if stalled and shots and shots[-1].vehicles:  # breaks down facing the way it was driving
                    facing = shots[-1].vehicles[0].facing
                act = "wave" if any(ACTIONS.get(w) == "wave" for w in pw) else "ride"
                actors = [Actor(cast_id=c, action=act, start_pos=(0.0, 0.0), facing=facing,
                                expression=expression if c == subject else "neutral") for c in cast]
                vehicles = [Vehicle(id="car1", kind="car", action="broken" if stalled else "drive" if travel else "idle",
                                    start_pos=(0.0, 0.0),
                                    end_pos=(0.0, 0.0) if travel else None, facing=facing, riders=list(cast),
                                    variant=car_variant(seed, "car1"))]
            else:
                # a mounted subject: the mount does the moving, the rider the talking / gesturing (_seat_riders)
                actors = _actors(spacers, pos, rides.get(subject, subject), pw, seconds, tdir, zs, mood, halves)
                actors = _seat_riders(actors, rides, pos, subject, action)
                if car_here:
                    v = _car_move(car_mode, park, actors, subject, seconds, seed)
                    vehicles = [v]
                    if v.action == "arrive":
                        park = (v.end_pos[0], v.facing)
                        subj = next(x for x in actors if x.cast_id == subject)
                        if subj.action == "talk":
                            subj.action = "react"  # the subject reacts to the car pulling up
                    elif v.action == "leave":
                        car_left, park = True, None
                if do:
                    actors = _apply_do(do[1], do[0], spacers, pos, actors, vehicles, seconds, fallen, handless, actions,
                                       halves)
                    actors = _seat_riders(actors, rides, pos)
                    if any(ac.action == "give" for ac in actors):  # a hand-over needs both people in frame: wide
                        angle = "wide" if prev_angle != "wide" else "medium"  # fits everyone; medium: the pair (engine)
                    for v in vehicles:
                        if v.action == "broken":  # it stays where it broke down
                            park, car_left = (v.start_pos[0], v.facing), False
            if back and not travel and not ride:  # the back row: idle, looking at the subject (not in travel shots:
                sx = next(ac.start_pos[0] for ac in actors if ac.cast_id == subject)  # the world scrolls past them)
                actors = list(actors) + [
                    Actor(cast_id=c, action="idle", start_pos=(back_pos[c], BACK_Z), expression="neutral",
                          facing="camera" if back_pos[c] == sx else "left" if sx < back_pos[c] else "right")
                    for c in back]
            xs = [x for ac in actors for x in (ac.start_pos[0], (ac.end_pos or ac.start_pos)[0])]
            for v in vehicles:  # where the car stands (arrive: its stop, leave: its start), both ends of the body
                cx = (v.end_pos or v.start_pos)[0] if v.action == "arrive" else v.start_pos[0]
                xs += [cx - CAR_HALF, cx + CAR_HALF]
            way = (1 if (vehicles[0].facing if vehicles else actors[0].facing) == "right" else -1) if travel else 0
            animals, bark = _dogs(dogs, xs, way, s0, s1, seed, sid, tspeed if travel else None)
            # no crowd in a travel shot: the world scrolls past and a standing crowd would seem to keep pace
            groups = list(crowd.items())
            extras = ([e for gi, (group, spec) in enumerate(groups)
                       for e in crowd_extras(group, spec, seed, set_, set_ not in outdoor, gi, len(groups),
                                             crowd_wardrobe.get(group))] if crowd and not travel else []) + runner_extras(
                runners, seed, sid, seconds, [a for a in actors if not ride], way, tspeed if travel else 0.0, set_ not in outdoor)
            if bark:
                cues.append(bark)
            # a mood word later in the phrase switches the subject's face on that word (a phrase split into several
            # shots: a later shot opens with the face switched to before it)
            turns = [(round(phrases.words[j].start * FPS), moods[j]) for j in range(p.word_start + 1, p.word_end + 1)
                     if j < len(moods) and moods[j] and moods[j] != moods[j - 1]]
            opened = [e for f, e in turns if f <= s0]
            switches = [FaceChange(frame=f, expression=e) for f, e in turns if s0 < f < s1]
            for ac in actors:  # @look: the look each cast member has on this line
                ac.look = looks.get(ac.cast_id)
                if held := holds.get(ac.cast_id):  # @hold: the look's props, with each held hand replaced
                    ac.props = [p for p in by_id[ac.cast_id].with_look(ac.look).props if p.hand not in held] + [
                        Prop(kind=k, hand=h) for h, k in held.items() if k]
                if face and ac.cast_id in face:  # @face: this face for the whole line, nothing else
                    ac.expression, ac.faces = face[ac.cast_id], []
                elif ac.cast_id == subject and ac.expression == expression:
                    ac.expression, ac.faces = (opened[-1] if opened else expression), switches
            shots.append(Shot(id=sid, start_frame=s0, end_frame=s1, set=set_,
                              phrase_range=(i, i), camera=Camera(angle=angle, move=move, speed=speed, roll_deg=roll),
                              actors=actors, animals=animals, vehicles=vehicles, extras=extras, twist=is_twist,
                              travel=Travel(speed=tspeed) if travel else None, weather=weather))
            prev_angle, prev_set = angle, set_
    lightning = [strike(shots, line, target, min(round(phrases.words[w].start * FPS), total - 1), series)
                 for w, (line, target) in ((w, t.strike) for w, t in enumerate(tags) if t.strike)]
    # @fx shake: the frame finish shows the line's first caption chunk on (finish._frame), so captions and camera hit together
    shakes = [min(math.ceil(phrases.words[w].start * FPS - 1e-6), total - 1) for w, t in enumerate(tags) if t.shake]
    # Add one cue at each narration line where the selected track changes. The audio stage stretches/loops it.
    previous = None
    for i, p in enumerate(phrases.phrases):
        selected = tags[p.word_start].bg_music
        if selected != previous and (selected is not None or previous is not None):
            cues.append(Cue(frame=starts[i], kind="background_music",
                            track=selected[0] if selected else None,
                            volume=selected[1] if selected else None))
            previous = selected
    width, height = FRAME_SIZE[series.style.aspect]
    return StoryModel(width=width, height=height, duration_frames=total, seed=seed, shots=shots, cues=cues, end_card=end_card, lightning=lightning,
                      shakes=shakes)


def strike(shots: list[Shot], line: int, target: str | None, frame: int, series: SeriesModel) -> Strike:
    """@fx lightning at frame: a target cast id must be on stage then; a prop target becomes whoever holds it (their
    cast or look props, or the prop of an eat / give)"""
    if target is None:
        return Strike(frame=frame)
    shot = next(s for s in shots if s.start_frame <= frame < s.end_frame)
    cast = {c.id: c for c in series.cast}

    def holds(a: Actor) -> bool:
        held = a.props if a.props is not None else cast[a.cast_id].with_look(a.look).props
        return a.prop == target or any(p.kind == target for p in held)
    who = next((a.cast_id for a in shot.actors if a.cast_id == target), None)
    who = who or next((a.cast_id for a in shot.actors if holds(a)), None)
    if who is None:
        on = ", ".join(a.cast_id for a in shot.actors) or "nobody"
        raise StageError(f"story.md line {line}: @fx lightning: {target} is not on stage on the next line "
                         f"(on stage: {on})" if target in cast else
                         f"story.md line {line}: @fx lightning: nobody on stage holds {target} on the next line "
                         f"(on stage: {on})")
    return Strike(frame=frame, target=who)


def run(part_dir: Path) -> None:
    story_md = part_dir / "story.md"
    if not story_md.exists():
        raise StageError("story.md not found")
    phrases = load_model(part_dir / "phrases.json", PhrasesModel)
    series = load_series(part_dir.parent / "series.json")
    library = library_of(part_dir)
    if unknown := unknown_cast_props(series.cast, library):
        raise StageError(f"cast holds a prop that is not in library/props.json: {', '.join(unknown)}")
    if problems := cast_body_problems(series.cast, library):
        raise StageError(f"cast body: {'; '.join(problems)}")
    story = plan(story_md.read_text(encoding="utf-8"), phrases, series, load_part(part_dir / "part.json").number,
                 prop_kinds(library), outdoor_sets(library), creature_bodies(library), custom_actions(library),
                 set_weather(library), wardrobe_slots(library), creature_halves(library))
    if unknown := sorted({s.set for s in story.shots} - set(set_kinds(library))):  # the engine would throw mid-render
        raise StageError(f"unknown set: {', '.join(unknown)} (built in: {', '.join(BUILTIN_SETS)}, or add it on the "
                         f"dashboard's Sets page)")
    errors = validate(story, phrases, {c.id for c in series.cast}, outdoor_sets(library), custom_moves(library))
    for e in errors:
        print(f"  {e.shot_id or '-'}  {e.rule}: {e.message}")
    if errors:
        raise StageError(f"planned story.json fails validation ({len(errors)} error(s)); nothing written")
    atomic_write_json(part_dir / "story.json", story.model_dump(mode="json"))
    print(f"shots: {len(story.shots)}, frames: {story.duration_frames}, seed: {story.seed}")
