"""cli export: the library's database as JSON files, laid out as the library was before the database (props.json,
settings.json, database/storage/<slug>/series.json, <slug>/<part folder>/part.json). For backups and git diffs:
copied into an empty library, io imports every file back (adopt, db._import_old). The Gemini key is left out; job
history is not exported; media stay the plain files they are."""

import json
import shutil
from pathlib import Path

from . import db
from .io import LIBRARY_FILES, PART_FILE, SERIES_FILE, catalog_bytes, load_part, load_series, part_folders_of, \
    series_dirs, storage_root
from .schemas import utcnow

SECRET_SETTINGS = {"gemini_key"}


def _write(f: Path, data) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def export(library, out) -> dict[str, int]:
    """write the export into out (replaced whole, only once it is complete); returns what it holds"""
    library, out = Path(library), Path(out)
    tmp = out.with_name(f".{out.name}-{utcnow():%Y%m%d%H%M%S}")
    counts = {"catalogs": 0, "series": 0, "parts": 0}
    try:
        settings = {k: v for k, v in db.get_settings(library).items() if k not in SECRET_SETTINGS}
        _write(tmp / "settings.json", dict(sorted(settings.items())))
        for name in LIBRARY_FILES:
            if (data := catalog_bytes(library, name)) is not None:
                (tmp / name).write_bytes(data)
                counts["catalogs"] += 1
        for d in series_dirs(library):
            dst = storage_root(tmp) / d.name
            _write(dst / SERIES_FILE, load_series(d / SERIES_FILE).model_dump(mode="json"))
            counts["series"] += 1
            for folder in part_folders_of(d).values():
                _write(dst / folder / PART_FILE, load_part(d / folder / PART_FILE).model_dump(mode="json"))
                counts["parts"] += 1
        shutil.rmtree(out, ignore_errors=True)
        tmp.rename(out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return counts
