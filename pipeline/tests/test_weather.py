"""@weather and @fx lightning: parsing, persistence, set defaults, strike timing and targets, story check."""
import pytest

from pipeline.scribble.io import save_set, set_weather
from pipeline.scribble.schemas import CustomSet, SeriesModel, Weather
from pipeline.scribble.stages import shots
from pipeline.scribble.stages.prep import parse_lightning, parse_weather
from pipeline.scribble.stages.runner import StageError
from pipeline.scribble.storycheck import check_story
from pipeline.scribble.validate import validate
from pipeline.tests.test_shots import SERIES, phrases_for
from pipeline.tests.test_storycheck import KITCHEN, setup

W = lambda kind, intensity="medium": Weather(kind=kind, intensity=intensity)


def test_parse_weather():
    assert parse_weather("storm heavy", 1) == W("storm", "heavy")
    assert parse_weather("fog", 1) == W("fog")  # default medium
    assert parse_weather("clear", 1) is None
    for bad in ("", "hail", "rain extreme", "clear light", "rain light heavy", "Rain"):
        with pytest.raises(StageError, match="story.md line 7: bad directive @weather"):
            parse_weather(bad, 7)


def test_parse_lightning():
    assert parse_lightning("lightning", 1) is None
    assert parse_lightning("lightning bob", 1, ["bob"]) == "bob"
    assert parse_lightning("lightning apple", 1, ["bob"], ("apple",)) == "apple"
    for bad in ("lightning bob amy", "lightningx"):
        with pytest.raises(StageError, match="line 4"):
            parse_lightning(bad, 4, ["bob"])
    with pytest.raises(StageError, match="neither a cast id"):
        parse_lightning("lightning zeus", 4, ["bob"])


def test_weather_persists_until_weather_or_set():
    md = ("# T\n\n@set street\n@weather rain heavy\nOne.\nTwo.\n@weather snow\nThree.\n@set kitchen\nFour.\n"
          "@set street\nFive.\n@weather clear\nSix.\n")
    words, tags = shots.tag_words(md, ["bob"], ["bob"], weather_of={"kitchen": W("fog", "light")})
    assert [t.weather for t in tags] == [W("rain", "heavy"), W("rain", "heavy"), W("snow"), W("fog", "light"), None, None]
    assert words == ["One.", "Two.", "Three.", "Four.", "Five.", "Six."]


def test_plan_weather_set_default_and_strikes():
    series = SeriesModel.model_validate({**SERIES.model_dump(), "cast": [
        {**c.model_dump(), "props": [{"kind": "apple"}] if c.id == "amy" else []} for c in SERIES.cast]})
    md = ("# T\n\n@set kitchen\n@cast bob, amy\nBob walked in.\n@weather storm heavy\n@fx lightning\nThe sky cracked.\n"
          "@fx lightning apple\nAmy screamed.\n@fx lightning bob\nBob fell.\n")
    ph = phrases_for(md)
    story = shots.plan(md, ph, series, 1, weather_of={"kitchen": W("fog")})
    by_text = {ph.phrases[s.phrase_range[0]].text: s.weather for s in story.shots}
    assert by_text == {"Bob walked in.": W("fog"), "The sky cracked.": W("storm", "heavy"),
                       "Amy screamed.": W("storm", "heavy"), "Bob fell.": W("storm", "heavy")}
    # each strike on the first word of the line after it; a prop target becomes whoever holds it
    firsts = [w.start for w in ph.words if w.text in ("The", "Amy", "Bob") and w.start > 0.2]
    assert [(k.frame, k.target) for k in story.lightning] == [(round(t * 30), who) for t, who in
                                                                zip(firsts, (None, "amy", "bob"))]
    assert validate(story, ph, {c.id for c in series.cast}) == []
    with pytest.raises(StageError, match="line 4: @fx lightning: karen is not on stage"):
        md2 = "# T\n\n@cast bob\n@fx lightning karen\nBob ran.\n"
        shots.plan(md2, phrases_for(md2), SERIES, 1)
    with pytest.raises(StageError, match="nobody on stage holds apple"):
        md2 = "# T\n\n@cast bob\n@fx lightning apple\nBob ran.\n"
        shots.plan(md2, phrases_for(md2), SERIES, 1)


def test_validator_checks_strike_target():
    md = "# T\n\n@cast bob\n@fx lightning bob\nBob ran.\n"
    ph = phrases_for(md)
    story = shots.plan(md, ph, SERIES, 1)
    story.lightning[0].target = "amy"
    assert [e.rule for e in validate(story, ph, {"bob", "amy"})] == ["lightning"]


def test_set_default_weather_saved(tmp_path):
    save_set(tmp_path, CustomSet.model_validate({**KITCHEN, "default_weather": {"kind": "snow", "intensity": "light"}}))
    assert set_weather(tmp_path) == {"kitchen": W("snow", "light")}
    with pytest.raises(ValueError):
        CustomSet.model_validate({**KITCHEN, "default_weather": {"kind": "hail"}})


def test_story_check(tmp_path):
    ok = setup(tmp_path, "# T\n\n@set office\n@cast bob\n@weather storm heavy\n@fx lightning bob\nBob ran.\n")
    assert check_story(ok)["problems"] == []
    story = ("# T\n\n@set office\n@cast bob\n@weather hail\n@weather rain heavy extra\n"
             "@fx lightning amy\nBob ran.\n@fx lightning\nOne.\n@fx lightning\nTwo.\n@fx lightning\n@fx lightning\n"
             "Three.\n@fx lightning\n")
    (ok / "story.md").write_text(story, encoding="utf-8")
    got = [(p["line"], p["message"].split(" (")[0]) for p in check_story(ok)["problems"]]
    assert got == [(5, "bad directive @weather hail"), (6, "bad directive @weather rain heavy extra"),
                   (7, "@fx lightning: amy is not on stage on the next line"),
                   (13, "@fx lightning: at most 3 per part"),  # the fourth strike
                   (13, "@fx lightning is replaced by the one on line 14 before any text line uses it"),
                   (16, "@fx lightning has no text line after it to strike on")]
