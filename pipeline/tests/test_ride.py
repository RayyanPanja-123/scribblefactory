"""@ride: parsing, the ride state rules, width-aware spacing and seating riders on their mounts"""
import pytest

from pipeline.scribble.schemas import Actor
from pipeline.scribble.stages.prep import parse_ride, ride
from pipeline.scribble.stages.runner import StageError
from pipeline.scribble.stages.shots import MIN_GAP, _free, _seat_riders

IDS, CREATURES = ["charro", "beto", "horse", "mule"], {"horse": "quadruped", "mule": "quadruped"}


def test_parse_ride():
    assert parse_ride("charro: horse", 3, IDS, CREATURES) == ("charro", "horse")
    assert parse_ride("charro: none", 3, IDS, CREATURES) == ("charro", None)
    for arg, msg in [("charro horse", "expected"), ("zed: horse", "unknown cast id"), ("charro: beto", "humanoid"),
                     ("horse: mule", "only people ride")]:
        with pytest.raises(StageError, match=msg):
            parse_ride(arg, 3, IDS, CREATURES)


def test_ride_state():
    rides = ride({}, "charro", "horse", 1)
    assert ride(rides, "charro", "horse", 2) == rides  # again: no change
    with pytest.raises(StageError, match="already rides horse"):
        ride(rides, "charro", "mule", 2)
    with pytest.raises(StageError, match="one rider per creature"):
        ride(rides, "beto", "horse", 2)
    assert ride(rides, "charro", None, 3) == {}


def test_spacing_by_width():
    assert _free(MIN_GAP, [0.0]) and not _free(MIN_GAP - 0.01, [0.0])  # stickmen: as before
    assert not _free(1.0, [(0.0, 0.723)]) and _free(1.13, [(0.0, 0.723)])  # beside a horse: its half width clear


def test_seat_riders():
    horse = Actor(cast_id="horse", action="walk", start_pos=(0.0, 0.0), end_pos=(1.5, 0.0), facing="right",
                  expression="neutral")
    charro = Actor(cast_id="charro", action="eat", start_pos=(2.0, 0.0), facing="camera", expression="happy",
                   prop="apple")
    pos = {"horse": 1.5, "charro": 2.0}
    out = {a.cast_id: a for a in _seat_riders([horse, charro], {"charro": "horse"}, pos)}
    c = out["charro"]
    assert (c.mount, c.action, c.prop, c.start_pos, c.end_pos, c.facing) == ("horse", "idle", None, (0.0, 0.0), None, "right")
    assert pos["charro"] == 1.5 and out["horse"].action == "walk"
    # a hand-off in the saddle keeps its partner and prop
    beto = Actor(cast_id="beto", action="give", start_pos=(1.0, 0.0), facing="right", expression="neutral",
                 target="charro", prop="scroll")
    charro.action, charro.target, charro.prop = "receive", "beto", None
    out = {a.cast_id: a for a in _seat_riders([horse, charro, beto], {"charro": "horse"}, pos)}
    assert (out["charro"].action, out["charro"].target) == ("receive", "beto")
