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


def plain(r: dict) -> dict:
    """a check result without its staging notes (test_staging_report covers those)"""
    return {**r, "warnings": [w for w in r["warnings"] if not w["message"].startswith("staging: ")]}


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


def test_ready_story_and_cast_approvals(tmp_path, capsys):
    pdir = setup(tmp_path, "# T\n\n@cast bob, fred\nBob met Fred.\n", approve=("bob",))
    r = check_story(pdir)
    assert [(p["line"], p["message"].split(" (")[0]) for p in r["problems"]] == [(4, "cast fred is not approved yet")]
    assert cli(["approve-cast", "demo", "fred", "--library", str(tmp_path)]) == 0
    assert plain(check_story(pdir)) == {"ok": True, "problems": [], "warnings": [], "words": 3, "seconds": 3.9,
                                 "wps": 2.6}  # 3 words / 2.6 per s + 1 s end card
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
    assert estimate_runtime(130, FALLBACK_WPS) == 52.8  # 130 / 2.6 + the 1.75 s sign-off pause + the 1 s end card
    for n, (words, speech) in enumerate([(120, 40.0), (180, 60.0)], 1):  # 300 words in 100 s: 3 per s
        d = tmp_path / "demo" / f"part-0{n}"
        d.mkdir(parents=True)
        (d / "qa.json").write_text(json.dumps({"runtime": {"seconds": speech + 1, "words": words,
                                                            "speech_seconds": speech}}), encoding="utf-8")
    (tmp_path / "demo" / "part-03").mkdir()
    (tmp_path / "demo" / "part-03" / "qa.json").write_text("{}", encoding="utf-8")  # older qa.json: ignored
    assert measured_wps(tmp_path) == 3.0


def test_runtime_warning_over_58_seconds(tmp_path):
    pdir = setup(tmp_path, "# T\n\n" + "Bob met Amy. " * 50 + "\n")  # 150 words / 2.6 + 1 = 58.7 s
    r = check_story(pdir)
    assert r["ok"] and r["seconds"] == 60.4
    assert [w["message"] for w in plain(r)["warnings"]] == [
        "estimated 60.4 s is 2.4 s over 58 s (150 words at 2.60 words/s): cut about 6 words"]
    (pdir / "story.md").write_text("# T\n\n" + "Bob met Amy. " * 40 + "\n", encoding="utf-8")
    assert plain(check_story(pdir))["warnings"] == []


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
