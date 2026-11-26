"""Rule checks for story.json against phrases.json and the series cast.

Covers shot layout, camera, actor motion, twist and cue rules from docs/brief.md.
Not checked here: idle breathing and blinks (the engine adds them to every character)
and audio levels (the mix stage owns them).
"""

import math
import re
from itertools import groupby
from typing import NamedTuple

from .schemas import BUILTIN_SETS, PhrasesModel, StoryModel

MAX_SHOT_FRAMES = 90
WALK_SPEED = (0.6, 1.8)   # units/s, inclusive
RUN_SPEED = (1.8, 4.0)
DOG_RUN_SPEED = (2.0, 5.0)
CAR_SPEED = (1.5, 8.0)    # drive: average speed; arrive/leave: peak speed (2x average: eased to / from a stop)
TWIST_CUE_WINDOW = 3      # frames either side of the twist shot's start
PHRASE_TOLERANCE = 3      # frames either side of a shot's phrase time span
STAGGER_SPEED = (0.3, 1.0)
SUPPORT_SPEED = (0.6, 1.0)  # supporters walk a staggering actor along: where walk and stagger speeds overlap
SPEEDS = {"walk": WALK_SPEED, "run": RUN_SPEED, "stagger": STAGGER_SPEED, "carry": WALK_SPEED, "support": SUPPORT_SPEED}
MOVING = set(SPEEDS)       # actions that may move (walk / run / stagger always do; a carry or support group may stand)
HOLDING = {"carry", "support"}
PARTNER = {"give": "receive", "receive": "give", "carry": "carried", "support": "supported"}  # action -> target's
GROUPS = {"carried": ("carry", 2, 2), "supported": ("support", 1, 2)}  # held actor -> (holder action, min, max)
NEEDS_PROP = {"eat", "give"}
MOODS = {"cheer", "angry", "gasp", "salute", "neutral"}  # crowd extras' actions
CROWD_Z = (-2.8, -1.2)     # crowd rows: behind the stage clearance zone (props in |x| < 2.2 sit behind z -1.0)
RUNNER_MAX_Z = -0.6        # background runners stay behind the actors' line
RIDING = {"ride", "wave", "talk"}  # what a seated rider may do
OUTDOOR_SETS = frozenset(k for k, v in BUILTIN_SETS.items() if v == "outdoor")  # built-ins that can scroll; custom ones come from the library


class Error(NamedTuple):
    shot_id: str | None
    rule: str
    message: str


# Every part ends the same way: the story's last word, TAIL_S of picture (the end of story.json), then finish appends
# the silent "Follow for more" end screen (with the handles from library/settings.json) for END_SCREEN_S.
TAIL_S = 0.3
END_SCREEN_S = 2.5
SENTENCE_END = re.compile(r"[.!?…][\"')\]]*$")


def duration_frames(seconds: float, fps: int) -> int:
    return math.ceil(round(seconds * fps, 6))  # round() guards float noise like 2.0000000001 * 30


def end_frame(phrases: PhrasesModel, fps: int) -> int:
    """the story's length: TAIL_S after the last word (finish appends the end screen after that)"""
    return duration_frames(phrases.words[-1].end + TAIL_S, fps)


def custom_speeds(move: float) -> tuple[float, float]:
    """the speed range (units/s) a custom action that moves at `move` may be planned at (shortened moves go slower)"""
    return round(abs(move) * 0.5, 3), round(abs(move) * 1.5, 3)


def validate(story: StoryModel, phrases: PhrasesModel, cast_ids: set[str], outdoor=OUTDOOR_SETS,
             moves=None) -> list[Error]:
    """moves: custom action id -> its move (units/s, - backward; io.custom_moves). Custom actions not in it stay
    in place."""
    moves = moves or {}
    errs: list[Error] = []
    err = lambda sid, rule, msg: errs.append(Error(sid, rule, msg))
    fps = story.fps

    want = end_frame(phrases, fps)
    if story.duration_frames != want:
        err(None, "duration", f"duration_frames {story.duration_frames} != {want} (last word "
                              f"{phrases.words[-1].end} s + {TAIL_S} s tail, x {fps})")
    if story.end_card and story.end_card.start_frame != story.duration_frames:
        err(None, "end_card", f"end screen starts at {story.end_card.start_frame}, expected {story.duration_frames} "
                              "(where the story ends)")

    expected_start, prev, seen = 0, None, set()
    for s in story.shots:
        if s.id in seen:
            err(s.id, "duplicate_shot_id", f"shot id {s.id} is used more than once")
        seen.add(s.id)
        if s.start_frame != expected_start:
            err(s.id, "contiguous", f"starts at {s.start_frame}, expected {expected_start}")
        expected_start = s.end_frame
        n = s.end_frame - s.start_frame
        if not 1 <= n <= MAX_SHOT_FRAMES:
            err(s.id, "shot_length", f"{n} frames, must be 1..{MAX_SHOT_FRAMES}")
        if prev and prev.camera.angle == s.camera.angle and not s.camera.forced:  # @cam may repeat an angle
            err(s.id, "repeated_angle", f"same camera angle {s.camera.angle!r} as {prev.id}")
        if not s.camera.speed > 0:
            err(s.id, "camera_speed", f"speed {s.camera.speed} must be > 0 (camera always creeps)")
        if not s.set.strip():
            err(s.id, "set", "set is empty")

        first, last = s.phrase_range
        if not 0 <= first <= last < len(phrases.phrases):
            err(s.id, "phrase_range", f"{[first, last]} invalid for {len(phrases.phrases)} phrases")
        elif prev and first < prev.phrase_range[1]:
            err(s.id, "phrase_range", f"{[first, last]} goes back before {prev.id} {list(prev.phrase_range)}")

        if s.travel:
            _check_travel(s, n / fps, err, outdoor)
        for a in s.actors:
            _check_actor(s.id, a, n / fps, cast_ids, err, s.travel, moves.get(a.action, 0))
        _check_partners(s, err)
        ids = [d.id for d in s.animals]
        if len(set(ids)) != len(ids):
            err(s.id, "animal_id", f"animal ids repeat: {ids}")
        for d in s.animals:
            _check_animal(s, d, n / fps, err)
        _check_vehicles(s, n / fps, cast_ids, err)
        _check_extras(s, n / fps, err)

        if s.twist:
            _check_twist(s, story, err)
        prev = s

    # Consecutive shots with the same phrase_range (a split phrase) are one group: together they must overlap
    # the phrase window, so a split piece that sits wholly in the pause after the phrase is fine.
    for (first, last), grp in groupby(story.shots, key=lambda s: s.phrase_range):
        grp = list(grp)
        if not 0 <= first <= last < len(phrases.phrases):
            continue  # already reported as phrase_range
        a, b = grp[0].start_frame, grp[-1].end_frame
        lo = phrases.phrases[first].start * fps - PHRASE_TOLERANCE
        hi = phrases.phrases[last].end * fps + PHRASE_TOLERANCE
        if not (a < hi and b > lo):
            ids = grp[0].id if len(grp) == 1 else f"{grp[0].id}..{grp[-1].id}"
            err(grp[0].id, "phrase_timing", f"{ids} frames {a}-{b} miss phrases {[first, last]} "
                                            f"at frames {lo:.0f}-{hi:.0f} (with +-{PHRASE_TOLERANCE} tolerance)")

    if story.shots and expected_start != story.duration_frames:
        err(story.shots[-1].id, "contiguous", f"last shot ends at {expected_start}, expected {story.duration_frames}")
    elif not story.shots:
        err(None, "contiguous", "no shots")

    for c in story.cues:
        if not 0 <= c.frame <= story.duration_frames:
            err(None, "cue_frame", f"{c.kind} cue at frame {c.frame} outside 0..{story.duration_frames}")
    for k in story.lightning:
        shot = next((s for s in story.shots if s.start_frame <= k.frame < s.end_frame), None)
        if shot is None:
            err(None, "lightning", f"strike at frame {k.frame} outside every shot")
        elif k.target and k.target not in {a.cast_id for a in shot.actors}:
            err(shot.id, "lightning", f"strike at frame {k.frame} targets {k.target}, who is not in {shot.id}")
    return errs


def travel_way(s) -> str | None:
    """the way a travel shot moves: its car's facing, else the first actor's"""
    return s.vehicles[0].facing if s.vehicles else s.actors[0].facing if s.actors else None


def _check_travel(s, seconds, err, outdoor=OUTDOOR_SETS) -> None:
    """Travel shot: outdoor set, every actor walks or runs, all facing one left/right direction.
    With a car: the car drives and keeps its x, the world scrolls at the car's speed, no actor walks or runs."""
    if s.set not in outdoor:
        err(s.id, "travel_set", f"travel on set {s.set!r}: only {', '.join(sorted(outdoor))}")
    if not s.actors:
        err(s.id, "travel_actors", "travel shot has no actors")
    if s.vehicles:
        lo, hi = CAR_SPEED
        if not lo <= s.travel.speed <= hi:
            err(s.id, "vehicle_speed", f"travel speed {s.travel.speed} is the car's speed: must be {lo}..{hi}")
        for v in s.vehicles:
            if v.action != "drive" or (v.end_pos is not None and v.end_pos[0] != v.start_pos[0]):
                err(s.id, "travel_vehicle", f"{v.id} {v.action}: a car in a travel shot drives and keeps its x")
        if len({v.facing for v in s.vehicles}) > 1:
            err(s.id, "travel_facing", "cars in a travel shot must all face one way")
        for a in s.actors:
            if a.action in MOVING:
                err(s.id, "travel_actors", f"{a.cast_id} {a.action}: nobody walks or runs in a car travel shot")
        return
    for a in s.actors:
        if a.action not in MOVING and a.action not in GROUPS and not a.mount:  # a rider goes with its mount
            err(s.id, "travel_actors", f"{a.cast_id} {a.action}: every actor in a travel shot must walk, run, stagger "
                                       f"or be carried / supported along")
    facings = {a.facing for a in s.actors}
    if len(facings) > 1 or facings - {"left", "right"}:
        err(s.id, "travel_facing", f"travel actors face {sorted(facings)}: all must face one way, left or right")


def _check_actor(sid, a, seconds, cast_ids, err, travel=None, move=0) -> None:
    """move: a custom action's speed (units/s; - backward: it faces away from where it goes), 0 for the rest"""
    if a.cast_id not in cast_ids:
        err(sid, "cast_id", f"{a.cast_id!r} is not in series.json cast")
    if move:  # a moving custom action (a moonwalk...): moves like a walk at its own speed, maybe backward
        if travel:
            err(sid, "travel_actors", f"{a.cast_id} {a.action}: a moving custom action can't play in a travel shot")
        _check_move(sid, a.cast_id, a, a.end_pos is not None, custom_speeds(move), seconds, err, None, move < 0)
        return
    if a.approach:  # walks to a World Item over the first `approach` of the shot (facing its way), then turns to act
        end = a.end_pos or a.start_pos
        speed = math.dist(a.start_pos, end) / (seconds * a.approach) if seconds > 0 else 0
        if not WALK_SPEED[0] <= speed <= WALK_SPEED[1]:
            err(sid, "gliding", f"{a.cast_id} walks to {a.item} at {speed:.2f} units/s, must be "
                                f"{WALK_SPEED[0]}..{WALK_SPEED[1]}")
        return
    # a carry / support group may also stand still (no end_pos); walk, run and stagger always move
    moving = a.action in MOVING and (a.action not in HOLDING or a.end_pos is not None or travel is not None)
    _check_move(sid, a.cast_id, a, moving, SPEEDS.get(a.action, WALK_SPEED), seconds, err, travel)


def _check_partners(s, err) -> None:
    """targets and props: give <-> receive pairs, carry / support groups around a carried / supported actor"""
    on = {a.cast_id: a for a in s.actors}
    for a in s.actors:
        if a.mount and (a.mount == a.cast_id or a.mount not in on or on[a.mount].mount
                        or sum(b.mount == a.mount for b in s.actors) > 1):
            err(s.id, "mount", f"{a.cast_id} rides {a.mount}: it must be another actor in the shot, not riding "
                               "itself, with no other rider")
        want = PARTNER.get(a.action)
        if want:
            t = on.get(a.target)
            if a.target is None or a.target == a.cast_id:
                err(s.id, "target", f"{a.cast_id} {a.action}: needs a target (another actor in the shot)")
            elif t is None:
                err(s.id, "target", f"{a.cast_id} {a.action} {a.target}: {a.target} is not on stage in this shot")
            elif t.action != want or (a.action in ("give", "receive") and t.target != a.cast_id):
                err(s.id, "target", f"{a.cast_id} {a.action} {a.target}: {a.target} must {want}"
                                    + (f" from / to {a.cast_id}" if a.action in ("give", "receive") else ""))
        elif a.target is not None:
            err(s.id, "target", f"{a.cast_id} {a.action}: only give / receive / carry / support take a target")
        if a.action in NEEDS_PROP and a.prop is None:
            err(s.id, "prop", f"{a.cast_id} {a.action}: needs a prop")
        elif a.action not in NEEDS_PROP and a.prop is not None:
            err(s.id, "prop", f"{a.cast_id} {a.action}: only eat / give take a prop")
        if a.action in GROUPS:
            role, lo, hi = GROUPS[a.action]
            holders = [h for h in s.actors if h.action == role and h.target == a.cast_id]
            if not lo <= len(holders) <= hi:
                need = str(lo) if lo == hi else f"{lo}-{hi}"
                err(s.id, "holders", f"{a.cast_id} {a.action}: needs {need} actor(s) with action {role} "
                                     f"targeting it, has {len(holders)}")
            moves = {_move(h) for h in holders}
            if len(moves) > 1 or len({h.facing for h in holders}) > 1:
                err(s.id, "holders", f"{a.cast_id} {a.action}: its {role} actors must move together, side by side "
                                     f"(same move and facing)")


def _move(a) -> tuple[float, float]:
    end = a.end_pos if a.end_pos is not None else a.start_pos
    return round(end[0] - a.start_pos[0], 2), round(end[1] - a.start_pos[1], 2)


def _check_animal(s, d, seconds, err) -> None:
    """Dogs: same facing / no-gliding rules as actors at DOG_RUN_SPEED; in travel shots every dog runs the travel way."""
    if s.travel:
        way = travel_way(s)
        if d.action != "run" or d.facing != way:
            err(s.id, "travel_animals", f"{d.id} {d.action} facing {d.facing}: dogs in a travel shot must run {way}")
    _check_move(s.id, d.id, d, d.action == "run", DOG_RUN_SPEED, seconds, err, s.travel)


def _check_move(sid, who, a, moving, lo_hi, seconds, err, travel, backward=False) -> None:
    if not moving:
        if a.end_pos is not None:
            err(sid, "end_pos", f"{who} {a.action}: end_pos must be null")
        return
    end = a.end_pos if a.end_pos is not None else a.start_pos
    if not travel and tuple(end) == tuple(a.start_pos):  # travel: may stay put, the world moves
        err(sid, "end_pos", f"{who} {a.action}: end_pos must differ from start_pos")
        return
    dx = end[0] - a.start_pos[0]
    want = None if not dx else "left" if (dx < 0) != backward else "right"  # pure z movement: any facing
    if want and a.facing != want:
        err(sid, "facing", f"{who} {a.action} moves {'backward' if backward else 'forward'}, so it faces {want}, "
                           f"not {a.facing}")
    if seconds > 0:
        lo, hi = lo_hi
        # travel: legs cover the scroll plus the actor's own x move (effective stride speed)
        speed = travel.speed + abs(dx) / seconds if travel else math.dist(a.start_pos, end) / seconds
        if not lo <= speed <= hi:
            err(sid, "gliding", f"{who} {a.action} speed {speed:.2f} units/s, must be {lo}..{hi}")


def _check_vehicles(s, seconds, cast_ids, err) -> None:
    ids = [v.id for v in s.vehicles]
    if len(set(ids)) != len(ids):
        err(s.id, "vehicle_id", f"vehicle ids repeat: {ids}")
    riders = [r for v in s.vehicles for r in v.riders] + [r for it in s.items for r in it.riders]
    if len(set(riders)) != len(riders):
        err(s.id, "riders", f"a cast member rides in two seats: {riders}")
    for v in s.vehicles:
        for r in v.riders:
            if r not in cast_ids:
                err(s.id, "cast_id", f"rider {r!r} of {v.id} is not in series.json cast")
            entries = [a for a in s.actors if a.cast_id == r]
            if len(entries) != 1 or entries[0].action not in RIDING:
                err(s.id, "riders", f"{r} rides {v.id}: needs exactly one actor entry with action "
                                    f"{'/'.join(sorted(RIDING))} (not also a standing actor)")
        if s.travel:
            continue  # speed and x rules in _check_travel
        end = v.end_pos if v.end_pos is not None else v.start_pos
        moved = tuple(end) != tuple(v.start_pos)
        if v.action in ("idle", "broken"):
            if moved:
                err(s.id, "vehicle_motion", f"{v.id} {v.action}: must not move")
            continue
        if not moved:
            err(s.id, "vehicle_motion", f"{v.id} {v.action}: end_pos must differ from start_pos")
            continue
        dx = end[0] - v.start_pos[0]
        want = "left" if dx < 0 else "right" if dx > 0 else None
        if want and v.facing != want:
            err(s.id, "facing", f"{v.id} {v.action}s {want} but faces {v.facing}")
        if seconds > 0:
            avg = math.dist(v.start_pos, end) / seconds
            speed = avg if v.action == "drive" else 2 * avg  # eased to/from a stop: peak = 2x average
            lo, hi = CAR_SPEED
            if not lo <= speed <= hi:
                err(s.id, "vehicle_speed", f"{v.id} {v.action} {'peak ' if v.action != 'drive' else ''}speed "
                                           f"{speed:.2f} units/s, must be {lo}..{hi}")
    for a in s.actors:
        if a.action == "ride" and a.cast_id not in riders:
            err(s.id, "riders", f"{a.cast_id} rides but no vehicle or item lists it")
    items = {it.id for it in s.items}
    for a in s.actors:
        if a.item is not None and a.item not in items:
            err(s.id, "item", f"{a.cast_id} {a.action}s {a.item}, which is not an item in this shot")


def _check_extras(s, seconds, err) -> None:
    """crowd extras stand still in a mood behind the stage; runners follow the actors' no-glide / facing / speed
    rules at RUN_SPEED (travel shots: they run the travel way, legs covering the scroll plus their own move)"""
    ids = [e.id for e in s.extras]
    if len(set(ids)) != len(ids):
        err(s.id, "extra_id", f"extra ids repeat: {ids}")
    for e in s.extras:
        if e.kind == "crowd":
            if e.action not in MOODS and e.action != "fight":
                err(s.id, "extras", f"{e.id} crowd {e.action}: a crowd extra takes a mood ({', '.join(sorted(MOODS))}) or fight")
            if e.action == "fight" and not e.target_group:
                err(s.id, "extras", f"{e.id}: fighting crowd needs a target_group")
            if e.end_pos is not None:
                err(s.id, "extras", f"{e.id}: crowd extras never move (end_pos must be null)")
            if s.travel:
                err(s.id, "extras", f"{e.id}: no crowd in a travel shot (it would seem to run along with the actors)")
            if not CROWD_Z[0] <= e.start_pos[1] <= CROWD_Z[1]:
                err(s.id, "extras_zone", f"{e.id} at z {e.start_pos[1]}: crowd stands at z {CROWD_Z[0]}..{CROWD_Z[1]}, "
                                         f"behind the stage clearance zone")
            continue
        if e.action != "run":
            err(s.id, "extras", f"{e.id} runner {e.action}: runners run")
            continue
        end = e.end_pos if e.end_pos is not None else e.start_pos
        if max(e.start_pos[1], end[1]) > RUNNER_MAX_Z:
            err(s.id, "extras_zone", f"{e.id}: runners stay behind the actors (z <= {RUNNER_MAX_Z})")
        if s.travel and e.facing != travel_way(s):
            err(s.id, "travel_extras", f"{e.id} faces {e.facing}: runners in a travel shot run {travel_way(s)}")
        _check_move(s.id, e.id, e, True, RUN_SPEED, seconds, err, s.travel)


def _check_twist(s, story, err) -> None:
    if s.camera.move != "push_in" and not s.camera.forced:  # @cam's move / dutch win on a twist
        err(s.id, "twist", f"twist shot needs move push_in, got {s.camera.move}")
    if s.camera.roll_deg == 0 and not s.camera.forced:
        err(s.id, "twist", "twist shot needs roll_deg != 0")
    near = {c.kind for c in story.cues if abs(c.frame - s.start_frame) <= TWIST_CUE_WINDOW}
    for kind in ("music_stop", "low_hit"):
        if kind not in near:
            err(s.id, "twist", f"twist shot needs a {kind} cue within +-{TWIST_CUE_WINDOW} frames of {s.start_frame}")
