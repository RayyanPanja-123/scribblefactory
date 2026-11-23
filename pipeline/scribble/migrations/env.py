"""Alembic env: db.engine() passes its connection in (config.attributes["connection"]); the alembic CLI (alembic.ini
at the repo root) uses sqlalchemy.url, the library's database."""
from alembic import context
from sqlalchemy import create_engine

from pipeline.scribble import db  # noqa: F401  the tables register on SQLModel.metadata
from sqlmodel import SQLModel

config = context.config


def run(conn) -> None:
    context.configure(connection=conn, target_metadata=SQLModel.metadata, render_as_batch=True)  # batch: SQLite ALTER
    with context.begin_transaction():
        context.run_migrations()


if conn := config.attributes.get("connection"):
    run(conn)
else:
    with create_engine(config.get_main_option("sqlalchemy.url")).connect() as c:
        run(c)
        c.commit()
