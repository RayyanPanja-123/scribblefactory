import pytest

from pipeline.scribble.cli import main
from pipeline.scribble.io import load_part, load_series


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


def test_new_part_numbering_and_story_kept(lib):
    main(["new-series", "cat", "--title", "Cat"])
    (lib / "cat" / "part-02").mkdir()
    (lib / "cat" / "part-02" / "story.md").write_text("my story")
    assert main(["new-part", "cat", "--title", "Pilot"]) == 0
    assert main(["new-part", "cat"]) == 0
    assert load_series(lib / "cat" / "series.json").parts == ["part-01", "part-02"]
    p1 = load_part(lib / "cat" / "part-01" / "part.json")
    assert (p1.id, p1.number, p1.title, p1.stages.render.status) == ("part-01", 1, "Pilot", "pending")
    assert (lib / "cat" / "part-01" / "story.md").read_text() == "# Pilot\n\n"
    assert (lib / "cat" / "part-02" / "story.md").read_text() == "my story"


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


def test_render_not_implemented(lib):
    assert main(["render", "cat", "part-01"]) == 2


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
