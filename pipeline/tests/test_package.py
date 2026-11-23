import json

import pytest

from pipeline.scribble import db, package
from pipeline.scribble.cli import main as cli
from pipeline.scribble.io import load_props, load_series, load_sets, save_prop
from pipeline.scribble.schemas import CustomProp

PROP = {"id": "lantern", "name": "Lantern", "shapes": [{"shape": "rect", "pts": [[0, -20], [30, 20]], "fill": "#f2d16b"}]}
SET = {"id": "bakery", "name": "Bakery", "kind": "indoor", "floor": "#8a6a4a", "back": "#f0e0c0", "pieces": []}
CAST = [{"id": "ava", "name": "Ava", "color": "#3b6ea5", "looks": {"lit": {"props": [{"kind": "lantern", "hand": "right"}]}}},
        {"id": "ben", "name": "Ben", "color": "#c0567a"}]
LINES = ["Ava found a lantern that glowed only for liars.", "She held it up to her brother Ben.",
         "It blazed like a bonfire.", "Ben swore he had never told a single lie in his whole life.",
         "The lantern flickered and hissed in the quiet bakery.", "Ava laughed so hard she dropped the flour.",
         "Then the lantern turned toward her and burned even brighter than before."]
NARRATION = " ".join(LINES * 2).split()[:120]


def script(title, end):
    body = " ".join(NARRATION)
    return f"# {title}\n\n@set bakery\n@cast ava, ben\n@look ava: lit\n{body}\n!! {end}\n"


def voice(end):
    return f"{' '.join(NARRATION)}\n{end}\n"


def pkg(parts=2, props=(PROP,), sets=(SET,), cast=CAST, voices=None, meta=None, script1=None):
    ends = [*["The lantern pointed at Ava. To be continued."] * (parts - 1), "Ava was the liar all along."]
    out = ["<<<SCRIBBLE_PACKAGE v1>>>", "<<<META>>>", json.dumps(meta or {"series_title": "The Liar Lantern", "parts": parts}),
           "<<<PROPS>>>", json.dumps(list(props)), "<<<SETS>>>", json.dumps(list(sets)), "<<<CREATURES>>>", "[]",
           "<<<ACTIONS>>>", "[]", "<<<CAST>>>", json.dumps(cast)]
    for n, end in enumerate(ends, 1):
        out += [f"<<<PART {n}>>>", "<<<SCRIPT>>>", (script1 if n == 1 and script1 else script(f"Part {n}", end)).rstrip("\n"),
                "<<<VOICE>>>", (voices or {}).get(n, voice(end)).rstrip("\n")]
    return "\n".join([*out, "<<<END>>>"]) + "\n"


@pytest.fixture
def lib(tmp_path):
    return tmp_path


def test_valid_package(lib):
    r = package.parse(pkg(), lib)
    assert r["errors"] == [] and r["ok"], r["errors"]
    assert r["series"]["slug"] == "the-liar-lantern"
    assert [p["title"] for p in r["parts"]] == ["Part 1", "Part 2"]
    assert not any("differs" in w["message"] for w in r["warnings"])
    assert list(lib.iterdir()) == []  # a dry run writes nothing


def test_fenced_chatter_crlf_bom_trailing_spaces(lib):
    text = "﻿Sure! Here it is:\r\n```text\r\n" + "\r\n".join(ln + "  " for ln in pkg().split("\n")) + "```\r\nEnjoy!"
    r = package.parse(text, lib)
    assert r["ok"], r["errors"]


def test_missing_section(lib):
    r = package.parse(pkg().replace("<<<CREATURES>>>\n[]\n", ""), lib)
    assert not r["ok"] and r["errors"][0]["section"] == "ACTIONS" and "CREATURES" in r["errors"][0]["message"]
    r = package.parse(pkg().replace("<<<END>>>", ""), lib)
    assert r["errors"][0]["section"] == "END"


def test_part_count_must_match_meta(lib):
    r = package.parse(pkg(meta={"series_title": "X", "parts": 3}), lib)
    assert not r["ok"] and "3 parts" in r["errors"][0]["message"]


def test_bad_json_names_section_and_line(lib):
    text = pkg().replace(json.dumps([SET]), '[{"id": "bakery",}]')
    r = package.parse(text, lib)
    e = r["errors"][0]
    assert e["section"] == "SETS" and "bad JSON" in e["message"]
    assert text.split("\n")[e["line"] - 1].startswith('[{"id"')
    r = package.parse(pkg(props=[{**PROP, "shapes": []}]), lib)
    assert r["errors"][0]["section"] == "PROPS" and "shapes" in r["errors"][0]["message"]


def test_unknown_id(lib):
    bad = script("Part 1", "x").replace("@set bakery", "@set moon").replace("@cast ava, ben", "@cast ava, zed")
    text = pkg(script1=bad)
    r = package.parse(text, lib)
    msgs = [(e["section"], e["message"]) for e in r["errors"]]
    assert ("PART 1 SCRIPT", "unknown set 'moon' (sets: room, office, street, dirt_road, countryside, orchard, stadium, bakery)") in msgs
    assert any("zed" in m for _, m in msgs)
    e = next(e for e in r["errors"] if "moon" in e["message"])
    assert text.split("\n")[e["line"] - 1] == "@set moon"
    r = package.parse(pkg(props=()), lib)  # the cast's look holds a prop that exists nowhere
    assert any("lantern" in e["message"] for e in r["errors"])


def test_voice_mismatch_warns_with_diff(lib):
    r = package.parse(pkg(voices={1: voice("Ava was the liar all along.").replace("bonfire", "campfire")}), lib)
    assert r["ok"]
    w = [w for w in r["warnings"] if w["section"] == "PART 1 VOICE"]
    assert w and "bonfire" in w[0]["message"] and "campfire" in w[0]["message"]


def test_id_clash_suffixes_and_rewrites(lib, monkeypatch):
    monkeypatch.setenv("SCRIBBLE_LIBRARY", str(lib))
    save_prop(lib, CustomProp.model_validate(PROP))
    assert cli(["new-series", "the-liar-lantern", "--title", "Old"]) == 0
    sets = {**SET, "id": "room"}  # a built-in id
    text = pkg(sets=[SET, sets], script1=script("Part 1", "x").replace("@set bakery", "@set room"))
    r = package.parse(text, lib)
    assert r["ok"], r["errors"]
    assert r["renames"]["PROPS"] == {"lantern": "lantern-2"} and r["renames"]["SETS"] == {"room": "room-2"}
    assert r["cast"][0].looks["lit"].props[0].kind == "lantern-2"
    assert "@set room-2" in r["parts"][0]["story"]
    res = package.import_package(text, lib)
    assert res["series"]["slug"] == "the-liar-lantern-2"
    assert load_series(lib / "the-liar-lantern" / "series.json").title == "Old"  # never overwritten
    assert [p.id for p in load_props(lib).props] == ["lantern", "lantern-2"]
    assert load_props(lib).props[0] == CustomProp.model_validate(PROP)


def test_import_writes_everything(lib):
    r = package.import_package(pkg(), lib)
    d = lib / r["series"]["slug"]
    s = load_series(d / "series.json")
    assert s.parts == ["part-01", "part-02"] and [c.id for c in s.cast] == ["ava", "ben"]
    assert all(c.approved_at is None for c in s.cast)  # an imported look still needs approval
    assert (d / "part-02" / "story.md").read_text(encoding="utf-8").startswith("# Part 2")
    assert (d / "part-01" / "script-for-tts.txt").read_text(encoding="utf-8") == voice("The lantern pointed at Ava. To be continued.")
    assert [x.id for x in load_sets(lib).sets] == ["bakery"]
    assert not list(lib.glob(".import-*"))


def test_import_is_atomic(lib, monkeypatch):
    with pytest.raises(package.PackageError):
        package.import_package(pkg(script1="# x\n@set moon\nHi.\n"), lib)
    assert list(lib.iterdir()) == []
    real = package.os.replace
    def boom(a, b):  # the library files are in, then the series folder rename fails
        if str(b).endswith("the-liar-lantern"):
            raise OSError("disk full")
        real(a, b)
    save_prop(lib, CustomProp.model_validate({**PROP, "id": "old"}))
    before = db.get_catalog(lib, "props")
    monkeypatch.setattr(package.os, "replace", boom)
    with pytest.raises(OSError):
        package.import_package(pkg(), lib)
    assert db.get_catalog(lib, "props") == before and db.get_catalog(lib, "sets") == []  # catalogs put back
    assert sorted(p.name for p in lib.iterdir()) == ["database"]


def test_doc_example_is_valid(lib):
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[2] / "docs" / "story-package.md").read_text(encoding="utf-8")
    r = package.parse(doc.split("## Example")[1], lib)
    assert r["ok"], r["errors"]
    assert [w["section"] for w in r["warnings"] if "words" not in w["message"] and "staging: " not in w["message"]] == []


def test_wardrobe_without_colors_gets_defaults(lib):
    """a look's top with no colour keeps the member's; the member's own items fall back to the default colours"""
    cast = [{"id": "ava", "name": "Ava", "eyes": "dots", "top": {"style": "plain"}, "headwear": "bowler", "legwear": "trousers",
             "looks": {"lit": {"top": {"style": "tank"}}}},
            {"id": "ben", "name": "Ben", "color": "#c0567a", "looks": {"boy": {"top": {"style": "shirt"}}}}]
    r = package.parse(pkg(cast=cast), lib)
    assert r["ok"], r["errors"]
    ava, ben = r["cast"]
    assert ava.top.color == ava.looks["lit"].top.color == "#4a6fa5"
    assert (ava.headwear.color, ava.legwear.color) == ("#2e3a59", "#3a3a3a")
    assert ben.looks["boy"].top.color == "#c0567a"
