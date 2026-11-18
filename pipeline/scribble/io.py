"""Load/save series.json, part.json, library/props.json and library/sets.json. Writes are atomic; saves never drop an existing approval."""

import json
import os
import re
import tempfile
import time
from pathlib import Path

from typing import get_args

from .schemas import (ACTIONS, BUILTIN_CREATURES, BUILTIN_SETS, ActionLibrary, BuiltinProp, CreatureLibrary,
                      CustomAction, CustomCreature, CustomProp, CustomSet, PartModel, PropLibrary, SeriesModel, SetLibrary)

# User-owned files a save must never write to.
PROTECTED = {"story.md", "voice.mp3"}
# The library's custom items, one file per kind (engine/page/library.js KINDS): every stage that reads one, and the
# render hash, depends on all of them, so a new kind of custom item is one entry here.
LIBRARY_FILES = ["props.json", "sets.json", "creatures.json", "actions.json"]
REPLACE_RETRIES = 5


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


def load_props(library) -> PropLibrary:
    """library/props.json (custom props, shared by every series); none yet: an empty library"""
    f = Path(library) / "props.json"
    return PropLibrary.model_validate_json(f.read_bytes()) if f.exists() else PropLibrary()


def prop_kinds(library) -> list[str]:
    """every prop kind a cast member or @do can use: the built-ins, then the library's custom props"""
    return [*get_args(BuiltinProp), *(p.id for p in load_props(library).props)]


def unknown_cast_props(cast, library) -> list[str]:
    """'<cast id>: <kind>' for each held prop that is neither built in nor in library/props.json"""
    known = set(prop_kinds(library))
    return [f"{c.id}: {p.kind}" for c in cast for p in c.props if p.kind not in known]


def prop_holders(library, kind: str) -> list[tuple[Path, str]]:
    """(series.json, cast id) for every cast member, in every series of the library, holding a prop of this kind"""
    return [(f, c.id) for f in sorted(Path(library).glob("*/series.json")) for c in load_series(f).cast
            if any(p.kind == kind for p in c.props)]


def save_prop(library, prop: CustomProp) -> list[str]:
    """add or replace a custom prop. A changed drawing changes the look of everyone holding it, so their cast
    approvals are cleared (like cast-edit). Returns "<slug>/<cast id>" for each approval cleared."""
    lib = load_props(library)
    old = next((p for p in lib.props if p.id == prop.id), None)
    lib.props = [prop if p.id == prop.id else p for p in lib.props] if old else [*lib.props, prop]
    atomic_write_json(Path(library) / "props.json", lib.model_dump(mode="json"))
    cleared = []
    if old and old.shapes != prop.shapes:
        for f, cid in prop_holders(library, prop.id):
            series = load_series(f)
            c = next(c for c in series.cast if c.id == cid)
            if c.approved_at:
                c.approved_at = None
                # written directly: save_series would restore the approval (it only ever adds approvals)
                atomic_write_json(f, series.model_dump(mode="json"))
                cleared.append(f"{series.slug}/{cid}")
    return cleared


def prop_users(library, kind: str) -> list[str]:
    """"<slug>/<part id>" for every story.md in the library with an @do line naming this prop (eat / give)"""
    # ponytail: whole-word match, so a cast id equal to the prop id also counts (blocks a delete, never breaks one)
    word = re.compile(rf"(?<![\w-]){re.escape(kind)}(?![\w-])")
    return [f"{f.parent.parent.name}/{f.parent.name}" for f in sorted(Path(library).glob("*/part-*/story.md"))
            if any(line.strip().startswith("@do") and word.search(line)
                   for line in f.read_text(encoding="utf-8").splitlines())]


def delete_prop(library, prop_id: str) -> None:
    """remove a custom prop; refused (ValueError) while any cast member holds it or any story's @do uses it"""
    lib = load_props(library)
    if not any(p.id == prop_id for p in lib.props):
        raise KeyError(prop_id)
    if held := prop_holders(library, prop_id):
        raise ValueError(f"{prop_id} is still held by " + ", ".join(f"{f.parent.name}/{cid}" for f, cid in held))
    if used := prop_users(library, prop_id):
        raise ValueError(f"{prop_id} is still used by @do in " + ", ".join(used))
    lib.props = [p for p in lib.props if p.id != prop_id]
    atomic_write_json(Path(library) / "props.json", lib.model_dump(mode="json"))



def load_creatures(library) -> CreatureLibrary:
    """library/creatures.json (custom cast bodies, shared by every series); none yet: an empty library"""
    f = Path(library) / "creatures.json"
    return CreatureLibrary.model_validate_json(f.read_bytes()) if f.exists() else CreatureLibrary()


def creature_bodies(library) -> dict[str, tuple[str, bool]]:
    """every creature a cast member can be: id -> (rig, has a stump); built-ins first, then library/creatures.json"""
    return {**BUILTIN_CREATURES, **{c.id: (c.rig, bool(c.parts.get("stump"))) for c in load_creatures(library).creatures}}


def cast_body_problems(cast, library) -> list[str]:
    """'<cast id>: <problem>' for each body that is not built in or in library/creatures.json, and each headless cast
    member whose creature has no stump"""
    bodies, out = creature_bodies(library), []
    for c in cast:
        if c.body not in bodies:
            out.append(f"{c.id}: unknown body {c.body!r} ({', '.join(bodies)})")
        elif c.headless and c.body in bodies and not bodies[c.body][1]:
            out.append(f"{c.id}: headless, but creature {c.body!r} has no stump part")
    return out


def creature_users(library, creature_id: str) -> list[tuple[Path, str]]:
    """(series.json, cast id) for every cast member, in every series of the library, with this body"""
    return [(f, c.id) for f in sorted(Path(library).glob("*/series.json")) for c in load_series(f).cast
            if c.body == creature_id]


def save_creature(library, creature: CustomCreature) -> list[str]:
    """add or replace a creature. A changed drawing changes the look of every cast member with that body, so their
    approvals are cleared (like save_prop). Returns "<slug>/<cast id>" for each approval cleared."""
    lib = load_creatures(library)
    old = next((c for c in lib.creatures if c.id == creature.id), None)
    lib.creatures = [creature if c.id == creature.id else c for c in lib.creatures] if old else [*lib.creatures, creature]
    atomic_write_json(Path(library) / "creatures.json", lib.model_dump(mode="json"))
    cleared = []
    if old and old.model_dump(exclude={"name"}) != creature.model_dump(exclude={"name"}):
        for f, cid in creature_users(library, creature.id):
            series = load_series(f)
            c = next(c for c in series.cast if c.id == cid)
            if c.approved_at:
                c.approved_at = None
                atomic_write_json(f, series.model_dump(mode="json"))  # directly: save_series keeps approvals
                cleared.append(f"{series.slug}/{cid}")
    return cleared


def delete_creature(library, creature_id: str) -> None:
    """remove a creature; refused (ValueError) while any cast member has it as its body"""
    lib = load_creatures(library)
    if not any(c.id == creature_id for c in lib.creatures):
        raise KeyError(creature_id)
    if used := creature_users(library, creature_id):
        raise ValueError(f"{creature_id} is still the body of " + ", ".join(f"{f.parent.name}/{cid}" for f, cid in used))
    lib.creatures = [c for c in lib.creatures if c.id != creature_id]
    atomic_write_json(Path(library) / "creatures.json", lib.model_dump(mode="json"))


def load_actions(library) -> ActionLibrary:
    """library/actions.json (custom actions: keyframes the stickman plays, shared by every series); none yet: empty"""
    f = Path(library) / "actions.json"
    return ActionLibrary.model_validate_json(f.read_bytes()) if f.exists() else ActionLibrary()


def custom_actions(library) -> list[str]:
    """the ids of library/actions.json: what @do may ask for besides the built-in actions"""
    return [a.id for a in load_actions(library).actions]


def action_users(library, action_id: str) -> list[str]:
    """"<slug>/<part id>" for every story.md in the library with an @do clause using this action"""
    used = re.compile(rf":\s*{re.escape(action_id)}\s*(,|$)")  # a clause's action follows its colon
    return [f"{f.parent.parent.name}/{f.parent.name}" for f in sorted(Path(library).glob("*/part-*/story.md"))
            if any(line.strip().startswith("@do") and used.search(line)
                   for line in f.read_text(encoding="utf-8").splitlines())]


def save_action(library, action: CustomAction) -> None:
    """add or replace a custom action (in-place moves: no cast approval depends on them)"""
    lib = load_actions(library)
    lib.actions = [action if a.id == action.id else a for a in lib.actions] if any(a.id == action.id for a in lib.actions) \
        else [*lib.actions, action]
    atomic_write_json(Path(library) / "actions.json", lib.model_dump(mode="json"))


def delete_action(library, action_id: str) -> None:
    """remove a custom action; refused (ValueError) while any story.md uses it in an @do"""
    lib = load_actions(library)
    if not any(a.id == action_id for a in lib.actions):
        raise KeyError(action_id)
    if used := action_users(library, action_id):
        raise ValueError(f"{action_id} is still used by " + ", ".join(used))
    lib.actions = [a for a in lib.actions if a.id != action_id]
    atomic_write_json(Path(library) / "actions.json", lib.model_dump(mode="json"))


def unknown_actions(story, library) -> list[str]:
    """actor actions in a story.json that are neither built in nor in library/actions.json (the engine would throw)"""
    known = set(ACTIONS) | set(custom_actions(library))
    return sorted({a.action for s in story.shots for a in s.actors} - known)


def load_sets(library) -> SetLibrary:
    """library/sets.json (custom sets, shared by every series); none yet: an empty library"""
    f = Path(library) / "sets.json"
    return SetLibrary.model_validate_json(f.read_bytes()) if f.exists() else SetLibrary()


def set_kinds(library) -> dict[str, str]:
    """every name @set can use -> "indoor" | "outdoor": the built-ins, then the library's custom sets"""
    return {**BUILTIN_SETS, **{s.id: s.kind for s in load_sets(library).sets}}


def outdoor_sets(library) -> set[str]:
    """the sets that can scroll (travel shots)"""
    return {k for k, v in set_kinds(library).items() if v == "outdoor"}


def set_users(library, set_id: str) -> list[str]:
    """"<slug>/<part id>" for every story.md in the library with an @set <set_id> line"""
    want = f"@set {set_id}"
    return [f"{f.parent.parent.name}/{f.parent.name}" for f in sorted(Path(library).glob("*/part-*/story.md"))
            if any(line.strip() == want for line in f.read_text(encoding="utf-8").splitlines())]


def save_set(library, custom: CustomSet) -> None:
    """add or replace a custom set"""
    lib = load_sets(library)
    lib.sets = [custom if s.id == custom.id else s for s in lib.sets] if any(s.id == custom.id for s in lib.sets)         else [*lib.sets, custom]
    atomic_write_json(Path(library) / "sets.json", lib.model_dump(mode="json"))


def delete_set(library, set_id: str) -> None:
    """remove a custom set; refused (ValueError) while any story uses it"""
    lib = load_sets(library)
    if not any(s.id == set_id for s in lib.sets):
        raise KeyError(set_id)
    if used := set_users(library, set_id):
        raise ValueError(f"{set_id} is still used by " + ", ".join(used))
    lib.sets = [s for s in lib.sets if s.id != set_id]
    atomic_write_json(Path(library) / "sets.json", lib.model_dump(mode="json"))


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
