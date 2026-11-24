"""World Items: the schema (card items, reserved states, rows that keep their bytes), @item / @do <item>: fly in the
shot planner and check-story."""

import json

import pytest

from pipeline.scribble.schemas import CustomSet, StoryModel, WorldObject, WorldObjectInstance
from pipeline.scribble.stages import shots
from pipeline.scribble.stages.prep import parse_item
from pipeline.scribble.stages.runner import StageError
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
