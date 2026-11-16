import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.scribble.io import load_part, save_part
from pipeline.scribble.schemas import PartModel, PhrasesModel
from pipeline.scribble.stages import timing
from pipeline.scribble.stages.runner import StageError, run_stage
from pipeline.scribble.stages.timing import align, split_phrases

FIXTURE = Path(__file__).parent / "fixtures" / "hello.wav"


def heard(*words, gap=0.0, dur=0.3):
    """Fake Whisper output: consecutive words, each `dur` long, separated by `gap`."""
    out, t = [], 0.0
    for w in words:
        out.append((w, t, t + dur))
        t += dur + gap
    return out


def times(words):
    return [(w["start"], w["end"]) for w in words]


# --- alignment ---

def test_align_exact_match_uses_script_text():
    words, matched = align(["Hello,", "Bob's", "stapler."], heard("hello", "Bobs", "Stapler"), 5)
    assert matched == 3
    assert [w["text"] for w in words] == ["Hello,", "Bob's", "stapler."]
    assert times(words) == [(0.0, 0.3), (0.3, 0.6), (0.6, 0.9)]


def test_align_missing_word_is_interpolated():
    # "red" not heard: it gets the gap between "the" (ends 0.6) and "stapler" (starts 1.0)
    h = [("wanted", 0.0, 0.3), ("the", 0.3, 0.6), ("stapler", 1.0, 1.4)]
    words, matched = align(["wanted", "the", "red", "stapler"], h, 5)
    assert matched == 3
    assert times(words) == [(0.0, 0.3), (0.3, 0.6), (0.6, 1.0), (1.0, 1.4)]


def test_align_extra_heard_word_is_ignored():
    words, matched = align(["he", "waited"], heard("he", "um", "waited"), 5)
    assert matched == 2
    assert [w["text"] for w in words] == ["he", "waited"]
    assert times(words) == [(0.0, 0.3), (0.6, 0.9)]


def test_align_interpolates_run_and_edges():
    h = [("b", 1.0, 1.2), ("e", 2.0, 2.2)]
    words, matched = align(["a", "b", "c", "d", "e", "f"], h, 10)
    assert matched == 2
    t = times(words)
    assert t[0] == (0.6, 1.0)                     # leading: one word-length (0.4 s) before "b"
    assert t[2] == (1.2, 1.6) and t[3] == (1.6, 2.0)  # split the 1.2-2.0 gap evenly
    assert t[5] == (2.2, 2.6)                     # trailing: one word-length after "e"


def test_align_clamps_overlap_and_duration():
    h = [("a", 0.0, 0.5), ("b", 0.4, 0.9), ("c", 2.9, 3.4)]  # b overlaps a, c runs past duration
    words, _ = align(["a", "b", "c"], h, 3.0)
    assert times(words) == [(0.0, 0.5), (0.5, 0.9), (2.9, 3.0)]
    PhrasesModel(duration=3.0, words=words, phrases=split_phrases(words))


def test_align_nothing_heard_fails():
    with pytest.raises(StageError):
        align(["hello"], heard("goodbye"), 5)


# --- phrases ---

def w(text, start, end):
    return {"text": text, "start": start, "end": end}


def test_split_on_sentence_punctuation():
    words = [w("Hi.", 0, 0.2), w("Bob", 0.2, 0.4), w("ran!", 0.4, 0.6), w('"Why?"', 0.6, 0.8), w("ok", 0.8, 1)]
    assert [p["text"] for p in split_phrases(words)] == ["Hi.", "Bob ran!", '"Why?"', "ok"]


def test_split_on_pause():
    words = [w("a", 0, 0.2), w("b", 0.2, 0.4), w("c", 0.76, 0.9), w("d", 1.2, 1.3)]  # gaps .36 then .30
    ps = split_phrases(words)
    assert [p["text"] for p in ps] == ["a b", "c d"]
    assert ps[1] == {"text": "c d", "start": 0.76, "end": 1.3, "word_start": 2, "word_end": 3}


def test_split_max_seven_words():
    words = [w(str(i), i * 0.1, i * 0.1 + 0.1) for i in range(16)]
    assert [len(p["text"].split()) for p in split_phrases(words)] == [7, 7, 2]


# --- schema ---

def phrases_doc(**over):
    d = {"duration": 2.0,
         "words": [w("a", 0.0, 0.5), w("b", 0.5, 1.0)],
         "phrases": [{"text": "a b", "start": 0.0, "end": 1.0, "word_start": 0, "word_end": 1}]}
    d.update(over)
    return d


def test_schema_valid():
    PhrasesModel.model_validate(phrases_doc())


@pytest.mark.parametrize("over", [
    {"words": [w("a", 0.0, 0.6), w("b", 0.5, 1.0)]},             # overlap
    {"words": [w("a", 0.5, 0.4), w("b", 0.5, 1.0)]},             # end before start
    {"words": [w("a", 0.0, 0.5), w("b", 0.5, 2.5)]},             # past duration
    {"words": [w("a", -0.1, 0.5), w("b", 0.5, 1.0)]},            # negative
    {"phrases": [{"text": "a", "start": 0, "end": 0.5, "word_start": 0, "word_end": 0}]},  # word b uncovered
    {"phrases": [{"text": "b", "start": 0.5, "end": 1, "word_start": 1, "word_end": 1}]},  # gap at start
    {"extra": 1},
])
def test_schema_invalid(over):
    with pytest.raises(ValidationError):
        PhrasesModel.model_validate(phrases_doc(**over))


# --- stage ---

@pytest.fixture
def part(tmp_path):
    d = tmp_path / "part-01"
    d.mkdir()
    save_part(d / "part.json", PartModel(id="part-01", number=1, title="T"))
    return d


def run(part):
    return run_stage(part, "timing", timing.run, inputs=timing.INPUTS, outputs=timing.OUTPUTS)


def test_missing_model_fails_clearly(part, monkeypatch):
    (part / "voice.mp3").write_bytes(b"x")
    (part / "script-for-tts.txt").write_text("hello\n")
    monkeypatch.setattr(timing, "MODEL_DIR", part / "no-model")
    assert run(part) == "failed"
    assert "run setup.sh" in load_part(part / "part.json").stages.timing.error


@pytest.mark.skipif(not (timing.MODEL_DIR / "model.bin").exists(), reason="whisper model not downloaded")
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")
def test_timing_real_model(part, capsys):
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(FIXTURE), str(part / "voice.mp3")], check=True)
    # "big" replaces "red" (not heard -> interpolated)
    (part / "script-for-tts.txt").write_text(
        "Hello there. Bob wanted the big stapler.\n\nHe waited until lunch, then he made his move.\n")
    voice = (part / "voice.mp3").read_bytes()
    assert run(part) == "done"
    doc = PhrasesModel.model_validate_json((part / "phrases.json").read_bytes())
    assert [x.text for x in doc.words][:3] == ["Hello", "there.", "Bob"]
    assert [p.text for p in doc.phrases][:2] == ["Hello there.", "Bob wanted the big stapler."]
    assert 6 < doc.duration < 9
    out = capsys.readouterr().out
    assert "words: 16, match rate: 94%" in out and "warning" not in out
    assert run(part) == "skipped"
    assert (part / "voice.mp3").read_bytes() == voice
    assert json.loads((part / "phrases.json").read_text())["schema_version"] == 1
