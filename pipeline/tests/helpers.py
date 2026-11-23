from pathlib import Path

from pipeline.scribble.io import cast_files, cast_key, load_series


def rendered(series_dir) -> None:
    """what cast-sheet leaves behind, for every cast member's current look: approve-cast accepts them"""
    for c in load_series(Path(series_dir) / "series.json").cast:
        f = cast_files(series_dir, c.id)
        f["sheet"].parent.mkdir(exist_ok=True)
        f["sheet"].write_bytes(b"png")
        f["idle"].write_bytes(b"png")
        f["key"].write_text(cast_key(c))


def new_part(library, number: int = 1, title: str = "T", slug: str = "s") -> Path:
    """a part folder of a series (created when missing) in library's database/storage: what stage tests run on"""
    from datetime import datetime, timezone
    from pipeline.scribble.io import save_part, save_series, series_exists
    from pipeline.scribble.schemas import PartModel, SeriesModel, Style, Voice
    d = Path(library) / "database" / "storage" / slug
    if not series_exists(d):
        d.mkdir(parents=True, exist_ok=True)
        save_series(d / "series.json", SeriesModel(slug=slug, title=slug.title(), created_at=datetime.now(timezone.utc),
                                                   voice=Voice(voice_name=""), style=Style(preset="default")))
    p = d / f"part-{number:02d}"
    p.mkdir(exist_ok=True)
    save_part(p / "part.json", PartModel(id=f"part-{number:02d}", number=number, title=title))
    return p
