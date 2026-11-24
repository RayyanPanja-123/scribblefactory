"""Golden hashes of a library: every catalog's bytes and rows, and every part's stage input hashes plus its planned
story.json. Read-only. Record before an engine/schema change, check after: nothing a change should leave alone moved.

  .venv/Scripts/python scripts/golden_hashes.py record golden.json [--library library]
  .venv/Scripts/python scripts/golden_hashes.py check golden.json [--library library]

check exits 1 and lists each difference. The render stage hashes the engine's page code, so an engine change always
moves render hashes (pass --skip render to leave them out). The library's database is opened read-only (sqlite
mode=ro): a snapshot never writes to it. --write allows writes (e.g. a library that still has old JSON to import)."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.scribble import db  # noqa: E402
from pipeline.scribble.io import LIBRARY_FILES, LIBRARY_MODELS, all_parts, catalog_bytes  # noqa: E402
from pipeline.scribble.stages import STAGES  # noqa: E402
from pipeline.scribble.stages.runner import inputs_hash  # noqa: E402
from pipeline.scribble.stages.shots import plan_part  # noqa: E402

sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731


def snapshot(lib: Path, skip: set[str]) -> dict:
    out = {"catalogs": {}, "rows": {}, "parts": {}}
    for f in LIBRARY_FILES:
        b = catalog_bytes(lib, f)
        out["catalogs"][f] = sha(b) if b else None
        kind = f.removesuffix(".json")
        item = LIBRARY_MODELS[kind].model_fields[kind].annotation.__args__[0]
        for row in db.get_catalog(lib, kind) or []:  # a row and what saving it again would write
            out["rows"][f"{kind}/{row['id']}"] = sha(json.dumps(item.model_validate(row).model_dump(mode="json"),
                                                            sort_keys=True).encode())
    for name, pdir in sorted(all_parts(lib)):
        p = {stage: inputs_hash(pdir, st.INPUTS, getattr(st, "extra_inputs", None))
             for stage, st in STAGES.items() if stage not in skip}
        try:
            p["plan"] = sha(json.dumps(plan_part(pdir)[0].model_dump(mode="json"), indent=2, ensure_ascii=False).encode())
        except Exception as e:  # noqa: BLE001 (a part that can't be planned yet stays that way)
            p["plan"] = f"error: {type(e).__name__}: {e}"[:200]
        out["parts"][name] = p
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["record", "check"])
    ap.add_argument("file")
    ap.add_argument("--library", default="library")
    ap.add_argument("--skip", action="append", default=[], help="stage names to leave out (e.g. render)")
    ap.add_argument("--write", action="store_true", help="open the database read-write (default: read-only)")
    a = ap.parse_args()
    if not a.write:
        db.read_only(a.library)
    now = snapshot(Path(a.library), set(a.skip))
    if a.mode == "record":
        Path(a.file).write_text(json.dumps(now, indent=1), encoding="utf-8")
        print(f"recorded {len(now['catalogs'])} catalogs, {len(now['rows'])} rows, {len(now['parts'])} parts")
        return 0
    was, diffs = json.loads(Path(a.file).read_text(encoding="utf-8")), []
    for section in ("catalogs", "rows"):
        diffs += [f"{section} {k}" for k in sorted(set(was[section]) | set(now[section])) if was[section].get(k) != now[section].get(k)]
    for part in sorted(set(was["parts"]) | set(now["parts"])):
        a_, b_ = was["parts"].get(part, {}), now["parts"].get(part, {})
        diffs += [f"part {part} {k}" for k in sorted(set(a_) | set(b_)) if k not in a.skip and a_.get(k) != b_.get(k)]
    print("\n".join(diffs) or f"unchanged: {len(now['catalogs'])} catalogs, {len(now['rows'])} rows, {len(now['parts'])} parts")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
