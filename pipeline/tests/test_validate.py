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


def rules(mutate=None, story=None, phrases_mutate=None):
    """Rules that fail after mutate(story_dict) / phrases_mutate(phrases_dict) on the valid fixture."""
    d, p = load("story.json"), load("phrases.json")
    if mutate:
        mutate(d)
    if phrases_mutate:
        phrases_mutate(p)
    s = story or StoryModel.model_validate(d)
    cast = {c.id for c in SeriesModel.model_validate(load("series.json")).cast}
    return {e.rule for e in validate(s, PhrasesModel.model_validate(p), cast)}


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


def _s01_on_phrase1(d):
    shot(d, 0)["phrase_range"] = [1, 1]
    shot(d, 1)["phrase_range"] = [2, 2]  # keep s01 a group of one (s02 + s03 form the phrase 2 group)


def _split_group(d, rng, end=60):
    """Replace s01 with two talk pieces 0-30 and 30-end on phrase rng, followed by s02 (end-120) on phrase 2."""
    s1, s2, _ = d["shots"]
    talk = [dict(s2["actors"][0], start_pos=[0, 0])]
    a = dict(s1, id="s01", start_frame=0, end_frame=30, phrase_range=rng, actors=talk)
    b = dict(s1, id="s04", start_frame=30, end_frame=end, phrase_range=rng, actors=talk,
             camera=dict(s1["camera"], angle="high"))
    s2.update(start_frame=end, phrase_range=[2, 2])
    d["shots"][:1] = [a, b]


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
    "duplicate_shot_id": ("duplicate_shot_id", _set(lambda d: shot(d, 2), "id", "s01")),
    # s01 alone (frames 0-60) pointed at phrase 1 (2.1-3.5 s = frames 63-105, 60-108 with tolerance)
    "phrase_timing": ("phrase_timing", _s01_on_phrase1),
    "phrase_timing split group": ("phrase_timing", lambda d: _split_group(d, [1, 1])),
}


def _phrase1_start(t):
    return lambda p: p["phrases"][1].__setitem__("start", t)


def test_phrase_timing_tolerance():
    # phrase 1 starts at 2.05 s = frame 61.5, -3 = 58.5 < 60: overlaps s01
    assert rules(_s01_on_phrase1, phrases_mutate=_phrase1_start(2.05)) == set()
    # starts at 2.1 s = frame 63, -3 = 60: touches s01's end only, no overlap
    assert rules(_s01_on_phrase1, phrases_mutate=_phrase1_start(2.1)) == {"phrase_timing"}


def test_split_piece_in_pause_passes_as_group():
    # s01 + s02 both on phrase 0: s02 (60-120) sits wholly after phrase 0 (0-51), the group 0-120 overlaps it
    assert rules(_set(lambda d: shot(d, 1), "phrase_range", [0, 0])) == set()
    # same with an explicit two-piece group on phrase 1 whose first piece is before it and second inside it
    assert rules(lambda d: _split_group(d, [1, 1], end=90)) == set()


@pytest.mark.parametrize("rule,mutate", CASES.values(), ids=CASES.keys())
def test_rule_fails(rule, mutate):
    assert rules(mutate) == {rule}


def test_camera_speed_rule():
    assert rules(story=_speed_zero()) == {"camera_speed"}


def test_duration_rule():
    def m(d):
        d["duration_frames"] = 181
        shot(d, 2)["end_frame"] = 181
        d["end_card"]["start_frame"] = 181
    assert rules(m) == {"duration"}  # the story must end 0.3 s after the last word


def test_end_card_starts_where_the_story_ends():
    def m(d):
        d["end_card"]["start_frame"] = 170  # the old style: a card over the last second
    assert rules(m) == {"end_card"}


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


# --- travel shots ---

def _travel(speed=1.2, set_="dirt_road", dx=0.0, facing="right", action="walk"):
    """s01 (2 s) as a travel shot: bob walks in place (or dx units) while the world scrolls at speed."""
    def m(d):
        s = shot(d, 0)
        s["set"], s["travel"] = set_, {"speed": speed}
        s["actors"] = [{"cast_id": "bob", "action": action, "start_pos": [0, 0], "end_pos": [dx, 0],
                        "facing": facing, "expression": "neutral"},
                       {"cast_id": "amy", "action": action, "start_pos": [1, 0.2], "end_pos": [1 + dx, 0.2],
                        "facing": facing, "expression": "neutral"}]
    return m


def test_travel_shot_passes():
    assert rules(_travel()) == set()                     # walk in place at 1.2 units/s
    assert rules(_travel(2.5, action="run", facing="left", set_="stadium")) == set()
    assert rules(_travel(1.0, dx=1.0)) == set()          # 1.0 scroll + 0.5 own move = 1.5: still a walk


@pytest.mark.parametrize("set_", ["room", "office", "moon"])
def test_travel_only_on_outdoor_sets(set_):
    assert rules(_travel(set_=set_)) == {"travel_set"}


def test_travel_actors_must_all_walk_or_run():
    def m(d):
        _travel()(d)
        actor(d, 0, 1).update(action="idle", end_pos=None)
    assert rules(m) == {"travel_actors"}


@pytest.mark.parametrize("facings", [("right", "left"), ("camera", "camera")])
def test_travel_actors_face_one_left_right_way(facings):
    def m(d):
        _travel()(d)
        for j, f in enumerate(facings):
            actor(d, 0, j)["facing"] = f
    assert rules(m) == {"travel_facing"}


@pytest.mark.parametrize("speed,dx,action", [
    (0.4, 0.0, "walk"),   # 0.4 < 0.6: legs too slow for the scroll
    (1.2, 2.0, "walk"),   # 1.2 + 1.0 = 2.2 > 1.8
    (1.2, 0.0, "run"),    # 1.2 < 1.8: a run this slow glides
    (3.8, 1.0, "run"),    # 3.8 + 0.5 = 4.3 > 4.0
])
def test_travel_effective_stride_speed(speed, dx, action):
    assert rules(_travel(speed, dx=dx, action=action)) == {"gliding"}


def test_schema_travel_speed_positive():
    d = load("story.json")
    shot(d, 0)["travel"] = {"speed": 0}
    with pytest.raises(ValidationError):
        StoryModel.model_validate(d)



# --- dogs ---

def _dog(action="run", start=(0.0, 0.3), end=(6.0, 0.3), facing="right", travel=None):
    """s01 (2 s) gets one dog; travel=speed makes s01 a travel shot (bob and amy run right in place)."""
    def m(d):
        if travel:
            _travel(travel, action="run")(d)
        shot(d, 0)["animals"] = [{"id": "dog1", "kind": "dog", "action": action, "start_pos": list(start),
                                  "end_pos": list(end) if end else None, "facing": facing, "variant": "tan"}]
    return m


def test_dogs_pass():
    assert rules(_dog()) == set()                                       # 6 units in 2 s = 3.0 u/s
    assert rules(_dog("bark", end=None, facing="left")) == set()
    assert rules(_dog(travel=2.5, start=(-2, 0.3), end=(-1.5, 0.3))) == set()  # 2.5 scroll + 0.25 = 2.75
    def cue(d):
        _dog("idle", end=None)(d)
        d["cues"].append({"frame": 10, "kind": "bark"})
    assert rules(cue) == set()


@pytest.mark.parametrize("kw", [
    dict(end=(3.0, 0.3)),                         # 1.5 u/s < 2.0
    dict(end=(10.4, 0.3)),                        # 5.2 u/s > 5.0
    dict(travel=1.2, start=(-2, 0), end=(-2, 0)),  # walk-speed scroll alone: 1.2 < 2.0
    dict(travel=2.5, start=(-8, 0), end=(-2, 0)),  # 2.5 + 3.0 = 5.5 > 5.0
])
def test_dog_run_speed(kw):
    assert rules(_dog(**kw)) == {"gliding"}


def test_dog_constants():
    from pipeline.scribble.validate import DOG_RUN_SPEED
    assert DOG_RUN_SPEED == (2.0, 5.0)


@pytest.mark.parametrize("kw,rule", [
    (dict(facing="left"), "facing"),                         # runs right, faces left
    (dict(end=(0.0, 0.3)), "end_pos"),                       # a run must move (outside travel)
    (dict(action="idle"), "end_pos"),                        # idle with an end_pos
    (dict(action="bark"), "end_pos"),
])
def test_dog_motion_rules(kw, rule):
    assert rules(_dog(**kw)) == {rule}


@pytest.mark.parametrize("kw", [
    dict(action="idle", end=None),                                       # must run
    dict(action="bark", end=None),
    dict(facing="left", start=(2, 0), end=(1.5, 0)),                     # runs against the travel way
])
def test_travel_dogs_run_the_travel_way(kw):
    assert "travel_animals" in rules(_dog(travel=2.5, **kw))


def test_dog_ids_unique_per_shot():
    def m(d):
        _dog()(d)
        shot(d, 0)["animals"].append(dict(shot(d, 0)["animals"][0]))
    assert rules(m) == {"animal_id"}


@pytest.mark.parametrize("mutate", [
    lambda a: a.update(kind="cat"), lambda a: a.update(variant="purple"), lambda a: a.update(facing="camera"),
    lambda a: a.update(action="sit"),
])
def test_schema_rejects_bad_animal(mutate):
    d = load("story.json")
    _dog()(d)
    mutate(shot(d, 0)["animals"][0])
    with pytest.raises(ValidationError):
        StoryModel.model_validate(d)


def test_animals_default_empty():
    assert StoryModel.model_validate(load("story.json")).shots[0].animals == []


# --- cars ---

def _car(action="drive", start=(0.0, -0.6), end=(6.0, -0.6), facing="right", riders=(), rider_action="ride",
         travel=None, extra_actor=None):
    """s01 (2 s) gets car1; riders become actor entries with rider_action. travel=speed: s01 is a travel shot."""
    def m(d):
        s = shot(d, 0)
        if travel:
            s["set"], s["travel"] = "dirt_road", {"speed": travel}
        s["actors"] = [{"cast_id": r, "action": rider_action, "start_pos": list(start), "facing": facing,
                        "expression": "neutral"} for r in riders] or s["actors"]
        if not riders and travel:
            s["actors"] = []
        if extra_actor:
            s["actors"].append(extra_actor)
        s["vehicles"] = [{"id": "car1", "kind": "car", "action": action, "start_pos": list(start),
                          "end_pos": list(end) if end else None, "facing": facing, "riders": list(riders),
                          "variant": "red"}]
    return m


def test_cars_pass():
    assert rules(_car()) == set()                                          # 3 u/s
    assert rules(_car("arrive", start=(6, 0), end=(1, 0), facing="left")) == set()  # peak 2 x 2.5 = 5
    assert rules(_car("leave", end=(4, -0.6))) == set()                    # peak 4
    assert rules(_car("idle", end=None, riders=("bob",))) == set()
    for act in ("ride", "wave", "talk"):
        assert rules(_car(riders=("bob", "amy"), rider_action=act)) == set()
    assert rules(_car(travel=4.0, end=(0, -0.6), riders=("bob",), rider_action="wave")) == set()


def test_car_constants():
    from pipeline.scribble.validate import CAR_SPEED
    assert CAR_SPEED == (1.5, 8.0)


@pytest.mark.parametrize("kw", [
    dict(end=(2.0, -0.6)),                         # drive 1.0 u/s < 1.5
    dict(end=(17.0, -0.6)),                        # 8.5 > 8
    dict(action="arrive", end=(8.5, -0.6)),        # peak 2 x 4.25 = 8.5 > 8
    dict(action="leave", end=(1.0, -0.6)),         # peak 2 x 0.5 = 1.0 < 1.5
    dict(travel=9.0, end=(0, -0.6), riders=("bob",)),  # travel speed is the car's speed
])
def test_car_speed(kw):
    assert rules(_car(**kw)) == {"vehicle_speed"}


@pytest.mark.parametrize("kw,rule", [
    (dict(action="idle"), "vehicle_motion"),                   # idle must not move
    (dict(action="arrive", end=(0.0, -0.6)), "vehicle_motion"),  # arrive must move
    (dict(facing="left"), "facing"),
])
def test_car_motion_rules(kw, rule):
    assert rules(_car(**kw)) == {rule}


def test_rider_rules():
    assert rules(_car(riders=("zed",))) >= {"cast_id"}
    assert rules(_car(riders=("bob",), rider_action="walk")) >= {"riders"}         # riders sit
    standing = {"cast_id": "bob", "action": "idle", "start_pos": [1, 0], "facing": "camera", "expression": "neutral"}
    assert rules(_car(riders=("bob",), extra_actor=standing)) == {"riders"}         # also standing
    def no_entry(d):
        _car(riders=("bob",))(d)
        shot(d, 0)["actors"] = []
    assert rules(no_entry) == {"riders"}
    def unlisted(d):
        _car()(d)
        shot(d, 0)["actors"][0]["action"] = "ride"                                  # rides, no car lists bob
        shot(d, 0)["actors"][0]["end_pos"] = None
    assert rules(unlisted) == {"riders"}
    def two_cars(d):
        _car(riders=("bob",))(d)
        shot(d, 0)["vehicles"].append(dict(shot(d, 0)["vehicles"][0], id="car2"))
    assert rules(two_cars) == {"riders"}


def test_car_travel_rule():
    walker = {"cast_id": "amy", "action": "walk", "start_pos": [2, 0], "end_pos": [2, 0], "facing": "right",
              "expression": "neutral"}
    assert "travel_actors" in rules(_car(travel=4.0, end=(0, -0.6), riders=("bob",), extra_actor=walker))
    assert rules(_car(travel=4.0, end=(1, -0.6), riders=("bob",))) == {"travel_vehicle"}   # car keeps its x
    assert rules(_car("idle", travel=4.0, end=None, riders=("bob",))) == {"travel_vehicle"}
    # with a car, the dogs chase the car's way (riders face anything)
    def dogs(d):
        _car(travel=4.0, end=(0, -0.6), riders=("bob",), facing="left")(d)
        shot(d, 0)["animals"] = [{"id": "dog1", "kind": "dog", "action": "run", "start_pos": [3, 0],
                                  "end_pos": [2.5, 0], "facing": "left", "variant": "tan"}]
    assert rules(dogs) == set()
