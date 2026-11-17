"""Run one stage of a part, tracking status/timestamps/inputs hash in part.json."""

import hashlib
import traceback
from pathlib import Path

from ..io import load_part, save_part
from ..schemas import utcnow


class StageError(Exception):
    """Expected stage failure; the message is stored in part.json."""


def inputs_hash(part_dir: Path, inputs) -> str:
    h = hashlib.sha256()
    for name in sorted(inputs):
        f = part_dir / name
        h.update(name.encode() + b"\0")
        if f.is_dir():  # a directory input: the names and bytes of the files directly inside it
            for x in sorted(x for x in f.iterdir() if x.is_file()):
                h.update(x.name.encode() + b"\0" + x.read_bytes() + b"\0")
        else:
            h.update(f.read_bytes() if f.exists() else b"<missing>")
        h.update(b"\0")
    return h.hexdigest()


def _update(part_json: Path, name: str, **fields) -> None:
    part = load_part(part_json)
    stage = getattr(part.stages, "validate_" if name == "validate" else name)
    for k, v in fields.items():
        setattr(stage, k, v)
    save_part(part_json, part)


def run_stage(part_dir, name, fn, force=False, inputs=(), outputs=()) -> str:
    """Run fn(part_dir). Returns "done", "skipped" or "failed".

    Skips when the stage is done, its input files hash the same, its outputs exist and not force.
    """
    part_dir = Path(part_dir)
    part_json = part_dir / "part.json"
    stage = getattr(load_part(part_json).stages, "validate_" if name == "validate" else name)
    digest = inputs_hash(part_dir, inputs)
    if (not force and stage.status == "done" and stage.inputs_hash == digest
            and all((part_dir / o).exists() for o in outputs)):
        print(f"{name}: skipped (up to date)")
        return "skipped"

    print(f"{name}: running")
    _update(part_json, name, status="running", started_at=utcnow(), finished_at=None, error=None, inputs_hash=None)
    try:
        fn(part_dir)
    except BaseException as e:
        msg = str(e) or type(e).__name__
        _update(part_json, name, status="failed", finished_at=utcnow(), error=msg)
        if not isinstance(e, Exception):  # Ctrl+C etc: record, then let it propagate
            raise
        if not isinstance(e, StageError):
            traceback.print_exc()  # unexpected: keep the trace for debugging
        print(f"{name}: failed: {msg}")
        return "failed"
    _update(part_json, name, status="done", finished_at=utcnow(), inputs_hash=digest)
    print(f"{name}: done")
    return "done"
