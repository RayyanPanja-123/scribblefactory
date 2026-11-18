"""import_check: prove voice.mp3 plays, report silences and duration mismatch. Read-only."""

import re
import shutil
import subprocess
from pathlib import Path

from .prep import estimate_seconds
from .runner import StageError

INPUTS = ["voice.mp3", "script-for-tts.txt"]
OUTPUTS = []
SILENCE_DB = -40
MAX_EDGE_SILENCE = 1.0
MAX_INTERNAL_SILENCE = 2.0
MAX_ESTIMATE_DIFF = 0.40


def _run(*cmd) -> subprocess.CompletedProcess:
    if not shutil.which(cmd[0]):
        raise StageError(f"{cmd[0]} not found on PATH")
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe_duration(path: Path) -> float:
    r = _run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path))
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise StageError(f"ffprobe could not read voice.mp3: {r.stderr.strip() or 'no duration'}")


def silences(path: Path, duration: float, min_len: float = MAX_EDGE_SILENCE) -> list[tuple[float, float]]:
    """(start, end) of each silence of at least min_len seconds."""
    r = _run("ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
             "-af", f"silencedetect=noise={SILENCE_DB}dB:d={min_len}", "-f", "null", "-")
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", r.stderr)]
    ends += [duration] * (len(starts) - len(ends))  # silence running to EOF may have no end line
    return list(zip(starts, ends))


def run(part_dir: Path) -> None:
    voice = part_dir / "voice.mp3"
    if not voice.exists():
        raise StageError("voice.mp3 not found")
    duration = probe_duration(voice)
    if duration <= 0:
        raise StageError("voice.mp3 has zero duration")

    r = _run("ffmpeg", "-v", "error", "-xerror", "-i", str(voice), "-f", "null", "-")
    if r.returncode != 0 or r.stderr.strip():
        raise StageError(f"voice.mp3 does not decode cleanly: {r.stderr.strip()[:300] or f'exit {r.returncode}'}")
    print(f"duration: {duration:.1f} s")

    edge = 0.05  # tolerance for "touches the start/end"
    for start, end in silences(voice, duration):
        length = end - start
        leading, trailing = start <= edge, end >= duration - edge
        if (leading or trailing) and length > MAX_EDGE_SILENCE:
            where = "leading" if leading else "trailing"
            print(f"warning: {where} silence {length:.1f} s (> {MAX_EDGE_SILENCE} s)")
        elif not (leading or trailing) and length > MAX_INTERNAL_SILENCE:
            print(f"warning: internal silence {length:.1f} s at {start:.1f} s (> {MAX_INTERNAL_SILENCE} s)")

    script = part_dir / "script-for-tts.txt"
    if not script.exists():
        print("warning: no script-for-tts.txt (run prep), skipping duration check")
        return
    est = estimate_seconds(script.read_text(encoding="utf-8"))
    if est > 0 and abs(duration - est) / est > MAX_ESTIMATE_DIFF:
        print(f"warning: duration {duration:.1f} s differs from prep estimate {est:.1f} s by more than "
              f"{MAX_ESTIMATE_DIFF:.0%}")
