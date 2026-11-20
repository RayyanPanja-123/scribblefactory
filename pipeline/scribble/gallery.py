"""The gallery: series posted everywhere, kept small. Moving a series there keeps, per part, its title, the chosen
thumbnail, the YouTube and Instagram links and the text written for it (story.md, upload.md), plus series.json (the
cast); every rendered file (videos, frames, audio, cast sheets) is deleted with the series folder.

library/_gallery/<slug>/gallery.json (GalleryEntry), series.json, part-NN/{thumbnail.png, story.md, upload.md}.
The leading _ keeps it out of the series list (a series folder holds series.json; this one doesn't)."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

from pydantic import Field

from .io import atomic_write_json, load_part, load_series
from .schemas import PartId, Post, Strict, UtcDateTime, utcnow

GALLERY = "_gallery"
KEEP = ("story.md", "upload.md")  # small, and written by hand: kept with the thumbnail
SITES = {"youtube": "YouTube", "instagram": "Instagram"}


class GalleryPart(Strict):
    id: PartId
    number: int
    title: str
    thumbnail: str | None = Field(description="path inside the entry's folder; null: the part had no thumbnail")
    youtube: Post
    instagram: Post


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
    """why the series at d can't move yet (every part posted to YouTube and Instagram), else []"""
    series = load_series(d / "series.json")
    if not series.parts:
        return ["it has no parts"]
    out = []
    for pid in series.parts:
        f = d / pid / "part.json"
        p = load_part(f) if f.exists() else None
        missing = [name for k, name in SITES.items() if not (p and getattr(p.posted, k))]
        if missing:
            out.append(f"{pid} is not marked posted to {' or '.join(missing)}")
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
        shutil.copy2(d / "series.json", tmp / "series.json")
        parts = []
        for pid in series.parts:
            pdir, out = d / pid, tmp / pid
            out.mkdir()
            p = load_part(pdir / "part.json")
            thumb = next((pdir / r for r in filter(None, (p.thumbnail_choice, "thumbs/thumb-1.png")) if (pdir / r).is_file()), None)
            if thumb:
                shutil.copy2(thumb, out / f"thumbnail{thumb.suffix}")
            for k in KEEP:
                if (pdir / k).is_file():
                    shutil.copy2(pdir / k, out / k)
            parts.append(GalleryPart(id=pid, number=p.number, title=p.title, youtube=p.posted.youtube,
                                     instagram=p.posted.instagram,
                                     thumbnail=f"{pid}/thumbnail{thumb.suffix}" if thumb else None))
        entry = GalleryEntry(slug=slug, title=series.title, created_at=series.created_at, moved_at=utcnow(),
                             freed_bytes=max(size(d) - size(tmp), 0), parts=parts)
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
