"""Load/save series.json and part.json. Writes are atomic; saves never drop an existing approval."""

import json
import os
import tempfile
import time
from pathlib import Path

from .schemas import PartModel, SeriesModel

# User-owned files a save must never write to.
PROTECTED = {"story.md", "voice.mp3"}
REPLACE_RETRIES = 5


def atomic_write_json(path, data) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def atomic_write_text(path, text: str) -> None:
    """Write via temp file in the same dir + fsync + os.replace (atomic on Windows and POSIX)."""
    path = Path(path)
    if path.name in PROTECTED:
        raise ValueError(f"refusing to write protected file {path.name}")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        # Windows: replace fails with PermissionError while another process
        # (editor, antivirus, indexer) has the target open. Retry briefly.
        for attempt in range(REPLACE_RETRIES + 1):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == REPLACE_RETRIES:
                    raise
                time.sleep(0.1)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_series(path) -> SeriesModel:
    return SeriesModel.model_validate_json(Path(path).read_bytes())


def load_part(path) -> PartModel:
    return PartModel.model_validate_json(Path(path).read_bytes())


def save_series(path, model: SeriesModel) -> None:
    path = Path(path)
    if path.exists():
        on_disk = {c.id: c.approved_at for c in load_series(path).cast}
        for c in model.cast:
            if c.approved_at is None and on_disk.get(c.id):
                c.approved_at = on_disk[c.id]
    atomic_write_json(path, model.model_dump(mode="json"))


def save_part(path, model: PartModel) -> None:
    path = Path(path)
    if path.exists():
        old = load_part(path).approvals
        for name in ("stills", "test_render", "final"):
            kept = getattr(old, name).approved_at
            if kept and getattr(model.approvals, name).approved_at is None:
                getattr(model.approvals, name).approved_at = kept
    atomic_write_json(path, model.model_dump(mode="json"))
