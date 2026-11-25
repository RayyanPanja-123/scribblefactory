"""tts: voice_source tts only. script-for-tts.txt, one Kokoro clip per story.md line (pronunciations already applied),
joined with settings tts_line_gap of silence -> voice.mp3, as if it had been uploaded: every later stage runs as for a
recorded voice. voice-tts.json lists the lines, voices and clip times.

A recorded part: nothing to do. A voice.mp3 this stage did not make (a recording) is moved to voice-recorded.mp3
first, never overwritten. The clips are all fetched (into the cache) before the part folder is touched: a server that
is down leaves the part as it was."""

import hashlib
import json
import os
from pathlib import Path

from .. import ff, tts
from ..io import atomic_write_json, library_of, load_part, load_series, part_exists, series_exists
from .prep import speakers, voice_marks
from .runner import StageError

INPUTS = ["script-for-tts.txt", "story.md"]
OUTPUTS = ["voice.mp3"]
MANIFEST = "voice-tts.json"
RECORDED = "voice-recorded.mp3"
MP3_ARGS = ["-c:a", "libmp3lame", "-b:a", "128k", "-map_metadata", "-1", "-id3v2_version", "0"]


def is_tts(part_dir: Path) -> bool:
    return part_exists(part_dir) and load_part(part_dir / "part.json").voice_source == "tts"


def narrator(part_dir: Path) -> tuple[str, float]:
    """(voice id, speed): the series' voice.tts, else settings tts_voice at speed 1"""
    v = load_series(part_dir.parent / "series.json").voice.tts if series_exists(part_dir.parent) else None
    if v:
        return v.id, v.speed
    from .. import settings
    return settings.load(library_of(part_dir))["tts_voice"], 1.0


def cast_voices(part_dir: Path) -> dict[str, tuple[str, float]]:
    """cast id -> (voice id, speed) for the cast members with a TTS voice"""
    if not series_exists(part_dir.parent):
        return {}
    return {c.id: (c.voice.id, c.voice.speed) for c in load_series(part_dir.parent / "series.json").cast if c.voice}


def extra_inputs(part_dir: Path) -> dict:
    """what else makes the voice: the narrator and cast voices, the gap, the cache tag and the server's model
    fingerprint last seen (settings: no network here). A new model, once seen, makes every TTS part stale."""
    if not is_tts(part_dir):
        return {"voice_source": "recorded"}
    from .. import settings
    s = settings.load(library_of(part_dir))
    return {"voice_source": "tts", "narrator": narrator(part_dir), "cast": cast_voices(part_dir), "gap": s["tts_line_gap"],
            "fp": s["tts_server_fp"], "tag": s["tts_model_tag"]}


def script_lines(part_dir: Path) -> list[tuple[int, str]]:
    """(story.md line number, its spoken text from script-for-tts.txt, without a speaker's "kai:") per line with
    words"""
    from ..sfx import line_words  # sfx imports the stages package
    words = (part_dir / "script-for-tts.txt").read_text(encoding="utf-8").split()
    spans = line_words((part_dir / "story.md").read_text(encoding="utf-8"))
    if sum(b - a + 1 for a, b in spans.values()) != len(words):
        raise StageError("script-for-tts.txt does not match story.md (run prep)")
    return [(no, " ".join(words[a:b + 1])) for no, (a, b) in sorted(spans.items())]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(part_dir: Path) -> None:
    if not is_tts(part_dir):
        print("recorded voice: nothing to do (voice_source tts makes voice.mp3 here)")
        return
    for f in INPUTS:
        if not (part_dir / f).is_file():
            raise StageError(f"{f} not found" + (" (run prep)" if f.startswith("script") else ""))
    lib, cfg = library_of(part_dir), tts.config(library_of(part_dir))
    lines = script_lines(part_dir)
    if not lines:
        raise StageError("script-for-tts.txt is empty")
    md = (part_dir / "story.md").read_text(encoding="utf-8")
    said, marks = speakers(md), voice_marks(md)
    by_cast, narr = cast_voices(part_dir), narrator(part_dir)
    voices = [by_cast.get(said.get(no), narr) for no, _ in lines]  # a speaker without a voice: the narrator's
    voices = [(v, round(min(2.0, max(0.5, s * marks.get(no, {}).get("pace", 1.0))), 3))  # @pace: this line only
              for (no, _), (v, s) in zip(lines, voices)]
    gaps = [marks.get(no, {}).get("pause", cfg["gap"]) for no, _ in lines]  # @pause: the silence before this line
    paths = tts.clips(lib, [(text, v, s) for (_, text), (v, s) in zip(lines, voices)], cfg)  # all before any write
    wav, spans = tts.stitch(paths, gaps)

    mp3, manifest = part_dir / "voice.mp3", part_dir / MANIFEST
    made = json.loads(manifest.read_text(encoding="utf-8")).get("mp3_sha256") if manifest.is_file() else None
    if mp3.is_file() and sha(mp3) != made:  # a recording (or a hand-placed file): keep it
        if (part_dir / RECORDED).exists():
            raise StageError(f"voice.mp3 is not the TTS voice and {RECORDED} already exists: move one of them first")
        os.replace(mp3, part_dir / RECORDED)
        print(f"kept the recorded voice as {RECORDED}")
    tmp = part_dir / "voice.tts.tmp.mp3"
    try:
        ff.run("ffmpeg", "-v", "error", "-y", "-f", "wav", "-i", "-", *MP3_ARGS, tmp, data=wav,
               fail="ffmpeg could not encode the TTS voice")
        os.replace(tmp, mp3)  # voice.mp3 is protected from atomic_write_*: replaced whole, like an upload
    finally:
        tmp.unlink(missing_ok=True)
    atomic_write_json(manifest, {
        "schema_version": 1, "mp3_sha256": sha(mp3), "gap": cfg["gap"], "tag": cfg["tag"],
        "lines": [{"line": no, "speaker": said.get(no), "voice": v, "speed": s, "text": text,
                   "clip": p.stem, "start": a, "end": b}
                  for (no, text), (v, s), p, (a, b) in zip(lines, voices, paths, spans)]})
    used = sorted({f"{v} at {s}x" for v, s in voices})
    print(f"voice.mp3: {len(lines)} lines, {spans[-1][1]:.1f} s, {len(said)} spoken by the cast; voices: {', '.join(used)}")
