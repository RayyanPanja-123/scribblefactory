"""Story Package v1: one pasted blob with everything for a new series (format: docs/story-package.md).

parse(text, library) is a pure check (it writes only to a temp folder): the items it would create, warnings, and
errors with their section and line in the pasted text. import_package(text, library) writes it all or nothing.
"""

import json
import os
import re
import secrets
import shutil
import tempfile
from pathlib import Path

from pydantic import ValidationError

from .io import (LIBRARY_FILES, atomic_write_json, cast_wardrobe_problems, creature_bodies, load_actions, load_creatures,
                 load_props, load_sets, load_wardrobe, prop_kinds, save_part, save_series, set_kinds, wardrobe_slots)
from .schemas import (ACTIONS, ActionLibrary, CastMember, CreatureLibrary, CustomAction, CustomCreature, CustomProp,
                      CustomSet, PartModel, PropLibrary, SeriesModel, SetLibrary, Style, Voice, WardrobeItem,
                      WardrobeLibrary, utcnow)
from .stages.prep import TWIST_PREFIX, clean_markdown, strip_directives
from .storycheck import check_story

START, END = "<<<SCRIBBLE_PACKAGE v1>>>", "<<<END>>>"
MARKER = re.compile(r"^<<<([A-Z_]+(?: [0-9]+| v[0-9]+)?)>>>$")
FENCE = re.compile(r"^(```|~~~)[\w-]*$")
ASSETS = {  # section -> (model, library loader, list field, library model)
    "PROPS": (CustomProp, load_props, "props", PropLibrary),
    "SETS": (CustomSet, load_sets, "sets", SetLibrary),
    "CREATURES": (CustomCreature, load_creatures, "creatures", CreatureLibrary),
    "ACTIONS": (CustomAction, load_actions, "actions", ActionLibrary),
    "WARDROBE": (WardrobeItem, load_wardrobe, "wardrobe", WardrobeLibrary),
}
OPTIONAL = {"WARDROBE"}  # packages written before the wardrobe have no WARDROBE section: read as []
HEAD = ["META", *ASSETS, "CAST"]
WORDS = (110, 175)
CONTINUED = "To be continued."


class PackageError(Exception):
    def __init__(self, result: dict):
        super().__init__("; ".join(f"{e['section']} line {e['line']}: {e['message']}" for e in result["errors"][:3]))
        self.result = result


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "new-story"


def unique(i: str, taken: set) -> str:
    """i, or i-2, i-3 ... the first one not taken"""
    n, out = 2, i
    while out in taken:
        out, n = f"{i}-{n}", n + 1
    return out


def cast_dict(c: dict) -> dict:
    """a cast-import entry (series.json cast shape, or the {"color"} shorthand) -> CastMember input"""
    c = {k: v for k, v in c.items() if k != "approved_at"}
    if "color" in c:
        top = c.get("top", {})
        top = {"id": top} if isinstance(top, str) else top
        c["top"] = {**top, "color": c.pop("color")} if isinstance(top, dict) else top
    c.setdefault("eyes", "dots")
    return c


def taken_ids(library: Path) -> dict[str, set[str]]:
    """every id already in the library, built in and custom, per asset section"""
    return {"PROPS": set(prop_kinds(library)) | {"none"}, "SETS": set(set_kinds(library)),
            "CREATURES": set(creature_bodies(library)) | {"stickman"},
            "ACTIONS": set(ACTIONS) | {a.id for a in load_actions(library).actions},
            "WARDROBE": set(wardrobe_slots(library)) | {"none"}}


def _sections(text: str, err) -> list[tuple[str, int, list[str]]]:
    """(marker, line of the marker, body lines) between START and END; line numbers are the pasted text's"""
    lines = [ln.rstrip() for ln in text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip().lstrip("﻿") == START)
    except StopIteration:
        err("START", None, f"no {START} line: paste the whole package")
        return []
    out = []
    for no, ln in enumerate(lines[start + 1:], start + 2):
        s = ln.strip()
        if s == END:
            return out
        if m := MARKER.match(s):
            out.append((m[1], no, []))
        elif FENCE.match(s):
            continue  # a code fence the chat wrapped around (part of) the package
        elif out:
            out[-1][2].append(ln)
        elif s:
            err("START", no, "text before the first section marker")
    err("END", None, f"no {END} line: the package is cut off")
    return []


def _json(sec: str, line: int, body: list[str], err):
    try:
        return json.loads("\n".join(body) or "null")
    except json.JSONDecodeError as e:
        err(sec, line + e.lineno, f"bad JSON: {e.msg}")


def _first_error(e: ValidationError) -> str:
    x = e.errors()[0]
    return f"{'.'.join(map(str, x['loc'])) or 'entry'}: {x['msg']}"


def _rewrite(md: str, renames: dict[str, dict[str, str]]) -> str:
    """point story.md at renamed assets: @set <set>, every word of an @do line (actions and props) and an
    @fx lightning target (a prop)"""
    out = []
    for ln in md.split("\n"):
        s = ln.strip()
        if s.startswith("@set ") and (new := renames["SETS"].get(s[5:].strip())):
            ln = f"@set {new}"
        elif s.startswith(("@do ", "@fx lightning ")):
            # ponytail: whole-word match on @do lines, so a cast id equal to a renamed asset id is renamed too
            for old, new in {**renames["PROPS"], **renames["ACTIONS"]}.items():
                ln = re.sub(rf"(?<![\w-]){re.escape(old)}(?![\w-])", new, ln)
        out.append(ln)
    return "\n".join(out)


WEAR_SLOTS = ("top", "headwear", "legwear", "hair", "facial_hair", "footwear", "back", "accessory", "face")


def _rename_wear(v, ren: dict):
    """one slot value (id string, {id | kind | style, ...} or a list of them) with renamed wardrobe ids"""
    if isinstance(v, list):
        return [_rename_wear(x, ren) for x in v]
    if isinstance(v, str):
        return ren.get(v, v)
    if isinstance(v, dict):
        return {k: ren.get(x, x) if k in ("id", "kind", "style") and isinstance(x, str) else x for k, x in v.items()}
    return v


def _rename_cast(c: dict, renames) -> dict:
    """a cast entry with renamed props, wardrobe items (its own and its looks') and body"""
    fix = lambda ps: [{**p, "kind": renames["PROPS"].get(p.get("kind"), p.get("kind"))} if isinstance(p, dict) else p
                      for p in ps] if isinstance(ps, list) else ps
    wear = lambda d: {k: _rename_wear(v, renames["WARDROBE"]) if k in WEAR_SLOTS else v for k, v in d.items()}
    c = wear({**c, "props": fix(c.get("props", []))})
    if c.get("body") in renames["CREATURES"]:
        c["body"] = renames["CREATURES"][c["body"]]
    if isinstance(c.get("looks"), dict):
        c["looks"] = {k: wear({**v, "props": fix(v["props"])} if "props" in v else v) if isinstance(v, dict) else v
                      for k, v in c["looks"].items()}
    return c


def _narration(md: str) -> str:
    return clean_markdown(strip_directives(md))


def parse(text: str, library) -> dict:
    """{"ok", "series": {title, slug, was}, "assets": {section: [model]}, "renames": {section: {old: new}},
    "cast": [CastMember], "parts": [{number, title, story, voice, words}], "warnings", "errors"}.
    errors / warnings: [{"section", "line" (pasted text, or None), "message"}]"""
    library = Path(library)
    errors, warnings = [], []
    err = lambda sec, line, msg: errors.append({"section": sec, "line": line, "message": msg})
    warn = lambda sec, line, msg: warnings.append({"section": sec, "line": line, "message": msg})
    result = {"ok": False, "series": None, "assets": {k: [] for k in ASSETS}, "renames": {k: {} for k in ASSETS},
              "cast": [], "parts": [], "warnings": warnings, "errors": errors}
    secs = _sections(text, err)
    if errors:
        return result

    # marker order: the head sections, then PART n / SCRIPT / VOICE for n = 1.. parts
    names = [s[0] for s in secs]
    got = {s[0]: s for s in secs if s[0] in HEAD}
    meta = _json("META", got["META"][1], got["META"][2], err) if "META" in got else None
    n_parts = meta.get("parts") if isinstance(meta, dict) else None
    if not isinstance(meta, dict) or not isinstance(meta.get("series_title"), str) or not meta["series_title"].strip() \
            or not isinstance(n_parts, int) or isinstance(n_parts, bool) or not 1 <= n_parts <= 99:
        if "META" in got and not errors:
            err("META", got["META"][1], 'expected {"series_title": "<title>", "parts": <1..99>}')
        n_parts = sum(n.startswith("PART ") for n in names)
    head = [h for h in HEAD if h not in OPTIONAL or h in got]
    want = [*head, *(x for n in range(1, n_parts + 1) for x in (f"PART {n}", "SCRIPT", "VOICE"))]
    if names != want:
        i = next((i for i, (a, b) in enumerate(zip(names, want)) if a != b), min(len(names), len(want)))
        line = secs[i][1] if i < len(secs) else None
        if i < len(want):
            err(names[i] if i < len(names) else "END", line, f"expected <<<{want[i]}>>> here"
                + (f" (META says {n_parts} parts)" if want[i].startswith("PART") or i >= len(names) else ""))
        else:
            err(names[i], line, f"unexpected <<<{names[i]}>>>: META says {n_parts} parts")
        return result
    if errors:
        return result

    # assets: suffix an id the library already has, and remember the rename for the cast and the scripts
    taken = taken_ids(library)
    for sec, (model, *_rest) in ASSETS.items():
        if sec not in got:
            continue  # an optional section left out: nothing new
        _, line, body = got[sec]
        items = _json(sec, line, body, err)
        if items is None and not body:
            items = []
        if not isinstance(items, list):
            if items is not None:
                err(sec, line + 1, "expected a JSON array ([] when nothing is new)")
            continue
        seen = set()
        for i, x in enumerate(items, 1):
            if not isinstance(x, dict) or not isinstance(x.get("id"), str):
                err(sec, line + 1, f"#{i}: expected an object with an id")
                continue
            if x["id"] in seen:
                err(sec, line + 1, f"#{i}: id {x['id']!r} appears twice in the package")
                continue
            new = unique(x["id"], taken[sec])
            seen.add(x["id"])
            if new != x["id"]:
                result["renames"][sec][x["id"]] = new
                warn(sec, line + 1, f"{x['id']!r} is already in the library: imported as {new!r}, references renamed")
            taken[sec].add(new)
            try:
                result["assets"][sec].append(model.model_validate({**x, "id": new}))
            except ValidationError as e:
                err(sec, line + 1, f"#{i} ({x['id']}): {_first_error(e)}")
    renames = result["renames"]

    _, line, body = got["CAST"]
    cast = _json("CAST", line, body, err)
    if not isinstance(cast, list) or not cast:
        if cast is not None:
            err("CAST", line + 1, "expected a JSON array with every character of every part")
        cast = []
    for i, c in enumerate(cast, 1):
        if not isinstance(c, dict):
            err("CAST", line + 1, f"#{i}: expected an object")
            continue
        try:
            result["cast"].append(CastMember.model_validate(cast_dict(_rename_cast(c, renames))))
        except ValidationError as e:
            err("CAST", line + 1, f"#{i} ({c.get('id', 'no id')}): {_first_error(e)}")
    for x in cast_wardrobe_problems(result["cast"], library, result["assets"]["WARDROBE"]):
        err("CAST", line + 1, x)
    ids = [c.id for c in result["cast"]]
    if dupes := sorted({i for i in ids if ids.count(i) > 1}):
        err("CAST", line + 1, f"cast ids must be unique: {', '.join(dupes)}")

    title = meta["series_title"].strip()[:120]
    want_slug = slugify(title)
    series = [d.name for d in library.iterdir() if (d / "series.json").is_file()] if library.is_dir() else []
    slug = unique(want_slug, set(series))
    result["series"] = {"title": title, "slug": slug, "was": want_slug if slug != want_slug else None}
    if slug != want_slug:
        warn("META", got["META"][1], f"series {want_slug!r} exists: imported as {slug!r}")

    by_name = {}
    for name, ln, body in secs[len(head):]:
        if name.startswith("PART "):
            n = int(name[5:])
        else:
            by_name[(n, name)] = (ln, "\n".join(body).rstrip("\n") + "\n")
    for n in range(1, n_parts + 1):
        (sl, story), (vl, voice) = by_name[(n, "SCRIPT")], by_name[(n, "VOICE")]
        story = _rewrite(story, renames)
        heading = next((ln[2:].strip() for ln in story.split("\n") if ln.startswith("# ")), "")
        narration = _narration(story)
        words = len(narration.split())
        result["parts"].append({"number": n, "title": heading or f"Part {n}", "story": story, "voice": voice,
                                "words": words, "script_line": sl, "voice_line": vl})
        sec = f"PART {n} SCRIPT"
        if not heading:
            warn(sec, sl + 1, 'no "# Part title" line')
        if not WORDS[0] <= words <= WORDS[1]:
            warn(sec, None, f"{words} words: aim for {WORDS[0]} to {WORDS[1]}")
        if (twists := sum(bool(TWIST_PREFIX.match(ln)) for ln in story.split("\n"))) > 1:
            warn(sec, None, f"{twists} !! lines: at most one twist per part")
        if n < n_parts and not narration.rstrip().endswith(CONTINUED):
            warn(sec, None, f'a part before the last ends with "{CONTINUED}"')
        if not voice.strip():
            err(f"PART {n} VOICE", vl, "empty: the narration, word for word")

    if not errors:
        with tempfile.TemporaryDirectory(prefix="scribble-package-") as tmp:
            stage(result, library, Path(tmp), approved=True)
            for p in result["parts"]:
                r = check_story(Path(tmp) / slug / f"part-{p['number']:02d}")
                for x in r["problems"]:
                    err(f"PART {p['number']} SCRIPT", p["script_line"] + x["line"] if x["line"] else None, x["message"])
                for x in r["warnings"]:
                    if x["message"].startswith("changed since script-for-tts.txt: "):  # VOICE vs the narration
                        diff = x["message"].removeprefix("changed since script-for-tts.txt: ").removesuffix(" (prep rewrites it)")
                        warn(f"PART {p['number']} VOICE", p["voice_line"], f"differs from the script's narration "
                             f"(script line {x['line']}): {diff}")
                    elif not x["message"].startswith("estimated "):  # the word count warning above covers runtime
                        warn(f"PART {p['number']} SCRIPT", p["script_line"] + x["line"] if x["line"] else None, x["message"])
    result["ok"] = not errors
    return result


def stage(result: dict, library: Path, root: Path, approved: bool = False) -> None:
    """write the package into root: the library's 4 item files with the new assets added, and the series folder.
    approved: cast marked approved (a check-only copy: check_story would report every new cast member)"""
    for sec, (_m, load, field, lib_model) in ASSETS.items():
        lib = load(library)
        atomic_write_json(root / f"{field}.json", lib_model(**{field: [*getattr(lib, field), *result["assets"][sec]]})
                          .model_dump(mode="json"))
    s = result["series"]
    d = root / s["slug"]
    d.mkdir(parents=True)
    now = utcnow()
    cast = [c.model_copy(update={"approved_at": now if approved else None}) for c in result["cast"]]
    parts = []
    for p in result["parts"]:
        pid = f"part-{p['number']:02d}"
        (d / pid).mkdir()
        save_part(d / pid / "part.json", PartModel(id=pid, number=p["number"], title=p["title"][:120]))
        (d / pid / "story.md").write_text(p["story"], encoding="utf-8", newline="\n")
        (d / pid / "script-for-tts.txt").write_text(p["voice"], encoding="utf-8", newline="\n")
        parts.append(pid)
    # voice_name and style preset are placeholders, as for new-series
    save_series(d / "series.json", SeriesModel(slug=s["slug"], title=s["title"], created_at=now, parts=parts,
                                               voice=Voice(voice_name=""), style=Style(preset="default"), cast=cast))


def import_package(text: str, library) -> dict:
    """parse, then write everything or nothing: the series folder is built aside and renamed in last; the library's
    item files are put back as they were if anything fails. Raises PackageError when the package has errors."""
    library = Path(library)
    result = parse(text, library)
    if not result["ok"]:
        raise PackageError(result)
    library.mkdir(parents=True, exist_ok=True)
    tmp = library / f".import-{secrets.token_hex(4)}"
    tmp.mkdir()
    old = {f: (library / f).read_bytes() if (library / f).is_file() else None for f in LIBRARY_FILES}
    try:
        stage(result, library, tmp)
        for f in LIBRARY_FILES:
            os.replace(tmp / f, library / f)
        os.replace(tmp / result["series"]["slug"], library / result["series"]["slug"])
    except BaseException:
        for f, data in old.items():
            if data is None:
                (library / f).unlink(missing_ok=True)
            else:
                (library / f).write_bytes(data)
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return result


def summary(result: dict) -> dict:
    """the JSON-safe view of a parse result (the API's answer)"""
    dump = lambda xs: [{"id": x.id, "name": x.name} for x in xs]
    return {"ok": result["ok"], "series": result["series"],
            "props": dump(result["assets"]["PROPS"]), "sets": dump(result["assets"]["SETS"]),
            "creatures": dump(result["assets"]["CREATURES"]), "actions": dump(result["assets"]["ACTIONS"]),
            "wardrobe": dump(result["assets"]["WARDROBE"]),
            "cast": dump(result["cast"]), "renames": {k.lower(): v for k, v in result["renames"].items()},
            "parts": [{k: p[k] for k in ("number", "title", "words")} for p in result["parts"]],
            "warnings": result["warnings"], "errors": result["errors"]}
