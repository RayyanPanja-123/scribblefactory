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


def test_align_misheard_word_keeps_heard_time():
    # "Four" heard as "For" after a silence: it takes For's time, not the silent gap after "milk."
    h = [("milk", 2.5, 2.8), ("For", 4.1, 4.18), ("dollars", 4.18, 4.44)]
    words, matched = align(["milk.", "Four", "dollars,"], h, 6)
    assert matched == 2
    assert times(words)[1] == (4.1, 4.18)


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
    words = [w("a", 0, 0.3), w("b", 0.3, 0.6), w("c", 0.96, 1.2), w("d", 1.5, 1.8)]  # gaps .36 then .30
    ps = split_phrases(words)
    assert [p["text"] for p in ps] == ["a b", "c d"]
    assert ps[1] == {"text": "c d", "start": 0.96, "end": 1.8, "word_start": 2, "word_end": 3}


def said(text: str, word_s: float = 0.3) -> list[dict]:
    """words of one breath: each word_s long, 0.05 s apart (no pauses)"""
    return [w(t, round(i * (word_s + 0.05), 3), round(i * (word_s + 0.05) + word_s, 3)) for i, t in enumerate(text.split())]


def texts(text: str, word_s: float = 0.3) -> list[str]:
    return [p["text"] for p in split_phrases(said(text, word_s))]


def test_split_max_seven_words():
    words = [w(str(i), i * 0.35, i * 0.35 + 0.3) for i in range(16)]
    assert [len(p["text"].split()) for p in split_phrases(words)] == [7, 7, 2]


def test_forced_split_never_inside_a_name():
    # limit falls between "Fred" and "Lorz": break before the name instead
    assert texts("Up at the front American runner Fred Lorz collapsed from exhaustion at mile nine.") == [
        "Up at the front American runner", "Fred Lorz collapsed from exhaustion at mile nine."]
    # limit on "Louis": breaking after it is allowed and keeps the name whole
    assert texts("one two three four five Saint Louis was hot and dry.") == [
        "one two three four five Saint Louis", "was hot and dry."]


def test_forced_split_never_after_article_or_preposition():
    # "until his manager pulled up in a car and offered him a lift." used to split as "... in a / car ..."
    out = texts("until his manager pulled up in a car and offered him a lift.")
    assert out == ["until his manager pulled up", "in a car and offered him", "a lift."]
    for phrase in out[:-1]:
        assert phrase.split()[-1].lower() not in {"a", "an", "the", "in", "on", "at", "of", "to", "by", "from", "with"}


def test_forced_split_prefers_comma_then_conjunction():
    assert texts("Halfway through, a runner from far away was chased off course.") == [
        "Halfway through, a runner from far away", "was chased off course."]  # limit is fine: no comma late
    assert texts("one two three four five, six seven eight nine ten.") == ["one two three four five,", "six seven eight nine ten."]
    assert texts("one two three four five six but seven eight nine.") == ["one two three four five six", "but seven eight nine."]


def test_nine_word_cap_when_no_allowed_break():
    # words 5..9 are all capitalised: no allowed break from word 5 to 9, so the phrase is cut at 9 words
    out = texts("one two three four Ann Bea Cal Dan Eve Fay Gus Hal.")
    assert [len(p.split()) for p in out] == [9, 3]
    # an allowed break past the limit (within 9 words) is used before the hard cap
    assert [len(p.split()) for p in texts("one two three four five Ann Bea Cal went home.")] == [5, 5]


def test_short_phrase_merges_into_previous_of_same_sentence():
    words = said("Another runner lay down under an oak tree, and took a forty-five-minute") + [w("nap.", 4.6, 4.9)]
    ps = split_phrases(words)
    assert ps[-1]["text"].endswith("forty-five-minute nap.") and ps[-1]["end"] == 4.9
    assert all(p["end"] - p["start"] >= 0.5 for p in ps)


def test_short_phrase_opening_a_sentence_merges_into_next():
    words = [w("Done.", 0.0, 0.6), w("So", 1.0, 1.2), w("then", 1.6, 1.9), w("we", 1.95, 2.2), w("left.", 2.25, 2.6)]
    assert [p["text"] for p in split_phrases(words)] == ["Done.", "So then we left."]  # "So" (0.2 s, pause after)


def test_short_single_phrase_sentence_stays():
    words = [w("Hi.", 0.0, 0.2), w("Then", 0.6, 0.9), w("we", 0.95, 1.2), w("left.", 1.25, 1.6)]
    assert [p["text"] for p in split_phrases(words)] == ["Hi.", "Then we left."]


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
    from pipeline.scribble.stages.import_check import probe_duration
    assert abs(probe_duration(part / timing.VOICE) - doc.duration) < 0.05  # the tight voice is what was timed


# --- pause clamping ---

def test_clamp_gaps_cuts_long_pauses_to_gap_keep():
    words = [w("a", 0.0, 0.5), w("b", 0.8, 1.2), w("c", 2.2, 2.5), w("d", 2.9, 3.0), w("e", 5.0, 5.5)]
    phrases = [{"text": "a b", "start": 0.0, "end": 1.2, "word_start": 0, "word_end": 1},
               {"text": "c d e", "start": 2.2, "end": 5.5, "word_start": 2, "word_end": 4}]
    out_w, out_p, dur, cuts = timing.clamp_gaps(words, phrases, 6.0)
    # 0.3 kept as is, 1.0 -> 0.3, 0.4 is not over GAP_MAX: kept, 2.0 -> 0.3
    assert cuts == [(1.35, 2.05), (3.15, 4.85)]
    assert [(x["start"], x["end"]) for x in out_w] == [(0.0, 0.5), (0.8, 1.2), (1.5, 1.8), (2.2, 2.3), (2.6, 3.1)]
    assert [(p["start"], p["end"]) for p in out_p] == [(0.0, 1.2), (1.5, 3.1)]
    assert dur == 3.6  # 6.0 - 0.7 - 1.7
    gaps = [b["start"] - a["end"] for a, b in zip(out_w, out_w[1:])]
    assert max(gaps) <= timing.GAP_MAX + 1e-9


def test_cuts_stay_inside_measured_silence():
    # whisper ends "a" at 0.5 but it sounds until 1.1; "c" starts at 3.0 but the pause before it is never quiet
    words = [w("a", 0.0, 0.5), w("b", 2.0, 2.2), w("c", 3.0, 3.2)]
    assert timing.gap_cuts(words, quiet=[(1.1, 2.0)]) == [(1.25, 1.85)]  # not from 0.65: the word's tail stays


def test_clamp_gaps_no_long_pause_changes_nothing():
    words = [w("a", 0.0, 0.5), w("b", 0.9, 1.2)]
    assert timing.clamp_gaps(words, [], 1.5) == (words, [], 1.5, [])


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")
def test_tighten_removes_the_cut_audio(tmp_path):
    from pipeline.scribble.stages.import_check import probe_duration
    src = tmp_path / "v.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=4", str(src)], check=True)
    timing.tighten(src, tmp_path / "t.wav", [(1.0, 1.5), (2.0, 2.7)])
    assert abs(probe_duration(tmp_path / "t.wav") - (probe_duration(src) - 1.2)) < 0.03
