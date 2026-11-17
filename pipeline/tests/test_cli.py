import json
from datetime import datetime, timezone

import pytest

from pipeline.scribble.cli import main
from pipeline.scribble.io import load_part, load_series, save_series


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBBLE_LIBRARY", str(tmp_path))
    return tmp_path


def test_new_series(lib):
    assert main(["new-series", "office-cat", "--title", "Office Cat"]) == 0
    f = lib / "office-cat" / "series.json"
    s = load_series(f)
    assert (s.title, s.status, s.parts, s.cast) == ("Office Cat", "draft", [], [])
    before = f.read_bytes()
    assert main(["new-series", "office-cat", "--title", "Other"]) == 1
    assert f.read_bytes() == before


def test_new_series_bad_slug(lib):
    assert main(["new-series", "../escape", "--title", "x"]) == 1
    assert list(lib.iterdir()) == []


def test_new_series_recovers_interrupted_run(lib):
    (lib / "cat").mkdir()  # folder left behind, no series.json
    assert main(["new-series", "cat", "--title", "Cat"]) == 0
    assert load_series(lib / "cat" / "series.json").title == "Cat"


def test_new_part_numbering(lib):
    main(["new-series", "cat", "--title", "Cat"])
    assert main(["new-part", "cat", "--title", "Pilot"]) == 0
    assert main(["new-part", "cat"]) == 0
    assert load_series(lib / "cat" / "series.json").parts == ["part-01", "part-02"]
    p1 = load_part(lib / "cat" / "part-01" / "part.json")
    assert (p1.id, p1.number, p1.title, p1.stages.render.status) == ("part-01", 1, "Pilot", "pending")
    assert (lib / "cat" / "part-01" / "story.md").read_text() == "# Pilot\n\n"


def test_new_part_skips_existing_folders(lib):
    main(["new-series", "cat", "--title", "Cat"])
    leftover = lib / "cat" / "part-02"
    leftover.mkdir()
    (leftover / "story.md").write_text("my story")
    (lib / "cat" / "part-xx").mkdir()  # non-matching folder names are ignored
    assert main(["new-part", "cat"]) == 0
    assert load_series(lib / "cat" / "series.json").parts == ["part-03"]
    assert (leftover / "story.md").read_text() == "my story"
    assert not (leftover / "part.json").exists()


def test_new_part_missing_series(lib, capsys):
    assert main(["new-part", "nope"]) == 1
    assert "not found" in capsys.readouterr().err


def test_new_part_limit_99(lib):
    main(["new-series", "cat", "--title", "Cat"])
    f = lib / "cat" / "series.json"
    s = load_series(f)
    s.parts = [f"part-{n:02d}" for n in range(1, 100)]
    f.write_text(s.model_dump_json())
    assert main(["new-part", "cat"]) == 1
    assert not (lib / "cat" / "part-100").exists()


def test_status(lib, capsys):
    main(["new-series", "cat", "--title", "Cat"])
    main(["new-part", "cat", "--title", "Pilot"])
    capsys.readouterr()
    assert main(["status", "cat"]) == 0
    out = capsys.readouterr().out
    assert "Cat (cat)" in out and "part-01" in out and "Pilot" in out
    for name in ("prep", "import_check", "validate", "thumbnails", "stills", "youtube"):
        assert name in out


def test_status_series_header(lib, capsys):
    main(["new-series", "cat", "--title", "Cat"])
    capsys.readouterr()
    main(["status", "cat"])
    out = capsys.readouterr().out.splitlines()
    assert out[1:3] == ["voice: -  style: default (unlocked)", "cast: -"]

    main(["cast-add", "cat", "bob", "--name", "Bob", "--color", "#3a7bd5"])
    main(["cast-add", "cat", "amy", "--name", "Amy", "--color", "#e2453c", "--eyes", "half_closed"])
    main(["set-voice", "cat", "--name", "Brian"])
    f = lib / "cat" / "series.json"
    s = load_series(f)
    s.style.locked = True
    s.cast[0].approved_at = datetime(2026, 11, 16, 23, 0, tzinfo=timezone.utc)
    save_series(f, s)
    capsys.readouterr()
    main(["status", "cat"])
    out = capsys.readouterr().out.splitlines()
    assert out[1:3] == ["voice: Brian  style: default (locked)",
                        "cast: bob (#3a7bd5, dots, approved 2026-11-16), amy (#e2453c, half_closed, -)"]


def test_render_missing_part(lib):
    main(["new-series", "cat", "--title", "Cat"])
    assert main(["render", "cat", "part-01"]) == 1


def test_usage_error_is_user_error(lib):
    with pytest.raises(SystemExit) as e:
        main(["new-series", "cat"])  # missing --title
    assert e.value.code == 1


def test_library_flag_beats_env(lib, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    assert main(["new-series", "cat", "--title", "Cat", "--library", str(other)]) == 0
    assert (other / "cat" / "series.json").exists()
    assert not (lib / "cat").exists()


def test_env_var_respected(lib):
    assert main(["new-series", "cat", "--title", "Cat"]) == 0
    assert (lib / "cat" / "series.json").exists()


def test_default_is_cwd_library(tmp_path, monkeypatch):
    monkeypatch.delenv("SCRIBBLE_LIBRARY", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["new-series", "cat", "--title", "Cat"]) == 0
    assert (tmp_path / "library" / "cat" / "series.json").exists()


def test_status_reports_orphans(lib, capsys):
    main(["new-series", "cat", "--title", "Cat"])
    (lib / "cat" / "part-03").mkdir()
    (lib / "cat" / "part-xx").mkdir()  # not a part folder, ignored
    capsys.readouterr()
    assert main(["status", "cat"]) == 0  # no parts listed: warning still shown
    assert capsys.readouterr().out.splitlines()[-1] == "warning: orphan folder part-03 (not in series.json)"
    main(["new-part", "cat"])  # becomes part-04
    capsys.readouterr()
    assert main(["status", "cat"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "warning: orphan folder part-03 (not in series.json)"
    assert out.index("part-04") < out.index("warning:")
    assert out.count("warning:") == 1


def test_cast_add(lib):
    main(["new-series", "cat", "--title", "Cat"])
    assert main(["cast-add", "cat", "bob", "--name", "Bob", "--color", "#3a7bd5"]) == 0
    assert main(["cast-add", "cat", "amy", "--name", "Amy", "--color", "#E2453C", "--eyes", "half_closed"]) == 0
    cast = load_series(lib / "cat" / "series.json").cast
    assert [(c.id, c.name, c.top.color, c.eyes, c.approved_at) for c in cast] == [
        ("bob", "Bob", "#3a7bd5", "dots", None), ("amy", "Amy", "#E2453C", "half_closed", None)]


def test_cast_add_keeps_approvals_and_rejects_duplicates(lib):
    main(["new-series", "cat", "--title", "Cat"])
    main(["cast-add", "cat", "bob", "--name", "Bob", "--color", "#3a7bd5"])
    f = lib / "cat" / "series.json"
    s = load_series(f)
    s.cast[0].approved_at = datetime(2026, 11, 16, tzinfo=timezone.utc)
    save_series(f, s)
    before = f.read_bytes()
    assert main(["cast-add", "cat", "bob", "--name", "Other", "--color", "#000000"]) == 1
    assert f.read_bytes() == before
    assert main(["cast-add", "cat", "amy", "--name", "Amy", "--color", "#e2453c"]) == 0
    cast = load_series(f).cast
    assert [c.id for c in cast] == ["bob", "amy"]
    assert cast[0].approved_at == datetime(2026, 11, 16, tzinfo=timezone.utc)


@pytest.mark.parametrize("color", ["red", "#12345", "#12345g"])
def test_cast_add_bad_color(lib, color):
    main(["new-series", "cat", "--title", "Cat"])
    assert main(["cast-add", "cat", "bob", "--name", "Bob", "--color", color]) == 1
    assert load_series(lib / "cat" / "series.json").cast == []


def test_cast_add_bad_eyes(lib):
    main(["new-series", "cat", "--title", "Cat"])
    with pytest.raises(SystemExit) as e:  # argparse choices: usage error, exit 1
        main(["cast-add", "cat", "bob", "--name", "Bob", "--color", "#123456", "--eyes", "big"])
    assert e.value.code == 1
    assert load_series(lib / "cat" / "series.json").cast == []


def test_cast_add_bad_id(lib):
    main(["new-series", "cat", "--title", "Cat"])
    assert main(["cast-add", "cat", "Bob Smith", "--name", "Bob", "--color", "#123456"]) == 1


@pytest.mark.parametrize("cmd", [["cast-add", "nope", "bob", "--name", "B", "--color", "#123456"],
                                 ["set-voice", "nope", "--name", "Brian"],
                                 ["set-style", "nope", "--preset", "chalk"]])
def test_series_commands_need_series(lib, cmd):
    assert main(cmd) == 1
    assert list(lib.iterdir()) == []


def test_set_voice_and_style(lib):
    main(["new-series", "cat", "--title", "Cat"])
    main(["cast-add", "cat", "bob", "--name", "Bob", "--color", "#3a7bd5"])
    assert main(["set-voice", "cat", "--name", "Brian"]) == 0
    assert main(["set-style", "cat", "--preset", "marker"]) == 0
    s = load_series(lib / "cat" / "series.json")
    assert (s.voice.provider, s.voice.voice_name, s.style.preset, s.style.locked) == ("freetts.ai", "Brian", "marker", False)
    assert [c.id for c in s.cast] == ["bob"]


def test_set_style_refuses_when_locked(lib):
    main(["new-series", "cat", "--title", "Cat"])
    f = lib / "cat" / "series.json"
    s = load_series(f)
    s.style.locked = True
    save_series(f, s)
    assert main(["set-style", "cat", "--preset", "other"]) == 1
    assert load_series(f).style.preset == "default"


# --- cast-edit ---

def _approved_cat(lib):
    main(["new-series", "cat", "--title", "Cat"])
    main(["cast-add", "cat", "bob", "--name", "Bob", "--color", "#3a7bd5"])
    main(["approve-cast", "cat", "bob"])
    return lib / "cat" / "series.json"


def test_cast_edit_name_keeps_approval(lib, capsys):
    f = _approved_cat(lib)
    approved = load_series(f).cast[0].approved_at
    assert main(["cast-edit", "cat", "bob", "--name", "Robert"]) == 0
    c = load_series(f).cast[0]
    assert (c.name, c.top.color, c.approved_at) == ("Robert", "#3a7bd5", approved)
    assert "approval was cleared" not in capsys.readouterr().out


@pytest.mark.parametrize("change", [["--color", "#c9d6e3"], ["--eyes", "half_closed"], ["--top", "suit"],
                                    ["--top-color", "#c9d6e3"], ["--accent", "#b71c1c"], ["--number", "31"],
                                    ["--headwear", "bowler", "--headwear-color", "#222222"],
                                    ["--legwear", "shorts", "--legwear-color", "#222222"], ["--props", "apple:left"],
                                    ["--default-expression", "cheeky"]])
def test_cast_edit_new_look_clears_approval(lib, capsys, change):
    f = _approved_cat(lib)
    assert main(["cast-edit", "cat", "bob", *change]) == 0
    assert load_series(f).cast[0].approved_at is None
    assert "bob's look changed, so its approval was cleared" in capsys.readouterr().out


def test_cast_edit_same_colour_keeps_approval(lib):
    f = _approved_cat(lib)
    approved = load_series(f).cast[0].approved_at
    assert main(["cast-edit", "cat", "bob", "--color", "#3A7BD5", "--eyes", "dots"]) == 0
    assert load_series(f).cast[0].approved_at == approved


def test_cast_edit_bad_input(lib, capsys):
    f = _approved_cat(lib)
    before = f.read_bytes()
    assert main(["cast-edit", "cat", "zed", "--name", "Z"]) == 1
    assert main(["cast-edit", "cat", "bob"]) == 1
    assert main(["cast-edit", "cat", "bob", "--color", "blue"]) == 1
    assert "nothing to change" in capsys.readouterr().err
    assert f.read_bytes() == before


def test_cast_edit_costume_flags(lib, capsys):
    f = _approved_cat(lib)
    assert main(["cast-edit", "cat", "bob", "--top", "tank", "--top-color", "#E53935", "--number", "31",
                 "--headwear", "postman_cap", "--headwear-color", "#2e3a59", "--legwear", "ragged_shorts",
                 "--legwear-color", "#3a3a3a", "--props", "clipboard:left",
                 "--default-expression", "exhausted"]) == 0
    c = load_series(f).cast[0]
    assert c.top.model_dump() == {"style": "tank", "color": "#E53935", "accent_color": None, "number": "31"}
    assert (c.headwear.kind, c.headwear.color, c.legwear.kind, c.legwear.color) ==         ("postman_cap", "#2e3a59", "ragged_shorts", "#3a3a3a")
    assert ([p.model_dump() for p in c.props], c.default_expression, c.approved_at) == \
        ([{"kind": "clipboard", "hand": "left"}], "exhausted", None)
    assert json.loads(f.read_text())["schema_version"] == 3
    main(["approve-cast", "cat", "bob"])
    approved = load_series(f).cast[0].approved_at
    # same look again (hex case differs): approval kept; clearing the number is a look change
    assert main(["cast-edit", "cat", "bob", "--top-color", "#e53935", "--props", "clipboard:left"]) == 0
    assert load_series(f).cast[0].approved_at == approved
    assert main(["cast-edit", "cat", "bob", "--number", "none"]) == 0
    c = load_series(f).cast[0]
    assert (c.top.number, c.approved_at) == (None, None)


@pytest.mark.parametrize("change", [["--number", "1234"], ["--number", "A1"], ["--accent", "red"],
                                    ["--headwear", "bowler"], ["--legwear-color", "#zzzzzz"],
                                    ["--props", "sword:right"], ["--props", "apple:left,medal:left"],
                                    ["--props", "apple:middle"], ["--props", "apple"],
                                    ["--props", "apple:left,medal:right,bottle:left"]])
def test_cast_edit_bad_costume(lib, change):
    f = _approved_cat(lib)
    before = f.read_bytes()
    assert main(["cast-edit", "cat", "bob", *change]) == 1  # bowler without a colour is refused
    assert f.read_bytes() == before


def test_cast_edit_props(lib, capsys):
    f = _approved_cat(lib)
    assert main(["cast-edit", "cat", "bob", "--props", "clipboard:right, stopwatch:left"]) == 0
    assert [(p.kind, p.hand) for p in load_series(f).cast[0].props] == [("clipboard", "right"), ("stopwatch", "left")]
    assert "approval was cleared" in capsys.readouterr().out
    main(["approve-cast", "cat", "bob"])
    approved = load_series(f).cast[0].approved_at
    assert main(["cast-edit", "cat", "bob", "--props", "clipboard:right,stopwatch:left"]) == 0  # same props
    assert load_series(f).cast[0].approved_at == approved
    assert main(["cast-edit", "cat", "bob", "--props", "none"]) == 0
    c = load_series(f).cast[0]
    assert (c.props, c.approved_at) == ([], None)


def test_clean_frames_posted(lib, capsys):
    main(["new-series", "cat", "--title", "Cat"])
    for _ in range(3):
        main(["new-part", "cat"])
    for pid in ("part-01", "part-02", "part-03"):
        d = lib / "cat" / pid
        (d / "frames").mkdir()
        (d / "frames" / "000000.png").write_bytes(b"x" * 2_000_000)
        (d / "final.mp4").write_bytes(b"mp4")
        main(["approve", "cat", pid, "final"])
        main(["mark-posted", "cat", pid, "youtube", "--url", "https://yt/x"])
    main(["mark-posted", "cat", "part-01", "instagram", "--url", "https://ig/x"])
    main(["mark-posted", "cat", "part-03", "instagram", "--url", "https://ig/y"])
    (lib / "cat" / "part-03" / "final.mp4").unlink()  # no final.mp4 on disk: frames kept
    capsys.readouterr()
    assert main(["clean-frames", "--posted"]) == 0  # dry run
    out = capsys.readouterr().out
    assert "would delete" in out and "dry run: 2.0 MB would be freed (1 part(s)); add --yes" in out
    assert (lib / "cat" / "part-01" / "frames").exists()
    assert main(["clean-frames", "--posted", "cat", "--yes"]) == 0
    assert "2.0 MB freed (1 part(s))" in capsys.readouterr().out
    assert not (lib / "cat" / "part-01" / "frames").exists()
    assert (lib / "cat" / "part-02" / "frames").exists()  # instagram missing
    assert (lib / "cat" / "part-03" / "frames").exists()
    assert main(["clean-frames", "--posted", "cat", "part-02"]) == 1
    assert main(["clean-frames", "cat"]) == 1


def test_cli_survives_a_cp1252_console(lib):
    import subprocess, sys
    main(["new-series", "cat", "--title", "Cat ≤ ✓"])
    r = subprocess.run([sys.executable, "-m", "pipeline.scribble.cli", "status", "cat", "--library", str(lib)],
                       capture_output=True, env={**__import__("os").environ, "PYTHONIOENCODING": "cp1252"})
    assert r.returncode == 0 and b"Cat ? ?" in r.stdout
