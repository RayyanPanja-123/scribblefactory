"""timing: voice.mp3 + script-for-tts.txt -> phrases.json via local faster-whisper, aligned to the script."""

import re
import shutil
import subprocess
from difflib import SequenceMatcher
from pathlib import Path

from ..io import atomic_write_json
from ..schemas import PhrasesModel
from .prep import WPM
from .runner import StageError

INPUTS = ["voice.mp3", "script-for-tts.txt"]
OUTPUTS = ["phrases.json"]
MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "faster-whisper-base.en"
SAMPLE_RATE = 16000
PAUSE = 0.35            # seconds of gap that ends a phrase
MAX_WORDS = 7           # words per phrase
MIN_MATCH = 0.85        # below this, the voice probably doesn't match the script
SECONDS_PER_WORD = 60 / WPM
SENTENCE_END = re.compile(r"[.!?…][\"')\]]*$")


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


def split_phrases(words: list[dict]) -> list[dict]:
    """Break after sentence punctuation, before a pause > PAUSE, or at MAX_WORDS."""
    phrases, first = [], 0
    for i, w in enumerate(words):
        last = i == len(words) - 1
        if (last or SENTENCE_END.search(w["text"]) or i - first + 1 >= MAX_WORDS
                or words[i + 1]["start"] - w["end"] > PAUSE):
            chunk = words[first:i + 1]
            phrases.append({"text": " ".join(x["text"] for x in chunk), "start": chunk[0]["start"],
                            "end": chunk[-1]["end"], "word_start": first, "word_end": i})
            first = i + 1
    return phrases


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
    phrases = split_phrases(words)
    model = PhrasesModel(duration=round(duration, 3), words=words, phrases=phrases)  # validates times
    atomic_write_json(part_dir / "phrases.json", model.model_dump(mode="json"))

    rate = matched / len(script_words)
    print(f"words: {len(words)}, match rate: {rate:.0%}, phrases: {len(phrases)}")
    if rate < MIN_MATCH:
        print(f"warning: only {rate:.0%} of script words heard (< {MIN_MATCH:.0%}); voice may not match script")
