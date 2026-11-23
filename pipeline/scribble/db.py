"""library/database/scribble.db: the library's data as SQLModel tables, schema changes as Alembic migrations
(pipeline/scribble/migrations; new one: `.venv/Scripts/alembic revision --autogenerate -m "..."` from the repo root).

Moved from JSON files so far: the job queue (was library/.jobs.json), settings (was library/settings.json) and the
six shared catalogs (were library/<kind>.json).
An old file found next to the database is imported, then renamed <name>.imported (kept, never deleted): a
settings.json replaces every setting (it always held all of them), a .jobs.json the job list, a <kind>.json that catalog.
"""

import json
import os
import threading
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Column, Engine, UniqueConstraint, delete, event
from sqlalchemy.pool import NullPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

MIGRATIONS = Path(__file__).parent / "migrations"


class Job(SQLModel, table=True):
    """one job of the API's queue (api/jobs.py); the web shows its tag, never its id"""
    id: int = Field(primary_key=True)
    tag: str | None = None  # series initials + part number, e.g. MDI001 (jobs.load_jobs fills in old ones)
    slug: str = Field(index=True)
    part: str
    steps: list[str] = Field(sa_column=Column(JSON, nullable=False))
    argv: list[list[str]] = Field(sa_column=Column(JSON, nullable=False))
    current_step: int | None = None
    status: str = Field(index=True)  # queued, running, done, failed, cancelled
    queued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    returncode: int | None = None
    output: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    error: str | None = None
    pid: int | None = None


CATALOG_KINDS = ("props", "sets", "objects", "creatures", "actions", "wardrobe")


class CatalogItem(SQLModel, table=True):
    """one custom item of a shared catalog (was library/<kind>.json); data is the item as its schema dumps it.
    Rows of a kind are in insertion order (id), which is the catalog's list order."""
    __tablename__ = "catalog_item"
    __table_args__ = (UniqueConstraint("kind", "item_id"),)
    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(index=True)  # one of CATALOG_KINDS
    item_id: str  # the item's slug (data["id"]): what stories and the web use
    data: dict = Field(sa_column=Column(JSON, nullable=False))


class Setting(SQLModel, table=True):
    """one machine-level option (pipeline/scribble/settings.py); unknown keys are kept"""
    key: str = Field(primary_key=True)
    value: Any = Field(sa_column=Column(JSON))


def path(library) -> Path:
    return Path(library) / "database" / "scribble.db"


_engines: dict[Path, Engine] = {}
_lock = threading.Lock()


def _pragmas(conn, _record) -> None:
    conn.execute("PRAGMA journal_mode=WAL")  # the API reads while CLI subprocesses write
    conn.execute("PRAGMA foreign_keys=ON")


def _migrate(e: Engine) -> None:
    # ponytail: runs Alembic on every process's first open (~0.1 s per CLI stage); check the version first if it shows
    from alembic import command
    from alembic.config import Config
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    with e.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def engine(library) -> Engine:
    """this library's database, created and migrated on first use in this process; old JSON files imported"""
    lib = Path(library).resolve()
    with _lock:
        if lib not in _engines:
            f = path(lib)
            f.parent.mkdir(parents=True, exist_ok=True)
            # NullPool: no connection left open, so Windows can move or delete the library between calls
            e = create_engine(f"sqlite:///{f}", poolclass=NullPool, connect_args={"timeout": 30})
            event.listen(e, "connect", _pragmas)
            _migrate(e)
            _engines[lib] = e
        e = _engines[lib]
        _import_old(lib, e)
        return e


def retire(f: Path) -> None:
    try:
        os.replace(f, f.with_name(f.name + ".imported"))
    except FileNotFoundError:  # another process imported it first
        pass


def _read_old(f: Path):
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return ...  # unreadable: retired without importing, as the old loaders ignored it


def _job(j: dict) -> Job:
    return Job(**{k: j.get(k) for k in Job.model_fields if k != "output"}, output=list(j.get("output") or []))


def _replace_settings(db: Session, s) -> None:
    if isinstance(s, dict):
        db.exec(delete(Setting))
        db.add_all(Setting(key=k, value=v) for k, v in s.items())


def _replace_jobs(db: Session, js) -> None:
    if isinstance(js, list):
        db.exec(delete(Job))
        db.add_all(_job(j) for j in js)


def _replace_kind(kind: str):
    def replace(db: Session, d) -> None:
        if isinstance(d, dict) and isinstance(d.get(kind), list):
            _put_kind(db, kind, d[kind])
    return replace


# old file -> what it replaces (settings.json: every setting, .jobs.json: every job, <kind>.json: that catalog)
_OLD_FILES = [("settings.json", _replace_settings), (".jobs.json", _replace_jobs),
              *((f"{k}.json", _replace_kind(k)) for k in CATALOG_KINDS)]


def _import_old(lib: Path, e: Engine) -> None:
    for name, replace in _OLD_FILES:
        f = lib / name
        if not f.is_file():
            continue
        data = _read_old(f)
        if data is None:
            continue
        if data is not ...:
            with Session(e) as db:
                replace(db, data)
                db.commit()
        retire(f)


def _has_data(library) -> bool:
    """a database, or an old file to import: reads of a library with neither are empty and create nothing"""
    lib = Path(library)
    return path(lib).is_file() or any((lib / name).is_file() for name, _ in _OLD_FILES)


# ---- settings ----

def get_settings(library) -> dict:
    if not _has_data(library):
        return {}
    with Session(engine(library)) as db:
        return {s.key: s.value for s in db.exec(select(Setting))}


def put_settings(library, values: dict, drop=()) -> None:
    """set these keys, remove the keys in drop; every other key stays"""
    with Session(engine(library)) as db:
        if drop:
            db.exec(delete(Setting).where(Setting.key.in_(list(drop))))
        for k, v in values.items():
            db.merge(Setting(key=k, value=v))
        db.commit()


# ---- jobs ----

def load_jobs(library) -> list[dict]:
    if not _has_data(library):
        return []
    with Session(engine(library)) as db:
        return [j.model_dump() for j in db.exec(select(Job).order_by(Job.id))]


def save_jobs(library, jobs: list[dict]) -> None:
    """the table becomes exactly this list (one transaction, like the old atomic file write)"""
    # ponytail: rewrites up to KEEP_JOBS rows per state change; upsert changed jobs only if it ever shows
    with Session(engine(library)) as db:
        db.exec(delete(Job))
        db.add_all(_job(j) for j in jobs)
        db.commit()


# ---- catalogs ----

def _put_kind(db: Session, kind: str, items: list[dict]) -> None:
    db.exec(delete(CatalogItem).where(CatalogItem.kind == kind))
    db.add_all(CatalogItem(kind=kind, item_id=str(x.get("id")), data=x) for x in items)


def get_catalog(library, kind: str) -> list[dict]:
    """this catalog's items in list order; [] when it has none"""
    if not _has_data(library):
        return []
    with Session(engine(library)) as db:
        return [r.data for r in db.exec(select(CatalogItem).where(CatalogItem.kind == kind).order_by(CatalogItem.id))]


def put_catalogs(library, kinds: dict[str, list[dict]]) -> None:
    """each kind's items become exactly this list, in this order; all kinds in one transaction"""
    with Session(engine(library)) as db:
        for kind, items in kinds.items():
            _put_kind(db, kind, items)
        db.commit()


# ---- series, parts, cast (were <series>/series.json and <series>/<part>/part.json) ----
# Columns hold what is queried; data holds the rest of the model exactly as it dumps. io.py turns rows back into
# SeriesModel / PartModel (load_series, load_part) and writes them (save_series, save_part).

SERIES_COLUMNS = ("slug", "title", "status", "created_at")
PART_COLUMNS = ("id", "number", "title")


class Series(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    title: str
    status: str
    created_at: str
    data: dict = Field(sa_column=Column(JSON, nullable=False))  # voice, style...: every other SeriesModel field
    # the imported series.json's text, until the series is next saved: hashes over ../series.json use it, so a file
    # written by an older model (a field added since) hashes as it did and nothing re-runs (io.series_bytes)
    file_text: str | None = None


class Part(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("series_id", "part_id"), UniqueConstraint("series_id", "folder"))
    id: int | None = Field(default=None, primary_key=True)
    series_id: int = Field(foreign_key="series.id", ondelete="CASCADE", index=True)
    part_id: str  # part-01: the stable id in URLs, CLI commands and job tags
    number: int
    title: str
    folder: str  # its folder in the series folder, 01-<title slug> (io.part_folder_name)
    data: dict = Field(sa_column=Column(JSON, nullable=False))  # approvals, posted...: every other PartModel field


class CastMember(SQLModel, table=True):
    __tablename__ = "cast_member"
    __table_args__ = (UniqueConstraint("series_id", "cast_id"),)
    id: int | None = Field(default=None, primary_key=True)  # insertion order: the cast's list order
    series_id: int = Field(foreign_key="series.id", ondelete="CASCADE", index=True)
    cast_id: str
    name: str
    approved_at: str | None = None
    data: dict = Field(sa_column=Column(JSON, nullable=False))  # the whole member as CastMember dumps it


class StageRun(SQLModel, table=True):
    __tablename__ = "stage_run"
    part: int = Field(foreign_key="part.id", ondelete="CASCADE", primary_key=True)
    stage: str = Field(primary_key=True)  # prep, import_check, timing, shots, validate, render, audio, finish
    status: str = Field(index=True)
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    inputs_hash: str | None = None
    pid: int | None = None


def _series_row(db: Session, slug: str) -> Series | None:
    return db.exec(select(Series).where(Series.slug == slug)).first()


def series_slugs(library) -> list[str]:
    if not _has_data(library):
        return []
    with Session(engine(library)) as db:
        return list(db.exec(select(Series.slug).order_by(Series.slug)))


def get_series(library, slug: str) -> dict | None:
    """the series as SeriesModel dumps it (parts: its part ids by number, cast: in list order), or None"""
    if not _has_data(library):
        return None
    with Session(engine(library)) as db:
        s = _series_row(db, slug)
        if s is None:
            return None
        parts = db.exec(select(Part.part_id).where(Part.series_id == s.id).order_by(Part.number))
        cast = db.exec(select(CastMember.data).where(CastMember.series_id == s.id).order_by(CastMember.id))
        return {**{k: getattr(s, k) for k in SERIES_COLUMNS}, **s.data, "parts": list(parts), "cast": list(cast)}


def put_series(library, d: dict, file_text: str | None = None) -> None:
    """add or replace the series d["slug"] (a SeriesModel dump) and its whole cast. Its parts are rows of their own
    and stay: d["parts"] is not stored."""
    with Session(engine(library)) as db:
        s = _series_row(db, d["slug"]) or Series(slug=d["slug"], title="", status="", created_at="", data={})
        s.title, s.status, s.created_at = d["title"], d["status"], d["created_at"]
        s.data = {k: v for k, v in d.items() if k not in (*SERIES_COLUMNS, "parts", "cast")}
        s.file_text = file_text
        db.add(s)
        db.flush()
        db.exec(delete(CastMember).where(CastMember.series_id == s.id))
        db.add_all(CastMember(series_id=s.id, cast_id=c["id"], name=c["name"], approved_at=c.get("approved_at"), data=c)
                   for c in d["cast"])
        db.commit()


def series_file_text(library, slug: str) -> str | None:
    if not _has_data(library):
        return None
    with Session(engine(library)) as db:
        return db.exec(select(Series.file_text).where(Series.slug == slug)).first()


def delete_series(library, slug: str) -> None:
    """the series row with its parts, stage runs and cast (cascade)"""
    with Session(engine(library)) as db:
        if s := _series_row(db, slug):
            db.delete(s)
            db.commit()


def part_folders(library, slug: str) -> dict[str, str]:
    """part id -> its folder, by number"""
    if not _has_data(library):
        return {}
    with Session(engine(library)) as db:
        s = _series_row(db, slug)
        rows = db.exec(select(Part.part_id, Part.folder).where(Part.series_id == s.id).order_by(Part.number)).all() if s else []
        return {pid: folder for pid, folder in rows}


def get_part(library, slug: str, folder: str) -> dict | None:
    """the part in this folder as PartModel dumps it (stages by name), or None"""
    if not _has_data(library):
        return None
    with Session(engine(library)) as db:
        s = _series_row(db, slug)
        p = db.exec(select(Part).where(Part.series_id == s.id, Part.folder == folder)).first() if s else None
        if p is None:
            return None
        stages = {r.stage: r.model_dump(exclude={"part", "stage"}) for r in db.exec(select(StageRun).where(StageRun.part == p.id))}
        return {"id": p.part_id, "number": p.number, "title": p.title, "stages": stages, **p.data}


def put_part(library, slug: str, folder: str, d: dict) -> None:
    """add or replace part d["id"] (a PartModel dump) of the series, in this folder, with its stage runs"""
    with Session(engine(library)) as db:
        s = _series_row(db, slug)
        if s is None:
            raise KeyError(f"series {slug!r} is not in the database")
        p = db.exec(select(Part).where(Part.series_id == s.id, Part.part_id == d["id"])).first() \
            or Part(series_id=s.id, part_id=d["id"], number=0, title="", folder=folder, data={})
        p.number, p.title, p.folder = d["number"], d["title"], folder
        p.data = {k: v for k, v in d.items() if k not in (*PART_COLUMNS, "stages")}
        db.add(p)
        db.flush()
        for name, st in d["stages"].items():
            db.merge(StageRun(part=p.id, stage=name, **st))
        db.commit()


def delete_part(library, slug: str, part_id: str) -> None:
    with Session(engine(library)) as db:
        s = _series_row(db, slug)
        p = db.exec(select(Part).where(Part.series_id == s.id, Part.part_id == part_id)).first() if s else None
        if p is not None:
            db.delete(p)
            db.commit()


# ---- stored files: every file of a series folder, with its metadata (io.sync_files keeps them current) ----

class StoredFile(SQLModel, table=True):
    __tablename__ = "stored_file"
    __table_args__ = (UniqueConstraint("path", "filename"),)
    id: int | None = Field(default=None, primary_key=True)
    series_id: int = Field(foreign_key="series.id", ondelete="CASCADE", index=True)
    part_id: int | None = Field(default=None, foreign_key="part.id", ondelete="CASCADE", index=True)  # None: series level
    path: str  # its folder, relative to library/database/storage: midnight-deals-inc/01-quota-night
    filename: str
    size_bytes: int
    content_type: str
    duration_s: float | None = None  # audio and video
    sha256: str
    created_at: str  # first seen
    updated_at: str  # the file's modified time


def get_files(library, slug: str | None = None) -> list[dict]:
    """stored files (one series, or all) with their series slug and part id (None: series level)"""
    if not _has_data(library):
        return []
    with Session(engine(library)) as db:
        q = (select(StoredFile, Series.slug, Part.part_id).join(Series, Series.id == StoredFile.series_id)
             .join(Part, Part.id == StoredFile.part_id, isouter=True).order_by(StoredFile.path, StoredFile.filename))
        if slug:
            q = q.where(Series.slug == slug)
        return [{**f.model_dump(exclude={"id", "series_id", "part_id"}), "slug": s, "part": p} for f, s, p in db.exec(q)]


def put_files(library, slug: str, rows: list[dict], gone: list[tuple[str, str]]) -> None:
    """add or replace these files (dicts with a "part" id or None, and every StoredFile field but the ids) of the
    series, and drop the (path, filename) pairs in gone"""
    with Session(engine(library)) as db:
        s = _series_row(db, slug)
        if s is None:
            return
        parts = {pid: i for pid, i in db.exec(select(Part.part_id, Part.id).where(Part.series_id == s.id))}
        for path, filename in gone:
            db.exec(delete(StoredFile).where(StoredFile.path == path, StoredFile.filename == filename))
        for r in rows:
            f = db.exec(select(StoredFile).where(StoredFile.path == r["path"], StoredFile.filename == r["filename"])).first() \
                or StoredFile(series_id=s.id, **{k: r[k] for k in ("path", "filename", "size_bytes", "content_type", "sha256",
                                                                   "created_at", "updated_at")})
            for k, v in r.items():
                if k != "part":
                    setattr(f, k, v)
            f.series_id, f.part_id = s.id, parts.get(r["part"])
            db.add(f)
        db.commit()
