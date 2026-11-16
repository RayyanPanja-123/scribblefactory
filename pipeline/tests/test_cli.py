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
    assert [(c.id, c.name, c.outfit_color, c.eyes, c.approved_at) for c in cast] == [
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
