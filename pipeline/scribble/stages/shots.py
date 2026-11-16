"""shots: story.md directives + phrases.json + series cast -> story.json. Rule-based and seeded, no AI.

Each phrase gets a shot starting at its first word (pauses stay with the earlier shot); shots over
MAX_SHOT_FRAMES split into equal parts. Directive state (@set, @cast, !!) is read at a phrase's first word.
The output must pass the validator, otherwise nothing is written.
"""

import math
import random
import re
import zlib
from pathlib import Path

from ..io import atomic_write_json
from ..schemas import Actor, Camera, Cue, PhrasesModel, SeriesModel, Shot, StoryModel
from ..validate import MAX_SHOT_FRAMES, RUN_SPEED, WALK_SPEED, duration_frames, validate
from .prep import MARKER_RE, clean_markdown, mark_directives
from .runner import StageError
from .validate import load_model

INPUTS = ["story.md", "phrases.json", "../series.json"]
OUTPUTS = ["story.json"]

FPS = 30
DEFAULT_SET = "room"
DEFAULT_CAST_SIZE = 2      # first N series cast members when story.md has no @cast
ANGLES = ["wide", "medium", "close", "low", "high", "over_shoulder"]
MOVES = ["push_in", "pull_out", "truck_left", "truck_right", "crane_up", "crane_down"]
SPEED = (0.15, 0.35)
TWIST_ROLL = (6.0, 10.0)   # degrees, sign seeded
STAGE_X = 1.5              # cast spread across -STAGE_X..STAGE_X, z = 0
BOUNDS = (-2.0, 2.0)       # x range a walk/run must end inside
MOVE_SPEED = {"walk": 1.2, "run": 2.5}  # units/s
MIN_SPEED = {"walk": WALK_SPEED[0], "run": RUN_SPEED[0]}  # shortened moves never go slower than the validator allows

# Lexicons match lowercase words with punctuation and a trailing 's stripped. First match in the phrase wins.
ACTIONS = {
    **dict.fromkeys(["walk", "walks", "walked", "walking", "went", "came", "left"], "walk"),
    **dict.fromkeys(["run", "runs", "ran", "running", "rushed", "chased"], "run"),
    **dict.fromkeys(["point", "points", "pointed", "pointing", "showed", "shows"], "point"),
    **dict.fromkeys(["gasped", "froze", "frozen", "shocked"], "react"),
}
EXPRESSIONS = {
    **dict.fromkeys(["happy", "glad", "smiled", "smiles", "laughed", "laughs", "grinned", "joy"], "happy"),
    **dict.fromkeys(["sad", "cried", "cries", "sighed", "tears", "lonely", "upset"], "sad"),
    **dict.fromkeys(["angry", "mad", "furious", "yelled", "shouted", "screamed"], "angry"),
    **dict.fromkeys(["surprised", "shocked", "gasped", "wow", "stunned"], "surprised"),
    **dict.fromkeys(["sleepy", "tired", "yawned", "yawns", "asleep", "nap", "napped", "slept"], "sleepy"),
}
DIRECTIONS = {"left": -1, "right": 1}


def token(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"['’]s\W*$", "", word.lower()))


def seed_for(slug: str, part_number: int) -> int:
    return zlib.crc32(slug.encode()) + part_number  # stable across runs (unlike hash())


def tag_words(md: str, cast_ids: list[str], default_cast: list[str]):
    """Return (words, [(set, cast tuple, twist starts here)]) from story.md, words as prep's script has them."""
    text, directives = mark_directives(md)
    set_, cast, twist_next = DEFAULT_SET, tuple(default_cast), False
    words, tags = [], []
    for tok in clean_markdown(text).split():
        m = MARKER_RE.match(tok)
        if not m:
            words.append(tok)
            tags.append((set_, cast, twist_next))
            twist_next = False
        elif m[1] == "!":
            twist_next = True
        else:
            line, d = directives[int(m[1])]
            name, _, arg = d.strip().partition(" ")
            arg = arg.strip()
            if name == "set" and arg:
                set_ = arg
            elif name == "cast":
                ids = [x.strip() for x in arg.split(",") if x.strip()]
                if not ids:
                    raise StageError(f"story.md line {line}: @cast needs at least one cast id")
                unknown = [x for x in ids if x not in cast_ids]
                if unknown:
                    raise StageError(f"story.md line {line}: @cast: unknown cast id {', '.join(unknown)} "
                                     f"(series cast: {', '.join(cast_ids)}; add with cast-add)")
                cast = tuple(ids)
            else:
                raise StageError(f"story.md line {line}: bad directive @{d.strip()} (use @set <name> or @cast a, b)")
    return words, tags


def spread(cast) -> dict[str, float]:
    n = len(cast)
    return {cid: 0.0 if n == 1 else round(-STAGE_X + 2 * STAGE_X * i / (n - 1), 3) for i, cid in enumerate(cast)}


def fit_move(x: float, d: int, action: str, seconds: float) -> tuple[str, int, float] | None:
    """(action, direction, distance) for a walk/run from x that ends inside the stage bounds, or None (go idle).

    Full distance in direction d; else flipped; else the roomier side shortened, but never slower than
    the validator's minimum speed (plus a mm of rounding margin). A run that can't fit is tried as a walk.
    """
    dist = MOVE_SPEED[action] * seconds
    for dd in (d, -d):
        if BOUNDS[0] <= x + dd * dist <= BOUNDS[1]:
            return action, dd, dist
    dd = 1 if BOUNDS[1] - x >= x - BOUNDS[0] else -1
    room = math.floor(((BOUNDS[1] - x) if dd > 0 else (x - BOUNDS[0])) * 1000) / 1000
    if room >= MIN_SPEED[action] * seconds + 0.001:
        return action, dd, room
    return fit_move(x, d, "walk", seconds) if action == "run" else None


def _actors(cast, pos, subject, words, seconds):
    """Actors for one shot, starting at pos[cid]. Updates pos to where each one ends."""
    action = next((ACTIONS[w] for w in words if w in ACTIONS), "talk")
    expression = next((EXPRESSIONS[w] for w in words if w in EXPRESSIONS), "neutral")
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
            move = fit_move(x, d, action, seconds)
        if move:
            act, d, dist = move
            pos[cid] = round(x + d * dist, 3)
            out.append(Actor(cast_id=cid, action=act, start_pos=(x, 0.0), end_pos=(pos[cid], 0.0),
                             facing="left" if d < 0 else "right", expression=expression))
        else:
            act = "idle" if action in MOVE_SPEED else action  # a walk/run that can't fit on stage
            out.append(Actor(cast_id=cid, action=act, start_pos=(x, 0.0), facing="camera", expression=expression))
    return out


def plan(md: str, phrases: PhrasesModel, series: SeriesModel, part_number: int) -> StoryModel:
    if not series.cast:
        raise StageError("series.json has no cast: add some with cast-add")
    ids = [c.id for c in series.cast]
    words, tags = tag_words(md, ids, ids[:DEFAULT_CAST_SIZE])
    heard = [w.text for w in phrases.words]
    if words != heard:
        i = next((i for i, (a, b) in enumerate(zip(words, heard)) if a != b), min(len(words), len(heard)))
        at = lambda ws: repr(ws[i]) if i < len(ws) else "(end)"
        raise StageError(f"story.md and phrases.json differ at word {i + 1}: story {at(words)}, phrases {at(heard)} "
                         f"({len(words)} vs {len(heard)} words). Re-run prep and timing after editing story.md.")

    seed = seed_for(series.slug, part_number)
    rng = random.Random(seed)
    total = duration_frames(phrases.duration, FPS)
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

    shots, cues = [], [Cue(frame=0, kind="music_start")]
    prev_angle = prev_set = subject = None
    pos: dict[str, float] = {}  # where each actor stands now; reset on a set change
    for i, p in enumerate(phrases.phrases):
        set_, cast, _ = tags[p.word_start]
        if set_ != prev_set:
            pos = {}
        home = spread(cast)
        for cid in cast:  # newcomers (start, set change, @cast change) take their even-spread spot
            pos.setdefault(cid, home[cid])
        twist = any(t[2] for t in tags[p.word_start:p.word_end + 1])
        pw = [token(w) for w in heard[p.word_start:p.word_end + 1]]
        mentioned = next((names[w] for w in pw if names.get(w) in cast), None)
        subject = mentioned or (subject if subject in cast else cast[0])
        a, b = starts[i], ends[i]
        parts = math.ceil((b - a) / MAX_SHOT_FRAMES)
        for k in range(parts):
            s0, s1 = a + (b - a) * k // parts, a + (b - a) * (k + 1) // parts
            angle = rng.choice([x for x in ANGLES if x != prev_angle])
            move, speed, roll = rng.choice(MOVES), round(rng.uniform(*SPEED), 3), 0.0
            is_twist = twist and k == 0
            if is_twist:
                move = "push_in"
                roll = round(rng.uniform(*TWIST_ROLL), 2) * rng.choice((-1, 1))
                cues += [Cue(frame=s0, kind="music_stop"), Cue(frame=s0, kind="low_hit")]
            if prev_set is not None and set_ != prev_set:
                cues.append(Cue(frame=s0, kind="whoosh"))
            shots.append(Shot(id=f"s{len(shots) + 1:02d}", start_frame=s0, end_frame=s1, set=set_,
                              phrase_range=(i, i), camera=Camera(angle=angle, move=move, speed=speed, roll_deg=roll),
                              actors=_actors(cast, pos, subject, pw, (s1 - s0) / FPS), twist=is_twist))
            prev_angle, prev_set = angle, set_
    return StoryModel(duration_frames=total, seed=seed, shots=shots, cues=cues)


def run(part_dir: Path) -> None:
    story_md = part_dir / "story.md"
    if not story_md.exists():
        raise StageError("story.md not found")
    phrases = load_model(part_dir / "phrases.json", PhrasesModel)
    series = load_model(part_dir.parent / "series.json", SeriesModel)
    story = plan(story_md.read_text(encoding="utf-8"), phrases, series, int(part_dir.name.split("-")[1]))
    errors = validate(story, phrases, {c.id for c in series.cast})
    for e in errors:
        print(f"  {e.shot_id or '-'}  {e.rule}: {e.message}")
    if errors:
        raise StageError(f"planned story.json fails validation ({len(errors)} error(s)); nothing written")
    atomic_write_json(part_dir / "story.json", story.model_dump(mode="json"))
    print(f"shots: {len(story.shots)}, frames: {story.duration_frames}, seed: {story.seed}")
