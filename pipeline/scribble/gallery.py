"""The gallery: series posted everywhere, kept small. Moving a series there keeps only the series title and, per
part, its title and YouTube and Instagram links; every file of the series folder is deleted with it.

library/_gallery/<slug>/gallery.json (GalleryEntry). Entries moved before this kept thumbnails and text files beside it;
those are ignored.
The leading _ keeps it out of the series list (a series folder holds series.json; this one doesn't)."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field

from .io import atomic_write_json, load_part, load_series, part_dir_of
from .schemas import PartId, Post, Strict, UtcDateTime, utcnow

GALLERY = "_gallery"
SITES = {"youtube": "YouTube", "instagram": "Instagram"}


class GalleryPart(Strict):
    model_config = ConfigDict(extra="ignore")  # older entries also hold a thumbnail path
    id: PartId
    number: int
    title: str
    youtube: Post | None = None  # a part may be posted to only one site
    instagram: Post | None = None


class GalleryEntry(Strict):
    schema_version: Literal[1] = 1
    slug: str = Field(description="the entry's folder in library/_gallery (the series slug, -2 etc. if reused)")
    title: str
    created_at: UtcDateTime
    moved_at: UtcDateTime
    freed_bytes: int
    parts: list[GalleryPart]


def size(d: Path) -> int:
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file())


def not_posted(d: Path) -> list[str]:
    """why the series at d can't move yet (every part posted to YouTube or Instagram), else []"""
    series = load_series(d / "series.json")
    if not series.parts:
        return ["it has no parts"]
    out = []
    for pid in series.parts:
        p = load_part(part_dir_of(d, pid) / "part.json")
        if not (p and any(getattr(p.posted, k) for k in SITES)):
            out.append(f"{pid} is not marked posted to {' or '.join(SITES.values())}")
    return out


def build(d: Path, library: Path) -> Path:
    """write the series at d into the gallery (the series itself is left alone); returns the new entry's folder"""
    series = load_series(d / "series.json")
    root = library / GALLERY
    root.mkdir(exist_ok=True)
    slug = series.slug
    n = 1
    while (root / slug).exists():
        n += 1
        slug = f"{series.slug}-{n}"
    tmp = root / f".tmp-{slug}-{utcnow():%Y%m%d%H%M%S}"
    tmp.mkdir()
    try:
        parts = []
        for pid in series.parts:
            p = load_part(part_dir_of(d, pid) / "part.json")
            parts.append(GalleryPart(id=pid, number=p.number, title=p.title, youtube=p.posted.youtube,
                                     instagram=p.posted.instagram))
        entry = GalleryEntry(slug=slug, title=series.title, created_at=series.created_at, moved_at=utcnow(),
                             freed_bytes=size(d), parts=parts)
        atomic_write_json(tmp / "gallery.json", entry.model_dump(mode="json"))
        tmp.rename(root / slug)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return root / slug


def entries(library: Path) -> list[GalleryEntry]:
    """newest move first"""
    root = library / GALLERY
    out = [GalleryEntry.model_validate_json(f.read_bytes()) for f in root.glob("*/gallery.json")] if root.is_dir() else []
    return sorted(out, key=lambda e: e.moved_at, reverse=True)
