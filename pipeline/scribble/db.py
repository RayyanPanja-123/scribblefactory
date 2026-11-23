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


def _retire(f: Path) -> None:
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
        _retire(f)


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
