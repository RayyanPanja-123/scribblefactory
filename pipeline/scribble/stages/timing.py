"""timing: voice.mp3 + script-for-tts.txt -> phrases.json via local faster-whisper, aligned to the script.

Pauses between words longer than GAP_MAX are clamped to GAP_KEEP: voice-tight.wav is voice.mp3 with that silence
cut out (voice.mp3 is protected, never rewritten), and phrases.json is timed on voice-tight.wav. Later stages use it.
"""

import re
import shutil
import subprocess
import wave
from difflib import SequenceMatcher
from pathlib import Path

from ..io import atomic_write_json, load_series
from ..schemas import PhrasesModel
from .import_check import silences
from .prep import WPM
from .runner import StageError
from ..validate import SENTENCE_END, SIGN_OFF_PAUSE_S, is_final, sign_off

INPUTS = ["voice.mp3", "script-for-tts.txt"]
VOICE = "voice-tight.wav"   # the voice every later stage uses
OUTPUTS = ["phrases.json", VOICE]
MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "faster-whisper-base.en"
SAMPLE_RATE = 16000
PAUSE = 0.35            # seconds of gap that ends a phrase
MAX_WORDS = 7           # words per phrase before the limit forces a split...
BREAK_WINDOW = 3        # ...at the best break among the last this-many words of the phrase
HARD_MAX_WORDS = 9      # if no allowed break exists there, a phrase may grow to this many words
MIN_PHRASE_S = 0.5      # shorter phrases merge into a neighbour in the same sentence
CONJUNCTIONS = {"and", "but", "so", "while", "until", "which"}     # a forced split prefers to go before these
NO_BREAK_AFTER = {"a", "an", "the", "in", "on", "at", "of", "to", "by", "from", "with"}
MIN_MATCH = 0.85        # below this, the voice probably doesn't match the script
SECONDS_PER_WORD = 60 / WPM
GAP_MAX = 0.4           # a pause between words longer than this...
GAP_KEEP = 0.3          # ...is cut down to this (the middle of it is removed)


def norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def transcribe(voice: Path) -> tuple[list[tuple[str, float, float]], float]:
    """Return ([(word, start, end)], duration). Decodes with ffmpeg, never downloads a model."""
    if not (MODEL_DIR / "model.bin").exists():
        raise StageError(f"whisper model missing in {MODEL_DIR}: run setup.sh")
    if not shutil.which("ffmpeg"):
        raise StageError("ffmpeg not found on PATH")
    # Decode ourselves: faster-whisper's PyAV decoder breaks with newer PyAV versions.
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(voice), "-f", "f32le", "-ac", "1",
                        "-ar", str(SAMPLE_RATE), "-"], capture_output=True)
    if r.returncode != 0:
        raise StageError(f"ffmpeg could not decode voice.mp3: {r.stderr.decode(errors='replace').strip()[:300]}")
    import numpy as np  # heavy imports only when the stage actually runs
    from faster_whisper import WhisperModel

    audio = np.frombuffer(r.stdout, np.float32)
    model = WhisperModel(str(MODEL_DIR), device="cpu", compute_type="int8", local_files_only=True)
    segments, _ = model.transcribe(audio, language="en", word_timestamps=True)
    heard = [(w.word.strip(), w.start, w.end) for s in segments for w in s.words]
    return heard, len(audio) / SAMPLE_RATE


def align(script_words: list[str], heard: list[tuple[str, float, float]], duration: float):
    """Time each SCRIPT word from matching heard words; interpolate the rest. Returns (words, matched)."""
    a, b = [norm(w) for w in script_words], [norm(h[0]) for h in heard]
    times: list[tuple[float, float] | None] = [None] * len(a)
    for blk in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            if a[blk.a + k]:  # punctuation-only tokens like "-" don't count as a match
                times[blk.a + k] = heard[blk.b + k][1:]
    matched = sum(t is not None for t in times)
    if not matched:
        raise StageError("no script words were heard in voice.mp3")

    i, n = 0, len(times)
    while i < n:  # spread each run of unmatched words evenly over the gap between its neighbours
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < n and times[j] is None:
            j += 1
        count = j - i
        lo = times[i - 1][1] if i > 0 else None
        hi = times[j][0] if j < n else None
        if lo is None:
            lo = max(0.0, hi - count * SECONDS_PER_WORD)
        if hi is None:
            hi = min(duration, lo + count * SECONDS_PER_WORD)
        step = max(hi - lo, 0.0) / count
        for k in range(count):
            times[i + k] = (lo + k * step, lo + (k + 1) * step)
        i = j

    dur, prev, words = round(duration, 3), 0.0, []
    for text, (s, e) in zip(script_words, times):  # clamp: in range, no overlaps, ms precision
        s = round(min(max(s, prev), dur), 3)
        e = round(min(max(e, s), dur), 3)
        words.append({"text": text, "start": s, "end": e})
        prev = e
    return words, matched


def _capitalised(word: str) -> bool:
    letters = re.sub(r"^[^A-Za-z]+", "", word)
    return bool(letters) and letters[0].isupper()


def _can_break_after(words: list[dict], i: int) -> bool:
    """Never inside a name (two capitalised words) and never right after an article or preposition."""
    w, nxt = words[i]["text"], words[i + 1]["text"]
    return not (_capitalised(w) and _capitalised(nxt)) and norm(w) not in NO_BREAK_AFTER


def _forced_break(words: list[dict], a: int, b: int) -> int:
    """Last word of the phrase starting at a when the word limit forces a split inside a..b (b = segment end)."""
    def best(candidates):
        ok = [i for i in candidates if i < b and _can_break_after(words, i)]
        for prefer in (lambda i: words[i]["text"].endswith(","),           # after a comma
                       lambda i: norm(words[i + 1]["text"]) in CONJUNCTIONS):  # before a conjunction
            hits = [i for i in ok if prefer(i)]
            if hits:
                return max(hits)
        return max(ok) if ok else None   # else at the limit (or as close to it as allowed)

    limit = a + MAX_WORDS - 1
    cut = best(range(limit - BREAK_WINDOW + 1, limit + 1))
    if cut is None:
        cut = best(range(limit + 1, a + HARD_MAX_WORDS))
    return cut if cut is not None else min(a + HARD_MAX_WORDS - 1, b - 1)


def _ends_sentence(words: list[dict], i: int) -> bool:
    return bool(SENTENCE_END.search(words[i]["text"]))


def split_phrases(words: list[dict]) -> list[dict]:
    """Break after sentence punctuation and before a pause > PAUSE; split longer runs at natural breaks
    (MAX_WORDS, up to HARD_MAX_WORDS); then merge phrases shorter than MIN_PHRASE_S into the same sentence."""
    segments, first = [], 0
    for i, w in enumerate(words):
        if i == len(words) - 1 or _ends_sentence(words, i) or words[i + 1]["start"] - w["end"] > PAUSE:
            segments.append((first, i))
            first = i + 1
    spans = []
    for a, b in segments:
        while b - a + 1 > MAX_WORDS:
            cut = _forced_break(words, a, b)
            spans.append((a, cut))
            a = cut + 1
        spans.append((a, b))

    merged, carry = [], None  # carry: a short sentence-opening phrase waiting to join the next one
    for a, b in spans:
        if carry is not None:
            a, carry = carry, None
        short = words[b]["end"] - words[a]["start"] < MIN_PHRASE_S
        opens_sentence = a == 0 or _ends_sentence(words, a - 1)
        if short and not opens_sentence and merged:
            merged[-1] = (merged[-1][0], b)          # into the previous phrase of the same sentence
        elif short and not _ends_sentence(words, b) and b < len(words) - 1:
            carry = a                                # first of its sentence: into the next phrase
        else:
            merged.append((a, b))
    return [{"text": " ".join(x["text"] for x in words[a:b + 1]), "start": words[a]["start"], "end": words[b]["end"],
             "word_start": a, "word_end": b} for a, b in merged]


def gap_cuts(words: list[dict], quiet: list[tuple[float, float]] | None = None) -> list[tuple[float, float]]:
    """(start, end) spans to cut: the middle of every pause > GAP_MAX, leaving GAP_KEEP (half on each side).
    quiet: measured silences of the voice. Whisper often ends a word before its sound does, so with quiet given a
    cut only takes the middle of the longest silence inside the pause: a word's tail is never cut."""
    half, cuts = GAP_KEEP / 2, []
    for a, b in zip(words, words[1:]):
        lo, hi = a["end"], b["start"]
        if hi - lo <= GAP_MAX:
            continue
        if quiet is not None:
            spans = [(max(lo, s), min(hi, e)) for s, e in quiet if min(hi, e) > max(lo, s)]
            lo, hi = max(spans, key=lambda x: x[1] - x[0], default=(lo, lo))
            if hi - lo <= GAP_KEEP:
                continue
        cuts.append((round(lo + half, 3), round(hi - half, 3)))
    return cuts


def shift(t: float, cuts: list[tuple[float, float]]) -> float:
    """time t on the tightened voice (t is never inside a cut: cuts are in pauses)"""
    return round(t - sum(min(t, b) - a for a, b in cuts if t > a), 3)


def clamp_gaps(words: list[dict], phrases: list[dict], duration: float, quiet: list[tuple[float, float]] | None = None):
    """-> (words, phrases, duration, cuts) retimed for the voice with every pause > GAP_MAX clamped to GAP_KEEP
    (only its measured silence, when quiet is given: see gap_cuts)"""
    cuts = gap_cuts(words, quiet)
    move = lambda xs: [{**x, "start": shift(x["start"], cuts), "end": shift(x["end"], cuts)} for x in xs]  # noqa: E731
    return move(words), move(phrases), shift(duration, cuts), cuts


def sign_off_pause(words: list[dict], quiet: list[tuple[float, float]]) -> float | None:
    """where to stretch the pause before the sign-off (validate.sign_off), on the untightened voice: the middle of
    the longest silence between it and the sentence before (a cut there joins two silences, so it stays silent)"""
    i = sign_off([w["text"] for w in words])
    if i is None:
        return None
    lo, hi = words[i - 1]["end"], words[i]["start"]
    spans = [(max(lo, s), min(hi, e)) for s, e in quiet if min(hi, e) > max(lo, s)]
    a, b = max(spans, key=lambda x: x[1] - x[0], default=(lo, hi))
    return (a + b) / 2


def add_pause(words: list[dict], phrases: list[dict], duration: float, at: float):
    """-> (words, phrases, duration, seconds added): the pause holding `at` (tight-voice time) grown to
    SIGN_OFF_PAUSE_S; everything from `at` on moves later"""
    nxt = next(w for w in words if w["start"] >= at)
    prev = max((w["end"] for w in words if w["end"] <= at), default=0.0)
    extra = round(max(0.0, SIGN_OFF_PAUSE_S - (nxt["start"] - prev)), 3)
    move = lambda t: round(t + extra, 3) if t >= at else t  # noqa: E731
    bump = lambda xs: [{**x, "start": move(x["start"]), "end": move(x["end"])} for x in xs]  # noqa: E731
    return bump(words), bump(phrases), round(duration + extra, 3), extra


def tighten(voice: Path, out: Path, cuts: list[tuple[float, float]], pause: tuple[float, float] | None = None) -> None:
    """voice with the cut spans removed (+ pause: (at, seconds) of silence inserted, tight-voice time)
    -> 48 kHz 16-bit WAV (written atomically)"""
    keep = "+".join(f"between(t,{a},{b})" for a, b in cuts)
    af = ["-af", f"aselect='not({keep})',asetpts=N/SR/TB"] if cuts else []
    tmp = out.with_name(f".{out.name}.tmp.wav")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(voice), *af, "-ar", "48000", "-ac", "2",
                        "-c:a", "pcm_s16le", str(tmp)], capture_output=True)
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise StageError(f"ffmpeg could not write {out.name}: {r.stderr.decode(errors='replace').strip()[:300]}")
    if pause and pause[1] > 0:
        with wave.open(str(tmp), "rb") as f:
            params, pcm = f.getparams(), f.readframes(f.getnframes())
        size = params.sampwidth * params.nchannels
        k = min(round(pause[0] * params.framerate) * size, len(pcm))
        with wave.open(str(tmp), "wb") as f:
            f.setparams(params)
            f.writeframes(pcm[:k] + bytes(round(pause[1] * params.framerate) * size) + pcm[k:])
    tmp.replace(out)


def run(part_dir: Path) -> None:
    voice, script = part_dir / "voice.mp3", part_dir / "script-for-tts.txt"
    if not voice.exists():
        raise StageError("voice.mp3 not found")
    if not script.exists():
        raise StageError("script-for-tts.txt not found (run prep)")
    script_words = script.read_text(encoding="utf-8").split()
    if not script_words:
        raise StageError("script-for-tts.txt is empty")

    heard, duration = transcribe(voice)
    words, matched = align(script_words, heard, duration)
    phrases = split_phrases(words)  # on the real pauses: clamped ones would no longer end a phrase
    quiet = silences(voice, duration, min_len=GAP_KEEP)
    series = part_dir.parent / "series.json"  # none (a bare part): no sign-off pause
    at = None if not series.exists() or is_final(load_series(series), part_dir.name) else sign_off_pause(words, quiet)
    words, phrases, duration, cuts = clamp_gaps(words, phrases, round(duration, 3), quiet)
    pause = None
    if at is not None:
        at = shift(at, cuts)
        words, phrases, duration, extra = add_pause(words, phrases, duration, at)
        pause = (at, extra)
        print(f"sign-off pause: +{extra:.2f} s at {at:.2f} s")
    model = PhrasesModel(duration=duration, words=words, phrases=phrases)  # validates times
    tighten(voice, part_dir / VOICE, cuts, pause)
    atomic_write_json(part_dir / "phrases.json", model.model_dump(mode="json"))
    print(f"pauses clamped: {len(cuts)}, {sum(b - a for a, b in cuts):.1f} s cut")

    rate = matched / len(script_words)
    print(f"words: {len(words)}, match rate: {rate:.0%}, phrases: {len(phrases)}")
    if rate < MIN_MATCH:
        print(f"warning: only {rate:.0%} of script words heard (< {MIN_MATCH:.0%}); voice may not match script")
