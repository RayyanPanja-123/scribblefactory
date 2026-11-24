"""The read-only guard and the library copy helper."""

import sqlite3

import pytest
from sqlalchemy.exc import OperationalError

from pipeline.scribble import db
from pipeline.scribble.io import save_prop
from pipeline.scribble.schemas import CustomProp
from pipeline.tests.helpers import REAL_LIBRARY, library_copy, new_part

DUMMY = CustomProp(id="dummy-unused-thing", name="Dummy", shapes=[{"shape": "circle", "pts": [[0, 0]], "r": 10}])


def test_read_only_library_refuses_writes(tmp_path):
    new_part(tmp_path)  # a library with a database (read-write while it is made)
    save_prop(tmp_path, DUMMY)
    db._engines.clear()
    db.read_only(tmp_path)
    try:
        assert [p["id"] for p in db.get_catalog(tmp_path, "props")] == ["dummy-unused-thing"]  # reads work
        with pytest.raises(OperationalError, match="readonly"):
            save_prop(tmp_path, DUMMY.model_copy(update={"name": "Changed"}))
    finally:
        db._read_only.discard(tmp_path.resolve())
        db._engines.clear()


def test_the_real_library_is_read_only_in_tests():
    assert db.is_read_only(REAL_LIBRARY)


@pytest.mark.skipif(not (REAL_LIBRARY / "database" / "scribble.db").is_file(), reason="no real library here")
def test_library_copy_unused_row_leaves_every_part_alone(tmp_path):
    """on a copy of the real library: a new prop no part names changes no part's stage or frame hash"""
    from pipeline.scribble.io import all_parts
    from pipeline.scribble.stages import STAGES
    from pipeline.scribble.stages.render import frames_hash
    from pipeline.scribble.stages.runner import inputs_hash
    lib = library_copy(tmp_path)
    before_rows = sqlite3.connect(REAL_LIBRARY / "database" / "scribble.db").execute("select count(*) from catalog_item").fetchone()
    hashes = lambda: {n: ({k: inputs_hash(p, s.INPUTS, getattr(s, "extra_inputs", None)) for k, s in STAGES.items()},  # noqa: E731
                          frames_hash(p)) for n, p in all_parts(lib)}
    before = hashes()
    save_prop(lib, DUMMY)
    assert hashes() == before and before
    assert sqlite3.connect(REAL_LIBRARY / "database" / "scribble.db").execute("select count(*) from catalog_item").fetchone() == before_rows
