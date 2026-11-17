from pipeline.scribble.cli import main as cli
from pipeline.scribble.storycheck import check_story, engine_sets

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


def setup(tmp_path, story, approve=("bob", "amy")):
    lib = str(tmp_path)
    assert cli(["new-series", "demo", "--title", "Demo", "--library", lib]) == 0
    for cid in ("bob", "amy", "fred"):
        assert cli(["cast-add", "demo", cid, "--name", cid.title(), "--color", "#ff0000", "--library", lib]) == 0
    for cid in approve:
        assert cli(["approve-cast", "demo", cid, "--library", lib]) == 0
    assert cli(["new-part", "demo", "--library", lib]) == 0
    pdir = tmp_path / "demo" / "part-01"
    (pdir / "story.md").write_text(story, encoding="utf-8")
    return pdir


def test_engine_sets_read_from_world_js():
    assert {"room", "office", "dirt_road", "stadium"} <= set(engine_sets())


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
    assert check_story(pdir) == {"ok": True, "problems": [], "warnings": [], "words": 3, "seconds": 1.2}
    assert cli(["check-story", "demo", "part-01", "--library", str(tmp_path)]) == 0
    assert capsys.readouterr().out.rstrip().endswith("ready")


def test_changed_words_against_the_recorded_script(tmp_path):
    pdir = setup(tmp_path, "# T\n\nBob met Amy.\n\n@set office\nThey sat down.\n")
    (pdir / "script-for-tts.txt").write_text("Bob met Amy.\n\nThey stood up.\n", encoding="utf-8")
    r = check_story(pdir)  # no voice yet: prep just rewrites the script
    assert r["ok"] and [w["line"] for w in r["warnings"]] == [6]
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
