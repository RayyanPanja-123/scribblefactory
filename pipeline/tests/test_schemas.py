import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from pipeline.scribble import io
from pipeline.scribble.schemas import PartModel, SeriesModel, utcnow
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
    (PartModel, part_data(id="part-03", number=1)),
    (PartModel, part_data(id="part-100", number=100)),
    (SeriesModel, series_data(created_at="2026-11-16T10:00:00")),  # naive
    (PartModel, part_data(posted={"youtube": {"url": "u", "posted_at": "2026-11-16T10:00:00"}})),
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


def test_part_id_matches_number():
    assert PartModel.model_validate(part_data(id="part-12", number=12)).number == 12


def test_utcnow_is_aware_utc():
    assert utcnow().tzinfo == timezone.utc


def test_datetimes_stored_as_utc_z(tmp_path):
    plus2 = datetime(2026, 11, 16, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    m = SeriesModel.model_validate(series_data(created_at=plus2))
    assert m.created_at == datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)
    p = tmp_path / "series.json"
    io.save_series(p, m)
    on_disk = json.loads(p.read_text())
    assert on_disk["created_at"] == "2026-11-16T10:00:00Z"
    assert on_disk["cast"][0]["approved_at"] == "2026-11-16T10:00:00Z"
    assert io.load_series(p) == m


def test_naive_datetime_object_rejected():
    with pytest.raises(ValidationError):
        SeriesModel.model_validate(series_data(created_at=datetime(2026, 1, 1)))


def test_replace_retries_then_raises(tmp_path, monkeypatch):
    p = tmp_path / "part.json"
    io.save_part(p, PartModel.model_validate(part_data()))
    before = p.read_bytes()
    calls = []

    def locked(src, dst):
        calls.append(1)
        raise PermissionError("file in use")

    monkeypatch.setattr(io.os, "replace", locked)
    monkeypatch.setattr(io.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        io.save_part(p, PartModel.model_validate(part_data(title="New")))
    assert len(calls) == 1 + io.REPLACE_RETRIES
    assert p.read_bytes() == before
    assert [f.name for f in tmp_path.iterdir()] == ["part.json"]


def test_replace_retry_succeeds(tmp_path, monkeypatch):
    p = tmp_path / "part.json"
    io.save_part(p, PartModel.model_validate(part_data()))
    real, calls = io.os.replace, []

    def flaky(src, dst):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("file in use")
        real(src, dst)

    monkeypatch.setattr(io.os, "replace", flaky)
    monkeypatch.setattr(io.time, "sleep", lambda s: None)
    io.save_part(p, PartModel.model_validate(part_data(title="New")))
    assert io.load_part(p).title == "New"


def test_series_v1_migrates_to_v3_keeping_approvals(tmp_path):
    from pipeline.scribble.io import load_series, save_series
    v1 = series_data(cast=[{"id": "bob", "name": "Bob", "outfit_color": "#1a2B3c", "eyes": "dots", "approved_at": T},
                           {"id": "amy", "name": "Amy", "outfit_color": "#e2453c", "eyes": "half_closed"}])
    v1["schema_version"] = 1
    f = tmp_path / "series.json"
    f.write_text(json.dumps(v1))
    s = load_series(f)
    bob, amy = s.cast
    assert s.schema_version == 3
    assert bob.top.model_dump() == {"style": "plain", "color": "#1a2B3c", "accent_color": None, "number": None}
    assert (bob.headwear.kind, bob.legwear.kind, bob.props, bob.default_expression) == ("none", "none", [], "neutral")
    assert bob.approved_at is not None and amy.approved_at is None
    save_series(f, s)
    on_disk = json.loads(f.read_text())
    assert on_disk["schema_version"] == 3 and "outfit_color" not in on_disk["cast"][0]
    assert on_disk["cast"][0]["approved_at"] == v1["cast"][0]["approved_at"]
    assert load_series(f) == s  # v2 round trip


def test_cast_v2_rules():
    def member(**kw):
        return {"id": "bob", "name": "B", "eyes": "dots", "top": {"color": "#123456"}, **kw}
    SeriesModel.model_validate(series_data(cast=[member(headwear={"kind": "straw_hat", "color": "#e8c76a"},
                                                         legwear={"kind": "trousers", "color": "#222222"},
                                                         props=[{"kind": "medal", "hand": "left"}, {"kind": "apple", "hand": "right"}],
                                                         default_expression="cheeky")]))
    for bad in [{"props": [{"kind": "Big Sword"}]}, {"props": [{"kind": "apple", "hand": "left"}] * 2},
                {"props": [{"kind": "none", "hand": "left"}]},
                {"default_expression": "smug"}, {"top": {"color": "#123456", "number": "1234"}},
                {"top": {"color": "#123456", "style": "Big Cape"}}]:
        with pytest.raises(ValidationError):
            SeriesModel.model_validate(series_data(cast=[member(**bad)]))


def test_series_v2_single_prop_migrates_to_props_keeping_approvals(tmp_path):
    from pipeline.scribble.io import load_series, save_series
    def member(cid, prop):
        return {"id": cid, "name": cid, "eyes": "dots", "top": {"style": "suit", "color": "#1f3a68"},
                "headwear": {"kind": "none", "color": None}, "legwear": {"kind": "none", "color": None},
                "prop": prop, "default_expression": "neutral", "approved_at": T}
    v2 = series_data(cast=[member("sul", {"kind": "clipboard", "hand": "right"}), member("fred", {"kind": "none", "hand": "right"})])
    v2["schema_version"] = 2
    f = tmp_path / "series.json"
    f.write_text(json.dumps(v2))
    sul, fred = load_series(f).cast
    assert [p.model_dump() for p in sul.props] == [{"kind": "clipboard", "hand": "right"}]
    assert fred.props == []
    assert sul.approved_at is not None and fred.approved_at is not None
    save_series(f, load_series(f))
    on_disk = json.loads(f.read_text())
    assert on_disk["schema_version"] == 3 and "prop" not in on_disk["cast"][0]
    assert [c["approved_at"] for c in on_disk["cast"]] == [T, T]
