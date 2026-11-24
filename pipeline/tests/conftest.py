"""Every test session opens the real library's database read-only: a test that reaches it by mistake can read but
never write. Tests needing real data take a copy (helpers.library_copy)."""

from pipeline.scribble import db
from pipeline.tests.helpers import REAL_LIBRARY

db.read_only(REAL_LIBRARY)
