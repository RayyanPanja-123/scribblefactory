"""Wardrobe: cast slot values, @look outfits, built-ins kept, library save / delete, story package WARDROBE."""

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.scribble import package
from pipeline.scribble.io import (WARDROBE_SEED, cast_wardrobe_problems, delete_wardrobe_item, load_series, load_wardrobe,
                                  save_series, save_wardrobe_item, wardrobe_slots)
from pipeline.scribble.schemas import (BUILTIN_WARDROBE, DRAW_ORDER, WARDROBE_SLOTS, CastMember, SeriesModel, WardrobeItem,
                                       WardrobeLibrary)
from pipeline.tests.test_package import CAST, pkg

ROOT = Path(__file__).resolve().parents[2]
T = "2026-01-01T00:00:00Z"
ITEM = {"id": "plume_helm", "name": "Plume helm", "slot": "headwear", "default_color": "#b0283a",
        "layers": [{"shape": "rect", "anchor": "head_top", "pts": [[-90, -40], [90, 60]], "fill": "$color"}]}


def member(**kw):
    return CastMember.model_validate({"id": "nero", "name": "Nero", "eyes": "dots", "top": {"color": "#f3efe2"}, **kw})


def test_slot_values_string_object_null_and_lists():
    a = member(hair="wild_hair", facial_hair={"id": "long_beard", "color": "#e8e8e8"}, footwear=None, back="none",
               accessory="belt", face=["glasses", "none", {"id": "blush"}])
    assert (a.hair.id, a.hair.color) == ("wild_hair", None)
    assert (a.facial_hair.id, a.facial_hair.color) == ("long_beard", "#e8e8e8")
    assert a.footwear is None and a.back is None
    assert [x.id for x in a.accessory] == ["belt"] and [x.id for x in a.face] == ["glasses", "blush"]
    # top / headwear / legwear: a plain id or {"id"} next to the original {"style"} / {"kind"}
    b = member(top={"id": "robe", "color": "#6b4f8a"}, headwear="crown", legwear=None)
    assert (b.top.style, b.headwear.kind, b.legwear.kind) == ("robe", "crown", "none")
    for bad in [{"face": ["a", "b", "c", "d"]}, {"hair": {"id": "Wild Hair"}}, {"hair": {"id": "x", "color": "red"}},
                {"headwear": "bowler"}, {"top": "robe"}]:  # bowler needs a colour; a top needs its colour
        with pytest.raises(ValidationError):
            member(**bad)


def test_old_casts_load_unchanged_and_wear_builtins():
    """built-in tops / headwear / legwear are wardrobe items with the same ids: an old entry needs no change"""
    old = {"id": "sul", "name": "Sul", "eyes": "dots", "top": {"style": "suit", "color": "#1f3a68", "accent_color": "#c0392b"},
           "headwear": {"kind": "bowler", "color": "#333333"}, "legwear": {"kind": "trousers", "color": "#222222"}}
    c = CastMember.model_validate(old)
    assert c.wardrobe() == [("top", "suit"), ("headwear", "bowler"), ("legwear", "trousers")]
    assert cast_wardrobe_problems([c], "nowhere") == []
    dumped = c.model_dump(mode="json")
    assert dumped["top"]["style"] == "suit" and dumped["headwear"] == {"kind": "bowler", "color": "#333333"}
    assert {k: v[0] for k, v in BUILTIN_WARDROBE.items()} == {k: v for k, v in wardrobe_slots("nowhere").items() if k in BUILTIN_WARDROBE}


def test_builtins_and_draw_order_match_the_engine():
    js = (ROOT / "engine" / "page" / "wardrobe.js").read_text(encoding="utf-8")
    block = js.split("BUILTIN_WARDROBE = {")[1].split("};")[0]
    assert dict(re.findall(r"(\w+): \"(\w+)\"", block)) == {k: v[0] for k, v in BUILTIN_WARDROBE.items()}
    assert json.loads(re.search(r"DRAW_ORDER = (\[.*?\]);", js)[1]) == DRAW_ORDER
    assert json.loads(re.search(r"SLOTS = (\[.*?\]);", js)[1]) == WARDROBE_SLOTS


def test_seed_has_the_starter_items():
    ids = {w.id: w.slot for w in WardrobeLibrary.model_validate_json(WARDROBE_SEED.read_bytes()).wardrobe}
    assert ids == {"short_hair": "hair", "long_hair": "hair", "wild_hair": "hair", "bald": "hair", "stubble": "facial_hair",
                   "moustache": "facial_hair", "short_beard": "facial_hair", "long_beard": "facial_hair",
                   "crown": "headwear", "sea_crown": "headwear", "hood": "headwear", "toga": "top", "robe": "top",
                   "armor": "top", "sandals": "footwear", "boots": "footwear", "cape": "back", "necklace": "accessory",
                   "belt": "accessory", "glasses": "face", "scar": "face", "face_paint": "face", "blush": "face"}


def test_unknown_or_wrong_slot_ids_are_problems(tmp_path):
    c = member(hair="crown", headwear="mohawk", looks={"x": {"face": ["boots"]}})
    assert cast_wardrobe_problems([c], tmp_path) == [
        "nero: unknown headwear 'mohawk' (flat_cap, postman_cap, bowler, straw_hat, wide_hat, crown, sea_crown, hood)",
        "nero: 'crown' is a headwear, not a hair",
        "nero: 'boots' is a footwear, not a face"]
    assert cast_wardrobe_problems([member(top={"id": "suit", "color": "#111111"})], tmp_path) == []
    with pytest.raises(ValidationError):
        WardrobeItem.model_validate({**ITEM, "id": "bowler"})  # a built-in id
    with pytest.raises(ValidationError):
        WardrobeItem.model_validate({**ITEM, "layers": [{"shape": "circle", "anchor": "elbow", "pts": [[0, 0]], "r": 5}]})


def test_look_swaps_a_whole_outfit():
    c = member(hair="short_hair", headwear={"kind": "bowler", "color": "#333333"}, face=["glasses"],
               looks={"coronation": {"headwear": "crown", "back": {"id": "cape", "color": "#6b2a8a"},
                                     "top": {"id": "robe", "color": "#6b4f8a"}, "face": [], "hair": "none"}})
    on = c.with_look("coronation")
    assert (on.headwear.kind, on.back.id, on.back.color, on.top.style) == ("crown", "cape", "#6b2a8a", "robe")
    assert on.face == [] and on.hair.id == "none"  # "none" takes it off; the engine draws nothing for it
    assert c.with_look("default") is c and c.headwear.kind == "bowler"
    assert ("back", "cape") in c.wardrobe() and ("hair", "short_hair") in c.wardrobe()
    # a look that sets nothing for a slot leaves it as it was
    keep = member(hair="short_hair", looks={"hat": {"headwear": "crown"}}).with_look("hat")
    assert keep.hair.id == "short_hair"
    # saved and loaded back: the look still swaps the same outfit (null in a saved look = unchanged)
    data = json.loads(c.model_dump_json())
    assert CastMember.model_validate(data).with_look("coronation").hair.id == "none"


def series_with(tmp_path, cast):
    d = tmp_path / "rome"
    d.mkdir()
    save_series(d / "series.json", SeriesModel.model_validate({"slug": "rome", "title": "Rome", "created_at": T,
                                                               "voice": {"voice_name": "x"}, "style": {"preset": "p"},
                                                               "cast": cast}))
    return d / "series.json"


def test_save_clears_wearers_approval_and_delete_is_blocked_while_worn(tmp_path):
    item = WardrobeItem.model_validate(ITEM)
    assert save_wardrobe_item(tmp_path, item) == []
    ids = [w.id for w in load_wardrobe(tmp_path).wardrobe]  # the first save writes the seed into the library's own file
    assert ids[-1] == "plume_helm" and "crown" in ids and (tmp_path / "wardrobe.json").exists()
    f = series_with(tmp_path, [{"id": "nero", "name": "Nero", "eyes": "dots", "top": {"color": "#f3efe2"},
                                "looks": {"war": {"headwear": "plume_helm"}}, "approved_at": T}])
    assert save_wardrobe_item(tmp_path, item) == []  # unchanged: approvals stay
    assert save_wardrobe_item(tmp_path, item.model_copy(update={"default_color": "#000000"})) == ["rome/nero"]
    assert load_series(f).cast[0].approved_at is None
    with pytest.raises(ValueError, match="worn as a headwear"):
        save_wardrobe_item(tmp_path, item.model_copy(update={"slot": "hair"}))
    with pytest.raises(ValueError, match="still worn by rome/nero"):
        delete_wardrobe_item(tmp_path, "plume_helm")
    with pytest.raises(KeyError):
        delete_wardrobe_item(tmp_path, "nothing")


# --- story package ---

def with_wardrobe(text: str, items) -> str:
    return text.replace("<<<CAST>>>", f"<<<WARDROBE>>>\n{json.dumps(items)}\n<<<CAST>>>", 1)


def test_package_wardrobe_section(tmp_path):
    cast = [{**CAST[0], "hair": {"id": "long_hair", "color": "#8a4b2a"}, "looks": {**CAST[0]["looks"], "war": {"headwear": "plume_helm"}}},
            {**CAST[1], "top": "toga", "facial_hair": "short_beard"}]
    r = package.parse(with_wardrobe(pkg(cast=cast), [ITEM]), tmp_path)
    assert r["ok"], r["errors"]
    assert [w.id for w in r["assets"]["WARDROBE"]] == ["plume_helm"]
    assert package.summary(r)["wardrobe"] == [{"id": "plume_helm", "name": "Plume helm"}]
    package.import_package(with_wardrobe(pkg(cast=cast), [ITEM]), tmp_path)
    assert "plume_helm" in {w.id for w in load_wardrobe(tmp_path).wardrobe}
    assert "crown" in {w.id for w in load_wardrobe(tmp_path).wardrobe}  # the seed came along into the library file


def test_package_without_wardrobe_still_imports(tmp_path):
    r = package.parse(pkg(), tmp_path)  # written before the wardrobe: no <<<WARDROBE>>>
    assert r["ok"], r["errors"]


def test_package_wardrobe_rename_and_errors(tmp_path):
    save_wardrobe_item(tmp_path, WardrobeItem.model_validate(ITEM))
    cast = [{**CAST[0], "headwear": "plume_helm", "looks": {**CAST[0]["looks"], "x": {"headwear": {"id": "plume_helm"}}}}, CAST[1]]
    r = package.parse(with_wardrobe(pkg(cast=cast), [ITEM]), tmp_path)
    assert r["ok"], r["errors"]
    assert r["renames"]["WARDROBE"] == {"plume_helm": "plume_helm-2"}
    ava = r["cast"][0]
    assert ava.headwear.kind == "plume_helm-2" and ava.looks["x"].headwear.kind == "plume_helm-2"
    # unknown id, wrong slot, a bad item, a misplaced section
    bad = [{**CAST[0], "hair": "crown"}, {**CAST[1], "back": "mystery"}]
    r = package.parse(pkg(cast=bad), tmp_path)
    msgs = [e["message"] for e in r["errors"] if e["section"] == "CAST"]
    assert "ava: 'crown' is a headwear, not a hair" in msgs and any("unknown back 'mystery'" in m for m in msgs)
    r = package.parse(with_wardrobe(pkg(), [{**ITEM, "id": "x", "slot": "hat"}]), tmp_path)
    assert r["errors"][0]["section"] == "WARDROBE" and "slot" in r["errors"][0]["message"]
    misplaced = pkg().replace("<<<SETS>>>", f"<<<WARDROBE>>>\n[]\n<<<SETS>>>", 1)
    r = package.parse(misplaced, tmp_path)
    assert not r["ok"] and "expected <<<SETS>>>" in r["errors"][0]["message"]
