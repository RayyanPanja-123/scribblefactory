"""Story quirks: several @do lines before one narration line, walk words, walks over several shots of one sentence.
(Item fly speed: test_items.test_fly_speed_cap_and_tokens.)"""

import pytest

from pipeline.scribble.stages import shots
from pipeline.scribble.stages.runner import StageError
from pipeline.scribble.validate import validate
from pipeline.tests import items_fixture as fx
from pipeline.tests.test_shots import SERIES, phrases_for


def plan(md, notes=None, word_s=0.4):
    ph = phrases_for(md, word_s)
    from pipeline.tests.test_items import SAUCER
    return shots.plan(md, ph, SERIES, 1, objects={**fx.OBJECTS, "saucer": SAUCER}, notes=notes), ph


def actor(shot, cid):
    return next(a for a in shot.actors if a.cast_id == cid)


# --- 1: several @do before one line all apply; the same target twice is an error ---

def test_separate_do_lines_for_different_targets_all_apply():
    md = "# M\n\n@set street\n@cast bob, amy\n@item ship: saucer\n@do bob: wave\n@do amy: point\n@do ship: fly left\nLook up.\n"
    story, ph = plan(md)
    s = story.shots[0]
    assert (actor(s, "bob").action, actor(s, "amy").action) == ("wave", "point")
    assert s.items[0].end_pos is not None  # the ship flies too
    assert not validate(story, ph, {c.id for c in SERIES.cast})


def test_two_do_lines_for_one_target_is_an_error():
    with pytest.raises(StageError, match="two @do for bob on one line"):
        plan("# M\n\n@set street\n@cast bob\n@do bob: wave\n@do bob: point\nHi.\n")


def test_storycheck_reports_two_do_for_one_target(tmp_path):
    from pipeline.scribble.storycheck import check_story
    from pipeline.tests.test_storycheck import setup
    part = setup(tmp_path, "@set street\n@cast bob, amy\n@do bob: wave\n@do amy: point\nHi.\n@do bob: wave\n@do bob: point\nAgain.\n")
    msgs = [(p["line"], p["message"]) for p in check_story(part)["problems"]]
    assert any(no == 7 and "two @do for bob on one line" in m for no, m in msgs), msgs
    assert not any(no in (3, 4) for no, _ in msgs)  # different targets: fine


# --- 2: walk words ---

def test_walk_word_moves_only_a_named_character():
    notes = []
    story, _ = plan("# N\n\n@set office\n@cast bob\nBob came home.\nThe saucer came back.\n", notes)
    assert actor(story.shots[0], "bob").action == "walk"  # named: walks, no note (the story asked for it)
    assert actor(story.shots[-1], "bob").action != "walk"  # names nobody: moves nobody
    assert notes == []


def test_pronoun_walk_warns_and_explicit_idle_stops_it():
    notes = []
    md = "# W\n\n@set office\n@cast bob\nBob sat.\nHe came home.\n@do bob: idle\nHe came back again.\n"
    story, _ = plan(md, notes)
    assert actor(story.shots[1], "bob").action == "walk"  # the pronoun points back at bob
    assert notes == [(6, "'came' starts a walk for bob; add @do bob: idle to stop it")]
    assert actor(story.shots[-1], "bob").action == "idle"  # the explicit @do wins, and no note for line 8


def test_unnamed_walk_word_outdoors_is_no_travel_shot():
    notes = []
    story, _ = plan("# T\n\n@set street\n@cast bob\nThe saucer came back.\nThen he came back too.\n", notes)
    assert story.shots[0].travel is None
    assert story.shots[-1].travel is not None
    assert notes and "starts a travel shot for bob" in notes[0][1]


def test_no_walk_word_walk_while_seated():
    md = ("# S\n\n@set street\n@cast bob\n@item b: bench\nA bench.\n@do bob: sit b\nHe sat down.\n"
          "Then he walked off in his mind.\n")
    story, _ = plan(md)
    assert actor(story.shots[-1], "bob").action == "sit"  # still seated: 'walked' moves nobody


# --- 3: a sentence's walk over several shots keeps going the same way ---

def test_walk_over_several_shots_never_turns_back():
    md = "# C\n\n@set office\n@cast bob\n@do bob: walk\nBob walked slowly along the long hall, past every single door, all the way.\n"
    story, ph = plan(md, word_s=0.6)
    walks = [actor(s, "bob") for s in story.shots if actor(s, "bob").action == "walk"]
    assert len(story.shots) > 1 and walks
    ways = {1 if a.end_pos[0] > a.start_pos[0] else -1 for a in walks}
    assert len(ways) == 1  # one direction for the whole sentence
    assert not validate(story, ph, {c.id for c in SERIES.cast})
