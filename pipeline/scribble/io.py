"""Load/save series, parts and the shared catalogs (rows of the database, db.py); file writes are atomic. Saves never drop an existing approval."""

import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path

from typing import get_args

from . import db
from .schemas import (ACTIONS, BUILTIN_CREATURES, BUILTIN_SETS, BUILTIN_WARDROBE, ActionLibrary, BuiltinProp,
                      JOINT_OF, CreatureLibrary, CustomAction, CustomCreature, CustomProp, CustomSet, PartModel, PropLibrary,
                      SeriesModel, SetLibrary, WardrobeItem, WardrobeLibrary, WorldObject, WorldObjectLibrary, worn)

# User-owned files a save must never write to.
PROTECTED = {"story.md", "voice.mp3"}
# The library's custom items, one catalog per kind (db.CATALOG_KINDS, engine/page/library.js KINDS), still named by
# their old file. A part's stage and render hashes cover only the rows it uses (used_catalog_bytes): a new library
# item changes nothing for the parts that don't name it.
LIBRARY_FILES = ["props.json", "sets.json", "objects.json", "creatures.json", "actions.json", "wardrobe.json"]
LIBRARY_MODELS = {"props": PropLibrary, "sets": SetLibrary, "objects": WorldObjectLibrary, "creatures": CreatureLibrary,
                  "actions": ActionLibrary, "wardrobe": WardrobeLibrary}
REPLACE_RETRIES = 5


def storage_root(library) -> Path:
    """where every series folder lives: library/database/storage/<slug>/<part>"""
    return Path(library) / "database" / "storage"


def library_of(path) -> Path:
    """the library a part folder (or a file in one) belongs to: the folder above database/storage. A part folder
    outside database/storage (a bare one in tests) has the library two levels up, the layout before storage."""
    p = Path(path)
    for q in (p, *p.parents):
        if q.name == "storage" and q.parent.name == "database":
            return q.parent.parent
    return p.parents[1] if p.is_dir() or p.name.startswith("part-") else p.parents[2]


# A series and its parts are database rows (db.py). The code still names them by their old files, as keys:
# <series folder>/series.json is the series, <part folder>/part.json the part; an old file found there is imported
# (adopt) and kept as <name>.imported.
SERIES_FILE, PART_FILE = "series.json", "part.json"


def series_where(series_dir) -> tuple[Path, str]:
    """(library, slug) of a series folder: library/database/storage/<slug>, or <library>/<slug> (bare, in tests)"""
    d = Path(series_dir)
    inside = d.parent.name == "storage" and d.parent.parent.name == "database"
    return (d.parent.parent.parent if inside else d.parent), d.name


def adopt(series_dir) -> None:
    """import an old series.json, and every part.json beside it, of this series folder into the database; each
    file is kept as <name>.imported"""
    d = Path(series_dir)
    f = d / SERIES_FILE
    old_parts = sorted(d.glob(f"*/{PART_FILE}")) if d.is_dir() else []
    if not f.is_file() and not old_parts:
        return
    library, slug = series_where(d)
    if f.is_file():
        text = f.read_text(encoding="utf-8")
        s = SeriesModel.model_validate_json(text)
        db.put_series(library, {**s.model_dump(mode="json"), "slug": slug}, cast_uses(s), file_text=text)
        db.retire(f)
    if db.get_series(library, slug) is None:
        return  # parts without their series: left for when it is there
    for pf in old_parts:
        db.put_part(library, slug, pf.parent.name, PartModel.model_validate_json(pf.read_bytes()).model_dump(mode="json"))
        db.retire(pf)


def series_exists(series_dir) -> bool:
    adopt(series_dir)
    return db.get_series(*series_where(series_dir)) is not None


def series_dirs(library) -> list[Path]:
    """every series folder of the library, by slug"""
    root = storage_root(library)
    for d in (root.iterdir() if root.is_dir() else []):
        if (d / SERIES_FILE).is_file():
            adopt(d)
    return [root / slug for slug in db.series_slugs(library)]


def atomic_write_json(path, data) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def atomic_write_text(path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_bytes(path, data: bytes) -> None:
    """Write via temp file in the same dir + fsync + os.replace (atomic on Windows and POSIX)."""
    path = Path(path)
    if path.name in PROTECTED:
        raise ValueError(f"refusing to write protected file {path.name}")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        replace_file(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def replace_file(tmp, path) -> None:
    """os.replace, retried: on Windows it fails with PermissionError while another process
    (editor, antivirus, indexer) has the target open."""
    if Path(path).name in PROTECTED:
        raise ValueError(f"refusing to write protected file {Path(path).name}")
    for attempt in range(REPLACE_RETRIES + 1):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == REPLACE_RETRIES:
                raise
            time.sleep(0.1)


def load_series(path) -> SeriesModel:
    """the series of this (former) series.json path; FileNotFoundError when there is none"""
    d = Path(path).parent
    adopt(d)
    data = db.get_series(*series_where(d))
    if data is None:
        raise FileNotFoundError(f"no series {d.name!r} in the database")
    return SeriesModel.model_validate(data)


# one cast member's render (cli cast-sheet <slug> [id]): <series>/cast/<id>.png (every pose in one row, plus a row
# per named look), <id>-idle.png (the card picture) and <id>.key (the look it was drawn from)
def cast_files(series_dir, cast_id: str) -> dict[str, Path]:
    d = Path(series_dir) / "cast"
    return {"sheet": d / f"{cast_id}.png", "idle": d / f"{cast_id}-idle.png", "key": d / f"{cast_id}.key"}


def cast_key(c) -> str:
    return hashlib.sha256(c.look().encode()).hexdigest()


def cast_render_current(series_dir, c) -> bool:
    """this member's render shows its look now. A look change, or a library drawing it uses changing
    (_clear_approvals drops the key), makes it stale: approving waits for a re-render."""
    f = cast_files(series_dir, c.id)
    return f["sheet"].is_file() and f["key"].is_file() and f["key"].read_text().strip() == cast_key(c)


# ---- the six shared catalogs (props, creatures, wardrobe, actions, sets, objects): catalog_item rows (db.py) ----

def _load_library(library, file: str, model, seed: Path | None = None):
    """the catalog <file> names (props.json: props); no items: the seed when there is one, else an empty catalog"""
    # ponytail: no items reads as "never written", so deleting every wardrobe item brings the starter set back
    kind = file.removesuffix(".json")
    items = db.get_catalog(library, kind)
    if not items and seed:
        return model.model_validate_json(seed.read_bytes())
    return model.model_validate({kind: items})


def _write_library(library, lib, field: str) -> None:
    db.put_catalogs(library, {field: [x.model_dump(mode="json") for x in getattr(lib, field)]})


def catalog_bytes(library, file: str) -> bytes | None:
    """the catalog as its old library/<file> held it, byte for byte (None: no items, as a missing file was), so the
    stage and frame hashes over it stay what they were before the database"""
    kind = file.removesuffix(".json")
    items = db.get_catalog(library, kind)
    if not items:
        return None
    version = LIBRARY_MODELS[kind].model_fields["schema_version"].default  # the rows are model dumps already
    return (json.dumps({"schema_version": version, kind: items}, indent=2, ensure_ascii=False) + "\n").encode()


ID_TOKEN = re.compile(r"[a-z0-9]+(?:[_-][a-z0-9]+)*")  # what a catalog id (Slug, WardrobeId) can be


def used_catalog_bytes(library, file: str, part_dir) -> bytes | None:
    """catalog_bytes cut down to the rows part_dir can use: ids named anywhere in its story.md or its series (cast
    props, bodies, wardrobe; @set, @do, @hold, @item...), plus the World Items a used set places and the props a used
    World Item is held as. A word that only looks like an id keeps that row too (never misses one). None: no row
    is used (an empty catalog too)."""
    kind = file.removesuffix(".json")
    items = db.get_catalog(library, kind)
    if not items:
        return None
    pdir = Path(part_dir)
    text = (pdir / "story.md").read_text(encoding="utf-8") if (pdir / "story.md").is_file() else ""
    words = set(ID_TOKEN.findall(text + (series_bytes(pdir.parent) or b"").decode("utf-8", "replace")))
    if kind in ("objects", "props"):  # reached through a used set / a used World Item
        sets = [s for s in db.get_catalog(library, "sets") if s["id"] in words]
        words |= {o["object"] for s in sets for o in s.get("objects", [])}
        if kind == "props":
            words |= {o["prop"] for o in db.get_catalog(library, "objects") if o["id"] in words and o.get("prop")}
    version = LIBRARY_MODELS[kind].model_fields["schema_version"].default
    used = [x for x in items if x["id"] in words]
    if not used:
        return None  # nothing used: as an empty catalog, so a first row it doesn't use changes nothing either
    return (json.dumps({"schema_version": version, kind: used}, indent=2, ensure_ascii=False) + "\n").encode()


def _put(library, file: str, lib, field: str, item):
    """add or replace item (same id) in lib.<field> and save the catalog; returns the item it replaced, or None"""
    items = getattr(lib, field)
    old = next((x for x in items if x.id == item.id), None)
    setattr(lib, field, [item if x.id == item.id else x for x in items] if old is not None else [*items, item])
    _write_library(library, lib, field)
    return old


def _remove(library, file: str, lib, field: str, item_id: str, *blockers) -> None:
    """remove item_id from lib.<field> and save the catalog. KeyError: it is not there. blockers: (verb, users)
    pairs, users() a list of names, tried in order: the first with any refuses (ValueError "<id> is still <verb> ...")"""
    items = getattr(lib, field)
    if not any(x.id == item_id for x in items):
        raise KeyError(item_id)
    for verb, users in blockers:
        if found := users():
            raise ValueError(f"{item_id} is still {verb} " + ", ".join(found))
    setattr(lib, field, [x for x in items if x.id != item_id])
    _write_library(library, lib, field)


def cast_uses(series: SeriesModel) -> dict[str, list[tuple[str, str]]]:
    """cast id -> the library items it uses: ("props", kind) held, ("wardrobe", id) worn in any look, ("creatures",
    body). Stored with the cast (db.cast_uses), so "who uses this item" is one query."""
    return {c.id: [*(("props", p.kind) for p in c.props), *(("wardrobe", wid) for _, wid in c.wardrobe()),
                   ("creatures", c.body)] for c in series.cast}


def _cast_using(library, kind: str, item_id: str) -> list[tuple[Path, str]]:
    """(series.json, cast id) for every cast member, in every series of the library, using this item"""
    dirs = series_dirs(library)  # also imports a series.json dropped into a series folder
    if db.uses_missing(library):  # a library from before cast_uses: filled once (not re-saved: hashes stay)
        for d in dirs:
            db.put_uses(library, d.name, cast_uses(load_series(d / SERIES_FILE)))
    return [(storage_root(library) / slug / SERIES_FILE, cid) for slug, cid in db.cast_users(library, kind, item_id)]


def _cast_names(pairs) -> list[str]:
    """(series.json, cast id) pairs as "<series folder>/<cast id>" """
    return [f"{f.parent.name}/{cid}" for f, cid in pairs]


def all_parts(library) -> list[tuple[str, Path]]:
    """("<slug>/<part id>", part folder) for every part of every series in the library"""
    return [(f"{d.name}/{pid}", d / folder) for d in series_dirs(library) for pid, folder in part_folders_of(d).items()]


def _stories_with(library, wants) -> list[str]:
    """"<slug>/<part id>" for every story.md in the library with a line (stripped) that wants(line)"""
    return [name for name, pdir in all_parts(library) if (f := pdir / "story.md").is_file()
            and any(wants(line.strip()) for line in f.read_text(encoding="utf-8").splitlines())]


def load_props(library) -> PropLibrary:
    """library/props.json (custom props, shared by every series); none yet: an empty library"""
    return _load_library(library, "props.json", PropLibrary)


def prop_kinds(library) -> list[str]:
    """every prop kind a cast member or @do can use: the built-ins, then the library's custom props"""
    return [*get_args(BuiltinProp), *(p.id for p in load_props(library).props)]


def unknown_cast_props(cast, library) -> list[str]:
    """'<cast id>: <kind>' for each held prop, its own or a look's, that is neither built in nor in library/props.json"""
    known = set(prop_kinds(library))
    return [f"{c.id}: {p.kind}" for c in cast for ps in [c.props, *(lk.props or [] for lk in c.looks.values())]
            for p in ps if p.kind not in known]


def prop_holders(library, kind: str) -> list[tuple[Path, str]]:
    """(series.json, cast id) for every cast member, in every series of the library, holding a prop of this kind"""
    return _cast_using(library, "props", kind)


def save_prop(library, prop: CustomProp) -> list[str]:
    """add or replace a custom prop. A changed drawing changes the look of everyone holding it, so their cast
    approvals are cleared (like cast-edit). Returns "<slug>/<cast id>" for each approval cleared."""
    old = _put(library, "props.json", load_props(library), "props", prop)
    return _clear_approvals(prop_holders(library, prop.id)) if old and (old.shapes, old.angle, old.grip) != (prop.shapes, prop.angle, prop.grip) else []


def prop_users(library, kind: str) -> list[str]:
    """"<slug>/<part id>" for every story.md in the library with an @do line naming this prop (eat / give)"""
    # ponytail: whole-word match, so a cast id equal to the prop id also counts (blocks a delete, never breaks one)
    word = re.compile(rf"(?<![\w-]){re.escape(kind)}(?![\w-])")
    return _stories_with(library, lambda line: line.startswith("@do") and word.search(line))


def delete_prop(library, prop_id: str) -> None:
    """remove a custom prop; refused (ValueError) while any cast member holds it or any story's @do uses it"""
    _remove(library, "props.json", load_props(library), "props", prop_id,
            ("held by", lambda: _cast_names(prop_holders(library, prop_id))),
            ("used by @do in", lambda: prop_users(library, prop_id)),
            ("the held prop of World Item", lambda: [o.id for o in load_objects(library).objects if o.prop == prop_id]))


def load_creatures(library) -> CreatureLibrary:
    """library/creatures.json (custom cast bodies, shared by every series); none yet: an empty library"""
    return _load_library(library, "creatures.json", CreatureLibrary)


def creature_bodies(library) -> dict[str, tuple[str, bool]]:
    """every creature a cast member can be: id -> (rig, has a stump); built-ins first, then library/creatures.json"""
    return {**BUILTIN_CREATURES, **{c.id: (c.rig, bool(c.parts.get("stump"))) for c in load_creatures(library).creatures}}


PX_WORLD = 1.6 / 1024  # world units per card canvas px (engine main.js CARD_H / CH)
# engine/page/creatures.js measure(def).half * PX_WORLD for the built-in creatures: half their width in world units
BUILTIN_CREATURE_HALF = {"chicken": 0.325, "cat": 0.339, "horse": 0.723, "monkey": 0.25, "snake": 0.602}


def creature_halves(library) -> dict[str, float]:
    """creature id -> half its width in world units (its widest reach from the centre line, any part), for stage
    spacing; humanoids are left out (the stickman's width)"""
    out = dict(BUILTIN_CREATURE_HALF)
    for c in load_creatures(library).creatures:
        if c.rig == "humanoid":
            continue
        reach = 0.0
        for part, shapes in c.parts.items():
            jx = 0.0 if part == "body" else c.joints.get(JOINT_OF[part], (0.0, 0.0))[0]
            for s in shapes:
                if s.shape in ("circle", "ellipse"):
                    m = max(s.r or 0, s.ry or 0)
                    xs = [s.pts[0][0] - m, s.pts[0][0] + m]
                else:
                    xs = [q[0] for q in s.pts]
                reach = max(reach, *(abs(x + jx) for x in xs))
        out[c.id] = round(reach * PX_WORLD, 3)
    return out


def cast_body_problems(cast, library, extra_wardrobe=()) -> list[str]:
    """'<cast id>: <problem>' for each body that is not built in or in library/creatures.json, each headless cast
    member whose creature has no stump, and each wardrobe problem (cast_wardrobe_problems). extra_wardrobe: items
    about to be added (a story package's)"""
    bodies, out = creature_bodies(library), []
    for c in cast:
        if c.body not in bodies:
            out.append(f"{c.id}: unknown body {c.body!r} ({', '.join(bodies)})")
        elif c.headless and c.body in bodies and not bodies[c.body][1]:
            out.append(f"{c.id}: headless, but creature {c.body!r} has no stump part")
    return out + cast_wardrobe_problems(cast, library, extra_wardrobe)


# the slots a creature can wear (custom items only: built-in hats are drawn for the stickman's head); keep equal to
# engine/page/creatures.js CREATURE_SLOTS
CREATURE_SLOTS = ("headwear", "face", "accessory", "back")
CREATURE_HINT = (f"a creature wears only custom {', '.join(CREATURE_SLOTS)} items (no top, legwear, footwear, hair, "
                 "facial hair or built-in hat); use @face or @do instead, or design a creature with it drawn in "
                 "(Creatures page)")


def creature_wardrobe(cast, bodies) -> dict[str, tuple[str, dict[str | None, list[str]]]]:
    """cast id -> (rig, {look name, None for its own: ["<slot> <id>", ...]}) for each cast member whose body is not a
    humanoid, listing only what the engine leaves out: every slot but CREATURE_SLOTS, and built-in items. bodies:
    creature_bodies(). A plain top is every member's default (its colour paints the creature): not listed."""
    out = {}
    for c in cast:
        rig = bodies.get(c.body, ("humanoid",))[0]
        if rig != "humanoid":
            out[c.id] = (rig, {k: [f"{s} {w}" for s, w in worn(m) if (s, w) != ("top", "plain")
                                   and (s not in CREATURE_SLOTS or w in BUILTIN_WARDROBE)]
                               for k, m in [(None, c), *c.looks.items()]})
    return out


def cast_wardrobe_problems(cast, library, extra_wardrobe=()) -> list[str]:
    """'<cast id>: <problem>' for each worn wardrobe id (own or a look's) that is unknown or in the wrong slot"""
    items, out = {**wardrobe_slots(library), **{w.id: w.slot for w in extra_wardrobe}}, []
    for c in cast:
        for slot, wid in dict.fromkeys(c.wardrobe()):
            if wid not in items:
                choices = [k for k, v in items.items() if v == slot]
                out.append(f"{c.id}: unknown {slot} {wid!r} ({', '.join(choices) or 'none in the wardrobe yet'})")
            elif items[wid] != slot:
                out.append(f"{c.id}: {wid!r} is a {items[wid]}, not a {slot}")
    return out


# the starter wardrobe (hair, beards, crowns, robes...): a library without its own wardrobe.json uses it; the first
# save writes it into the library, where it can be edited like any custom item (engine/render.mjs falls back too)
WARDROBE_SEED = Path(__file__).parent / "seed" / "wardrobe.json"


def load_wardrobe(library) -> WardrobeLibrary:
    """library/wardrobe.json (custom clothing, hair and cosmetics, shared by every series); none yet: the seed"""
    return _load_library(library, "wardrobe.json", WardrobeLibrary, WARDROBE_SEED)


def wardrobe_slots(library) -> dict[str, str]:
    """every wardrobe id a cast slot can use -> its slot: the built-ins, then library/wardrobe.json"""
    return {**{k: v[0] for k, v in BUILTIN_WARDROBE.items()}, **{w.id: w.slot for w in load_wardrobe(library).wardrobe}}


def wardrobe_wearers(library, item_id: str) -> list[tuple[Path, str]]:
    """(series.json, cast id) for every cast member, in every series of the library, wearing this item in any look"""
    return _cast_using(library, "wardrobe", item_id)


def _clear_approvals(pairs) -> list[str]:
    """clear the cast approval of each (series.json, cast id); "<slug>/<cast id>" for each one cleared"""
    cleared = []
    for f, cid in pairs:
        cast_files(f.parent, cid)["key"].unlink(missing_ok=True)  # its render shows the old drawing
        series = load_series(f)
        c = next(c for c in series.cast if c.id == cid)
        if c.approved_at:
            c.approved_at = None
            # written directly: save_series would restore the approval (it only ever adds approvals)
            write_series(f, series)
            cleared.append(f"{series.slug}/{cid}")
    return cleared


def save_wardrobe_item(library, item: WardrobeItem) -> list[str]:
    """add or replace a custom wardrobe item. A changed drawing changes the look of everyone wearing it: their cast
    approvals are cleared. Returns "<slug>/<cast id>" for each approval cleared."""
    lib = load_wardrobe(library)
    old = next((w for w in lib.wardrobe if w.id == item.id), None)
    if old and old.slot != item.slot and (worn := wardrobe_wearers(library, item.id)):
        raise ValueError(f"{item.id} is worn as a {old.slot} by {', '.join(cid for _, cid in worn)}: keep its slot")
    _put(library, "wardrobe.json", lib, "wardrobe", item)
    return _clear_approvals(wardrobe_wearers(library, item.id)) if old and old != item else []


def delete_wardrobe_item(library, item_id: str) -> None:
    """remove a custom wardrobe item; refused (ValueError) while any cast member wears it"""
    _remove(library, "wardrobe.json", load_wardrobe(library), "wardrobe", item_id,
            ("worn by", lambda: _cast_names(wardrobe_wearers(library, item_id))))


def creature_users(library, creature_id: str) -> list[tuple[Path, str]]:
    """(series.json, cast id) for every cast member, in every series of the library, with this body"""
    return _cast_using(library, "creatures", creature_id)


def save_creature(library, creature: CustomCreature) -> list[str]:
    """add or replace a creature. A changed drawing changes the look of every cast member with that body, so their
    approvals are cleared (like save_prop). Returns "<slug>/<cast id>" for each approval cleared."""
    old = _put(library, "creatures.json", load_creatures(library), "creatures", creature)
    changed = old and old.model_dump(exclude={"name"}) != creature.model_dump(exclude={"name"})
    return _clear_approvals(creature_users(library, creature.id)) if changed else []


def delete_creature(library, creature_id: str) -> None:
    """remove a creature; refused (ValueError) while any cast member has it as its body"""
    _remove(library, "creatures.json", load_creatures(library), "creatures", creature_id,
            ("the body of", lambda: _cast_names(creature_users(library, creature_id))))


def load_actions(library) -> ActionLibrary:
    """library/actions.json (custom actions: keyframes the stickman plays, shared by every series); none yet: empty"""
    return _load_library(library, "actions.json", ActionLibrary)


def custom_actions(library) -> dict[str, CustomAction]:
    """library/actions.json by id: what @do may ask for besides the built-in actions"""
    return {a.id: a for a in load_actions(library).actions}


def custom_moves(library) -> dict[str, float]:
    """custom action id -> its move (units/s, - backward) for the ones that cross the stage (validate's moves)"""
    return {k: a.move for k, a in custom_actions(library).items() if a.move}


def action_users(library, action_id: str) -> list[str]:
    """"<slug>/<part id>" for every story.md in the library with an @do clause using this action"""
    used = re.compile(rf":\s*{re.escape(action_id)}\s*(,|$)")  # a clause's action follows its colon
    return _stories_with(library, lambda line: line.startswith("@do") and used.search(line))


def save_action(library, action: CustomAction) -> None:
    """add or replace a custom action (in-place moves: no cast approval depends on them)"""
    _put(library, "actions.json", load_actions(library), "actions", action)


def delete_action(library, action_id: str) -> None:
    """remove a custom action; refused (ValueError) while any story.md uses it in an @do"""
    _remove(library, "actions.json", load_actions(library), "actions", action_id,
            ("used by", lambda: action_users(library, action_id)))


def unknown_actions(story, library) -> list[str]:
    """actor actions in a story.json that are neither built in nor in library/actions.json (the engine would throw)"""
    known = set(ACTIONS) | set(custom_actions(library))
    return sorted({a.action for s in story.shots for a in s.actors} - known)


def load_sets(library) -> SetLibrary:
    """library/sets.json (custom sets, shared by every series); none yet: an empty library"""
    return _load_library(library, "sets.json", SetLibrary)


def load_objects(library) -> WorldObjectLibrary:
    """library/objects.json: reusable geometry and capabilities for large scene objects."""
    return _load_library(library, "objects.json", WorldObjectLibrary)


def world_object_kinds(library) -> dict[str, WorldObject]:
    """World Object definitions by id; set instances are validated against this catalog by callers."""
    return {o.id: o for o in load_objects(library).objects}


def save_object(library, obj: WorldObject) -> None:
    """add or replace a world object; ValueError when the prop it is held as (pickup) is no prop"""
    if obj.prop and obj.prop not in prop_kinds(library):
        raise ValueError(f"prop {obj.prop!r} (held after pickup) is not a prop: built in or on the Props page")
    _put(library, "objects.json", load_objects(library), "objects", obj)


def object_users(library, object_id: str) -> list[str]:
    """"<slug>/<part id>" for every story.md with an "@item <tag>: <object_id> ..." line, and "set <id>" for every
    custom set placing it"""
    def places(line: str) -> bool:
        head, sep, rest = line.partition(":")
        return line.startswith("@item ") and bool(sep) and rest.split()[:1] == [object_id]
    return _stories_with(library, places) + [f"set {s.id}" for s in load_sets(library).sets
                                             if any(i.object == object_id for i in s.objects)]


def delete_object(library, object_id: str) -> None:
    """remove a World Item; refused (ValueError) while any story's @item or any set places it"""
    _remove(library, "objects.json", load_objects(library), "objects", object_id,
            ("used by", lambda: object_users(library, object_id)))


def set_kinds(library) -> dict[str, str]:
    """every name @set can use -> "indoor" | "outdoor": the built-ins, then the library's custom sets"""
    return {**BUILTIN_SETS, **{s.id: s.kind for s in load_sets(library).sets}}


def set_weather(library) -> dict:
    """custom set id -> its default_weather (Weather or None); built-in sets start clear"""
    return {s.id: s.default_weather for s in load_sets(library).sets}


def outdoor_sets(library) -> set[str]:
    """the sets that can scroll (travel shots)"""
    return {k for k, v in set_kinds(library).items() if v == "outdoor"}


def set_users(library, set_id: str) -> list[str]:
    """"<slug>/<part id>" for every story.md in the library with an @set <set_id> line"""
    return _stories_with(library, lambda line: line == f"@set {set_id}")


def save_set(library, custom: CustomSet) -> None:
    """add or replace a custom set"""
    _put(library, "sets.json", load_sets(library), "sets", custom)


def delete_set(library, set_id: str) -> None:
    """remove a custom set; refused (ValueError) while any story uses it"""
    _remove(library, "sets.json", load_sets(library), "sets", set_id, ("used by", lambda: set_users(library, set_id)))


def load_part(path) -> PartModel:
    """the part whose folder holds this (former) part.json path; FileNotFoundError when there is none"""
    pdir = Path(path).parent
    adopt(pdir.parent)
    library, slug = series_where(pdir.parent)
    data = db.get_part(library, slug, pdir.name)
    if data is None:
        raise FileNotFoundError(f"no part in {pdir}")
    return PartModel.model_validate(data)


def part_exists(part_dir) -> bool:
    part_dir = Path(part_dir)
    adopt(part_dir.parent)
    return db.get_part(*series_where(part_dir.parent), part_dir.name) is not None


def part_folders_of(series_dir) -> dict[str, str]:
    """part id -> its folder name, by number"""
    adopt(series_dir)
    return db.part_folders(*series_where(series_dir))


def part_dir_of(series_dir, part_id: str) -> Path:
    """the folder of this part (series_dir / its folder; series_dir / part_id when there is no such part)"""
    return Path(series_dir) / part_folders_of(series_dir).get(part_id, part_id)


def part_id_of(part_dir) -> str:
    """the part id (part-NN) of a part folder"""
    return load_part(Path(part_dir) / PART_FILE).id


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "new-story"


def part_folder_name(number: int, title: str) -> str:
    """a part's folder: 01-<title slug>, so folders sort in part order and never clash"""
    return f"{number:02d}-{slugify(title)}"


def _managed_series_status(series_dir: Path, model: SeriesModel) -> str:
    """Derive the workflow status while leaving archived as an explicit manual state."""
    if model.status == "archived":
        return "archived"
    folders = list(part_folders_of(series_dir).values())
    if not folders:
        return "draft"
    parts = [load_part(series_dir / f / PART_FILE) for f in folders]
    complete = all(p.stages.finish.status == "done"
                   and p.approvals.final.approved_at
                   and (p.posted.youtube or p.posted.instagram)
                   for p in parts)
    return "complete" if complete else "active"


def write_series(path, model: SeriesModel) -> None:
    """store the series as it is: approvals cleared on purpose stay cleared (save_series keeps every approval)"""
    d = Path(path).parent
    library, slug = series_where(d)
    db.put_series(library, {**model.model_dump(mode="json"), "slug": slug}, cast_uses(model))


def save_series(path, model: SeriesModel) -> None:
    """add or update the series of this (former) series.json path; never drops a cast approval. Its parts are
    their own rows (save_part): model.parts is not stored."""
    d = Path(path).parent
    if series_exists(d):
        on_disk = {c.id: c.approved_at for c in load_series(path).cast}
        for c in model.cast:
            if c.approved_at is None and on_disk.get(c.id):
                c.approved_at = on_disk[c.id]
        model.status = _managed_series_status(d, model)
    else:
        model.status = "draft" if model.status != "archived" else "archived"
    write_series(path, model)


def save_part(path, model: PartModel, *, drop_approvals: bool = False) -> None:
    """add or update the part in the folder of this (former) part.json path; never drops an approval unless
    drop_approvals (reopen: the part starts over)"""
    pdir = Path(path).parent
    library, slug = series_where(pdir.parent)
    if part_exists(pdir) and not drop_approvals:
        old = load_part(path).approvals
        for name in ("stills", "final"):
            kept = getattr(old, name).approved_at
            if kept and getattr(model.approvals, name).approved_at is None:
                getattr(model.approvals, name).approved_at = kept
    db.put_part(library, slug, pdir.name, model.model_dump(mode="json"))
    series = load_series(pdir.parent / SERIES_FILE)
    updated = _managed_series_status(pdir.parent, series)
    if series.status != updated:
        series.status = updated
        write_series(pdir.parent / SERIES_FILE, series)


def series_bytes(series_dir) -> bytes | None:
    """the series as its old series.json held it, byte for byte (None: no such series), so stage and frame hashes
    over ../series.json stay what they were before the database"""
    if not series_exists(series_dir):
        return None
    if (text := db.series_file_text(*series_where(series_dir))) is not None:
        return text.encode()  # imported and not saved since: the file's own bytes
    d = load_series(Path(series_dir) / SERIES_FILE).model_dump(mode="json")
    d["voice"].pop("tts", None)  # the TTS voices (narrator, cast): hashed by the tts stage alone, so choosing one
    for c in d["cast"]:            # never re-plans or re-renders
        c.pop("voice", None)
    return (json.dumps(d, indent=2, ensure_ascii=False) + "\n").encode()


# ---- stored files (db.StoredFile): the files of a series folder and their metadata ----

UNTRACKED_DIRS = {"frames", "cast-frames"}  # thousands of render frames each: no row per frame
MEDIA = {".mp3", ".wav", ".mp4", ".m4a"}  # files with a duration
CONTENT_TYPES = {".md": "text/markdown", ".txt": "text/plain", ".json": "application/json", ".ass": "text/x-ssa",
                 ".key": "text/plain", ".png": "image/png", ".jpg": "image/jpeg", ".mp3": "audio/mpeg",
                 ".wav": "audio/wav", ".m4a": "audio/mp4", ".mp4": "video/mp4"}


def _iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(f: Path) -> str:
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sync_files(series_dir) -> int:
    """bring the stored_file rows of a series folder up to date: a new or changed file (size or modified time) is
    measured and hashed again, the row of a file gone is dropped. Returns how many rows changed."""
    from . import ff  # ffprobe only when something is measured (ff imports the stage runner, which imports io)
    d = Path(series_dir)
    if not series_exists(d):
        return 0
    library, slug = series_where(d)
    root = storage_root(library)
    part_of = {folder: pid for pid, folder in part_folders_of(d).items()}
    known = {(r["path"], r["filename"]): r for r in db.get_files(library, slug)}
    seen, rows = set(), []
    for f in sorted(d.rglob("*")):
        rel = f.relative_to(d)
        if (not f.is_file() or UNTRACKED_DIRS & set(rel.parts) or f.name.startswith(".")
                or f.name.endswith((".imported", ".tmp"))):
            continue
        st = f.stat()
        key = (f.parent.relative_to(root).as_posix(), f.name)
        seen.add(key)
        updated, old = _iso(st.st_mtime), known.get(key)
        if old and (old["size_bytes"], old["updated_at"]) == (st.st_size, updated):
            continue
        rows.append({"part": part_of.get(rel.parts[0]) if len(rel.parts) > 1 else None, "path": key[0],
                     "filename": f.name, "size_bytes": st.st_size,
                     "content_type": CONTENT_TYPES.get(f.suffix.lower(), "application/octet-stream"),
                     "duration_s": ff.duration(f) if f.suffix.lower() in MEDIA else None, "sha256": _sha256(f),
                     "created_at": old["created_at"] if old else _iso(time.time()), "updated_at": updated})
    gone = [k for k in known if k not in seen]
    if rows or gone:
        db.put_files(library, slug, rows, gone)
    return len(rows) + len(gone)
