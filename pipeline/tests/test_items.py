"""World Items: the schema (card items, reserved states, rows that keep their bytes), @item / @do <item>: fly in the
shot planner and check-story."""

import json

import pytest

from pipeline.scribble.schemas import CustomSet, StoryModel, WorldObject, WorldObjectInstance
from pipeline.scribble.stages import shots
from pipeline.scribble.stages.prep import parse_item
from pipeline.scribble.stages.runner import StageError
from pipeline.scribble.validate import validate
from pipeline.tests.test_shots import DIRECTED, SERIES, phrases_for

SAUCER = WorldObject(id="saucer", name="Saucer", category="scifi", look="card", draw="saucer", size=1.6, layer="back",
                     states=["flying", "landed"], anims=[{"kind": "bob", "amp": 0.15, "hz": 0.6, "when": ["flying"]}])
PLANET = WorldObject(id="ringed-planet", name="Ringed planet", category="sky", look="card", draw="planet", size=12,
                     layer="sky", anims=[{"kind": "flow", "hz": 0.02}, {"kind": "drift", "amp": 0.4, "hz": 0.03}])
BARREL = WorldObject(id="barrel", name="Barrel", pieces=[{"shape": "cyl", "at": [0, 0.5, 0], "size": [0.4, 0.4, 1],
                                                          "color": "#8a5a32"}])
OBJECTS = {o.id: o for o in (SAUCER, PLANET, BARREL)}


def plan(md, objects=OBJECTS):
    return shots.plan(md, phrases_for(md), SERIES, 1, objects=objects)


def items_of(story):
    return [[(i.id, i.start_pos[0], (i.end_pos or i.start_pos)[0], i.facing, i.state) for i in s.items] for s in story.shots]


# --- schema: old rows keep their bytes ---

def test_rows_without_item_fields_dump_unchanged():
    """a catalog row saved before World Items (and a set, a placement) dumps to exactly what it was"""
    for model, row in [
        (WorldObject, {"id": "barrel", "name": "Barrel", "category": "container", "capabilities": ["carry"],
                       "carry_mode": "two-hand", "pieces": []}),
        (WorldObjectInstance, {"id": "b1", "object": "barrel", "at": [1.0, 0.0, -2.0], "visible": True}),
        (CustomSet, {"id": "yard", "name": "Yard", "use_for": None, "kind": "outdoor", "floor": "#88aa55",
                     "back": "#99ccee", "pieces": [], "objects": [], "default_weather": None}),
    ]:
        assert model.model_validate(row).model_dump(mode="json") == row


def test_story_without_items_has_no_items_key():
    """a plan with no @item writes the bytes it wrote before World Items: no "items" in any shot"""
    story = plan(DIRECTED)
    assert all("items" not in s for s in story.model_dump(mode="json")["shots"])
    assert '"items"' not in json.dumps(story.model_dump(mode="json"))


def test_card_rules():
    with pytest.raises(ValueError, match="reserved"):
        WorldObject(id="pod", name="Pod", look="card", draw="saucer", states=["closed", "remove"])
    with pytest.raises(ValueError, match="reserved"):
        WorldObject(id="pod", name="Pod", look="card", draw="saucer", states=["state"])
    with pytest.raises(ValueError, match="needs a built-in drawing"):
        WorldObject(id="pod", name="Pod", look="card")
    with pytest.raises(ValueError, match="for a card"):
        WorldObject(id="pod", name="Pod", anims=[{"kind": "bob"}])
    with pytest.raises(ValueError, match="unknown state"):
        WorldObject(id="pod", name="Pod", look="card", draw="saucer", anims=[{"kind": "bob", "when": ["open"]}])
    with pytest.raises(ValueError, match="share"):
        WorldObject(id="pod", name="Pod", look="card", draw="saucer", anims=[{"kind": "pulse", "amp": 2}])


def test_set_water_field():
    s = dict(id="lake", name="Lake", kind="outdoor", floor="#3a8fb7", back="#99ccee")
    assert CustomSet(**s, water=False).model_dump(mode="json")["water"] is False
    with pytest.raises(ValueError, match="outdoor"):
        CustomSet(**{**s, "kind": "indoor"}, water=True)


# --- prep: the @item line ---

def test_parse_item():
    assert parse_item("ship: saucer back far-left landed", 3, OBJECTS)[1:] == ("place", "saucer", "back", "far-left", "landed")
    assert parse_item("ship: saucer", 3, OBJECTS)[1:] == ("place", "saucer", None, "center", None)
    assert parse_item("ship: remove", 3).op == "remove"
    assert parse_item("ship: state landed", 3).state == "landed"
    for arg, msg in [("ship saucer", "expected"), ("ship: blimp", "unknown World Item"), ("ship: barrel", "set pieces"),
                     ("ship: saucer parked", "no state"), ("bob: saucer", "cast id"), ("ship: state", "one state"),
                     ("ship: remove saucer", "takes no item")]:
        with pytest.raises(StageError, match=msg):
            parse_item(arg, 3, OBJECTS, ["bob"])


# --- shots: placing, flying, state, removing ---

FLY = """# Fly

@set street
@cast bob
@item ship: saucer back
@item world: ringed-planet far-right
Bob looked up at the sky.
@do ship: fly left
Something flew over the roofs, very fast and very low, and nobody else saw it at all.
@item ship: state landed
Then it landed.
@item ship: remove
Bob went home.
"""


def test_items_place_fly_state_remove():
    story = plan(FLY)
    per_shot = items_of(story)
    assert per_shot[0] == [("ship", 0.0, 0.0, "right", None), ("world", 8.0, 8.0, "right", None)]
    # the fly line: from the middle off screen left, spread over all the line's shots with no jump between them
    fly = [s for s, sh in zip(per_shot, story.shots) if sh.items and sh.items[0].end_pos]
    assert len(fly) >= 2
    path = [x for s in fly for x in s[0][1:3]]
    assert path[0] == 0.0 and path[-1] == -shots.ITEM_PLACE["back"]["reach"]
    assert all(b == c for b, c in zip(path[1::2], path[2::2]))  # each shot starts where the last one ended
    assert all(s[0][3] == "left" for s in fly)
    landed = next(s for s in per_shot if s[0][4] == "landed")
    assert landed[0][1] == -shots.ITEM_PLACE["back"]["reach"]  # still where it flew to, now landed
    assert per_shot[-1] == [("world", 8.0, 8.0, "right", None)]  # removed
    StoryModel.model_validate(story.model_dump(mode="json"))  # round-trips


def test_fly_again_comes_back_from_the_far_side():
    md = "# Twice\n\n@set street\n@item ship: saucer\n@do ship: fly left\nIt went left.\n@do ship: fly left\nIt went again.\n"
    per_shot = items_of(plan(md))
    reach = shots.ITEM_PLACE["back"]["reach"]  # the saucer's own layer
    assert per_shot[0][0][1:3] == (0.0, -reach)
    assert per_shot[-1][0][1:3] == (reach, -reach)


def test_items_belong_to_a_set_and_cast_do_still_applies():
    md = "# Sets\n\n@set street\n@cast bob\n@item ship: saucer\n@do ship: fly right, bob: wave\nBob waved at it.\n@set office\nBob sat down.\n"
    story = plan(md)
    assert story.shots[0].items and story.shots[0].actors[0].action == "wave"
    assert not story.shots[-1].items


@pytest.mark.parametrize("md, msg", [
    ("@do ship: fly left\nHi.\n", "not an item on stage"),
    ("@item ship: remove\nHi.\n", "not on stage"),
    ("@item ship: state landed\nHi.\n", "not on stage"),
    ("@item ship: saucer\n@item ship: state open\nHi.\n", "no state"),
    ("@do ship: fly up\nHi.\n", "direction"),
])
def test_item_errors(md, msg):
    with pytest.raises(StageError, match=msg):
        plan("# E\n\n@set street\n" + md)


def test_storycheck_items(tmp_path):
    from pipeline.scribble.io import save_object
    from pipeline.scribble.storycheck import check_story
    from pipeline.tests.test_storycheck import setup
    part = setup(tmp_path, "@set street\n@cast bob\n@item ship: saucer\n@do ship: fly left\nBob saw it.\n"
                           "@item ship: state open\n@do plane: fly left\nThen nothing.\n@item pod: barrel\nEnd.\n")
    for o in (SAUCER, BARREL):
        save_object(tmp_path, o)
    msgs = [p["message"] for p in check_story(part)["problems"]]
    assert any("no state 'open'" in m for m in msgs)
    assert any("plane is not an item on stage" in m for m in msgs)
    assert any("set pieces" in m for m in msgs)
    assert not any("ship is not an item" in m for m in msgs)


def test_action_keys_without_snap_round_trip():
    """custom actions saved before ActionKey.snap existed dump back to the same row; snap true is kept"""
    from pipeline.scribble.schemas import CustomAction
    row = {"id": "bow", "name": "Bow", "use_for": None, "duration": 1.0, "loop": True, "facing": "camera", "move": 0.0,
           "keys": [{"t": 0.0, "arms": None, "legs": None, "knees": None, "lean": 0.0, "ease": "in-out"},
                    {"t": 1.0, "arms": None, "legs": None, "knees": None, "lean": 30.0, "ease": "in-out", "snap": True}]}
    assert CustomAction.model_validate(row).model_dump(mode="json") == row


# --- Phase B: interactions (fixtures: pipeline/tests/items_fixture.py, not library items) ---

from pipeline.tests import items_fixture as fx  # noqa: E402


def plan_b(md):
    return shots.plan(md, phrases_for(md), SERIES, 1, objects=fx.OBJECTS)


def actor(shot, cid="bob"):
    return next(a for a in shot.actors if a.cast_id == cid)


def test_pickup_holds_the_item_from_the_next_shot():
    story = plan_b("# P\n\n@set street\n@cast bob\n@item gem: glow-crystal\nA stone.\n@do bob: pickup gem\nHe took it.\nThen he left.\n")
    take = next(s for s in story.shots if actor(s).action == "pickup")
    assert actor(take).item == "gem" and [i.id for i in take.items] == ["gem"]
    gem = take.items[0]
    assert actor(take).facing == ("right" if gem.start_pos[0] > actor(take).start_pos[0] else "left")
    after = story.shots[story.shots.index(take) + 1:]
    assert after and all(not s.items for s in after)  # held: off the stage
    StoryModel.model_validate(story.model_dump(mode="json"))


def test_drop_puts_it_back_beside_the_dropper():
    story = plan_b("# D\n\n@set street\n@cast bob\n@item gem: glow-crystal\nA stone.\n@do bob: pickup gem\nHe took it.\n"
                   "@do bob: drop gem\nHe put it down.\nDone.\n")
    drop = next(s for s in story.shots if actor(s).action == "drop")
    gx, bx = drop.items[0].start_pos[0], actor(drop).start_pos[0]
    assert abs(gx - bx) >= shots.ITEM_BODY  # beside the feet, not inside the body
    assert story.shots[-1].items[0].start_pos[0] == gx  # and it stays there


def test_open_switches_state_mid_shot_and_keeps_it():
    story = plan_b("# O\n\n@set street\n@cast bob\n@item pod: escape-pod\nA pod.\n@do bob: open pod\nHe opened it.\nInside it was dark.\n")
    op = next(s for s in story.shots if actor(s).action == "open")
    pod = next(i for i in op.items if i.id == "pod")
    assert pod.state == "closed" and pod.switch.to == "open" and op.start_frame < pod.switch.frame < op.end_frame
    assert next(i for i in story.shots[-1].items if i.id == "pod").state == "open"


def test_close_after_open():
    story = plan_b("# C\n\n@set street\n@cast bob\n@item pod: escape-pod\nA pod.\n@do bob: open pod\nOpen.\n@do bob: close pod\nShut.\nDone.\n")
    assert next(i for i in story.shots[-1].items if i.id == "pod").state == "closed"


def test_push_slides_it_away():
    obj = {**fx.OBJECTS, "escape-pod": fx.POD.model_copy(update={"capabilities": [*fx.POD.capabilities, "push"]})}
    md = "# Pu\n\n@set street\n@cast bob\n@item pod: escape-pod\nA pod.\n@do bob: push pod\nHe pushed it.\nIt stayed.\n"
    story = shots.plan(md, phrases_for(md), SERIES, 1, objects=obj)
    sh = next(s for s in story.shots if actor(s).action == "push")
    pod = next(i for i in sh.items if i.id == "pod")
    assert pod.end_pos and abs(abs(pod.end_pos[0] - pod.start_pos[0]) - shots.PUSH_D) < 1e-9
    assert (pod.end_pos[0] - pod.start_pos[0]) * (pod.start_pos[0] - actor(sh).start_pos[0]) > 0  # away from bob
    assert next(i for i in story.shots[-1].items if i.id == "pod").start_pos[0] == pod.end_pos[0]


def test_sit_lasts_until_the_next_do_and_stand_gets_up():
    story = plan_b("# S\n\n@set street\n@cast bob\n@item b: bench\nA bench.\n@do bob: sit b\nHe sat down.\n"
                   "He thought.\nAnd thought.\n@do bob: stand\nHe got up.\nThen he left.\n")
    acts = [actor(s).action for s in story.shots]
    first, up = acts.index("sit"), acts.index("stand")
    assert set(acts[first:up]) == {"sit"} and all(actor(s).item == "b" for s in story.shots[first:up + 1])
    assert acts[up + 1:] and "sit" not in acts[up + 1:] and "stand" not in acts[up + 1:]
    assert len({actor(s).start_pos for s in story.shots[first:up + 1]}) == 1  # stays where it sat down


def test_another_do_ends_the_sit_and_stand_without_sitting_is_idle():
    story = plan_b("# S2\n\n@set street\n@cast bob\n@item b: bench\nA bench.\n@do bob: sit b\nHe sat down.\n"
                   "@do bob: wave\nHe waved.\n@do bob: stand\nHe stood.\n")
    acts = [actor(s).action for s in story.shots]
    assert "wave" in acts and "sit" not in acts[acts.index("wave"):] and "stand" not in acts


APPROACH_MD = ("# A\n\n@set street\n@cast bob, amy, karen\n@item b: bench left\nBob saw a bench by the wall.\n"
               "@do karen: sit b\nKaren walked over and sat down on it with a long tired sigh of relief.\nAmy laughed.\n")


def test_approach_walk_then_act():
    ph = phrases_for(APPROACH_MD)
    story = shots.plan(APPROACH_MD, ph, SERIES, 1, objects=fx.OBJECTS)
    walk = [s for s in story.shots if actor(s, "karen").action == "walk"]
    arrive = next(s for s in story.shots if actor(s, "karen").approach)
    a = actor(arrive, "karen")
    assert walk and walk[0].start_frame < arrive.start_frame  # the walk starts with the line, the action after it
    assert 0 < a.approach < 1 and a.end_pos and a.item == "b" and a.action == "sit"
    bench = next(i for i in arrive.items if i.id == "b").start_pos[0]
    reach = 0.5 * shots.ITEM_FILL * fx.BENCH.size * shots.ITEM_ASPECT["bench"] + shots.ITEM_BODY + 0.05
    assert abs(abs(a.end_pos[0] - bench) - reach) < 1e-6  # arrives at arm's reach
    line = [s for s in story.shots if s.phrase_range[0] >= walk[0].phrase_range[0] and s.phrase_range[0] <= arrive.phrase_range[0]]
    walked = sum(s.end_frame - s.start_frame for s in walk) + a.approach * (arrive.end_frame - arrive.start_frame)
    assert walked <= shots.APPROACH_SHARE * sum(s.end_frame - s.start_frame for s in line) + 1
    assert not validate(story, ph, {c.id for c in SERIES.cast})


def test_in_reach_plays_as_before():
    """an actor already in reach gets no approach walk: no approach field, nothing new in the plan"""
    story = plan_b(fx.STORY)
    assert all(a.approach is None for s in story.shots for a in s.actors)
    assert '"approach"' not in json.dumps(story.model_dump(mode="json"))


def test_too_far_warns():
    notes = []
    md = "# F\n\n@set street\n@cast bob, amy, karen\n@item b: bench left\nBob saw it.\n@do karen: sit b\nSat.\n"
    story = shots.plan(md, phrases_for(md), SERIES, 1, objects=fx.OBJECTS, notes=notes)
    assert notes and "too far to walk to" in notes[0][1] and "place the item closer or add a line" in notes[0][1]
    assert not validate(story, phrases_for(md), {c.id for c in SERIES.cast})  # walks as fast as a walk may, short
    notes.clear()
    shots.plan(APPROACH_MD, phrases_for(APPROACH_MD), SERIES, 1, objects=fx.OBJECTS, notes=notes)
    assert not notes  # a long enough line: no warning


def test_storycheck_reports_too_far(tmp_path):
    from pipeline.scribble.io import save_object
    from pipeline.scribble.storycheck import check_story
    from pipeline.tests.test_storycheck import setup
    part = setup(tmp_path, "@set street\n@cast bob, amy, fred\n@item b: bench left\nBob saw it.\n@do fred: sit b\nSat.\n")
    save_object(tmp_path, fx.BENCH)
    (part / "phrases.json").write_text(phrases_for((part / "story.md").read_text(encoding="utf-8")).model_dump_json())
    warns = [w["message"] for w in check_story(part)["warnings"]]
    assert any("too far to walk to" in w for w in warns), warns


def test_item_prop_must_exist(tmp_path):
    from pipeline.scribble.io import delete_prop, save_object, save_prop
    with pytest.raises(ValueError, match="'glow-crystal' .* is not a prop"):
        save_object(tmp_path, fx.CRYSTAL)  # its prop isn't in the library yet
    save_prop(tmp_path, fx.GLOW)
    save_object(tmp_path, fx.CRYSTAL)
    with pytest.raises(ValueError, match="glow-crystal is still the held prop of World Item glow-crystal"):
        delete_prop(tmp_path, "glow-crystal")


def test_storycheck_item_prop_missing(tmp_path):
    from pipeline.scribble import db
    from pipeline.scribble.storycheck import check_story
    from pipeline.tests.test_storycheck import setup
    part = setup(tmp_path, "@set street\n@cast bob\n@item gem: glow-crystal\nA stone.\n")
    db.put_catalogs(tmp_path, {"objects": [fx.CRYSTAL.model_dump(mode="json")]})  # saved before the check existed
    msgs = [p["message"] for p in check_story(part)["problems"]]
    assert any("held as prop 'glow-crystal', which is not a prop" in m for m in msgs), msgs


def test_enter_ride_and_exit_follow_the_pod():
    story = plan_b("# E\n\n@set street\n@cast bob\n@item pod: escape-pod\nA pod.\n@do bob: enter pod\nIn he went.\n"
                   "@do pod: fly right\nOff it flew, far away over the hills.\n@do bob: exit pod\nOut he came.\nDone.\n")
    rides = [s for s in story.shots if actor(s).action == "ride"]
    assert rides and all(next(i for i in s.items if i.id == "pod").riders == ["bob"] for s in rides)
    assert any(next(i for i in s.items if i.id == "pod").end_pos for s in rides)  # seated while the pod flies
    assert any(actor(s).action == "exit" for s in story.shots)
    assert not next(i for i in story.shots[-1].items if i.id == "pod").riders and actor(story.shots[-1]).action != "ride"


def test_stage_items_never_overlap_actors():
    story = plan_b("# Sp\n\n@set street\n@cast bob, amy, karen\n@item b: bench\n@item pod: escape-pod\nThree people and things.\n"
                   "Amy talked.\nKaren talked.\n")
    for s in story.shots:
        for it in s.items:
            o = fx.OBJECTS[it.object]
            half = 0.5 * shots.ITEM_FILL * o.size * shots.ITEM_ASPECT[o.draw]
            for a in s.actors:
                assert abs(it.start_pos[0] - a.start_pos[0]) >= half + shots.ITEM_BODY - 1e-9, (s.id, it.id, a.cast_id)


@pytest.mark.parametrize("md, msg", [
    ("@item gem: glow-crystal\n@do bob: open gem\nHi.\n", "open capability"),
    ("@item gem: glow-crystal\n@do bob: drop gem\nHi.\n", "doesn't hold"),
    ("@item pod: escape-pod\n@do bob: exit pod\nHi.\n", "is not inside"),
    ("@item gem: glow-crystal\n@item g2: glow-crystal\n@do bob: pickup gem\nOne.\n@do bob: pickup g2\nTwo.\n", "already holds gem"),
    ("@item pod: escape-pod\n@do bob: enter pod\nIn.\n@do bob: wave\nHi.\n", "inside pod"),
    ("@do bob: pickup gem\nHi.\n", "not an item on stage"),
])
def test_interaction_errors(md, msg):
    with pytest.raises(StageError, match=msg):
        plan_b("# E\n\n@set street\n@cast bob\n" + md)


def test_storycheck_interactions(tmp_path):
    from pipeline.scribble.io import save_object, save_prop
    from pipeline.scribble.storycheck import check_story
    from pipeline.tests.test_storycheck import setup
    part = setup(tmp_path, "@set street\n@cast bob\n@item gem: glow-crystal\n@item pod: escape-pod\n@do bob: pickup gem\nOne.\n"
                           "@do bob: pickup gem\nTwo.\n@do bob: open gem\nThree.\n@do bob: exit pod\nFour.\n@do bob: enter pod\nFive.\n"
                           "@do bob: wave\nSix.\n")
    save_prop(tmp_path, fx.GLOW)
    for o in fx.OBJECTS.values():
        save_object(tmp_path, o)
    msgs = [p["message"] for p in check_story(part)["problems"]]
    for want in ("bob already holds gem", "open capability", "bob is not inside pod", "bob is inside pod (exit first"):
        assert any(want in m for m in msgs), (want, msgs)


def test_delete_guard_names_the_stories(tmp_path):
    from pipeline.scribble.io import delete_object, save_object
    from pipeline.tests.test_storycheck import setup
    setup(tmp_path, "@set street\n@cast bob\n@item ship: saucer back\nBob looked up.\n")
    save_object(tmp_path, SAUCER)
    save_object(tmp_path, PLANET)
    with pytest.raises(ValueError, match=r"saucer is still used by demo/part-01"):
        delete_object(tmp_path, "saucer")
    delete_object(tmp_path, "ringed-planet")  # unused: goes


def test_package_carries_world_items(tmp_path):
    from pipeline.scribble.io import save_object
    from pipeline.scribble.package import parse
    save_object(tmp_path, SAUCER)  # taken: the package's saucer is renamed, and its @item line follows
    text = "\n".join(["<<<SCRIBBLE_PACKAGE v1>>>", "<<<META>>>", '{"series_title": "Ufo", "parts": 1}',
                      "<<<PROPS>>>", "[]", "<<<SETS>>>", "[]", "<<<CREATURES>>>", "[]", "<<<ACTIONS>>>", "[]",
                      "<<<WARDROBE>>>", "[]", "<<<OBJECTS>>>", json.dumps([SAUCER.model_dump(mode="json")]),
                      "<<<CAST>>>", '[{"id": "bob", "name": "Bob", "color": "#3a7bd5"}]',
                      "<<<PART 1>>>", "<<<SCRIPT>>>", "# Ufo\n\n@set street\n@cast bob\n@item ship: saucer back\nBob looked up.",
                      "<<<VOICE>>>", "Bob looked up.", "<<<END>>>"])
    r = parse(text, tmp_path)
    assert [o.id for o in r["assets"]["OBJECTS"]] == ["saucer-2"] and r["renames"]["OBJECTS"] == {"saucer": "saucer-2"}
    assert "@item ship: saucer-2 back" in r["parts"][0]["story"]


def test_approach_passes_behind_actors_in_the_way():
    story = shots.plan(APPROACH_MD, phrases_for(APPROACH_MD), SERIES, 1, objects=fx.OBJECTS)
    walk = [actor(s, "karen") for s in story.shots if actor(s, "karen").action == "walk" or actor(s, "karen").approach]
    others = sorted(actor(story.shots[0], c).start_pos[0] for c in ("bob", "amy"))
    assert walk and all(a.behind == others for a in walk)  # both stand between karen and the bench
    later = [actor(s, "karen") for s in story.shots if actor(s, "karen").action == "sit" and not actor(s, "karen").approach]
    assert later and all(a.behind == [] for a in later)


def test_approach_with_nobody_in_the_way_has_no_dip():
    md = ("# N\n\n@set street\n@cast bob\n@item b: bench mid right\nBob saw a bench across the way.\n"
          "@do bob: sit b\nBob walked over and sat down on it with a long tired sigh of relief.\n")
    story = shots.plan(md, phrases_for(md), SERIES, 1, objects=fx.OBJECTS)
    walks = [actor(s) for s in story.shots if actor(s).action == "walk" or actor(s).approach]
    assert walks and all(a.behind == [] for a in walks)
    assert '"behind"' not in json.dumps(story.model_dump(mode="json"))  # left out: the plan is as before


def test_stage_hash_covers_only_used_catalog_rows(tmp_path):
    """a new library row a part doesn't name leaves its stage and frame hashes alone; one it names (directly, or a
    World Item its set places, or that item's prop) changes them"""
    from pipeline.scribble.io import save_object, save_prop, save_set
    from pipeline.scribble.schemas import CustomProp, CustomSet
    from pipeline.scribble.stages import shots as shots_stage
    from pipeline.scribble.stages.render import frames_hash
    from pipeline.scribble.stages.runner import inputs_hash
    from pipeline.tests.test_storycheck import setup
    part = setup(tmp_path, "@set lake\n@cast bob\nBob looked at the lake.\n")
    lake = CustomSet(id="lake", name="Lake", kind="outdoor", floor="#7a4fa3", back="#2fb3a0", water=False)
    save_set(tmp_path, lake)
    h = lambda: (inputs_hash(part, shots_stage.INPUTS), frames_hash(part))  # noqa: E731
    before = h()
    save_prop(tmp_path, CustomProp(id="spare-hat", name="Spare hat", shapes=[{"shape": "circle", "pts": [[0, 0]], "r": 9}]))
    save_set(tmp_path, CustomSet(id="desert", name="Desert", kind="outdoor", floor="#d9b36a", back="#9fd3f5"))
    save_prop(tmp_path, fx.GLOW)
    save_object(tmp_path, fx.CRYSTAL)
    assert h() == before  # nothing the part uses
    save_set(tmp_path, CustomSet(**{**lake.model_dump(), "objects": [{"id": "gem1", "object": "glow-crystal", "at": [3, 0, -3]}]}))
    placed = h()
    assert placed != before  # its set now places an item (and so the item and its prop count)
    save_prop(tmp_path, fx.GLOW.model_copy(update={"name": "Glow crystal 2"}))
    assert h() != placed  # the placed item's prop changed: the part's hash follows


def test_late_arrival_acts_in_the_next_shot():
    """a walk that arrives with less than ACT_ROOM of its shot left (and more line to come): that shot only walks
    (idle after arriving), the action plays whole in the line's next shot"""
    md = ("# L\n\n@set street\n@cast bob\n@item gem: glow-crystal stage left\nBob was alone on the street.\n"
          "@do bob: walk\nHe wandered off.\n@do bob: pickup gem\nThen he went back for the glowing crystal.\nDone.\n")
    ph = phrases_for(md, word_s=0.5)
    story = shots.plan(md, ph, SERIES, 1, objects=fx.OBJECTS)
    arrive = next(s for s in story.shots if actor(s).approach)
    a, nxt = actor(arrive), actor(story.shots[story.shots.index(arrive) + 1])
    assert a.action == "idle" and a.approach > 1 - shots.ACT_ROOM and a.item is None
    assert nxt.action == "pickup" and nxt.item == "gem" and nxt.approach is None
    assert nxt.start_pos[0] == a.end_pos[0]  # it picks up where the walk ended
    assert not validate(story, ph, {c.id for c in SERIES.cast})
