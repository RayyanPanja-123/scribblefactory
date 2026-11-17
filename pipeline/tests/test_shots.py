import json

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


def _subject(md):
    story, _ = plan("# K\n\n@cast bob, amy\n" + md + "\n", word_s=0.15)  # short shot (~1.55 s): a run fits on stage
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
    a, s = _subject("Amy ran right.")  # 4.25 units fits neither way: flipped, shortened to the left edge
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
    ("Bob waved cheerfully.", "point", "happy"),
    ("Bob kept waving.", "point", "neutral"),
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
