import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.scribble.cli import main
from pipeline.scribble.io import load_part, save_part
from pipeline.scribble.schemas import PartModel, PhrasesModel, SeriesModel, StoryModel
from pipeline.scribble.validate import validate

FIX = Path(__file__).parent / "fixtures" / "story"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def rules(mutate=None, story=None):
    """Rules that fail after mutate(story_dict) is applied to the valid fixture."""
    d = load("story.json")
    if mutate:
        mutate(d)
    s = story or StoryModel.model_validate(d)
    cast = {c.id for c in SeriesModel.model_validate(load("series.json")).cast}
    return {e.rule for e in validate(s, PhrasesModel.model_validate(load("phrases.json")), cast)}


def shot(d, i):
    return d["shots"][i]


def actor(d, i, j=0):
    return d["shots"][i]["actors"][j]


def test_valid_fixture_passes():
    assert rules() == set()


def _set(path_fn, key, value):
    return lambda d: path_fn(d).__setitem__(key, value)


def _move_s02_start(d):
    shot(d, 0)["end_frame"] = 61
    shot(d, 1)["start_frame"] = 62


def _long_s01(d):
    shot(d, 0)["end_frame"] = 100
    shot(d, 1)["start_frame"] = 100


def _speed_zero():
    s = StoryModel.model_validate(load("story.json"))
    s.shots[0].camera.speed = 0  # the schema forbids < 0.05; check the rule still fires on a bypassed model
    return s


def _drop_cue(kind):
    return lambda d: d.__setitem__("cues", [c for c in d["cues"] if c["kind"] != kind])


CASES = {
    "contiguous gap": ("contiguous", _move_s02_start),
    "contiguous first not 0": ("contiguous", lambda d: shot(d, 0).__setitem__("start_frame", 1)),
    "contiguous last short": ("contiguous", lambda d: shot(d, 2).__setitem__("end_frame", 179)),
    "shot_length": ("shot_length", _long_s01),
    "repeated_angle": ("repeated_angle", lambda d: shot(d, 1)["camera"].__setitem__("angle", "wide")),
    "cast_id": ("cast_id", _set(lambda d: actor(d, 1), "cast_id", "ghost")),
    "set": ("set", _set(lambda d: shot(d, 1), "set", "  ")),
    "end_pos walk null": ("end_pos", _set(lambda d: actor(d, 0), "end_pos", None)),
    "end_pos walk same": ("end_pos", _set(lambda d: actor(d, 0), "end_pos", [0, 0])),
    "end_pos talk set": ("end_pos", _set(lambda d: actor(d, 1), "end_pos", [3, 0])),
    "facing": ("facing", _set(lambda d: actor(d, 0), "facing", "left")),
    "gliding walk fast": ("gliding", _set(lambda d: actor(d, 0), "end_pos", [10, 0])),
    "gliding run slow": ("gliding", _set(lambda d: actor(d, 0), "action", "run")),
    "twist move": ("twist", lambda d: shot(d, 2)["camera"].__setitem__("move", "pull_out")),
    "twist roll": ("twist", lambda d: shot(d, 2)["camera"].__setitem__("roll_deg", 0)),
    "twist no low_hit": ("twist", _drop_cue("low_hit")),
    "twist no music_stop": ("twist", _drop_cue("music_stop")),
    "twist cue too far": ("twist", lambda d: d["cues"][1].__setitem__("frame", 124)),
    "cue_frame": ("cue_frame", lambda d: d["cues"].append({"frame": 181, "kind": "pop"})),
    "phrase_range out of bounds": ("phrase_range", _set(lambda d: shot(d, 2), "phrase_range", [2, 3])),
    "phrase_range first > last": ("phrase_range", _set(lambda d: shot(d, 1), "phrase_range", [2, 1])),
    "phrase_range backwards": ("phrase_range", _set(lambda d: shot(d, 2), "phrase_range", [0, 2])),
}


@pytest.mark.parametrize("rule,mutate", CASES.values(), ids=CASES.keys())
def test_rule_fails(rule, mutate):
    assert rules(mutate) == {rule}


def test_camera_speed_rule():
    assert rules(story=_speed_zero()) == {"camera_speed"}


def test_duration_rule():
    def m(d):
        d["duration_frames"] = 181
        shot(d, 2)["end_frame"] = 181
    assert rules(m) == {"duration"}


def test_pure_z_walk_may_face_camera():
    def m(d):
        actor(d, 0)["end_pos"] = [0, 2.4]
        actor(d, 0)["facing"] = "camera"
    assert rules(m) == set()


@pytest.mark.parametrize("mutate", [
    lambda d: d.__setitem__("extra", 1),
    lambda d: shot(d, 0).__setitem__("extra", 1),
    lambda d: shot(d, 0)["camera"].__setitem__("extra", 1),
    lambda d: actor(d, 0).__setitem__("extra", 1),
    lambda d: shot(d, 0)["camera"].__setitem__("move", "static"),
    lambda d: shot(d, 0)["camera"].__setitem__("speed", 0),
    lambda d: d.__setitem__("fps", 24),
], ids=["root", "shot", "camera", "actor", "static", "speed0", "fps"])
def test_schema_rejects(mutate):
    d = load("story.json")
    mutate(d)
    with pytest.raises(ValidationError):
        StoryModel.model_validate(d)


# --- stage ---

@pytest.fixture
def part(tmp_path):
    """tmp_path is the library: <tmp>/office-nap/{series.json, part-01/}."""
    sd = tmp_path / "office-nap"
    d = sd / "part-01"
    d.mkdir(parents=True)
    shutil.copy(FIX / "series.json", sd / "series.json")
    save_part(d / "part.json", PartModel(id="part-01", number=1, title="T"))
    for name in ("story.json", "phrases.json"):
        shutil.copy(FIX / name, d / name)
    return d


def run_validate(part):
    return main(["run", "office-nap", "part-01", "--stage", "validate", "--library", str(part.parent.parent)])


def test_stage_passes(part, capsys):
    assert run_validate(part) == 0
    assert load_part(part / "part.json").stages.validate_.status == "done"
    assert "ok: 3 shots, 180 frames" in capsys.readouterr().out


def test_stage_fails_and_prints_every_error(part, capsys):
    d = json.loads((part / "story.json").read_text())
    d["shots"][1]["camera"]["angle"] = "wide"
    d["shots"][0]["actors"][0]["facing"] = "left"
    (part / "story.json").write_text(json.dumps(d))
    assert run_validate(part) == 1
    out = capsys.readouterr().out
    assert "repeated_angle" in out and "facing" in out
    st = load_part(part / "part.json").stages.validate_
    assert st.status == "failed" and st.error == "2 validation error(s)"


def test_stage_reruns_when_series_cast_changes(part, capsys):
    assert run_validate(part) == 0
    sj = part.parent / "series.json"
    d = json.loads(sj.read_text())
    d["cast"] = [c for c in d["cast"] if c["id"] != "amy"]
    sj.write_text(json.dumps(d))
    assert run_validate(part) == 1
    assert "cast_id" in capsys.readouterr().out


def test_stage_reports_invalid_story(part, capsys):
    (part / "story.json").write_text('{"schema_version": 1}')
    assert run_validate(part) == 1
    assert "story.json is invalid" in load_part(part / "part.json").stages.validate_.error
