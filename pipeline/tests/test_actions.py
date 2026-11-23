"""Step 5c-6: stagger, lie, collapse, eat, give / receive, carry / carried, support / supported, the broken car, and the
@do directive: planner output, validator rules, parse errors with story.md line numbers, prep leaves the script alone."""

import json
import subprocess
from pathlib import Path

import pytest

from pipeline.scribble.io import save_part, unknown_actions
from pipeline.scribble.schemas import (ACTIONS, ActionLibrary, CustomAction, PartModel, SeriesModel, StoryModel,
                                       actions_with)
from pipeline.scribble.stages import prep, shots
from pipeline.scribble.stages.prep import clean_markdown, strip_directives
from pipeline.scribble.stages.runner import StageError, run_stage
from pipeline.scribble.validate import STAGGER_SPEED, validate

from .test_shots import phrases_for, plan
from .test_validate import actor, rules, shot

SERIES = SeriesModel.model_validate({
    "slug": "track-day", "title": "Track Day", "created_at": "2026-11-16T10:00:00Z",
    "voice": {"voice_name": "Brian"}, "style": {"preset": "default"},
    "cast": [{"id": c, "name": c.title(), "outfit_color": "#3a7bd5", "eyes": "dots"}
             for c in ("fred", "amy", "tom", "sue")],
})
IDS = {c.id for c in SERIES.cast}
ROOT = Path(__file__).resolve().parents[2]


def planned(md, word_s=0.4):
    story, ph = plan(md, word_s, SERIES)
    assert validate(story, ph, IDS) == [], validate(story, ph, IDS)
    return story


def who(shot_, cid):
    return next(a for a in shot_.actors if a.cast_id == cid)


# --- @do in the planner ---

def test_do_applies_to_every_shot_of_the_next_line_only():
    md = ("# T\n\n@set office\n@cast fred, amy\n@do fred: collapse\n"
          "Fred talked and talked about the long long race he once ran. Then he stopped.\nAmy walked in.\n")
    story = planned(md, word_s=0.5)
    line_shots = [s for s in story.shots if s.phrase_range[0] <= 1]  # the @do line is phrases 0 and 1
    assert len(line_shots) >= 2
    assert [who(s, "fred").action for s in line_shots] == ["collapse"] + ["lie"] * (len(line_shots) - 1)  # falls once
    assert all(who(s, "fred").end_pos is None for s in line_shots)
    assert who(story.shots[-1], "amy").action == "walk"            # next line: the planner's choice again
    assert who(story.shots[-1], "fred").action == "idle"


def test_do_keeps_unnamed_cast_on_the_planners_choice():
    plain = planned("# T\n\n@cast fred, amy\nAmy walked left.\n")
    done = planned("# T\n\n@cast fred, amy\n@do fred: lie\nAmy walked left.\n")
    assert who(done.shots[0], "fred").action == "lie"
    assert who(done.shots[0], "amy") == who(plain.shots[0], "amy")


def test_do_eat_give_and_props():
    story = planned("# T\n\n@cast fred, amy, tom\n@do fred: eat apple, amy: give medal tom\nThey met.\n")
    f, a, t = (who(story.shots[0], c) for c in ("fred", "amy", "tom"))
    assert (f.action, f.prop) == ("eat", "apple")
    assert (a.action, a.prop, a.target) == ("give", "medal", "tom")
    assert (t.action, t.target) == ("receive", "amy")
    assert a.facing == ("right" if t.start_pos[0] > a.start_pos[0] else "left") and t.facing != a.facing


def test_do_give_happens_once_and_frames_both():
    md = ("# T\n\n@set office\n@cast fred, amy, tom\n@do amy: give medal tom\n"
          "Amy talked and talked about the long long race he once ran, then handed it over to Tom at last.\n")
    story = planned(md, word_s=0.5)
    gives = [s for s in story.shots if who(s, "amy").action == "give"]
    assert len(story.shots) >= 2 and len(gives) == 1 and gives[0] is story.shots[0]  # once, in the line's first shot
    assert gives[0].camera.angle in ("wide", "medium")                              # both people in frame


def test_do_carry_group_walks_together_and_carried_has_no_own_move():
    story = planned("# T\n\n@set office\n@cast fred, amy, tom\n@do amy, tom: carry fred\nThey carried him home.\n")
    s = story.shots[0]
    f, a, t = (who(s, c) for c in ("fred", "amy", "tom"))
    assert f.action == "carried" and f.end_pos is None
    assert (a.action, t.action, a.target, t.target) == ("carry", "carry", "fred", "fred")
    assert a.end_pos and t.end_pos and a.facing == t.facing in ("left", "right")
    assert round(a.end_pos[0] - a.start_pos[0], 3) == round(t.end_pos[0] - t.start_pos[0], 3)  # side by side
    assert a.start_pos[0] < f.start_pos[0] < t.start_pos[0]                                  # held between them
    # next line: the carried actor starts where the group ended
    story2 = planned("# T\n\n@set office\n@cast fred, amy, tom\n@do amy, tom: carry fred\nThey carried him.\nFred sat.\n")
    moved = who(story2.shots[0], "amy").end_pos[0] - who(story2.shots[0], "amy").start_pos[0]
    assert who(story2.shots[-1], "fred").start_pos[0] == pytest.approx(who(story2.shots[0], "fred").start_pos[0] + moved)


def test_do_support_with_one_supporter():
    s = planned("# T\n\n@cast fred, amy\n@do amy: support fred\nAmy helped Fred along.\n").shots[0]
    assert (who(s, "fred").action, who(s, "amy").action, who(s, "amy").target) == ("supported", "support", "fred")


def test_do_stagger_moves_without_gliding():
    s = planned("# T\n\n@cast fred\n@do fred: stagger\nFred kept going somehow.\n").shots[0]
    f = who(s, "fred")
    assert f.action == "stagger" and f.end_pos
    speed = abs(f.end_pos[0] - f.start_pos[0]) / ((s.end_frame - s.start_frame) / 30)
    assert STAGGER_SPEED[0] <= speed <= STAGGER_SPEED[1]


def test_do_car_broken_stops_the_arrived_car():
    md = "# T\n\n@set dirt_road\n@cast fred\n@car arrive\nA car came.\n@do car: broken\nIt broke down.\nFred sighed.\n"
    story = planned(md)
    broken = [v for s in story.shots for v in s.vehicles if v.action == "broken"]
    assert broken and broken[0].end_pos is None
    assert story.shots[-1].vehicles[0].start_pos == broken[0].start_pos  # still parked where it broke


def test_do_car_broken_during_ride_stalls_with_riders_seated():
    md = "# T\n\n@set dirt_road\n@cast fred\n@car ride\nFred rode along.\n@do car: broken\nIt broke down.\n"
    story = planned(md)
    drive, stall = story.shots[0].vehicles[0], story.shots[-1].vehicles[0]
    assert drive.action == "drive" and stall.action == "broken" and stall.riders == ["fred"]
    assert story.shots[-1].travel is None and stall.facing == drive.facing
    with pytest.raises(StageError, match="story.md line 7: @do: not while @car ride"):
        planned(md.replace("@do car: broken", "@do fred: wave"))


def test_do_suppresses_travel_outdoors():
    story = planned("# T\n\n@set dirt_road\n@cast fred, amy\n@do fred: lie\nAmy ran on.\n")
    assert story.shots[0].travel is None and who(story.shots[0], "fred").action == "lie"


def test_keyword_guesses_for_new_actions():
    for line, act in [("Fred staggered on.", "stagger"), ("Fred lay down.", "lie"), ("Fred fainted.", "collapse"),
                      ("Fred ate lunch.", "eat")]:
        s = planned(f"# T\n\n@cast fred\n{line}\n").shots[0]
        assert who(s, "fred").action == act, line


# --- @do errors name the story.md line ---

@pytest.mark.parametrize("line,msg", [
    ("@do fred: dance", "unknown action 'dance'"),
    ("@do zed: lie", "unknown cast id 'zed'"),
    ("@do amy: give medal zed", "unknown target 'zed'"),
    ("@do fred: eat shoe", "unknown prop 'shoe'"),
    ("@do fred: carry amy", "carry needs 2 cast"),
    ("@do fred, amy, tom: support sue", "support needs 1-2 cast"),
    ("@do fred collapse", 'expected "@do <cast>: <action>'),
    ("@do car: lie", 'the car only takes "car: broken"'),
    ("@do fred: lie, fred: eat", "fred is given two actions"),
])
def test_do_parse_errors_have_line_numbers(line, msg):
    md = f"# T\n\n@cast fred, amy\n{line}\nFred sat.\n"
    with pytest.raises(StageError, match=f"story.md line 4: @do: .*{msg[:20]}".replace("(", r"\(").replace(")", r"\)")):
        plan(md, series=SERIES)


@pytest.mark.parametrize("line,msg", [
    ("@do sue: lie", "sue is not on stage"),
    ("@do car: broken", "car: broken, but there is no car on stage"),
    ("@do fred: give medal amy, amy: wave", "amy is the target of give and has its own action"),
])
def test_do_stage_errors_have_line_numbers(line, msg):
    with pytest.raises(StageError, match=f"story.md line 4: @do: {msg}"):
        plan(f"# T\n\n@cast fred, amy\n{line}\nFred sat.\n", series=SERIES)


def test_prep_fails_on_a_bad_do_and_keeps_the_script_identical(tmp_path):
    d = tmp_path / "part-01"
    d.mkdir()
    save_part(d / "part.json", PartModel(id="part-01", number=1, title="T"))
    plain = "# T\n\n@cast fred\nFred ran.\n\nFred sat.\n"
    (d / "story.md").write_text(plain, encoding="utf-8")
    assert run_stage(d, "prep", prep.run, inputs=prep.INPUTS, outputs=prep.OUTPUTS) == "done"
    before = (d / "script-for-tts.txt").read_bytes()
    (d / "story.md").write_text(plain.replace("Fred sat.", "@do fred: collapse\nFred sat."), encoding="utf-8")
    assert run_stage(d, "prep", prep.run, inputs=prep.INPUTS, outputs=prep.OUTPUTS) == "done"
    assert (d / "script-for-tts.txt").read_bytes() == before
    (d / "story.md").write_text(plain.replace("Fred sat.", "@do fred: moonwalk\nFred sat."), encoding="utf-8")
    assert run_stage(d, "prep", prep.run, inputs=prep.INPUTS, outputs=prep.OUTPUTS, force=True) == "failed"
    assert (d / "script-for-tts.txt").read_bytes() == before
    assert clean_markdown(strip_directives("@do fred: lie\nFred.\n")) == "Fred."


# --- validator ---

def _set_actor(i, j=0, **kw):
    return lambda d: actor(d, i, j).update(kw)


def _pair(giver_kw, taker_kw):
    """s02 has bob (talk) and amy (idle): make them a give / receive pair, then apply overrides"""
    def m(d):
        actor(d, 1, 0).update({"action": "give", "target": "amy", "prop": "medal", **giver_kw})
        actor(d, 1, 1).update({"action": "receive", "target": "bob", **taker_kw})
    return m


def _group(holders, role="carry", held_action="carried", move=(1.6, 1.6), facings=("right", "right")):
    """s02 (2 s): bob held by `holders` entries walking `move` units (1.6 = 0.8 u/s). The fixture cast is only
    bob and amy, so every holder entry is amy: the partner rules match on actions and targets, not on ids."""
    def m(d):
        s = shot(d, 1)
        s["actors"] = [{"cast_id": "bob", "action": held_action, "start_pos": [2.4, 0], "facing": "right",
                        "expression": "neutral"}]
        for k in range(holders):
            x = 2.0 + 0.8 * k
            s["actors"].append({"cast_id": "amy", "action": role, "target": "bob", "start_pos": [x, 0],
                                "end_pos": [x + move[k % len(move)], 0], "facing": facings[k % len(facings)],
                                "expression": "neutral"})
    return m


def test_validator_give_receive_pairs():
    assert rules(_pair({}, {})) == set()
    assert "target" in rules(_pair({}, {"action": "idle", "target": None}))   # nobody receives
    assert "target" in rules(_pair({"target": "zed"}, {}))                     # target not on stage
    assert "prop" in rules(_pair({"prop": None}, {}))                          # give needs a prop
    assert "target" in rules(_set_actor(1, 1, target="bob"))                    # idle takes no target
    assert "prop" in rules(_set_actor(1, 0, prop="apple"))                     # talk takes no prop
    assert "prop" in rules(_set_actor(1, 0, action="eat")) and rules(_set_actor(1, 0, action="eat", prop="apple")) == set()


def test_validator_carried_needs_exactly_two_carriers_moving_together():
    assert rules(_group(2)) == set()
    assert "holders" in rules(_group(1))
    assert "holders" in rules(_group(3))
    assert "holders" in rules(_group(2, move=(1.6, 2.0)))                 # not side by side
    assert "holders" in rules(_group(2, facings=("right", "left")))
    def held_moves(d):
        _group(2)(d)
        actor(d, 1, 0)["end_pos"] = [3.0, 0]
    assert "end_pos" in rules(held_moves)                                    # the carried actor has no own move


def test_validator_support_one_or_two():
    for n in (1, 2):
        assert rules(_group(n, role="support", held_action="supported")) == set(), n
    assert "holders" in rules(_group(3, role="support", held_action="supported", move=(1.6,)))
    assert "gliding" in rules(_group(1, role="support", held_action="supported", move=(2.4,)))  # 1.2 > 1.0 u/s


def test_validator_stagger_speed_and_still_actions():
    assert rules(_set_actor(0, 0, action="stagger", end_pos=[1.2, 0])) == set()          # 0.6 u/s
    assert "gliding" in rules(_set_actor(0, 0, action="stagger"))                         # 1.2 u/s: too fast
    for act in ("lie", "collapse"):
        assert "end_pos" in rules(_set_actor(0, 0, action=act)), act                       # no movement
        assert rules(_set_actor(0, 0, action=act, end_pos=None)) == set(), act


def test_validator_broken_car_must_not_move():
    def car(end):
        def m(d):
            shot(d, 1)["vehicles"] = [{"id": "car1", "kind": "car", "action": "broken", "start_pos": [0, -0.6],
                                       "end_pos": end, "facing": "right", "variant": "red"}]
        return m
    assert rules(car(None)) == set()
    assert "vehicle_motion" in rules(car([2, -0.6]))


def test_schema_accepts_new_actions():
    StoryModel.model_validate({"duration_frames": 1, "seed": 1, "shots": [{
        "id": "s01", "start_frame": 0, "end_frame": 1, "set": "room", "phrase_range": [0, 0],
        "camera": {"angle": "wide", "move": "push_in", "speed": 0.2},
        "actors": [{"cast_id": "bob", "action": a, "start_pos": [0, 0], "facing": "camera", "expression": "neutral"}
                   for a in ("stagger", "lie", "collapse", "eat", "give", "receive", "carry", "carried", "support",
                             "supported")]}]})


def test_phrases_helper_ignores_do_lines():
    md = "# T\n\n@do fred: lie\nFred slept.\n"
    assert [w.text for w in phrases_for(md).words] == ["Fred", "slept."]


def test_engine_builtin_actions_match_the_schema():
    """engine/page/actions.js BUILTIN_ACTIONS and schemas ACTIONS each list the built-in actions: they must agree"""
    js = "import('./engine/page/actions.js').then((m) => console.log(JSON.stringify([...m.BUILTIN_ACTIONS])))"
    out = subprocess.run(["node", "-e", js], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert sorted(json.loads(out)) == sorted(ACTIONS)
    assert prep.DO_ACTIONS == actions_with("do") and "receive" not in prep.DO_ACTIONS


SALUTE = {"id": "salute", "name": "Salute", "duration": 1.5, "loop": False,
          "keys": [{"t": 0}, {"t": 0.4, "arms": [[-16, 0], [150, 70]]}]}


def test_custom_action_schema():
    a = CustomAction.model_validate(SALUTE)
    assert a.keys[1].arms[1] == (150, 70) and a.keys[0].arms is None
    for bad, msg in [({"id": "wave"}, "built-in action"), ({"keys": [{"t": 0.5}, {"t": 0.1}]}, "time order"),
                     ({"keys": [{"t": 0, "legs": [-100, 6]}]}, "legs: angles"), ({"keys": [{"t": 0, "knees": [0, 180]}]}, "knees: bends"), ({"keys": []}, "at least 1"),
                     ({"duration": 0}, "greater than or equal")]:
        with pytest.raises(ValueError, match=msg):
            CustomAction.model_validate({**SALUTE, **bad})
    side = {"id": "jab", "name": "Jab", "duration": 1, "facing": "side"}
    with pytest.raises(ValueError, match="elbow only bends forward"):
        CustomAction.model_validate({**side, "keys": [{"t": 0, "arms": [[60, -30], [90, 0]]}]})
    CustomAction.model_validate({**side, "facing": "camera", "keys": [{"t": 0, "arms": [[-60, -30], [60, 30]]}]})  # camera: - mirrors
    with pytest.raises(ValueError, match="duplicate action id"):
        ActionLibrary.model_validate({"actions": [SALUTE, SALUTE]})


def test_do_plays_a_custom_action_from_the_library(tmp_path):
    """@do accepts a library/actions.json id only when it is passed in; the actor gets it, in place, for its line"""
    with pytest.raises(StageError, match="unknown action 'salute'"):
        prep.parse_do("fred: salute", 4)
    with pytest.raises(StageError, match="salute takes no target"):
        prep.parse_do("fred: salute amy tom", 4, actions=["salute"])
    md = "# T\n\n@set office\n@cast fred, amy\n@do fred: salute\nFred stood up straight.\nAmy walked in.\n"
    ph = phrases_for(md)
    story = shots.plan(md, ph, SERIES, 1, actions={"salute": CustomAction.model_validate(SALUTE)})
    assert validate(story, ph, IDS) == []
    first = story.shots[0]
    assert who(first, "fred").action == "salute" and who(first, "fred").end_pos is None
    (tmp_path / "actions.json").write_text(json.dumps({"actions": [SALUTE]}), encoding="utf-8")
    assert unknown_actions(story, tmp_path) == []
    assert unknown_actions(story, tmp_path / "database" / "storage" / "empty") == ["salute"]  # the validate stage refuses it


MOONWALK = {"id": "moonwalk", "name": "Moonwalk", "duration": 1, "facing": "side", "move": -0.8,
            "keys": [{"t": 0, "legs": [-15, 10]}, {"t": 0.5, "legs": [10, -15]}]}


def test_side_actions_turn_and_moving_ones_cross_the_stage_backward():
    """a side action faces left / right; a moving one crosses like a walk at its own speed, a - move faces away"""
    with pytest.raises(ValueError, match="only a side action"):
        CustomAction.model_validate({**MOONWALK, "facing": "camera"})
    moon, bow = CustomAction.model_validate(MOONWALK), CustomAction.model_validate(
        {"id": "bow", "name": "Bow", "duration": 1, "facing": "side", "loop": False, "keys": [{"t": 0}, {"t": 1, "lean": 25}]})
    md = "# T\n\n@set office\n@cast fred, amy\n@do fred: moonwalk, amy: bow\nFred slid across the floor. Amy bowed.\n"
    ph = phrases_for(md)
    story = shots.plan(md, ph, SERIES, 1, actions={"moonwalk": moon, "bow": bow})
    assert validate(story, ph, IDS, moves={"moonwalk": -0.8}) == []
    fred, amy = who(story.shots[0], "fred"), who(story.shots[0], "amy")
    dx = fred.end_pos[0] - fred.start_pos[0]
    assert dx and fred.facing == ("left" if dx > 0 else "right"), "faces away from where it glides"
    assert amy.facing in ("left", "right") and amy.end_pos is None
    # the same move facing the way it goes is caught; without the moves table it must stay put
    wrong = fred.model_copy(update={"facing": "right" if dx > 0 else "left"})
    s0 = story.shots[0].model_copy(update={"actors": [wrong if a.cast_id == "fred" else a for a in story.shots[0].actors]})
    bad = story.model_copy(update={"shots": [s0, *story.shots[1:]]})
    assert "facing" in {e.rule for e in validate(bad, ph, IDS, moves={"moonwalk": -0.8})}
    assert "end_pos" in {e.rule for e in validate(story, ph, IDS)}


def test_custom_action_aimed_at_a_target_faces_and_moves_toward_it():
    """two movers either side of a target both head for it, not for the middle (and into each other)"""
    moon = CustomAction.model_validate({**MOONWALK, "move": 0.8})
    md = "# T\n\n@set office\n@cast fred, tom, amy\n@do fred: moonwalk tom, amy: moonwalk tom\nFred and Amy charged at Tom.\n"
    assert prep.parse_do("fred: moonwalk tom", 4, actions=["moonwalk"])[0].target == "tom"
    ph = phrases_for(md)
    story = shots.plan(md, ph, SERIES, 1, actions={"moonwalk": moon})
    assert validate(story, ph, IDS, moves={"moonwalk": 0.8}) == []
    s0 = story.shots[0]
    t = who(s0, "tom").start_pos[0]
    for cid in ("fred", "amy"):
        a = who(s0, cid)
        d = 1 if t > a.start_pos[0] else -1
        assert a.facing == ("right" if d > 0 else "left") and a.target is None
        if a.end_pos:
            assert (a.end_pos[0] - a.start_pos[0]) * d > 0, f"{cid} moves toward tom"


def test_do_takes_custom_props_from_the_library():
    """eat / give accept a library/props.json id only when it is passed in (prop_kinds): unknown otherwise"""
    line = "@do fred: give flag amy"
    with pytest.raises(StageError, match="give needs a prop and a target"):
        prep.parse_do(line[4:], 4)
    [c] = prep.parse_do(line[4:], 4, props=[*prep.BUILTIN_PROPS, "flag"])
    assert (c.action, c.prop, c.target) == ("give", "flag", "amy")
    with pytest.raises(StageError, match="unknown prop 'torch'"):
        prep.parse_do("fred: eat torch", 4, props=[*prep.BUILTIN_PROPS, "flag"])
