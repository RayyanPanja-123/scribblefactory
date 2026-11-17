"""Step 5c-7 (+ layout fix): crowd and runner extras (@crowd, @runners), the dress / wide_hat costume and the mood
actions. The screen-space head-overlap rule lives in the engine (engine/test/extras.test.mjs)."""

import pytest

from pipeline.scribble.cli import main
from pipeline.scribble.io import load_series
from pipeline.scribble.schemas import CastMember
from pipeline.scribble.stages.runner import StageError
from pipeline.scribble.stages.shots import CROWD_DEFAULT, CROWD_GAP, RUNNER_GAP
from pipeline.scribble.validate import CROWD_Z, RUN_SPEED, validate

from .test_actions import IDS, SERIES, who
from .test_shots import plan
from .test_validate import rules, shot


def planned(md, word_s=0.4):
    story, ph = plan(md, word_s, SERIES)
    assert validate(story, ph, IDS) == [], validate(story, ph, IDS)
    return story


def crowd(s):
    return [e for e in s.extras if e.kind == "crowd"]


def runners(s):
    return [e for e in s.extras if e.kind == "runner"]


# --- directives ---

def test_crowd_and_runners_directives_until_changed():
    md = ("# T\n\n@set stadium\n@cast fred, amy\n@crowd angry 10\n@runners 3\nFred spoke.\n\nAmy spoke.\n"
          "@crowd off\n@runners 0\nFred sat.\n")
    story = planned(md)
    first, second, last = story.shots[0], story.shots[1], story.shots[-1]
    assert len(crowd(first)) == 10 and {e.action for e in crowd(first)} == {"angry"}
    assert len(runners(first)) == 3 and len(crowd(second)) == 10
    assert last.extras == []


def test_crowd_default_size_and_moods():
    for mood in ("cheer", "angry", "gasp", "neutral"):
        s = planned(f"# T\n\n@set stadium\n@cast fred\n@crowd {mood}\nFred spoke.\n").shots[0]
        assert len(crowd(s)) == CROWD_DEFAULT and {e.action for e in s.extras} == {mood}


def test_extras_reset_on_set_change_unless_repeated():
    md = ("# T\n\n@set stadium\n@cast fred\n@crowd cheer\n@runners 2\nFred spoke.\n"
          "@set office\nFred sat.\n@set street\n@crowd gasp 5\nFred stood.\n")
    story = planned(md)
    sets = {s.set: s for s in story.shots}
    assert len(sets["stadium"].extras) == CROWD_DEFAULT + 2
    assert sets["office"].extras == []
    assert len(crowd(sets["street"])) == 5 and runners(sets["street"]) == []


@pytest.mark.parametrize("line", ["@crowd dance", "@crowd cheer 13", "@crowd cheer 0", "@crowd", "@crowd cheer 5 6",
                                  "@runners 7", "@runners x"])
def test_bad_extras_directives_name_the_line(line):
    with pytest.raises(StageError, match="story.md line 4: bad directive"):
        plan(f"# T\n\n@cast fred\n{line}\nFred sat.\n", series=SERIES)


# --- crowd layout ---

def _rows(s):
    es = sorted(crowd(s), key=lambda e: e.start_pos[0])
    return [e for e in es if e.start_pos[1] > -2.2], [e for e in es if e.start_pos[1] <= -2.2]


@pytest.mark.parametrize("n", [1, 5, 7, 8, 12])
@pytest.mark.parametrize("set_", ["stadium", "office", "street"])
def test_crowd_rows_spacing_and_depth(n, set_):
    s = planned(f"# T\n\n@set {set_}\n@cast fred\n@crowd cheer {n}\nFred spoke.\n").shots[0]
    front, back = _rows(s)
    assert len(front) + len(back) == n
    assert (len(back) > 0) == (n > 7) and len(front) >= len(back)            # a second row only above 7
    for row in (front, back):
        xs = [e.start_pos[0] for e in row]
        assert all(b - a >= CROWD_GAP for a, b in zip(xs, xs[1:])), xs        # neighbours 0.55+ apart
    for e in crowd(s):
        assert CROWD_Z[0] <= e.start_pos[1] <= CROWD_Z[1] and e.end_pos is None and e.facing == "camera"
    if set_ == "stadium":
        assert all(e.start_pos[1] <= -1.8 for e in crowd(s))                  # behind the rail (z -1.6)
    if set_ == "office":
        assert all(e.start_pos[1] >= -2.5 for e in crowd(s))                  # in front of the back wall
    assert all(-2.8 <= e.start_pos[1] <= -2.2 for e in back)
    if back:  # offset half a step: each back extra stands between two front ones
        fx = [e.start_pos[0] for e in front]
        assert all(any(a < e.start_pos[0] < b for a, b in zip(fx, fx[1:])) for e in back)


def test_crowd_is_deterministic_and_stays_put_across_cuts():
    md = "# T\n\n@set stadium\n@cast fred\n@crowd neutral 9\nFred spoke for a long long while about it.\nFred sat.\n"
    a, b = planned(md, 0.6), planned(md, 0.6)
    assert [s.extras for s in a.shots] == [s.extras for s in b.shots]
    assert len(a.shots) >= 2 and all(s.extras == a.shots[0].extras for s in a.shots)  # same people, same spots


def test_no_crowd_in_travel_shots():
    s = planned("# T\n\n@set dirt_road\n@cast fred\n@crowd cheer\nFred ran on.\n").shots[0]
    assert s.travel is not None and crowd(s) == []


# --- runners ---

def _min_gap(a, b, c):
    """smallest x distance between point c and the run a..b"""
    lo, hi = min(a, b), max(a, b)
    return c - hi if c > hi else lo - c if c < lo else 0.0


@pytest.mark.parametrize("verb", ["walked", "ran"])  # walk travel: runners gain 1.4 u/s; run travel: 0.1 u/s
def test_runners_in_travel_shots_keep_clear_of_the_cast_and_each_other(verb):
    story = planned(f"# T\n\n@set dirt_road\n@cast fred, amy\n@runners 4\nFred {verb} on and on and on.\n", 0.5)
    for s in story.shots:
        assert s.travel is not None and len(runners(s)) == 4
        way = s.actors[0].facing
        secs = (s.end_frame - s.start_frame) / 30
        cast_x = [x for a in s.actors for x in (a.start_pos[0], a.end_pos[0])]
        for e in runners(s):
            assert e.facing == way and e.start_pos[1] < -0.6
            speed = s.travel.speed + abs(e.end_pos[0] - e.start_pos[0]) / secs  # legs: scroll + own gain
            assert RUN_SPEED[0] <= speed <= RUN_SPEED[1]
            for c in cast_x:  # the whole run stays 0.6+ clear of the cast
                assert _min_gap(e.start_pos[0], e.end_pos[0], c) >= RUNNER_GAP - 1e-9, (s.id, e.id, c)
        for t in ("start_pos", "end_pos"):
            xs = sorted(getattr(e, t)[0] for e in runners(s))
            assert all(b - a >= RUNNER_GAP - 1e-9 for a, b in zip(xs, xs[1:])), xs
    # placed near the frame centre first, so some are on screen (|x| < 1.8) when there is room
    assert any(abs(e.start_pos[0]) < 1.8 for s in story.shots for e in runners(s))


def test_runners_cross_the_background_in_normal_shots_all_one_way():
    s = planned("# T\n\n@set office\n@cast fred\n@runners 4\nFred spoke.\n").shots[0]
    assert len({e.facing for e in runners(s)}) == 1  # one way: they never pass each other
    for e in runners(s):
        dx = e.end_pos[0] - e.start_pos[0]
        assert abs(e.start_pos[0]) >= 3.0 and e.facing == ("right" if dx > 0 else "left")
        assert -2.5 <= e.start_pos[1] <= -2.0  # behind the crowd's front row, in front of the office wall
    xs = sorted(e.start_pos[0] for e in runners(s))
    assert all(b - a >= RUNNER_GAP for a, b in zip(xs, xs[1:]))


# --- moods as cast actions ---

def test_do_mood_actions():
    s = planned("# T\n\n@cast fred, amy, tom\n@do fred: cheer, amy: angry, tom: gasp\nThey reacted.\n").shots[0]
    assert [who(s, c).action for c in ("fred", "amy", "tom")] == ["cheer", "angry", "gasp"]


# --- validator ---

def _extras(*items):
    return lambda d: shot(d, 1).__setitem__("extras", list(items))


def _crowd(**kw):
    return {"id": "crowd1", "kind": "crowd", "action": "cheer", "start_pos": [0, -1.8], "facing": "camera", "variant": 3,
            **kw}


def _runner(**kw):
    # s02 is 2 s long: 5.2 units = 2.6 u/s
    return {"id": "runner1", "kind": "runner", "action": "run", "start_pos": [-3, -1.5], "end_pos": [2.2, -1.5],
            "facing": "right", "variant": 7, **kw}


def test_validator_extras_rules():
    assert rules(_extras(_crowd(), _runner())) == set()
    assert "extras" in rules(_extras(_crowd(end_pos=[1, -1.8])))            # crowd never moves
    assert "extras_zone" in rules(_extras(_crowd(start_pos=[0, -0.5])))     # inside the clearance zone
    assert "extras_zone" in rules(_extras(_crowd(start_pos=[0, -2.9])))     # past the back row
    assert "extras" in rules(_extras(_crowd(action="run")))                  # a crowd takes a mood
    assert "extra_id" in rules(_extras(_crowd(), _crowd()))
    assert "gliding" in rules(_extras(_runner(end_pos=[-2.0, -1.5])))       # 0.5 u/s: legs would slide
    assert "facing" in rules(_extras(_runner(facing="left")))
    assert "extras_zone" in rules(_extras(_runner(start_pos=[-3, 0], end_pos=[2.2, 0])))  # on the actors' line
    assert "extras" in rules(_extras(_runner(action="cheer")))


def test_validator_travel_extras():
    def travel(d):
        s = shot(d, 1)
        s["set"] = "street"
        s["travel"] = {"speed": 1.2}
        for a in s["actors"]:
            a.update(action="walk", facing="right", end_pos=list(a["start_pos"]))
    ok = _runner(start_pos=[1, -1.0], end_pos=[3.8, -1.0])  # 1.2 scroll + 1.4 own = 2.6 u/s
    assert rules(lambda d: (travel(d), _extras(ok)(d))) == set()
    assert "travel_extras" in rules(lambda d: (travel(d), _extras(dict(ok, facing="left", end_pos=[1, -1.0]))(d)))
    assert "extras" in rules(lambda d: (travel(d), _extras(_crowd())(d)))  # no crowd in a travel shot


# --- dress and wide hat ---

def test_dress_and_wide_hat_in_schema_and_cast_edit(tmp_path, monkeypatch):
    CastMember.model_validate({"id": "d", "name": "D", "top": {"style": "dress", "color": "#f7f2e8",
                                                              "accent_color": "#c2185b"},
                               "headwear": {"kind": "wide_hat", "color": "#f7f2e8"}, "eyes": "dots"})
    monkeypatch.setenv("SCRIBBLE_LIBRARY", str(tmp_path))
    assert main(["new-series", "s", "--title", "S"]) == 0
    assert main(["cast-add", "s", "dee", "--name", "Dee", "--color", "#f7f2e8"]) == 0
    assert main(["cast-edit", "s", "dee", "--top", "dress", "--accent", "#c2185b", "--headwear", "wide_hat",
                 "--headwear-color", "#f7f2e8"]) == 0
    c = load_series(tmp_path / "s" / "series.json").cast[0]
    assert (c.top.style, c.top.accent_color, c.headwear.kind, c.approved_at) == ("dress", "#c2185b", "wide_hat", None)
