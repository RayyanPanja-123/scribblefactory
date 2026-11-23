from pipeline.scribble.cli import main as cli
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.scribble.io import delete_set, outdoor_sets, save_set, set_kinds
from pipeline.scribble.schemas import BUILTIN_SETS, CustomSet, SetLibrary
from pipeline.scribble.storycheck import check_story
from pipeline.tests.helpers import rendered

STORY = """# Test

@set office
@cast bob, amy
Bob walked in.
@sett room
@cast zed
@set moon
@do bob: give medal amy
@do amy: wave
Amy waved back.
@do fred: lie
Fred is not here.
@do amy: dance
Amy tried.
@cast bob
@car ride
@do bob: wave
They drove off.
@car off
@do car: broken
The end.
@do bob: lie
"""


def plain(r: dict, short_ok: bool = True) -> dict:
    """a check result without its staging notes (test_staging_report covers those) and, for the deliberately tiny
    fixture stories (short_ok), without the under-30-s runtime warning (test_runtime_warning_outside_30_to_35_seconds)"""
    return {**r, "warnings": [w for w in r["warnings"] if not w["message"].startswith("staging: ")
                              and not (short_ok and " s under 30 s (" in w["message"])]}


def setup(tmp_path, story, approve=("bob", "amy")):
    lib = str(tmp_path)
    assert cli(["new-series", "demo", "--title", "Demo", "--library", lib]) == 0
    for cid in ("bob", "amy", "fred"):
        assert cli(["cast-add", "demo", cid, "--name", cid.title(), "--color", "#ff0000", "--library", lib]) == 0
    rendered(Path(lib) / "demo")
    for cid in approve:
        assert cli(["approve-cast", "demo", cid, "--library", lib]) == 0
    assert cli(["new-part", "demo", "--library", lib]) == 0
    pdir = tmp_path / "demo" / "part-01"
    (pdir / "story.md").write_text(story, encoding="utf-8")
    return pdir


def test_builtin_sets_match_world_js():
    js = (Path(__file__).resolve().parents[2] / "engine" / "page" / "world.js").read_text(encoding="utf-8")
    assert re.findall(r'"([a-z_]+)"', re.search(r"export const SETS = \[([^\]]*)\]", js)[1]) == list(BUILTIN_SETS)


KITCHEN = {"id": "kitchen", "name": "Kitchen", "kind": "indoor", "floor": "#d9c7a3", "back": "#f6e7c8",
           "pieces": [{"shape": "box", "at": [-1.8, 0.45, -2.2], "size": [1.6, 0.9, 0.6], "color": "#8a5a32"}]}


def test_custom_set_schema():
    CustomSet.model_validate(KITCHEN)
    for bad in ({"id": "room"}, {"pieces": [{**KITCHEN["pieces"][0], "size": [1, 2]}]},
                {"pieces": [{**KITCHEN["pieces"][0], "at": [0, 0, -99]}]}, {"kind": "space"}):
        with pytest.raises(ValidationError):
            CustomSet.model_validate({**KITCHEN, **bad})
    with pytest.raises(ValidationError, match="unique"):
        SetLibrary.model_validate({"sets": [KITCHEN, KITCHEN]})


def test_custom_set_in_a_story(tmp_path):
    pdir = setup(tmp_path, "# T\n\n@set beach\nBob walked in.\n")
    assert any("unknown set 'beach'" in p["message"] for p in check_story(pdir)["problems"])
    save_set(tmp_path, CustomSet.model_validate({**KITCHEN, "id": "beach", "kind": "outdoor"}))
    assert set_kinds(tmp_path)["beach"] == "outdoor" and "beach" in outdoor_sets(tmp_path)
    assert not any("set" in p["message"] for p in check_story(pdir)["problems"])
    with pytest.raises(ValueError, match="demo/part-01"):
        delete_set(tmp_path, "beach")
    (pdir / "story.md").write_text("# T\n\nBob walked in.\n", encoding="utf-8")
    delete_set(tmp_path, "beach")
    assert "beach" not in set_kinds(tmp_path)


def test_problems_with_line_numbers(tmp_path, capsys):
    pdir = setup(tmp_path, STORY)
    r = check_story(pdir)
    got = {(p["line"], p["message"].split(" (")[0]) for p in r["problems"]}
    assert (6, "unknown directive @sett") in got
    assert (7, "unknown cast id zed") in got
    assert (8, "unknown set 'moon'") in got
    assert (9, "@do is replaced by the @do on line 10 before any text line uses it") in got
    assert (12, "@do: fred is not on stage on this line") in got
    assert (14, "@do: unknown action 'dance'") in got
    assert (18, "@do: not while @car ride, except \"car: broken\"") in got
    assert (21, "@do car: broken, but there is no car on stage") in got
    assert (23, "@do has no text line after it to apply to") in got
    assert len(got) == 9 and not r["ok"] and r["words"] == 17
    assert cli(["check-story", "demo", "part-01", "--library", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "problem: line 8: unknown set 'moon'" in out and out.rstrip().endswith("problems")


def test_missing_items_are_tagged(tmp_path):
    story = ("# T\n\n@set moon\n@cast bob, zed, kim\nBob looked.\n@do bob: give trident amy\nBob gave.\n"
             "@do bob: dance\nBob danced.\n@look bob: crown\nBob shone.\n@sfx boing\nBob jumped.\n")
    got = [(p["line"], p.get("missing")) for p in check_story(setup(tmp_path, story))["problems"] if p.get("missing")]
    assert (3, {"kind": "set", "ids": ["moon"], "owner": None}) in got
    assert (4, {"kind": "cast", "ids": ["zed", "kim"], "owner": None}) in got
    assert (6, {"kind": "prop", "ids": ["trident"], "owner": None}) in got
    assert (8, {"kind": "action", "ids": ["dance"], "owner": None}) in got
    assert (10, {"kind": "look", "ids": ["crown"], "owner": "bob"}) in got
    assert (12, {"kind": "sound", "ids": ["boing"], "owner": None}) in got


def test_ready_story_and_cast_approvals(tmp_path, capsys):
    pdir = setup(tmp_path, "# T\n\n@cast bob, fred\nBob met Fred.\n", approve=("bob",))
    r = check_story(pdir)
    assert [(p["line"], p["message"].split(" (")[0]) for p in r["problems"]] == [(4, "cast fred is not approved yet")]
    assert cli(["approve-cast", "demo", "fred", "--library", str(tmp_path)]) == 0
    assert plain(check_story(pdir)) == {"ok": True, "problems": [], "warnings": [], "words": 3, "seconds": 4.0,
                                 "wps": 2.6}  # 3 words / 2.6 per s + 0.3 s tail + 2.5 s end screen
    assert cli(["check-story", "demo", "part-01", "--library", str(tmp_path)]) == 0
    assert capsys.readouterr().out.rstrip().endswith("ready")


def test_changed_words_against_the_recorded_script(tmp_path):
    pdir = setup(tmp_path, "# T\n\nBob met Amy.\n\n@set office\nThey sat down.\n")
    (pdir / "script-for-tts.txt").write_text("Bob met Amy.\n\nThey stood up.\n", encoding="utf-8")
    r = check_story(pdir)  # no voice yet: prep just rewrites the script
    assert r["ok"] and [w["line"] for w in plain(r)["warnings"]] == [6]
    (pdir / "voice.mp3").write_bytes(b"ID3")
    r = check_story(pdir)
    assert [(p["line"], p["message"]) for p in r["problems"]] == [
        (6, "changed since voice.mp3 was recorded: word 5: 'stood up.' -> 'sat down.' "
            "(re-record the voice, or undo the edit)")]


def test_missing_story_and_empty_body(tmp_path):
    pdir = setup(tmp_path, "# Only a title\n")
    assert [p["message"] for p in check_story(pdir)["problems"]] == ["story.md has no body text (only a title?)"]
    (pdir / "story.md").unlink()
    assert check_story(pdir)["problems"] == [{"line": None, "message": "story.md not found"}]


def test_too_many_on_stage(tmp_path):
    pdir = setup(tmp_path, "# T\n\nBob sat.\n")
    extra = [f"c{i}" for i in range(4, 14)]
    for cid in extra:
        assert cli(["cast-add", "demo", cid, "--name", cid, "--color", "#00ff00", "--library", str(tmp_path)]) == 0
    (pdir / "story.md").write_text("# T\n\n@cast bob, amy, fred, " + ", ".join(extra) + "\nThey met.\n", encoding="utf-8")
    msgs = [(p["line"], p["message"].split(" (")[0]) for p in check_story(pdir)["problems"]]
    assert (3, "@cast: 13 on stage, at most 12 fit") in msgs


# --- runtime estimate and hook ---

def test_duration_estimate_uses_measured_words_per_second(tmp_path):
    from pipeline.scribble.storycheck import FALLBACK_WPS, estimate_runtime, measured_wps
    assert measured_wps(tmp_path) == FALLBACK_WPS  # nothing finished yet
    assert estimate_runtime(130, FALLBACK_WPS) == 52.8  # 130 / 2.6 + the 0.3 s tail + the 2.5 s end screen
    for n, (words, speech) in enumerate([(120, 40.0), (180, 60.0)], 1):  # 300 words in 100 s: 3 per s
        d = tmp_path / "demo" / f"part-0{n}"
        d.mkdir(parents=True)
        (d / "qa.json").write_text(json.dumps({"runtime": {"seconds": speech + 1, "words": words,
                                                            "speech_seconds": speech}}), encoding="utf-8")
    (tmp_path / "demo" / "part-03").mkdir()
    (tmp_path / "demo" / "part-03" / "qa.json").write_text("{}", encoding="utf-8")  # older qa.json: ignored
    assert measured_wps(tmp_path) == 3.0


def test_runtime_warning_outside_30_to_35_seconds(tmp_path):
    pdir = setup(tmp_path, "# T\n\n" + "Bob met Amy. " * 30 + "\n")  # 90 words / 2.6 + 2.8 = 37.4 s
    r = check_story(pdir)
    assert r["ok"] and r["seconds"] == 37.4
    assert [w["message"] for w in plain(r, short_ok=False)["warnings"]] == [
        "estimated 37.4 s is 2.4 s over 35 s (90 words at 2.60 words/s): cut about 6 words"]
    (pdir / "story.md").write_text("# T\n\n" + "Bob met Amy. " * 26 + "\n", encoding="utf-8")  # 78 words: 32.8 s
    assert plain(check_story(pdir), short_ok=False)["warnings"] == []
    (pdir / "story.md").write_text("# T\n\n" + "Bob met Amy. " * 20 + "\n", encoding="utf-8")  # 60 words: 25.9 s
    assert [w["message"] for w in plain(check_story(pdir), short_ok=False)["warnings"]] == [
        "estimated 25.9 s is 4.1 s under 30 s (60 words at 2.60 words/s): add about 11 words"]


@pytest.mark.parametrize("first,slow", [
    ("In nineteen twenty-five, Victor sold the Eiffel Tower.", True),
    ("In twenty twelve, a man walked in.", True),
    ("Once upon a time, a man sold a tower.", True),
    ("!! In July of fifteen eighteen, a woman began to dance.", True),
    ("A man sold the Eiffel Tower. Twice.", False),
    ("Inside the tower, nobody noticed.", False),
])
def test_hook_check(tmp_path, first, slow):
    from pipeline.scribble.storycheck import slow_open
    md = f"# T\n\n@set office\n@cast bob\n{first}\nIt was nineteen twenty-five.\n"
    assert slow_open(md) == ((5, first.removeprefix("!! ")) if slow else None)


def test_hook_warning_in_check_story(tmp_path):
    pdir = setup(tmp_path, "# T\n\n@cast bob\nOnce upon a time Bob met Amy.\n")
    assert [(w["line"], w["message"].split(":")[0]) for w in plain(check_story(pdir))["warnings"]] == [
        (4, "the first line opens on a date or backstory")]


def test_face_directive(tmp_path):
    pdir = setup(tmp_path, "# T\n\n@set office\n@cast bob, amy\n@face bob: angry\nBob sat.\n@face zed: sad\nAmy sat.\n@face amy: happy\n")
    msgs = [(p["line"], p["message"]) for p in check_story(pdir)["problems"]]
    assert not any(line == 5 for line, _ in msgs)
    assert any(line == 7 and "unknown cast id 'zed'" in m for line, m in msgs)
    assert (9, "@face has no narration line after it") in msgs


def test_staging_report(tmp_path):
    from pipeline.scribble.io import load_series, save_series
    pdir = setup(tmp_path, "# T\n\n@set office\n@cast bob, amy\nBob sat down.\nAmy laughed.\nBob read.\n")
    f = tmp_path / "demo" / "series.json"
    s = load_series(f)
    s.cast[0] = type(s.cast[0]).model_validate({**s.cast[0].model_dump(), "default_expression": "cheeky",
                                                "looks": {"party": {"props": []}}})
    save_series(f, s)
    warn = [w["message"] for w in check_story(pdir)["warnings"] if w["message"].startswith("staging: ")]
    assert any("directives besides @set and @cast" in w for w in warn)
    assert any(w.startswith("staging: 0 @do in 3 narration lines") for w in warn)
    assert any("lines 5, 7: no mood word" in w and "bob (cheeky)" in w for w in warn)  # Amy laughed: has a mood
    assert any("no @sfx" in w for w in warn)
    assert any("looks never switched on in this series: bob: party" in w for w in warn)
    # an emotional @do or @face covers its line; staging notes are warnings only, never problems
    pdir.joinpath("story.md").write_text("# T\n\n@set office\n@cast bob, amy\n@face bob: sad\nBob sat down.\n"
                                         "@do bob: angry\nBob read.\n", encoding="utf-8")
    r = check_story(pdir)
    assert r["ok"] and not any("no mood word" in w["message"] for w in r["warnings"])


def test_spoken_sign_off_warns(tmp_path):
    from pipeline.scribble.storycheck import spoken_sign_off
    pdir = setup(tmp_path, "# T\n\nBob met Amy.\nPart two is on my profile.\n")
    assert [w["line"] for w in plain(check_story(pdir))["warnings"] if "sign-off" in w["message"]] == [4]
    assert spoken_sign_off("Bob sat.\nTo be continued.") == (2, "To be continued.")
    assert spoken_sign_off("Bob sat.\n@fx pop\n!! Amy took the crown.") is None  # a twist ending is fine
    assert spoken_sign_off("He ran to the part of town that was up north.") is None


def test_look_on_a_creature(tmp_path):
    """a non-humanoid draws no wardrobe: a look that dresses it fails, one that does not (expression) passes"""
    pdir = setup(tmp_path, "# T\n\n@cast bob, amy\n@look amy: hat\nAmy sat.\n@look amy: nap\nAmy slept.\n@look amy: wig\nAmy sat.\n")
    f = tmp_path / "demo" / "series.json"
    s = json.loads(f.read_text(encoding="utf-8"))
    amy = next(c for c in s["cast"] if c["id"] == "amy")
    amy.update(body="cat", headwear={"kind": "crown"}, looks={"hat": {"headwear": {"kind": "crown"}}, "nap": {"default_expression": "sleepy"}})
    f.write_text(json.dumps(s), encoding="utf-8")
    r = check_story(pdir)
    looks = {p["line"]: p["message"] for p in r["problems"] if "@look" in p["message"]}
    assert set(looks) == {4, 8} and "look 'hat' puts on headwear crown" in looks[4] and "not dress it" in looks[8]
    warn = [w["message"] for w in r["warnings"] if "not a humanoid" in w["message"]]
    assert len(warn) == 2 and "its own look puts on headwear crown" in warn[0]


def test_flame_look_on_a_creature(tmp_path):
    """flame is a creature's look: @look horse: blazing passes; on a humanoid it warns (not drawn); a bad level is refused"""
    pdir = setup(tmp_path, "# T\n\n@cast bob, amy\n@look amy: blazing\nAmy rode.\n@look amy: default\nAmy rested.\n")
    f = tmp_path / "demo" / "series.json"
    s = json.loads(f.read_text(encoding="utf-8"))
    amy = next(c for c in s["cast"] if c["id"] == "amy")
    bob = next(c for c in s["cast"] if c["id"] == "bob")
    amy.update(body="horse", looks={"blazing": {"flame": "high", "flame_color": "#3a7bff"}, "embers": {"flame": "low"}})
    bob.update(flame="low")
    f.write_text(json.dumps(s), encoding="utf-8")
    r = check_story(pdir)
    assert not [p for p in r["problems"] if "@look" in p["message"]]
    warn = [w["message"] for w in r["warnings"] if "sets a flame" in w["message"]]
    assert warn == ["bob is a humanoid: its own look sets a flame, which is only drawn on creatures (horse, cat...)"]
    amy["looks"]["blazing"]["flame"] = "huge"
    f.write_text(json.dumps(s), encoding="utf-8")
    with pytest.raises(ValueError, match="flame"):  # rejected on load (the editor and API never save one)
        check_story(pdir)


def test_hold_in_check_story(tmp_path):
    pdir = setup(tmp_path, "# T\n\n@cast bob, amy\n@hold bob: medal\nBob won.\n@hold amy: trident\nAmy too.\n")
    r = check_story(pdir)
    holds = [(p["line"], p["message"], p.get("missing")) for p in r["problems"] if "@hold" in p["message"]]
    assert holds == [(6, "@hold: unknown prop 'trident' (props: " + holds[0][1].split("(props: ")[1],
                      {"kind": "prop", "ids": ["trident"], "owner": None})]
