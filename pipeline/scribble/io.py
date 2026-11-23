"""Load/save series.json, part.json and the shared catalogs (database: db.py). Writes are atomic; saves never drop an existing approval."""

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
# their old file: every stage that reads one, and the render hash, depends on all of them (catalog_bytes).
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
    return p.parents[1] if p.name.startswith("part-") else p.parents[2]


def series_dirs(library) -> list[Path]:
    """every series folder of the library (a folder holding series.json), by slug"""
    root = storage_root(library)
    return sorted(d for d in root.iterdir() if (d / "series.json").is_file()) if root.is_dir() else []


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
    return SeriesModel.model_validate_json(Path(path).read_bytes())


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


def _cast_with(library, wants) -> list[tuple[Path, str]]:
    """(series.json, cast id) for every cast member, in every series of the library, that wants(member)"""
    return [(f, c.id) for f in sorted(storage_root(library).glob("*/series.json")) for c in load_series(f).cast if wants(c)]


def _cast_names(pairs) -> list[str]:
    """(series.json, cast id) pairs as "<series folder>/<cast id>" """
    return [f"{f.parent.name}/{cid}" for f, cid in pairs]


def _stories_with(library, wants) -> list[str]:
    """"<slug>/<part id>" for every story.md in the library with a line (stripped) that wants(line)"""
    return [f"{f.parent.parent.name}/{f.parent.name}" for f in sorted(storage_root(library).glob("*/part-*/story.md"))
            if any(wants(line.strip()) for line in f.read_text(encoding="utf-8").splitlines())]


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
    return _cast_with(library, lambda c: any(p.kind == kind for p in c.props))


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
            ("used by @do in", lambda: prop_users(library, prop_id)))


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
    return _cast_with(library, lambda c: any(wid == item_id for _, wid in c.wardrobe()))


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
            atomic_write_json(f, series.model_dump(mode="json"))
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
    return _cast_with(library, lambda c: c.body == creature_id)


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
    """add or replace a world object"""
    _put(library, "objects.json", load_objects(library), "objects", obj)


def delete_object(library, object_id: str) -> None:
    """remove a world object"""
    _remove(library, "objects.json", load_objects(library), "objects", object_id)


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
    return PartModel.model_validate_json(Path(path).read_bytes())


def _managed_series_status(path: Path, model: SeriesModel) -> str:
    """Derive the workflow status while leaving archived as an explicit manual state."""
    if model.status == "archived":
        return "archived"
    if not model.parts:
        return "draft"
    parts = [load_part(path.parent / pid / "part.json") if (path.parent / pid / "part.json").is_file() else None
             for pid in model.parts]
    complete = all(p is not None and p.stages.finish.status == "done"
                   and p.approvals.final.approved_at
                   and (p.posted.youtube or p.posted.instagram)
                   for p in parts)
    return "complete" if complete else "active"


def save_series(path, model: SeriesModel) -> None:
    path = Path(path)
    if path.exists():
        on_disk = {c.id: c.approved_at for c in load_series(path).cast}
        for c in model.cast:
            if c.approved_at is None and on_disk.get(c.id):
                c.approved_at = on_disk[c.id]
    model.status = _managed_series_status(path, model)
    atomic_write_json(path, model.model_dump(mode="json"))


def save_part(path, model: PartModel) -> None:
    path = Path(path)
    if path.exists():
        old = load_part(path).approvals
        for name in ("stills", "final"):
            kept = getattr(old, name).approved_at
            if kept and getattr(model.approvals, name).approved_at is None:
                getattr(model.approvals, name).approved_at = kept
    atomic_write_json(path, model.model_dump(mode="json"))
    series_path = path.parent.parent / "series.json"
    if series_path.is_file():
        series = load_series(series_path)
        updated = _managed_series_status(series_path, series)
        if series.status != updated:
            series.status = updated
            atomic_write_json(series_path, series.model_dump(mode="json"))
