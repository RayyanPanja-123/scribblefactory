"""Rule checks for story.json against phrases.json and the series cast.

Covers shot layout, camera, actor motion, twist and cue rules from docs/brief.md.
Not checked here: idle breathing and blinks (the engine adds them to every character)
and audio levels (the mix stage owns them).
"""

import math
from itertools import groupby
from typing import NamedTuple

from .schemas import PhrasesModel, StoryModel

MAX_SHOT_FRAMES = 90
WALK_SPEED = (0.6, 1.8)   # units/s, inclusive
RUN_SPEED = (1.8, 4.0)
TWIST_CUE_WINDOW = 3      # frames either side of the twist shot's start
PHRASE_TOLERANCE = 3      # frames either side of a shot's phrase time span
MOVING = {"walk", "run"}
OUTDOOR_SETS = {"street", "dirt_road", "countryside", "orchard", "stadium"}  # sets that can scroll (travel shots)


class Error(NamedTuple):
    shot_id: str | None
    rule: str
    message: str


def duration_frames(seconds: float, fps: int) -> int:
    return math.ceil(round(seconds * fps, 6))  # round() guards float noise like 2.0000000001 * 30


def validate(story: StoryModel, phrases: PhrasesModel, cast_ids: set[str]) -> list[Error]:
    errs: list[Error] = []
    err = lambda sid, rule, msg: errs.append(Error(sid, rule, msg))
    fps = story.fps

    want = duration_frames(phrases.duration, fps)
    if story.duration_frames != want:
        err(None, "duration", f"duration_frames {story.duration_frames} != ceil({phrases.duration} s x {fps}) = {want}")

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
        if prev and prev.camera.angle == s.camera.angle:
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
            _check_travel(s, n / fps, err)
        for a in s.actors:
            _check_actor(s.id, a, n / fps, cast_ids, err, s.travel)

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
    return errs


def _check_travel(s, seconds, err) -> None:
    """Travel shot: outdoor set, every actor walks or runs, all facing one left/right direction."""
    if s.set not in OUTDOOR_SETS:
        err(s.id, "travel_set", f"travel on set {s.set!r}: only {', '.join(sorted(OUTDOOR_SETS))}")
    if not s.actors:
        err(s.id, "travel_actors", "travel shot has no actors")
    for a in s.actors:
        if a.action not in MOVING:
            err(s.id, "travel_actors", f"{a.cast_id} {a.action}: every actor in a travel shot must walk or run")
    facings = {a.facing for a in s.actors}
    if len(facings) > 1 or facings - {"left", "right"}:
        err(s.id, "travel_facing", f"travel actors face {sorted(facings)}: all must face one way, left or right")


def _check_actor(sid, a, seconds, cast_ids, err, travel=None) -> None:
    who = a.cast_id
    if who not in cast_ids:
        err(sid, "cast_id", f"{who!r} is not in series.json cast")
    if a.action not in MOVING:
        if a.end_pos is not None:
            err(sid, "end_pos", f"{who} {a.action}: end_pos must be null")
        return
    end = a.end_pos if a.end_pos is not None else a.start_pos
    if not travel and tuple(end) == tuple(a.start_pos):  # travel: may stay put, the world moves
        err(sid, "end_pos", f"{who} {a.action}: end_pos must differ from start_pos")
        return
    dx = end[0] - a.start_pos[0]
    want = "left" if dx < 0 else "right" if dx > 0 else None  # pure z movement: any facing
    if want and a.facing != want:
        err(sid, "facing", f"{who} {a.action}s {want} but faces {a.facing}")
    if seconds > 0:
        lo, hi = WALK_SPEED if a.action == "walk" else RUN_SPEED
        # travel: legs cover the scroll plus the actor's own x move (effective stride speed)
        speed = travel.speed + abs(dx) / seconds if travel else math.dist(a.start_pos, end) / seconds
        if not lo <= speed <= hi:
            err(sid, "gliding", f"{who} {a.action} speed {speed:.2f} units/s, must be {lo}..{hi}")


def _check_twist(s, story, err) -> None:
    if s.camera.move != "push_in":
        err(s.id, "twist", f"twist shot needs move push_in, got {s.camera.move}")
    if s.camera.roll_deg == 0:
        err(s.id, "twist", "twist shot needs roll_deg != 0")
    near = {c.kind for c in story.cues if abs(c.frame - s.start_frame) <= TWIST_CUE_WINDOW}
    for kind in ("music_stop", "low_hit"):
        if kind not in near:
            err(s.id, "twist", f"twist shot needs a {kind} cue within +-{TWIST_CUE_WINDOW} frames of {s.start_frame}")
