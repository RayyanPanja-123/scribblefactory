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
