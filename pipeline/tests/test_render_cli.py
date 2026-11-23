import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from pipeline.scribble import cli, sheet
from pipeline.scribble.cli import main
from pipeline.scribble.io import load_part, load_series
from pipeline.tests.helpers import rendered

FIX = Path(__file__).parent / "fixtures" / "story"


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """tmp library with series 'nap' (cast bob, amy unapproved) and part-01 holding the fixture story.json."""
    monkeypatch.setenv("SCRIBBLE_LIBRARY", str(tmp_path))
    main(["new-series", "nap", "--title", "Nap"])
    main(["cast-add", "nap", "bob", "--name", "Bob", "--color", "#3a7bd5"])
    main(["cast-add", "nap", "amy", "--name", "Amy", "--color", "#e2453c", "--eyes", "half_closed"])
    main(["new-part", "nap"])
    shutil.copy(FIX / "story.json", tmp_path / "database" / "storage" / "nap" / "part-01" / "story.json")
    rendered(tmp_path / "database" / "storage" / "nap")
    return tmp_path


@pytest.fixture
def engine_calls(monkeypatch):
    """Fake render.mjs: records its args and writes the frames + manifest it would have written."""
    calls = []

    def frames(d: Path, name: str):
        d.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1080, 1920), "white").save(d / name)
        (d / "manifest.json").write_text(json.dumps([{"label": "a", "file": name}]))

    def fake(*args):
        calls.append([str(a) for a in args])
        if args[0] == "--batch":  # cast-sheet: one job per member, --series <dir> --cast-sheet --cast <id>
            for job in json.loads(Path(args[1]).read_text()):
                frames(Path(job[1]) / "cast-frames" / job[4], f"{job[4]}-idle.png")
        else:
            frames(Path(args[1]) / "frames/stills", "a.png")
    monkeypatch.setattr(cli, "run_engine", fake)
    return calls


# --- approvals ---

def test_approve_part_sets_once_and_never_clears(lib, capsys):
    f = lib / "database" / "storage" / "nap" / "part-01" / "part.json"
    assert main(["approve", "nap", "part-01", "stills"]) == 0
    first = load_part(f).approvals.stills.approved_at
    assert first is not None and load_part(f).approvals.final.approved_at is None
    assert main(["approve", "nap", "part-01", "stills"]) == 0
    assert load_part(f).approvals.stills.approved_at == first
    assert "already approved" in capsys.readouterr().out
    assert main(["approve", "nap", "part-01", "final"]) == 0
    a = load_part(f).approvals
    assert a.stills.approved_at == first and a.final.approved_at


def test_approve_bad_input(lib):
    assert main(["approve", "nap", "part-09", "stills"]) == 1
    with pytest.raises(SystemExit) as e:
        main(["approve", "nap", "part-01", "thumbnail"])
    assert e.value.code == 1


def test_approve_cast(lib, capsys):
    f = lib / "database" / "storage" / "nap" / "series.json"
    assert main(["approve-cast", "nap", "bob"]) == 0
    first = load_series(f).cast[0].approved_at
    assert first is not None and load_series(f).cast[1].approved_at is None
    assert main(["approve-cast", "nap", "bob"]) == 0
    assert load_series(f).cast[0].approved_at == first
    assert main(["approve-cast", "nap", "zed"]) == 1
    assert "not in nap (cast: bob, amy)" in capsys.readouterr().err


# --- render-stills cast gate ---

def test_render_stills_refuses_unapproved_cast(lib, engine_calls, capsys):
    main(["approve-cast", "nap", "bob"])
    capsys.readouterr()
    assert main(["render-stills", "nap", "part-01"]) == 1
    assert "cast not approved: amy" in capsys.readouterr().err
    assert engine_calls == []
    assert not (lib / "database" / "storage" / "nap" / "part-01" / "stills-sheet.png").exists()


def test_render_stills_runs_engine_then_sheet_when_approved(lib, engine_calls):
    main(["approve-cast", "nap", "bob"])
    main(["approve-cast", "nap", "amy"])
    assert main(["render-stills", "nap", "part-01"]) == 0
    pdir = lib / "database" / "storage" / "nap" / "part-01"
    assert engine_calls == [["--part", str(pdir), "--stills"]]
    assert (pdir / "stills-sheet.png").exists()


def test_render_stills_needs_story(lib, engine_calls, capsys):
    (lib / "database" / "storage" / "nap" / "part-01" / "story.json").unlink()
    assert main(["render-stills", "nap", "part-01"]) == 1
    assert "run --stage shots first" in capsys.readouterr().err


def test_cast_sheet(lib, engine_calls):
    d = lib / "database" / "storage" / "nap"
    shutil.rmtree(d / "cast")
    assert main(["approve-cast", "nap", "bob"]) == 1  # no render yet
    assert main(["cast-sheet", "nap"]) == 0
    assert engine_calls[0][0] == "--batch"
    assert all((d / "cast" / f).exists() for f in ["bob.png", "bob-idle.png", "amy.png", "amy-idle.png"])
    assert main(["approve-cast", "nap", "bob"]) == 0
    main(["cast-edit", "nap", "amy", "--top-color", "#00ff00"])  # amy's render is stale now, bob's is not
    assert main(["approve-cast", "nap", "amy"]) == 1
    (d / "cast" / "bob.png").unlink()
    assert main(["cast-sheet", "nap", "amy"]) == 0  # only amy
    assert [j[4] for j in json.loads((d / "cast-frames" / "batch.json").read_text())] == ["amy"]
    assert not (d / "cast" / "bob.png").exists()
    assert main(["approve-cast", "nap", "amy"]) == 0
    assert main(["cast-sheet", "nap", "zed"]) == 1


def test_cast_sheet_needs_cast(tmp_path, monkeypatch, engine_calls):
    monkeypatch.setenv("SCRIBBLE_LIBRARY", str(tmp_path))
    main(["new-series", "empty", "--title", "Empty"])
    assert main(["cast-sheet", "empty"]) == 1
    assert engine_calls == []


# --- sheet.py ---

@pytest.mark.parametrize("n,cols,rows", [(7, 3, 3), (9, 9, 1), (18, 9, 2), (2, 6, 1)])
def test_sheet_grid_size(tmp_path, n, cols, rows):
    items = []
    for i in range(n):
        p = tmp_path / f"f{i}.png"
        Image.new("RGB", (1080, 1920), (i * 20, 0, 0)).save(p)
        items.append((f"f{i}", p))
    out = sheet.build_sheet(items, tmp_path / "sheet.png", cols)
    used = min(cols, n)
    w = used * (sheet.THUMB_W + sheet.PAD) + sheet.PAD
    h = rows * (sheet.THUMB_H + sheet.LABEL_H + sheet.PAD) + sheet.PAD
    with Image.open(out) as im:
        assert im.size == (w, h)
        # first thumbnail sits at (PAD, PAD) and is the first frame's colour
        assert im.getpixel((sheet.PAD + 5, sheet.PAD + 5)) == (0, 0, 0)
    assert [p.name for p in tmp_path.glob(".*tmp*")] == []


def test_sheet_from_manifest_keeps_order(tmp_path):
    for name, col in [("b.png", (255, 0, 0)), ("a.png", (0, 0, 255))]:
        Image.new("RGB", (1080, 1920), col).save(tmp_path / name)
    (tmp_path / "manifest.json").write_text(json.dumps([{"label": "B", "file": "b.png"}, {"label": "A", "file": "a.png"}]))
    with Image.open(sheet.from_manifest(tmp_path, tmp_path / "s.png", cols=2)) as im:
        assert im.getpixel((sheet.PAD + 5, sheet.PAD + 5)) == (255, 0, 0)


def test_sheet_empty_fails(tmp_path):
    with pytest.raises(ValueError):
        sheet.build_sheet([], tmp_path / "s.png", 3)
