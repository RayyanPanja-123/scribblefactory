"""library/database/scribble.db: created and migrated on first use; old JSON files imported, then kept as .imported."""
import json

from pipeline.scribble import db


def test_migrates_and_imports_old_files(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"render_workers": 4, "socials": {"youtube": "@x"}}))
    (tmp_path / ".jobs.json").write_text(json.dumps([{"id": 3, "tag": "MDI001", "slug": "s", "part": "part-01",
                                                      "steps": ["render"], "argv": [["py"]], "status": "done",
                                                      "output": ["ok"]}]))
    assert db.get_settings(tmp_path) == {"render_workers": 4, "socials": {"youtube": "@x"}}
    assert db.path(tmp_path).is_file()
    assert not (tmp_path / "settings.json").exists() and (tmp_path / "settings.json.imported").exists()
    [j] = db.load_jobs(tmp_path)
    assert (j["id"], j["tag"], j["output"], j["pid"]) == (3, "MDI001", ["ok"], None)
    (tmp_path / "settings.json").write_text(json.dumps({"caption_model": "m"}))  # a newer file replaces all settings
    assert db.get_settings(tmp_path) == {"caption_model": "m"}


def test_settings_put_drop_and_jobs_save(tmp_path):
    db.put_settings(tmp_path, {"a": 1, "b": [1, 2]})
    db.put_settings(tmp_path, {"a": 2}, drop=["b"])
    assert db.get_settings(tmp_path) == {"a": 2}
    job = {"id": 1, "tag": "X001", "slug": "s", "part": "part-01", "steps": [], "argv": [], "status": "queued"}
    db.save_jobs(tmp_path, [job, {**job, "id": 2}])
    db.save_jobs(tmp_path, [{**job, "status": "done"}])  # the table becomes exactly the list
    assert [(j["id"], j["status"]) for j in db.load_jobs(tmp_path)] == [(1, "done")]


def test_catalogs_import_keep_order_and_hash_as_the_old_file(tmp_path):
    from pipeline.scribble import io
    old = (json.dumps({"schema_version": 1, "props": [{"id": "b", "name": "B", "shapes": []},
                                                     {"id": "a", "name": "A", "shapes": []}]}, indent=2) + "\n").encode()
    (tmp_path / "props.json").write_bytes(old)
    assert [x["id"] for x in db.get_catalog(tmp_path, "props")] == ["b", "a"]  # imported, list order kept
    assert (tmp_path / "props.json.imported").exists() and io.catalog_bytes(tmp_path, "props.json") == old
    assert io.catalog_bytes(tmp_path, "sets.json") is None  # no items: hashes as a missing file did
    db.put_catalogs(tmp_path, {"props": [{"id": "a"}], "sets": [{"id": "s"}]})
    assert [x["id"] for x in db.get_catalog(tmp_path, "props")] == ["a"] and db.get_catalog(tmp_path, "sets") == [{"id": "s"}]


def test_reading_an_empty_library_creates_nothing(tmp_path):
    lib = tmp_path / "nowhere"
    assert db.get_settings(lib) == {} and db.load_jobs(lib) == [] and db.get_catalog(lib, "props") == []
    assert not lib.exists()


def test_stored_files_follow_the_series_folder(tmp_path):
    import os
    from pipeline.scribble.cli import main
    from pipeline.scribble.io import part_dir_of, sync_files
    lib = ["--library", str(tmp_path)]
    assert main(["new-series", "cat", "--title", "Cat", *lib]) == 0 and main(["new-part", "cat", "--title", "Pilot", *lib]) == 0
    d = tmp_path / "database" / "storage" / "cat"
    p = part_dir_of(d, "part-01")
    (p / "frames").mkdir()
    (p / "frames" / "000000.png").write_bytes(b"png")  # frames: no rows
    (d / "cast").mkdir()
    (d / "cast" / "bob.png").write_bytes(b"png")
    assert sync_files(d) == 2 and sync_files(d) == 0  # story.md and the cast sheet; nothing changed the second time
    rows = {(r["part"], r["filename"]): r for r in db.get_files(tmp_path, "cat")}
    assert set(rows) == {("part-01", "story.md"), (None, "bob.png")}
    assert rows[("part-01", "story.md")]["path"] == "cat/01-pilot" and rows[(None, "bob.png")]["content_type"] == "image/png"
    (p / "story.md").write_bytes(b"# Pilot\n\nlonger now\n")
    os.utime(p / "story.md", (1e9, 1e9))
    (d / "cast" / "bob.png").unlink()
    assert sync_files(d) == 2  # one changed, one gone
    [r] = db.get_files(tmp_path, "cat")
    assert r["size_bytes"] == len("# Pilot\n\nlonger now\n") and r["updated_at"].startswith("2001-09-09")
