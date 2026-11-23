"""The six shared library catalogs (props, creatures, wardrobe, actions, sets, objects)."""

import inspect
from typing import get_args

from fastapi import HTTPException, APIRouter
from pydantic import BaseModel

from api.core import lib
from api.events import publish
from api.jobs import check_no_jobs
from pipeline.scribble.io import (delete_prop, delete_set, delete_object, load_props, load_sets, save_prop, save_set,
                                  delete_creature, load_creatures, save_creature, delete_action, load_actions,
                                  save_action, delete_wardrobe_item, load_wardrobe, save_wardrobe_item, load_objects,
                                  save_object)
from pipeline.scribble.schemas import (ACTIONS, BUILTIN_CREATURES, BUILTIN_SETS, BuiltinProp, CreatureRig,
                                       CustomAction, CustomCreature, actions_with, CustomProp, CustomSet, SetKind,
                                       Slug, WorldObject, BUILTIN_WARDROBE, WardrobeId, WardrobeItem,
                                       WardrobeSlotName)

router = APIRouter()


# ---------------- props (library/props.json, shared by every series) ----------------

class PropCatalog(BaseModel):
    builtin: list[BuiltinProp]
    custom: list[CustomProp]
    cleared: list[str] = []  # after a save: "<slug>/<cast id>" approvals cleared because the drawing changed


def prop_catalog(cleared=()) -> PropCatalog:
    return PropCatalog(builtin=list(get_args(BuiltinProp)), custom=load_props(lib()).props, cleared=list(cleared))


def library_routes(kind: str, one: str, noun: str, catalog, save, delete, model, id_type=Slug) -> None:
    """GET /api/<kind>, PUT and DELETE /api/<kind>/{item_id}: one shared catalog, library/<kind>.json. Every render
    reads it, so nothing changes while a job runs. A save can clear cast approvals (its drawing changed): those
    series hear about it too. one: the route names (put_<one>, remove_<one>); noun: for the 404."""
    response_model = inspect.signature(catalog).return_annotation

    def put(item_id: id_type, body: model):
        if body.id != item_id:
            raise HTTPException(409, f"body id {body.id!r} does not match {item_id!r}")
        check_no_jobs()
        lib().mkdir(parents=True, exist_ok=True)
        try:
            cleared = save(lib(), body) or []
        except ValueError as e:
            raise HTTPException(409, str(e))
        publish(f"{kind}-changed", {"id": item_id})
        for slug in {c.split("/")[0] for c in cleared}:
            publish("series-changed", {"slug": slug})
        return catalog(cleared) if cleared else catalog()

    def remove(item_id: id_type):
        check_no_jobs()
        try:
            delete(lib(), item_id)
        except KeyError:
            raise HTTPException(404, f"no {noun} {item_id!r}")
        except ValueError as e:
            raise HTTPException(409, str(e))
        publish(f"{kind}-changed", {"id": item_id})
        return catalog()

    router.get(f"/api/{kind}", response_model=response_model, name=f"get_{kind}")(lambda: catalog())
    router.put(f"/api/{kind}/{{item_id}}", response_model=response_model, name=f"put_{one}")(put)
    router.delete(f"/api/{kind}/{{item_id}}", response_model=response_model, name=f"remove_{one}")(remove)


library_routes("props", "prop", "custom prop", prop_catalog, save_prop, delete_prop, CustomProp)


# ---------------- creatures (library/creatures.json, shared by every series) ----------------

class BuiltinCreature(BaseModel):
    id: str
    rig: CreatureRig


class CreatureCatalog(BaseModel):
    builtin: list[BuiltinCreature]  # drawn by engine/page/creatures.js BUILTIN (the editor previews them from there)
    custom: list[CustomCreature]
    cleared: list[str] = []  # after a save: "<slug>/<cast id>" approvals cleared because the drawing changed


def creature_catalog(cleared=()) -> CreatureCatalog:
    return CreatureCatalog(builtin=[BuiltinCreature(id=k, rig=v[0]) for k, v in BUILTIN_CREATURES.items()],
                           custom=load_creatures(lib()).creatures, cleared=list(cleared))


library_routes("creatures", "creature", "custom creature", creature_catalog, save_creature, delete_creature,
               CustomCreature)


# ---------------- wardrobe (library/wardrobe.json: clothing, hair, cosmetics, shared by every series) ----------------

class BuiltinWardrobeItem(BaseModel):
    id: str
    name: str
    slot: WardrobeSlotName


class WardrobeCatalog(BaseModel):
    builtin: list[BuiltinWardrobeItem]  # hand-drawn by engine/page/stickman.js: read only
    custom: list[WardrobeItem]
    cleared: list[str] = []  # after a save: "<slug>/<cast id>" approvals cleared because the drawing changed


def wardrobe_catalog(cleared=()) -> WardrobeCatalog:
    return WardrobeCatalog(builtin=[BuiltinWardrobeItem(id=k, slot=v[0], name=v[1]) for k, v in BUILTIN_WARDROBE.items()],
                           custom=load_wardrobe(lib()).wardrobe, cleared=list(cleared))


library_routes("wardrobe", "wardrobe_item", "custom wardrobe item", wardrobe_catalog, save_wardrobe_item,
               delete_wardrobe_item, WardrobeItem, WardrobeId)


# ---------------- actions (library/actions.json: custom moves, shared by every series) ----------------

class ActionCatalog(BaseModel):
    builtin: list[str]  # code in the engine (schemas ACTIONS); @do may ask for those with the "do" trait
    do: list[str]       # the built-ins @do accepts
    custom: list[CustomAction]


def action_catalog() -> ActionCatalog:
    return ActionCatalog(builtin=list(ACTIONS), do=sorted(actions_with("do")), custom=load_actions(lib()).actions)


library_routes("actions", "action", "custom action", action_catalog, save_action, delete_action, CustomAction)


# ---------------- sets (library/sets.json, shared by every series) ----------------

class BuiltinSet(BaseModel):
    id: str
    kind: SetKind


class SetCatalog(BaseModel):
    builtin: list[BuiltinSet]
    custom: list[CustomSet]


def set_catalog() -> SetCatalog:
    return SetCatalog(builtin=[BuiltinSet(id=k, kind=v) for k, v in BUILTIN_SETS.items()], custom=load_sets(lib()).sets)


library_routes("sets", "set", "custom set", set_catalog, save_set, delete_set, CustomSet)


# ---------------- world objects (library/objects.json, shared by every series) ----------------

class WorldObjectCatalog(BaseModel):
    objects: list[WorldObject]


def object_catalog() -> WorldObjectCatalog:
    return WorldObjectCatalog(objects=load_objects(lib()).objects)


library_routes("objects", "object", "world object", object_catalog, save_object, delete_object, WorldObject)
