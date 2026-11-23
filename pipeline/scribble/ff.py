"""ffmpeg and ffprobe: one way to run them, and the duration probe."""

import shutil
import subprocess
from pathlib import Path

from .stages.runner import StageError


def run(tool: str, *args, data: bytes | None = None, text: bool = False, fail: str | None = None) -> subprocess.CompletedProcess:
    """tool ("ffmpeg" / "ffprobe") with args, output captured: str (utf-8) when text, else bytes. StageError when the
    tool is not on PATH and, with fail given, when it exits non-zero: "<fail>: <the end of its stderr>"."""
    if not shutil.which(tool):
        raise StageError(f"{tool} not found on PATH")
    r = subprocess.run([tool, *map(str, args)], input=data, capture_output=True,
                       **({"text": True, "encoding": "utf-8", "errors": "replace"} if text else {}))
    if fail and r.returncode != 0:
        err = r.stderr if text else r.stderr.decode(errors="replace")
        raise StageError(f"{fail}: {err.strip()[-300:]}")
    return r


def duration(path: Path) -> float | None:
    """an audio or video file's length in seconds; None when ffprobe can't tell"""
    r = run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None
