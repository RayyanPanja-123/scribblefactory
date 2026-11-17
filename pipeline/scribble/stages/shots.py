"""shots: story.md directives + phrases.json + series cast -> story.json. Rule-based and seeded, no AI.

Each phrase gets a shot starting at its first word (pauses stay with the earlier shot); shots over
MAX_SHOT_FRAMES split into equal parts. Directive state (@set, @cast, @dogs, !!) is read at a phrase's first word.
The output must pass the validator, otherwise nothing is written.
"""

import math
import random
import re
import zlib
from pathlib import Path

from ..io import atomic_write_json
from ..schemas import Actor, Animal, Camera, Cue, PhrasesModel, SeriesModel, Shot, StoryModel, Travel
from ..validate import DOG_RUN_SPEED, MAX_SHOT_FRAMES, OUTDOOR_SETS, RUN_SPEED, WALK_SPEED, duration_frames, validate
from .prep import MARKER_RE, clean_markdown, mark_directives
from .runner import StageError
from .validate import load_model

INPUTS = ["story.md", "phrases.json", "../series.json"]
OUTPUTS = ["story.json"]

FPS = 30
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
MOVE_SPEED = {"walk": 1.2, "run": 2.5}  # units/s
MIN_SPEED = {"walk": WALK_SPEED[0], "run": RUN_SPEED[0]}  # shortened moves never go slower than the validator allows
MIN_GAP = 0.8              # actors at least this far apart in x at the start and end of every shot
TRAVEL_Z = 0.3             # travel shots: each actor seeded in z -0.3..0.3 so a pack reads as a group
# dogs (@dogs N): ids dog1..dogN, colour variant seeded per id (stable for the whole part)
MAX_DOGS = 6
DOG_VARIANTS = ["brown", "black", "tan", "white_patches"]
DOG_GAP = 0.6              # travel: a dog never gets closer than this to the rearmost actor (x, so also 2D)
DOG_STEP = 0.35            # x stagger between dogs in a pack / on one stage edge
DOG_Z = 0.45               # travel: dogs seeded in z -0.45..0.45
DOG_CLOSE = (0.15, 0.35)   # travel: units/s a dog gains on the actors (on top of the scroll)
DOG_EDGE_X = 1.8           # non-travel: dogs stand at |x| >= this ...
DOG_EDGE_GAP = 0.9         # ... and at least this far (x) outside every actor's start/end, so cards never overlap

# Lexicons match lowercase words with punctuation and a trailing 's stripped. First match in the phrase wins.
ACTIONS = {
    **dict.fromkeys(["walk", "walks", "walked", "walking", "went", "came", "left"], "walk"),
    **dict.fromkeys(["run", "runs", "ran", "running", "rushed", "chased", "sprint", "sprinted", "sprinting", "dodging"],
                    "run"),
    # no "showed": it fires on "showed up". waved/waving stand in until a wave action exists (Step 5c)
    **dict.fromkeys(["point", "points", "pointed", "pointing", "shows", "waved", "waving"], "point"),
    **dict.fromkeys(["gasped", "froze", "frozen", "shocked", "collapsed", "collapse", "dizzy", "cramps", "hopped"],
                    "react"),
}
EXPRESSIONS = {
    **dict.fromkeys(["happy", "glad", "smiled", "smiles", "laughed", "laughs", "laughing", "grinned", "joy",
                     "cheerfully", "comfortably"], "happy"),
    **dict.fromkeys(["sad", "cried", "cries", "sighed", "tears", "lonely", "upset", "cramps", "collapsed"], "sad"),
    **dict.fromkeys(["angry", "mad", "furious", "yelled", "shouted", "screamed"], "angry"),
    **dict.fromkeys(["surprised", "shocked", "gasped", "wow", "stunned", "chased"], "surprised"),
    **dict.fromkeys(["sleepy", "tired", "yawned", "yawns", "asleep", "nap", "napped", "slept", "dizzy", "exhaustion",
                     "exhausted"], "sleepy"),
}
DIRECTIONS = {"left": -1, "right": 1}


def token(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"['’]s\W*$", "", word.lower()))


def seed_for(slug: str, part_number: int) -> int:
    return zlib.crc32(slug.encode()) + part_number  # stable across runs (unlike hash())


def tag_words(md: str, cast_ids: list[str], default_cast: list[str]):
    """Return (words, [(set, cast tuple, twist starts here, dogs)]) from story.md, words as prep's script has them."""
    text, directives = mark_directives(md)
    set_, cast, twist_next, dogs = DEFAULT_SET, tuple(default_cast), False, 0
    words, tags = [], []
    for tok in clean_markdown(text).split():
        m = MARKER_RE.match(tok)
        if not m:
            words.append(tok)
            tags.append((set_, cast, twist_next, dogs))
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
            elif name == "dogs" and arg.isdigit() and int(arg) <= MAX_DOGS:
                dogs = int(arg)
            else:
                raise StageError(f"story.md line {line}: bad directive @{d.strip()} "
                                 f"(use @set <name>, @cast a, b or @dogs 0-{MAX_DOGS})")
    return words, tags


def spread(cast) -> dict[str, float]:
    """even spots across -STAGE_X..STAGE_X, widened for big casts so neighbours stay MIN_GAP apart"""
    n = len(cast)
    gap = max(2 * STAGE_X / (n - 1), MIN_GAP) if n > 1 else 0
    return {cid: round((i - (n - 1) / 2) * gap, 3) for i, cid in enumerate(cast)}


def _free(x: float, others) -> bool:
    return BOUNDS[0] <= x <= BOUNDS[1] and all(abs(x - o) >= MIN_GAP - 1e-9 for o in others)


def place(want: float, others) -> float:
    """nearest x to want (0.1 steps, right first on ties) that keeps MIN_GAP from others, inside the bounds"""
    for k in range(int((BOUNDS[1] - BOUNDS[0]) * 10) + 1):
        for x in (round(want + k / 10, 3), round(want - k / 10, 3)):
            if _free(x, others):
                return x
    raise StageError(f"no room on stage for {len(others) + 1} actors {MIN_GAP} units apart")


def fit_move(x: float, d: int, action: str, seconds: float, others=()) -> tuple[str, int, float] | None:
    """(action, direction, distance) for a walk/run from x that ends inside the stage bounds and at least MIN_GAP
    from every other actor's x, or None (go idle).

    Full distance in direction d; else flipped; else the free distance nearest the full one (roomier side first,
    0.01 steps; may pass another actor), never slower than the validator's minimum speed (plus a mm of rounding
    margin) and never past the stage edge. A run that can't fit is tried as a walk.
    """
    dist = MOVE_SPEED[action] * seconds
    for dd in (d, -d):
        if _free(round(x + dd * dist, 3), others):
            return action, dd, dist
    lo = MIN_SPEED[action] * seconds + 0.001
    hi_speed = (WALK_SPEED if action == "walk" else RUN_SPEED)[1] * seconds
    room = {dd: math.floor(((BOUNDS[1] - x) if dd > 0 else (x - BOUNDS[0])) * 1000) / 1000 for dd in (1, -1)}
    cands = []
    for dd in (1, -1):
        top = min(room[dd], math.floor(hi_speed * 1000) / 1000)
        cands += [(dd, r) for r in [top] + [round(top - k / 100, 3) for k in range(1, int((top - lo) * 100) + 1)]
                  if r >= lo]
    # nearest the full distance; ties: roomier side, then right, then the longer move
    for dd, r in sorted(cands, key=lambda c: (abs(c[1] - dist), -room[c[0]], -c[0], -c[1])):
        if _free(round(x + dd * r, 3), others):
            return action, dd, r
    return fit_move(x, d, "walk", seconds, others) if action == "run" else None


def _actors(cast, pos, subject, words, seconds, travel_dir=0, zs=None):
    """Actors for one shot, starting at pos[cid]. Updates pos to where each one ends.
    travel_dir (+1 right / -1 left): travel shot, every actor does the subject's walk/run in place at z zs[cid]."""
    action = next((ACTIONS[w] for w in words if w in ACTIONS), "talk")
    expression = next((EXPRESSIONS[w] for w in words if w in EXPRESSIONS), "neutral")
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
            move = fit_move(x, d, action, seconds, [pos[c] for c in cast if c != cid])
        if move:
            act, d, dist = move
            pos[cid] = round(x + d * dist, 3)
            out.append(Actor(cast_id=cid, action=act, start_pos=(x, 0.0), end_pos=(pos[cid], 0.0),
                             facing="left" if d < 0 else "right", expression=expression))
        else:
            act = "idle" if action in MOVE_SPEED else action  # a walk/run that can't fit on stage
            out.append(Actor(cast_id=cid, action=act, start_pos=(x, 0.0), facing="camera", expression=expression))
    return out


def dog_variant(seed: int, dog_id: str) -> str:
    return random.Random(f"{seed}:dog:{dog_id}").choice(DOG_VARIANTS)


def _dogs(n, actors, s0, s1, seed, sid, travel_speed=None):
    """(animals, bark cue or None) for a shot with n dogs.
    Travel: the pack runs behind the actors (the side they run away from), staggered in x and z, each dog closing
    in at a seeded DOG_CLOSE rate and ending >= DOG_GAP behind the rearmost actor.
    Otherwise: dogs idle or bark at the stage edges, alternating sides, outside every actor's path; one bark cue."""
    R, seconds = random.Random(f"{seed}:dogs:{sid}"), (s1 - s0) / FPS
    ids = [f"dog{j + 1}" for j in range(n)]
    out = []
    if travel_speed:
        d = 1 if actors[0].facing == "right" else -1
        rear = min(a.start_pos[0] for a in actors) if d > 0 else max(a.start_pos[0] for a in actors)
        min_close = DOG_RUN_SPEED[0] - travel_speed + 0.01  # a walk-speed scroll alone is too slow for a gallop
        for j, did in enumerate(ids):
            close = math.ceil(max(R.uniform(*DOG_CLOSE), min_close) * seconds * 1000) / 1000
            end = round(rear - d * (DOG_GAP + 0.15 + j * DOG_STEP + R.uniform(0, 0.1)), 3)
            z = round(R.uniform(-DOG_Z, DOG_Z), 2)
            out.append(Animal(id=did, kind="dog", action="run", start_pos=(round(end - d * close, 3), z),
                              end_pos=(end, z), facing=actors[0].facing, variant=dog_variant(seed, did)))
        return out, None
    xs = [x for a in actors for x in (a.start_pos[0], (a.end_pos or a.start_pos)[0])] or [0.0]
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
        names.setdefault(token(c.id) + "s", c.id)  # plural: "the runners" -> runner

    shots, cues = [], [Cue(frame=0, kind="music_start")]
    prev_angle = prev_set = subject = None
    prev_cast, travel_run = (), None  # travel_run: first shot id of the current run of travel shots on one set
    pos: dict[str, float] = {}  # where each actor stands now; reset on a set change
    for i, p in enumerate(phrases.phrases):
        set_, cast, _, dogs = tags[p.word_start]
        if set_ != prev_set:
            pos = {}
        home, placed = spread(cast), []
        # actors on stage last shot stay put; newcomers (start, set change, @cast change) and returners take the
        # free spot nearest their even-spread one, MIN_GAP from everyone already placed
        for cid in sorted(cast, key=lambda c: c not in prev_cast or c not in pos):
            if cid not in pos or cid not in prev_cast or not _free(pos[cid], placed):
                pos[cid] = place(home[cid], placed)
            placed.append(pos[cid])
        prev_cast = cast
        twist = any(t[2] for t in tags[p.word_start:p.word_end + 1])
        pw = [token(w) for w in heard[p.word_start:p.word_end + 1]]
        mentioned = next((names[w] for w in pw if names.get(w) in cast), None)
        subject = mentioned or (subject if subject in cast else cast[0])
        action = next((ACTIONS[w] for w in pw if w in ACTIONS), None)
        travel = action in MOVE_SPEED and set_ in OUTDOOR_SETS
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
            if travel:  # direction and z stagger seeded once per run of travel shots, so the run keeps them
                if travel_run is None or set_ != prev_set:
                    travel_run = sid
                tdir = random.Random(f"{seed}:travel:{travel_run}").choice((-1, 1))
                zs = {c: round(random.Random(f"{seed}:travel:{travel_run}:{c}").uniform(-TRAVEL_Z, TRAVEL_Z), 2)
                      for c in cast}
            else:
                travel_run = None
            actors = _actors(cast, pos, subject, pw, (s1 - s0) / FPS, tdir, zs)
            animals, bark = _dogs(dogs, actors, s0, s1, seed, sid, MOVE_SPEED[action] if travel else None)
            if bark:
                cues.append(bark)
            shots.append(Shot(id=sid, start_frame=s0, end_frame=s1, set=set_,
                              phrase_range=(i, i), camera=Camera(angle=angle, move=move, speed=speed, roll_deg=roll),
                              actors=actors, animals=animals, twist=is_twist,
                              travel=Travel(speed=MOVE_SPEED[action]) if travel else None))
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
