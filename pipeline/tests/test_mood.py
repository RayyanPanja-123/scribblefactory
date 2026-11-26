"""@mood: parsing, persistence (until @mood / @set), the shot field (left out of story.json when neutral)."""
import pytest

from pipeline.scribble.stages import shots
from pipeline.scribble.stages.prep import parse_mood
from pipeline.scribble.stages.runner import StageError
from pipeline.tests.test_shots import SERIES, phrases_for


def test_parse_mood():
    assert parse_mood("tense", 1) == "tense"
    assert parse_mood(" flashback ", 1) == "flashback"
    assert parse_mood("off", 1) is None
    for bad in ("", "sad", "Dark", "dark bright"):
        with pytest.raises(StageError, match="story.md line 5: bad directive @mood"):
            parse_mood(bad, 5)


def test_mood_persists_until_mood_or_set():
    md = "# T\n\n@set street\n@mood dark\nOne.\nTwo.\n@mood bright\nThree.\n@set kitchen\nFour.\n@mood tense\nFive.\n@mood off\nSix.\n"
    _, tags = shots.tag_words(md, ["bob"], ["bob"])
    assert [t.mood for t in tags] == ["dark", "dark", "bright", None, "tense", None]


def test_plan_carries_mood_and_omits_it_when_neutral():
    md = "# T\n\n@set kitchen\n@cast bob\nBob came in.\n@mood tense\nBob froze.\n"
    story = shots.plan(md, phrases_for(md), SERIES, 1)
    assert [s.mood for s in story.shots] == [None, "tense"]
    dumped = story.model_dump(mode="json")["shots"]
    assert "mood" not in dumped[0] and dumped[1]["mood"] == "tense"


def test_a_bad_mood_fails_the_plan():
    with pytest.raises(StageError, match="line 4: bad directive @mood sad"):
        shots.tag_words("# T\n\n@set kitchen\n@mood sad\nBob sat.\n", ["bob"], ["bob"])
