import json
import math

import pytest

from pipeline.scribble.io import atomic_write_json, load_part, save_part, save_series
from pipeline.scribble.schemas import PartModel, PhrasesModel, SeriesModel
from pipeline.scribble.stages import prep, shots
from pipeline.scribble.stages.prep import clean_markdown, strip_directives
from pipeline.scribble.stages.runner import StageError, run_stage
from pipeline.scribble.stages.timing import SENTENCE_END, split_phrases
from pipeline.scribble.validate import MAX_SHOT_FRAMES, validate

SERIES = SeriesModel.model_validate({
    "slug": "office-nap", "title": "Office Nap", "created_at": "2026-11-16T10:00:00Z",
    "voice": {"voice_name": "Brian"}, "style": {"preset": "default"},
    "cast": [{"id": "bob", "name": "Bob", "outfit_color": "#3a7bd5", "eyes": "dots"},
             {"id": "amy", "name": "Amy", "outfit_color": "#e2453c", "eyes": "half_closed"},
             {"id": "karen", "name": "Karen", "outfit_color": "#22aa55", "eyes": "dots"}],
})

SHORT = "# Short\n\nBob sat down. Amy smiled.\n"
LONG = "# Long\n\nBob kept on talking about his very long day.\n"
DIRECTED = """# Directed

@set office
@cast bob, karen
Bob walked in. Karen yelled at him.

@set street
@cast bob, amy
Amy gasped.
!! Bob was the boss.
"""


def phrases_for(md: str, word_s=0.4) -> PhrasesModel:
    """Fake timing: words of word_s seconds, 0.5 s pause after each sentence, split like the timing stage."""
    t, words = 0.2, []
    for w in clean_markdown(strip_directives(md)).split():
        words.append({"text": w, "start": round(t, 3), "end": round(t + word_s, 3)})
        t += word_s + (0.5 if SENTENCE_END.search(w) else 0.05)
    return PhrasesModel(duration=round(t + 0.3, 3), words=words, phrases=split_phrases(words))


def plan(md, word_s=0.4, series=SERIES):
    ph = phrases_for(md, word_s)
    return shots.plan(md, ph, series, 1), ph


def errors(md, word_s=0.4):
    story, ph = plan(md, word_s)
    return validate(story, ph, {c.id for c in SERIES.cast})


# --- prep: directives ---

def test_prep_strips_directives():
    md = "# T\n\n@set office\n  @cast bob, amy\nBob came in.\n!! He was *fired*.\r\n  !!  Twice.\nWow!! ok\n"
    assert clean_markdown(strip_directives(md)) == "Bob came in. He was fired. Twice. Wow!! ok"


def test_prep_stage_writes_script_without_directives(tmp_path):
    d = tmp_path / "part-01"
    d.mkdir()
    save_part(d / "part.json", PartModel(id="part-01", number=1, title="T"))
    (d / "story.md").write_text(DIRECTED, encoding="utf-8")
    assert run_stage(d, "prep", prep.run, inputs=prep.INPUTS, outputs=prep.OUTPUTS) == "done"
    script = (d / "script-for-tts.txt").read_text(encoding="utf-8")
    assert "@" not in script and "!!" not in script and "Bob was the boss." in script


# --- planner ---

@pytest.mark.parametrize("md,word_s", [(SHORT, 0.4), (LONG, 1.0), (DIRECTED, 0.4)], ids=["short", "long", "directed"])
def test_output_passes_validator(md, word_s):
    assert errors(md, word_s) == []


def test_defaults_room_and_first_two_cast():
    story, _ = plan(SHORT)
    assert {s.set for s in story.shots} == {"room"}
    assert all([a.cast_id for a in s.actors] == ["bob", "amy"] for s in story.shots)
    assert [c.kind for c in story.cues] == ["music_start"]


def test_directives_applied():
    story, ph = plan(DIRECTED)
    texts = [p.text for p in ph.phrases]
    assert texts == ["Bob walked in.", "Karen yelled at him.", "Amy gasped.", "Bob was the boss."]
    s1, s2, s3, s4 = story.shots
    assert [s.set for s in story.shots] == ["office", "office", "street", "street"]
    assert [a.cast_id for a in s1.actors] == ["bob", "karen"]
    assert [a.cast_id for a in s3.actors] == ["bob", "amy"]
    assert [s.twist for s in story.shots] == [False, False, False, True]
    assert s4.camera.move == "push_in" and 6 <= abs(s4.camera.roll_deg) <= 10
    cues = [(c.frame, c.kind) for c in story.cues]
    assert cues == [(0, "music_start"), (s3.start_frame, "whoosh"),
                    (s4.start_frame, "music_stop"), (s4.start_frame, "low_hit")]


def test_shot_frames_follow_phrases():
    story, ph = plan(DIRECTED)
    assert story.shots[0].start_frame == 0
    assert [s.start_frame for s in story.shots[1:]] == [round(p.start * 30) for p in ph.phrases[1:]]
    assert story.shots[-1].end_frame == story.duration_frames
    for s in story.shots:
        assert 0.15 <= s.camera.speed <= 0.35
    assert all(a.camera.angle != b.camera.angle for a, b in zip(story.shots, story.shots[1:]))


def test_long_phrase_splits_with_new_angles():
    story, ph = plan(LONG, word_s=1.0)
    assert len(ph.phrases) == 2  # 7-word cap, then "day."
    first = [s for s in story.shots if s.phrase_range == (0, 0)]
    assert len(first) >= 3
    lengths = [s.end_frame - s.start_frame for s in first]
    assert max(lengths) <= MAX_SHOT_FRAMES and max(lengths) - min(lengths) <= 1
    assert all(a.camera.angle != b.camera.angle for a, b in zip(first, first[1:]))


FINAL = SERIES.model_copy(update={"status": "complete", "parts": ["part-01"]})  # last part: no end card


def _subject(md, word_s=0.15):  # short shot (final part, no end card): a run fits on stage
    story, _ = plan("# K\n\n@cast bob, amy\n" + md + "\n", word_s=word_s, series=FINAL)
    s = story.shots[0]
    return next(a for a in s.actors if a.action != "idle"), s


@pytest.mark.parametrize("line,action,expression", [
    ("Bob walked home.", "walk", "neutral"),
    ("Amy ran away.", "run", "neutral"),
    ("Bob pointed, glad.", "point", "happy"),
    ("Amy froze, sad.", "react", "sad"),
    ("Bob gasped.", "react", "surprised"),
    ("Amy yawned.", "talk", "sleepy"),
    ("Bob's boss was furious.", "talk", "angry"),
])
def test_keywords(line, action, expression):
    a, _ = _subject(line)
    assert (a.action, a.expression) == (action, expression)


def test_subject_is_first_named_cast_and_others_idle():
    story, _ = plan("# K\n\n@cast bob, amy\nThen Amy met Bob. She stayed.\n")
    first, second = story.shots
    assert [(a.cast_id, a.action, a.facing) for a in first.actors] == [("bob", "idle", "right"), ("amy", "talk", "camera")]
    assert [(a.cast_id, a.action) for a in second.actors] == [("bob", "idle"), ("amy", "talk")]  # previous subject


def test_walk_direction_distance_and_facing():
    a, s = _subject("Amy walked in.")  # amy at x=STAGE_X, no direction word: toward the centre
    secs = (s.end_frame - s.start_frame) / 30
    assert a.start_pos == (shots.STAGE_X, 0.0) and a.facing == "left"
    # full walk would end 0.56 from bob (at -STAGE_X): it stops MIN_GAP short of him instead
    assert shots.STAGE_X - 1.2 * secs < -shots.STAGE_X + shots.MIN_GAP
    assert a.end_pos[0] == pytest.approx(-shots.STAGE_X + shots.MIN_GAP, abs=1e-3)
    a, s = _subject("Amy ran right.", 0.3)  # ~1.5 s, 4.25 units fits neither way: flipped, shortened to the left edge
    assert a.facing == "left" and a.end_pos == (shots.BOUNDS[0], 0.0)
    a, _ = _subject("Amy left.")  # "left": walk keyword and direction (amy at STAGE_X has room to the left)
    assert (a.action, a.facing) == ("walk", "left") and a.end_pos[0] < a.start_pos[0]


def test_unknown_cast_id_fails_clearly():
    md = "# X\n\n@cast bob, zed\nBob sat.\n"
    with pytest.raises(StageError, match=r"line 3: @cast: unknown cast id zed \(series cast: bob, amy, karen"):
        shots.plan(md, phrases_for(md), SERIES, 1)


@pytest.mark.parametrize("line", ["@cast", "@set", "@scene office"])
def test_bad_directive_fails(line):
    md = f"# X\n\n{line}\nBob sat.\n"
    with pytest.raises(StageError, match="line 3"):
        shots.plan(md, phrases_for(md), SERIES, 1)


def test_story_changed_after_timing_fails_clearly():
    ph = phrases_for(SHORT)
    with pytest.raises(StageError, match=r"differ at word 2: story 'stood', phrases 'sat'"):
        shots.plan(SHORT.replace("sat", "stood"), ph, SERIES, 1)


def test_seed_is_stable_and_per_part():
    assert shots.seed_for("office-nap", 1) == shots.seed_for("office-nap", 1)
    assert shots.seed_for("office-nap", 2) == shots.seed_for("office-nap", 1) + 1
    assert plan(DIRECTED)[0].seed == shots.seed_for("office-nap", 1)


# --- stage ---

@pytest.fixture
def part(tmp_path):
    save_series(tmp_path / "series.json", SERIES)
    d = tmp_path / "part-01"
    d.mkdir()
    save_part(d / "part.json", PartModel(id="part-01", number=1, title="T"))
    (d / "story.md").write_text(DIRECTED, encoding="utf-8")
    atomic_write_json(d / "phrases.json", phrases_for(DIRECTED).model_dump(mode="json"))
    return d


def run(part, force=False):
    return run_stage(part, "shots", shots.run, force=force, inputs=shots.INPUTS, outputs=shots.OUTPUTS)


def test_stage_deterministic(part):
    assert run(part) == "done"
    first = (part / "story.json").read_bytes()
    assert run(part) == "skipped"
    assert run(part, force=True) == "done"
    assert (part / "story.json").read_bytes() == first
    assert json.loads(first)["shots"][0]["id"] == "s01"


def test_stage_fails_and_writes_nothing(part):
    (part / "story.md").write_text(DIRECTED.replace("@cast bob, amy", "@cast bob, zed"), encoding="utf-8")
    assert run(part) == "failed"
    assert not (part / "story.json").exists()
    assert "unknown cast id zed" in load_part(part / "part.json").stages.shots.error


def test_stage_unknown_set_fails_before_render(part):
    (part / "story.md").write_text(DIRECTED.replace("@set street", "@set moon"), encoding="utf-8")
    assert run(part) == "failed"
    assert "unknown set: moon" in load_part(part / "part.json").stages.shots.error
    assert not (part / "story.json").exists()


def test_stage_invalid_plan_writes_nothing(part, monkeypatch, capsys):
    monkeypatch.setattr(shots, "MOVE_SPEED", {"walk": 0.3, "run": 2.5})  # walk too slow for the validator: gliding
    assert run(part) == "failed"
    assert not (part / "story.json").exists()
    assert "gliding" in capsys.readouterr().out
    assert "fails validation" in load_part(part / "part.json").stages.shots.error


# --- position carry-over and stage bounds ---

def _amy(story, i):
    return next(a for a in story.shots[i].actors if a.cast_id == "amy")


def test_next_shot_starts_where_walk_ended():
    story, _ = plan("# C\n\n@cast bob, amy\nAmy walked in. Amy smiled.\n")
    walk, after = _amy(story, 0), _amy(story, 1)
    assert walk.action == "walk" and walk.end_pos[0] < shots.STAGE_X
    assert after.start_pos == walk.end_pos and after.end_pos is None
    bob = next(a for a in story.shots[1].actors if a.cast_id == "bob")
    assert bob.start_pos == (-shots.STAGE_X, 0.0)  # bob never moved


def test_set_change_resets_positions():
    story, _ = plan("# C\n\n@cast bob, amy\nAmy walked in.\n@set street\nAmy smiled.\n")
    assert _amy(story, 0).end_pos[0] < shots.STAGE_X
    assert _amy(story, 1).start_pos == (shots.STAGE_X, 0.0)


def test_walk_off_the_edge_flips_direction():
    story, _ = plan("# C\n\n@cast bob, amy\nAmy walked right.\n")  # amy at STAGE_X, right would end past 2.0
    a = _amy(story, 0)
    assert a.facing == "left" and shots.BOUNDS[0] <= a.end_pos[0] < a.start_pos[0]


@pytest.mark.parametrize("x,d,action,secs,want", [
    (0.0, 1, "walk", 1.0, ("walk", 1, 1.2)),    # fits as asked
    (1.5, 1, "walk", 1.0, ("walk", -1, 1.2)),   # flipped
    (0.0, 1, "walk", 3.0, ("walk", 1, 2.0)),    # 3.6 fits neither way: shortened to the edge, 0.67 units/s
    (0.5, -1, "walk", 3.0, ("walk", -1, 2.5)),  # shortened toward the roomier side
    (-0.5, 1, "run", 1.0, ("run", 1, 2.5)),     # run fits
    (1.9, 1, "run", 2.0, ("run", -1, 3.9)),     # run shortened to the far edge: 1.95 units/s, still a run
    (0.0, 1, "run", 3.0, ("walk", 1, 2.0)),     # run too slow even shortened (0.67 < 1.8): walk, shortened
    (1.5, 1, "run", 2.0, ("walk", -1, 2.4)),    # run can't fit (1.75 < 1.8): full walk, flipped like a walk
    (0.0, 1, "walk", 4.0, None),                # 2.0 in 4 s = 0.5 < walk's 0.6 units/s: idle
    (0.0, 1, "run", 4.0, None),                 # run -> walk -> still too slow: idle
])
def test_fit_move(x, d, action, secs, want):
    got = shots.fit_move(x, d, action, secs)
    assert got == want if want is None else got == (want[0], want[1], pytest.approx(want[2]))


def test_repeated_walks_stay_inside_and_validate():
    md = "# C\n\n@cast bob, amy\n" + " ".join(["Amy walked right."] * 6) + " Bob ran left. Bob ran left.\n"
    story, ph = plan(md)
    for s in story.shots:
        for a in s.actors:
            for p in (a.start_pos, a.end_pos):
                assert p is None or shots.BOUNDS[0] <= p[0] <= shots.BOUNDS[1]
    for prev, cur in zip(story.shots, story.shots[1:]):  # carry-over across every shot
        ends = {a.cast_id: a.end_pos or a.start_pos for a in prev.actors}
        assert all(a.start_pos == ends[a.cast_id] for a in cur.actors)
    assert validate(story, ph, {c.id for c in SERIES.cast}) == []
    assert plan(md)[0] == story  # deterministic


def test_long_run_becomes_walk_and_validates():
    md = "# R\n\n@cast bob, amy\nAmy ran away. Amy ran away. Bob ran away. Amy smiled.\n"
    story, ph = plan(md)  # ~2.3 s shots: a 2.5 units/s run (5.75) can't fit on the 4-unit stage
    acts = [next(a for a in s.actors if a.action != "idle") for s in story.shots[:3]]
    assert acts[0].action == "walk"  # the first, longest shot (from frame 0) can't hold a run
    assert {a.action for a in acts} <= {"walk", "run"}  # shorter shots may keep a shortened run
    for a, s in zip(acts, story.shots):
        lo, hi = {"walk": (0.6, 1.8), "run": (1.8, 4.0)}[a.action]
        speed = abs(a.end_pos[0] - a.start_pos[0]) / ((s.end_frame - s.start_frame) / 30)
        assert lo <= speed <= hi and shots.BOUNDS[0] <= a.end_pos[0] <= shots.BOUNDS[1]
    assert validate(story, ph, {c.id for c in SERIES.cast}) == []
    assert plan(md)[0] == story  # deterministic


def test_move_that_cannot_fit_goes_idle(monkeypatch):
    # unreachable with real values (<= 3 s shots x 0.6 min walk speed < 2.0 of room); force it
    monkeypatch.setattr(shots, "MOVE_SPEED", {"walk": 50.0, "run": 50.0})  # full move never fits
    monkeypatch.setattr(shots, "MIN_SPEED", {"walk": 5.0, "run": 5.0})     # shortened move always too slow
    story, ph = plan("# R\n\n@cast bob, amy\nAmy ran away. Amy walked in.\n")
    assert [_amy(story, i).action for i in (0, 1)] == ["idle", "idle"]
    assert all(_amy(story, i).end_pos is None for i in (0, 1))


# --- establishing wide shots ---

def test_first_shot_and_set_changes_are_wide():
    story, ph = plan(DIRECTED)  # office: s01, s02; street: s03, s04
    assert [s.set for s in story.shots] == ["office", "office", "street", "street"]
    assert story.shots[0].camera.angle == "wide" and story.shots[2].camera.angle == "wide"
    assert story.shots[1].camera.angle != "wide" and story.shots[3].camera.angle != "wide"
    assert validate(story, ph, {c.id for c in SERIES.cast}) == []


def test_set_change_right_after_a_wide_shot_takes_next_angle():
    md = "# W\n\n@set office\nBob sat.\n@set street\nAmy smiled.\n@set room\nBob left.\n"
    story, ph = plan(md)
    assert [(s.set, s.camera.angle) for s in story.shots] == [
        ("office", "wide"), ("street", "medium"), ("room", "wide")]
    assert validate(story, ph, {c.id for c in SERIES.cast}) == []


def test_starting_spread_is_plus_minus_one():
    assert shots.STAGE_X == 1.0
    assert shots.spread(["bob", "amy"]) == {"bob": -1.0, "amy": 1.0}
    assert shots.spread(["bob", "amy", "karen"]) == {"bob": -1.0, "amy": 0.0, "karen": 1.0}
    assert shots.spread(["bob"]) == {"bob": 0.0}
    story, ph = plan("# S\n\n@cast bob, amy, karen\nBob sat. Amy smiled.\n")
    assert [a.start_pos for a in story.shots[0].actors] == [(-1.0, 0.0), (0.0, 0.0), (1.0, 0.0)]
    assert validate(story, ph, {c.id for c in SERIES.cast}) == []


# --- lexicon additions (map onto existing actions / expressions) ---

@pytest.mark.parametrize("line,action,expression", [
    ("Amy sprinted off.", "run", "neutral"),
    ("Amy kept dodging.", "run", "neutral"),
    ("Amy was chased.", "run", "surprised"),
    ("Bob collapsed.", "react", "sad"),
    ("Bob got dizzy.", "react", "sleepy"),
    ("Bob had cramps.", "react", "sad"),
    ("Bob hopped in.", "react", "neutral"),
    ("Bob waved cheerfully.", "wave", "happy"),
    ("Bob kept waving.", "wave", "neutral"),
    ("Amy showed up late.", "talk", "neutral"),        # "showed" no longer points
    ("Bob rode comfortably.", "talk", "happy"),
    ("Bob fought exhaustion.", "talk", "sleepy"),
    ("Bob was exhausted, laughing.", "talk", "sleepy"),  # first expression word wins
    ("Bob was furious.", "talk", "angry"),
])
def test_lexicon_additions(line, action, expression):
    a, _ = _subject(line)
    assert (a.action, a.expression) == (action, expression)


def test_plural_cast_id_matches_subject():
    story, _ = plan("# P\n\n@cast bob, amy\nThen the amys had to leave.\n")
    assert next(a for a in story.shots[0].actors if a.action != "idle").cast_id == "amy"


# --- actor spacing and travel shots ---

def _xs_apart(story):
    """every pair of actors >= MIN_GAP apart in x at the start and at the end of every shot"""
    for s in story.shots:
        for pts in ([a.start_pos for a in s.actors], [a.end_pos or a.start_pos for a in s.actors]):
            xs = sorted(p[0] for p in pts)
            assert all(b - a >= shots.MIN_GAP - 1e-9 for a, b in zip(xs, xs[1:])), (s.id, xs)


def test_spacing_holds_through_walks_cast_changes_and_big_casts():
    md = ("# S\n\n@cast bob, amy, karen\n" + " ".join(["Amy walked left.", "Bob ran right.", "Karen walked in."] * 3)
          + "\n@cast amy\nAmy walked right. Amy ran left.\n@cast karen, bob, amy\nBob walked left. Karen smiled.\n")
    story, ph = plan(md)
    _xs_apart(story)
    assert validate(story, ph, {c.id for c in SERIES.cast}) == []
    assert all(b - a >= shots.MIN_GAP for a, b in zip(*[iter(sorted(shots.spread("abcdef").values()))] * 2))


def test_spread_widens_for_big_casts():
    xs = sorted(shots.spread(["a", "b", "c", "d"]).values())
    assert xs == pytest.approx([-1.2, -0.4, 0.4, 1.2]) and shots.spread(["a", "b"]) == {"a": -1.0, "b": 1.0}


def test_fit_move_keeps_gap_and_may_pass():
    # 1 s from 1.0 with someone at 0: left would end 0.2 from them, right past the edge: the free 1.0 to the right
    assert shots.fit_move(1.0, -1, "walk", 1.0, [0.0]) == ("walk", 1, pytest.approx(1.0))
    # 2.3 s: min walk 1.38 > the 1.2 to the gap, so it walks past bob (at -1) to -1.8, 0.8 beyond him
    assert shots.fit_move(1.0, -1, "walk", 2.3, [-1.0]) == ("walk", -1, pytest.approx(2.8))


TRAVEL = "# T\n\n@set dirt_road\n@cast bob, amy\nAmy ran away. Bob ran on. Amy walked on. Amy smiled.\n"


def test_outdoor_walk_or_run_becomes_travel_shot():
    story, ph = plan(TRAVEL)
    travel = [s for s in story.shots if s.travel]
    assert [s.travel.speed for s in travel] == [2.5, 2.5, 1.2] and story.shots[-1].travel is None
    for s in travel:
        assert {a.cast_id for a in s.actors} == {"bob", "amy"}  # the whole on-stage cast joins
        assert len({a.action for a in s.actors}) == 1 and len({a.facing for a in s.actors}) == 1
        for a in s.actors:
            assert a.end_pos == a.start_pos and -shots.TRAVEL_Z <= a.start_pos[1] <= shots.TRAVEL_Z  # dx = 0
    assert {a.facing for s in travel for a in s.actors} < {"left", "right"}  # one run: one direction
    assert len({a.start_pos[1] for a in travel[0].actors}) == 2  # staggered in z
    _xs_apart(story)
    assert validate(story, ph, {c.id for c in SERIES.cast}) == []


def test_travel_direction_seeded_per_run():
    story, _ = plan(TRAVEL)
    dirs = {}
    for seed_part in range(1, 30):  # across seeds both directions occur, each run keeps one
        st = shots.plan(TRAVEL, phrases_for(TRAVEL), SERIES, seed_part)
        facings = {a.facing for s in st.shots if s.travel for a in s.actors}
        assert len(facings) == 1
        dirs[seed_part] = facings.pop()
    assert set(dirs.values()) == {"left", "right"}
    assert plan(TRAVEL)[0] == story  # deterministic


def test_no_travel_indoors():
    story, _ = plan(TRAVEL.replace("@set dirt_road", "@set office"))
    assert all(s.travel is None for s in story.shots)


# --- dogs ---

CHASE = "# T\n\n@set dirt_road\n@cast bob, amy\n@dogs 4\nAmy ran away. Bob ran on.\n@dogs 0\nAmy smiled.\n"
EDGES = "# T\n\n@set office\n@cast bob, amy\n@dogs 3\nBob walked in. Amy smiled. Bob walked out.\n"


def test_dogs_directive_sets_pack_until_changed():
    story, ph = plan(CHASE)
    assert [len(s.animals) for s in story.shots] == [4, 4, 0]
    assert [d.id for d in story.shots[0].animals] == ["dog1", "dog2", "dog3", "dog4"]
    assert all(d.kind == "dog" for s in story.shots for d in s.animals)
    assert validate(story, ph, {c.id for c in SERIES.cast}) == []
    assert all(not s.animals for s in plan(SHORT)[0].shots)  # default: no dogs


@pytest.mark.parametrize("line", ["@dogs 7", "@dogs", "@dogs x", "@dogs -1"])
def test_bad_dogs_directive_fails(line):
    with pytest.raises(StageError, match="@dogs 0-6"):
        plan(f"# T\n\n{line}\nBob sat.\n")


def test_prep_strips_dogs_directive_and_line_breaks_keep_the_script():
    plain = "# T\n\nThe dogs came. Another runner got dizzy.\n"
    marked = "# T\n\n@dogs 4\nThe dogs came.\n@dogs 0\nAnother runner got dizzy.\n"
    assert clean_markdown(strip_directives(marked)) == clean_markdown(strip_directives(plain))


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def test_travel_pack_runs_behind_closing_in_never_touching():
    seen = set()
    for part in range(1, 12):
        story = shots.plan(CHASE, phrases_for(CHASE), SERIES, part)
        for s in story.shots:
            if not s.animals:
                continue
            assert s.travel
            way = 1 if s.actors[0].facing == "right" else -1
            seen.add(way)
            rear = min(a.start_pos[0] * way for a in s.actors) * way
            for d in s.animals:
                assert d.action == "run" and d.facing == s.actors[0].facing
                assert (rear - d.end_pos[0]) * way >= shots.DOG_GAP          # behind, never past the gap
                assert abs(d.end_pos[0] - rear) < abs(d.start_pos[0] - rear)  # closing in
                for a in s.actors:                                           # closest at the end: >= 0.6 in 2D
                    assert _dist(d.end_pos, a.start_pos) >= shots.DOG_GAP
            assert len({d.end_pos[0] for d in s.animals}) == 4 and len({d.end_pos[1] for d in s.animals}) > 1
        assert validate(story, phrases_for(CHASE), {c.id for c in SERIES.cast}) == []
    assert seen == {1, -1}


def test_walk_travel_pack_still_gallops_fast_enough():
    md = CHASE.replace("ran away. Bob ran on.", "walked away. Bob walked on.")
    story, ph = plan(md)
    assert story.shots[0].travel.speed == 1.2 and story.shots[0].animals
    assert validate(story, ph, {c.id for c in SERIES.cast}) == []


def test_edge_dogs_idle_or_bark_clear_of_actors_one_bark_cue_per_shot():
    story, ph = plan(EDGES)
    assert validate(story, ph, {c.id for c in SERIES.cast}) == []
    barks = [c.frame for c in story.cues if c.kind == "bark"]
    assert len(barks) == len(story.shots)
    for s, f in zip(story.shots, barks):
        assert s.start_frame <= f < s.end_frame
        assert {d.action for d in s.animals} <= {"idle", "bark"} and any(d.action == "bark" for d in s.animals)
        xs = [x for a in s.actors for x in (a.start_pos[0], (a.end_pos or a.start_pos)[0])]
        for d in s.animals:
            assert d.end_pos is None and abs(d.start_pos[0]) >= shots.DOG_EDGE_X
            assert min(abs(d.start_pos[0] - x) for x in xs) >= shots.DOG_EDGE_GAP - 1e-9
            assert d.facing == ("left" if d.start_pos[0] > 0 else "right")       # toward the stage centre
        assert {d.start_pos[0] > 0 for d in s.animals} == {True, False}          # both edges


def test_dog_variants_seeded_and_stable_for_the_part():
    story, _ = plan(EDGES)
    by_id = {}
    for s in story.shots:
        for d in s.animals:
            assert by_id.setdefault(d.id, d.variant) == d.variant
    seen = {shots.dog_variant(seed, f"dog{j}") for seed in range(20) for j in range(1, 7)}
    assert seen == set(shots.DOG_VARIANTS)
    assert plan(EDGES)[0] == story


# --- dog fixes ---

def test_dog_colours_unique_until_all_used():
    for seed in range(30):
        cols = [shots.dog_variant(seed, f"dog{j}") for j in range(1, 7)]
        assert sorted(cols[:4]) == sorted(shots.DOG_VARIANTS) and cols[4:] == cols[:2]
    orders = {tuple(shots.dog_variant(seed, f"dog{j}") for j in range(1, 5)) for seed in range(30)}
    assert len(orders) > 1  # seeded order


def test_chase_pack_spacing_and_z_stagger():
    md = CHASE.replace("@dogs 4", "@dogs 6")
    for part in range(1, 8):
        story = shots.plan(md, phrases_for(md), SERIES, part)
        for s in story.shots:
            if not s.animals:
                continue
            for u in (0, 0.5, 1):  # spacing holds all shot long (one closing rate per shot)
                xs = sorted(d.start_pos[0] + (d.end_pos[0] - d.start_pos[0]) * u for d in s.animals)
                assert min(b - a for a, b in zip(xs, xs[1:])) >= shots.CHASE_STEP - 1e-6
            zs = [d.start_pos[1] for d in s.animals]
            assert all((z > 0) != (z2 > 0) for z, z2 in zip(zs, zs[1:]))  # alternating sides in z
            assert all(0.1 <= abs(z) <= shots.DOG_Z for z in zs)


# --- car ---

CAR_STORY = ("# T\n\n@set dirt_road\n@cast bob\nBob sat down.\n@car arrive\nA car pulled up. It waited there.\n"
             "@car ride\nBob hopped in. Bob waved at us. Bob rode on.\n@car leave\nThe car drove away. It was quiet.\n"
             "@car off\nThe end came.\n")


def _car_plan(md=CAR_STORY, part=1):
    story = shots.plan(md, phrases_for(md), SERIES, part)
    assert validate(story, phrases_for(md), {c.id for c in SERIES.cast}) == []
    return story


def test_car_directive_modes():
    story = _car_plan()
    modes = [(s.vehicles[0].action if s.vehicles else None) for s in story.shots]
    assert modes == [None, "arrive", "idle", "drive", "drive", "drive", "leave", None, None]


def test_car_arrives_beside_subject_who_reacts_then_parks():
    story = _car_plan()
    arrive, parked = story.shots[1], story.shots[2]
    v, bob = arrive.vehicles[0], arrive.actors[0]
    assert abs(abs(v.end_pos[0] - bob.start_pos[0]) - shots.CAR_BESIDE) < 1e-9
    assert abs(v.start_pos[0] - v.end_pos[0]) == shots.car_dist((arrive.end_frame - arrive.start_frame) / 30)
    assert bob.action == "react" and v.riders == [] and not arrive.travel
    assert parked.vehicles[0].start_pos == v.end_pos and parked.vehicles[0].facing == v.facing


def test_car_ride_is_a_travel_shot_riders_wave_on_wave_lines():
    story = _car_plan()
    for s in story.shots[3:6]:
        assert s.travel.speed == shots.CAR_TRAVEL_SPEED == 4.0
        v = s.vehicles[0]
        assert v.riders == ["bob"] and v.end_pos == v.start_pos and v.facing in ("left", "right")
        assert [a.cast_id for a in s.actors] == ["bob"]
    assert [s.actors[0].action for s in story.shots[3:6]] == ["ride", "wave", "ride"]  # "hopped" is not a ride verb


def test_car_leave_drives_off_then_gone():
    story = _car_plan()
    leave = story.shots[6].vehicles[0]
    way = 1 if leave.facing == "right" else -1
    assert (leave.end_pos[0] - leave.start_pos[0]) * way > 0 and not story.shots[7].vehicles


def test_car_ride_indoors_parks_and_car_variant_stable():
    story = _car_plan(CAR_STORY.replace("dirt_road", "office"))
    ride = story.shots[3]
    assert ride.travel is None and ride.vehicles[0].action == "idle" and ride.vehicles[0].riders == ["bob"]
    assert len({v.variant for s in story.shots for v in s.vehicles}) == 1


@pytest.mark.parametrize("line", ["@car fly", "@car", "@car ride now"])
def test_bad_car_directive_fails(line):
    with pytest.raises(StageError, match=r"@car arrive \| ride \| leave \| off"):
        plan(f"# T\n\n{line}\nBob sat.\n")


def test_car_seats_three():
    md = "# T\n\n@set dirt_road\n@cast bob, amy, karen, bob\n@car ride\nThey rode.\n"
    with pytest.raises(StageError, match="seats 3"):
        plan(md)


def test_prep_strips_car_directive():
    plain = "# T\n\nUntil his manager pulled up. Fred hopped in.\n"
    marked = "# T\n\n@car arrive\nUntil his manager pulled up.\n@car ride\nFred hopped in.\n"
    assert clean_markdown(strip_directives(marked)) == clean_markdown(strip_directives(plain))


# --- how many fit on stage ---

CROWD9 = SeriesModel.model_validate({**SERIES.model_dump(mode="json"), "cast": [
    {"id": f"p{i}", "name": n, "top": {"color": "#3a7bd5"}, "eyes": "dots"}
    for i, n in enumerate(["Ann", "Ben", "Cal", "Dot", "Eve", "Fay", "Gus", "Hal", "Ivy"], 1)]})


def test_too_many_on_stage_fails_with_the_line():
    big = SeriesModel.model_validate({**CROWD9.model_dump(mode="json"), "cast": [
        {"id": f"q{i}", "name": f"Q{i}", "top": {"color": "#3a7bd5"}, "eyes": "dots"} for i in range(13)]})
    md = "# X\n\n@cast " + ", ".join(f"q{i}" for i in range(13)) + "\nThey all talked.\n"
    with pytest.raises(StageError, match=r"line 3: @cast: 13 on stage, at most 12 fit \(6 in front, 6 behind\)"):
        shots.plan(md, phrases_for(md), big, 1)


def test_crowded_scene_puts_the_unfeatured_in_a_back_row():
    md = ("# X\n\n@cast p1, p2, p3, p4, p5, p6, p7, p8, p9\nAnn danced. Ben begged her to stop.\n"
          "@do p9: wave\nThe music played on and on.\n")
    ph = phrases_for(md)
    story = shots.plan(md, ph, CROWD9, 1)
    assert validate(story, ph, {c.id for c in CROWD9.cast}) == []
    first = story.shots[0]
    front = {a.cast_id for a in first.actors if a.start_pos[1] == 0}
    back = {a.cast_id: a for a in first.actors if a.start_pos[1] == shots.BACK_Z}
    # featured (named: Ann, Ben; @do: p9) in front, the other 6 fill the back row
    assert front == {"p1", "p2", "p9"} and set(back) == {"p3", "p4", "p5", "p6", "p7", "p8"}
    assert all(a.action == "idle" for a in back.values())
    bx = sorted(a.start_pos[0] for a in back.values())
    assert all(y - x >= shots.MIN_GAP - 1e-9 for x, y in zip(bx, bx[1:])) and all(-2 <= x <= 2 for x in bx)
    fx = [a.start_pos[0] for a in first.actors if a.cast_id in front]
    assert all(abs(x - f) > 0.1 for x in bx for f in fx)  # in the gaps, not hidden behind a front actor
    for sh in story.shots:  # the back row stands still for the whole scene
        assert {a.cast_id: a.start_pos for a in sh.actors if a.cast_id in back} == {c: a.start_pos for c, a in back.items()}


def test_full_back_row_sends_the_first_listed_forward():
    assert shots.split_rows(tuple(f"q{i}" for i in range(1, 11)), {"q5"}) == (
        ("q1", "q2", "q3", "q5"), ("q4", "q6", "q7", "q8", "q9", "q10"))
    assert shots.split_rows(("a", "b", "c"), set()) == (("a", "b", "c"), ())
    assert shots.split_rows(tuple("abcdefg"), set())[0] == ("a",)  # nobody featured: the first listed leads


def test_too_many_featured_in_one_scene_fails():
    md = "# X\n\n@cast p1, p2, p3, p4, p5, p6, p7\nAnn, Ben, Cal, Dot, Eve, Fay and Gus all danced.\n"
    with pytest.raises(StageError, match=r"7 of them are named or directed in one scene, at most 6 fit in front"):
        shots.plan(md, phrases_for(md), CROWD9, 1)


def test_six_or_fewer_stay_in_one_row():
    md = "# X\n\n@cast p1, p2, p3, p4, p5, p6\nAnn danced.\n"
    story = shots.plan(md, phrases_for(md), CROWD9, 1)
    assert all(a.start_pos[1] == 0 for sh in story.shots for a in sh.actors)


def test_six_fit_even_after_walks_left_odd_spots():
    md = ("# X\n\n@cast p1, p2, p3\nAnn walked right. Ben walked left. Cal ran.\n"
          "@cast p1, p2, p3, p4, p5, p6\nThey all talked.\n")
    story = shots.plan(md, phrases_for(md), CROWD9, 1)
    last = story.shots[-1]
    xs = sorted(a.start_pos[0] for a in last.actors)
    assert len(xs) == 6 and all(b - a >= shots.MIN_GAP - 1e-9 for a, b in zip(xs, xs[1:]))
    assert validate(story, phrases_for(md), {c.id for c in CROWD9.cast}) == []


def test_every_part_ends_on_the_follow_screen_after_a_short_tail():
    for series in (SERIES, FINAL):  # the last part of a complete series too
        story, ph = plan(SHORT, series=series)
        assert story.duration_frames == math.ceil(round((ph.words[-1].end + 0.3) * 30, 6))  # no sign-off pause or card
        assert story.end_card.text == "Follow for more" and story.end_card.start_frame == story.duration_frames
        assert validate(story, ph, {c.id for c in SERIES.cast}) == []


# --- chicken cast members ---

CHICKEN = SeriesModel.model_validate({**SERIES.model_dump(mode="json"), "cast": [
    *SERIES.model_dump(mode="json")["cast"],
    {"id": "mike", "name": "Mike", "top": {"color": "#f2f2f2"}, "eyes": "dots", "body": "chicken", "headless": True}]})


def test_chicken_takes_moves_but_has_no_hands():
    story, _ = plan("# C\n\n@cast bob, mike\n@do mike: stagger\nThe head dropped.\n@do bob: support mike\nBob held him.\n",
                    series=CHICKEN)
    acts = {(a.cast_id, a.action) for s in story.shots for a in s.actors}
    assert ("mike", "stagger") in acts and ("mike", "supported") in acts  # a chicken can be held up
    for do in ("mike: give medal bob", "bob: give medal mike", "mike: support bob"):
        with pytest.raises(StageError, match="mike is a bird"):
            plan(f"# C\n\n@cast bob, mike\n@do {do}\nHere.\n", series=CHICKEN)


def test_only_a_creature_is_headless():
    with pytest.raises(ValueError, match="human has no stump"):
        SeriesModel.model_validate({**CHICKEN.model_dump(mode="json"), "cast": [
            {"id": "bob", "name": "Bob", "top": {"color": "#3a7bd5"}, "eyes": "dots", "headless": True}]})


def test_every_cast_member_has_a_body_default_human_and_legacy_stickman_is_human():
    bob = {"id": "bob", "name": "Bob", "top": {"color": "#3a7bd5"}, "eyes": "dots"}
    cast = SeriesModel.model_validate({**CHICKEN.model_dump(mode="json"), "cast": [bob, {**bob, "id": "al", "body": "stickman"}]}).cast
    assert [c.body for c in cast] == ["human", "human"]


# --- @look: named cast looks ---

LOOKS = SeriesModel.model_validate({**SERIES.model_dump(mode="json"), "cast": [
    *SERIES.model_dump(mode="json")["cast"],
    {"id": "mike", "name": "Mike", "top": {"color": "#f2f2f2"}, "eyes": "dots", "body": "chicken",
     "looks": {"headless": {"headless": True}, "red": {"top": {"color": "#ff0000"}}}}]})


def test_look_holds_from_its_line_across_scenes_until_default():
    md = ("# L\n\n@cast bob, mike\nMike stood there.\n@look mike: headless\nThe head dropped.\n\n@set street\n"
          "Mike ran.\n@look mike: default\nIt was a dream.\n")
    story, _ = plan(md, series=LOOKS)
    looks = [next(a.look for a in s.actors if a.cast_id == "mike") for s in story.shots]
    runs = [k for i, k in enumerate(looks) if i == 0 or k != looks[i - 1]]
    assert runs == [None, "headless", None]  # own look, headless from its line, back at @look default
    street = [s for s in story.shots if s.set == "street"]
    assert any(next(a.look for a in s.actors if a.cast_id == "mike") == "headless" for s in street)  # kept over @set


def test_look_errors_name_the_line():
    for line, msg in [("@look mike: wings", "mike has no look 'wings'"), ("@look zed: red", "unknown cast id 'zed'"),
                      ("@look mike", "expected")]:
        with pytest.raises(StageError, match=msg):
            plan(f"# L\n\n@cast bob, mike\n{line}\nHi.\n", series=LOOKS)


def test_with_look_overrides_only_what_it_sets():
    mike = next(c for c in LOOKS.cast if c.id == "mike")
    assert mike.with_look("headless").headless and not mike.headless
    assert mike.with_look("red").top.color == "#ff0000" and mike.with_look("red").headless is False
    assert mike.with_look("default") is mike
    with pytest.raises(ValueError, match="default is reserved"):
        SeriesModel.model_validate({**LOOKS.model_dump(mode="json"), "cast": [
            {**LOOKS.model_dump(mode="json")["cast"][-1], "looks": {"default": {}}}]})



# --- @hold: a prop in hand for the rest of the part ---

def test_hold_keeps_a_prop_over_the_look_until_changed():
    md = ("# H\n\n@cast bob, mike\nBob stood.\n@hold bob: medal\nBob won.\n\n@set street\nBob ran.\n"
          "@hold bob: apple left\nBob ate.\n@fx lightning apple\n@hold bob: none right\nBob tossed it.\n"
          "@hold bob: none\nBob was empty handed.\n")
    story, _ = plan(md, series=LOOKS)
    held = [next(a.props for a in s.actors if a.cast_id == "bob") for s in story.shots]
    kinds = [None if h is None else sorted((x.hand, x.kind) for x in h) for h in held]
    runs = [k for i, k in enumerate(kinds) if i == 0 or k != kinds[i - 1]]
    assert runs == [None, [("right", "medal")], [("left", "apple"), ("right", "medal")], [("left", "apple")], []]
    assert story.lightning[0].target == "bob"  # whoever holds the apple on the struck line


def test_hold_errors_name_the_line():
    for line, msg in [("@hold mike: medal", "mike is a bird"), ("@hold zed: medal", "unknown cast id 'zed'"),
                      ("@hold bob: trident", "unknown prop 'trident'"), ("@hold bob: medal up", "expected"),
                      ("@hold bob", "expected")]:
        with pytest.raises(StageError, match=f"line 4: @hold: {msg}"):
            plan(f"# L\n\n@cast bob, mike\n{line}\nHi.\n", series=LOOKS)


# --- faces: @do emotions and moods that cover the whole line ---

def faces(md, who):
    story, _ = plan(md)
    return [next(a.expression for a in s.actors if a.cast_id == who) for s in story.shots]


def test_do_emotion_sets_the_face_when_the_line_names_no_mood():
    # no mood word: a "neutral" face would show the cast's default_expression (a cheeky smirk while stomping)
    assert set(faces("# T\n\n@cast bob, amy\n@do bob: angry\nBob stomped around the room.\n", "bob")) == {"angry"}
    assert set(faces("# T\n\n@cast bob, amy\n@do amy: gasp\nBob opened the door.\n", "amy")) == {"surprised"}


def test_mood_word_beats_the_action_face():
    assert set(faces("# T\n\n@cast bob, amy\n@do bob: react\nBob laughed and patted the dog on its head.\n", "bob")) == {"happy"}


def test_mood_covers_every_shot_of_its_line():
    md = "# T\n\n@cast bob, amy\nBob pointed at the big dark sky and then shouted at the clouds above.\n"
    fs = faces(md, "bob")
    assert len(fs) > 1 and set(fs) == {"angry"}  # "shouted" in the second phrase sets the first one too


def bob_faces(md):
    """per shot: (opening face, [(frame, face) changes]) of bob, and the phrases"""
    story, ph = plan(md)
    out = []
    for s in story.shots:
        a = next(a for a in s.actors if a.cast_id == "bob")
        out.append((a.expression, [(f.frame, f.expression) for f in a.faces], s.start_frame, s.end_frame))
    return out, ph


def test_face_switches_on_the_mood_word():
    rows, ph = bob_faces("# T\n\n@cast bob, amy\nBob grinned, then screamed.\n")
    scream = round(next(w.start for w in ph.words if w.text.startswith("screamed")) * 30)
    opening = [r[0] for r in rows]
    changes = [c for r in rows for c in r[1]]
    assert opening[0] == "happy"
    # angry from "screamed" on: a change inside the shot that holds it, or the next shot opens angry
    assert (scream, "angry") in changes or any(o == "angry" and s0 == scream for o, _c, s0, _e in rows)
    for o, cs, s0, s1 in rows:
        assert all(s0 < f < s1 for f, _ in cs)


def test_face_directive_wins_for_its_line_only():
    story, _ = plan("# T\n\n@cast bob, amy\n@face bob: sad\nBob laughed at the joke.\nBob laughed again.\n")
    lines = [next(a for a in s.actors if a.cast_id == "bob") for s in story.shots]
    assert lines[0].expression == "sad" and not lines[0].faces
    assert lines[-1].expression == "happy"


def test_face_directive_errors():
    with pytest.raises(StageError, match=r"line 4: @face: expected"):
        plan("# T\n\n@cast bob, amy\n@face bob: grumpy\nBob sat.\n")
    with pytest.raises(StageError, match=r"line 4: @face: unknown cast id 'zed'"):
        plan("# T\n\n@cast bob, amy\n@face zed: sad\nBob sat.\n")
