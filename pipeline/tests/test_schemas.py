import json

import pytest
from pydantic import ValidationError

from pipeline.scribble import io
from pipeline.scribble.schemas import PartModel, SeriesModel
from pipeline.scribble.schemas.export import OUT_DIR, render

T = "2026-11-16T10:00:00Z"


def series_data(**over):
    d = {
        "slug": "office-cat",
        "title": "Office Cat",
        "created_at": T,
        "status": "active",
        "parts": ["part-01", "part-02"],
        "voice": {"provider": "freetts.ai", "voice_name": "Brian", "notes": ""},
        "style": {"preset": "chalk", "locked": True},
        "cast": [{"id": "bob", "name": "Bob", "outfit_color": "#1a2B3c", "eyes": "dots", "approved_at": T}],
    }
    d.update(over)
    return d


def part_data(**over):
    d = {"id": "part-01", "number": 1, "title": "Pilot",
         "stages": {"validate": {"status": "done", "started_at": T, "finished_at": T}},
         "approvals": {"stills": {"approved_at": T}},
         "posted": {"youtube": {"url": "https://youtu.be/x", "posted_at": T}}}
    d.update(over)
    return d


def test_series_round_trip(tmp_path):
    p = tmp_path / "series.json"
    m = SeriesModel.model_validate(series_data())
    io.save_series(p, m)
    assert io.load_series(p) == m
    io.save_series(p, io.load_series(p))
    assert io.load_series(p) == m


def test_part_round_trip(tmp_path):
    p = tmp_path / "part.json"
    m = PartModel.model_validate(part_data())
    io.save_part(p, m)
    assert io.load_part(p) == m
    on_disk = json.loads(p.read_text())
    assert on_disk["stages"]["validate"]["status"] == "done"
    assert list(on_disk["stages"]) == ["prep", "import_check", "timing", "shots", "validate",
                                       "render", "audio", "finish", "thumbnails"]


@pytest.mark.parametrize("model,data", [
    (SeriesModel, series_data(slug="Office_Cat")),
    (SeriesModel, series_data(slug="-cat")),
    (SeriesModel, series_data(parts=["part-1"])),
    (SeriesModel, series_data(parts=["part-٠١"])),  # Unicode digits
    (SeriesModel, series_data(parts=["part-01", "part-01"])),
    (SeriesModel, series_data(cast=[{"id": "bob", "name": "B", "outfit_color": "#12345g", "eyes": "dots"}])),
    (SeriesModel, series_data(cast=[{"id": "bob", "name": "B", "outfit_color": "red", "eyes": "dots"}])),
    (SeriesModel, series_data(extra=1)),
    (SeriesModel, series_data(voice={"voice_name": "x", "pitch": 2})),
    (PartModel, part_data(id="part-001")),
    (PartModel, part_data(stages={"bogus": {}})),
    (PartModel, part_data(foo="bar")),
])
def test_invalid(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_atomic_write_keeps_original_on_failure(tmp_path, monkeypatch):
    p = tmp_path / "part.json"
    io.save_part(p, PartModel.model_validate(part_data()))
    before = p.read_bytes()

    def boom(fd):
        raise OSError("disk died mid-write")

    monkeypatch.setattr(io.os, "fsync", boom)
    with pytest.raises(OSError):
        io.save_part(p, PartModel.model_validate(part_data(title="New")))
    assert p.read_bytes() == before
    assert [f.name for f in tmp_path.iterdir()] == ["part.json"]  # temp file cleaned up


def test_refuses_protected_files(tmp_path):
    for name in ("story.md", "voice.mp3"):
        with pytest.raises(ValueError):
            io.atomic_write_json(tmp_path / name, {})
        assert not (tmp_path / name).exists()


def test_part_approval_not_lost(tmp_path):
    p = tmp_path / "part.json"
    io.save_part(p, PartModel.model_validate(part_data()))
    io.save_part(p, PartModel.model_validate(part_data(approvals={})))  # stale model without approval
    assert io.load_part(p).approvals.stills.approved_at is not None


def test_cast_approval_not_lost(tmp_path):
    p = tmp_path / "series.json"
    io.save_series(p, SeriesModel.model_validate(series_data()))
    stale = series_data()
    stale["cast"][0]["approved_at"] = None
    io.save_series(p, SeriesModel.model_validate(stale))
    assert io.load_series(p).cast[0].approved_at is not None


def test_exported_schemas_match_models():
    for name, text in render().items():
        assert (OUT_DIR / name).read_text(encoding="utf-8") == text, f"{name} drifted: run export"
