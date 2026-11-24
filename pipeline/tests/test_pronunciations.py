import pytest
from pydantic import ValidationError

from pipeline.scribble.schemas.series import Voice
from pipeline.scribble.stages.prep import respell
from pipeline.scribble.stages.timing import caption_words

SAY = {"Negro": "Neh-groh"}


def test_respell_whole_words_case_sensitive_keeps_punctuation():
    assert respell("El Charro Negro rides. Negro!", SAY) == "El Charro Neh-groh rides. Neh-groh!"
    assert respell("negro Negroes Negro-ish", SAY) == "negro Negroes Negro-ish"


def test_respelling_must_be_one_token():
    with pytest.raises(ValidationError):
        Voice(voice_name="", pronunciations={"Negro": "Neh groh"})


def test_timing_captions_story_words_only_when_counts_match():
    timed = [{"text": "Charro", "start": 0, "end": 1}, {"text": "Neh-groh.", "start": 1, "end": 2}]
    assert [w["text"] for w in caption_words(timed, ["Charro", "Negro."])] == ["Charro", "Negro."]
    assert caption_words(timed, ["Charro"]) == timed
