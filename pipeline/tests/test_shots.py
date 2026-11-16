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
    story, _ = plan("# K\n\n@cast bob, amy\n" + md + "\n")
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
    a, s = _subject("Amy walked in.")  # amy at x=1.5, no direction word: toward the centre
    secs = (s.end_frame - s.start_frame) / 30
    assert a.start_pos == (1.5, 0.0) and a.facing == "left"
    assert a.end_pos[0] == pytest.approx(1.5 - 1.2 * secs, abs=1e-3)
    a, s = _subject("Amy ran right.")
    assert a.facing == "right" and a.end_pos[0] == pytest.approx(1.5 + 2.5 * (s.end_frame - s.start_frame) / 30, abs=1e-3)
    a, _ = _subject("Bob left.")  # "left": walk keyword and direction
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
    monkeypatch.setattr(shots, "MOVE_SPEED", {"walk": 5.0, "run": 2.5})  # walk far too fast: gliding
    assert run(part) == "failed"
    assert not (part / "story.json").exists()
    assert "gliding" in capsys.readouterr().out
    assert "fails validation" in load_part(part / "part.json").stages.shots.error
