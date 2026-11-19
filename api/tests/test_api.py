import contextlib
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error

import httpx2 as httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

import api.main as m
from pipeline.scribble.cli import main as cli
from pipeline.scribble.io import load_part, save_part
from pipeline.scribble.stages import render as render_stage
from pipeline.scribble.stages.render import pid_alive
from pipeline.tests.helpers import rendered

P = "/api/series/demo/parts/part-01"
PY = sys.executable


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBBLE_LIBRARY", str(tmp_path))
    assert cli(["new-series", "demo", "--title", "Demo"]) == 0
    assert cli(["cast-add", "demo", "bob", "--name", "Bob", "--color", "#ff0000"]) == 0
    assert cli(["new-part", "demo", "--title", "Pilot"]) == 0
    d = tmp_path / "demo" / "part-01"
    (d / "thumbs").mkdir()
    for n in (1, 2, 3):
        (d / "thumbs" / f"thumb-{n}.png").write_bytes(b"png%d" % n)
    (d / "stills-sheet.png").write_bytes(b"sheet")
    (d / "final.mp4").write_bytes(bytes(range(256)) * 4)
    (d / "qa.json").write_text('{"ok": true, "checks": {}}', encoding="utf-8")
    (d / "upload.md").write_text("Title\n", encoding="utf-8")
    (d / "frames").mkdir()
    (d / "frames" / "000001.png").write_bytes(b"x" * 100)
    return tmp_path


@pytest.fixture
def client(lib):
    return TestClient(m.app)


def finish_done(lib):
    f = lib / "demo" / "part-01" / "part.json"
    p = load_part(f)
    p.stages.finish.status = "done"
    save_part(f, p)


def wait_job(client, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        job = next(j for j in client.get("/api/jobs").json() if j["id"] == job_id)
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} still {job['status']}")


def fake_steps(monkeypatch, scripts: dict):
    """step text -> python -c script, in place of the CLI"""
    monkeypatch.setattr(m, "step_argv", lambda slug, part, step: [PY, "-c", scripts[step]])


# ---------------- reads ----------------

def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_overview(client, lib):
    o = client.get("/api/overview").json()
    assert len(o["sheet_steps"]) == 7  # Story Voice Plan Stills Final Thumb Post (the test render is optional)
    [row] = o["sheet"]  # story not prepped yet: the first column is current, the rest to do
    assert (row["part"], row["number"], row["cells"]) == ("part-01", 1, ["current"] + ["todo"] * 6)
    cli(["mark-posted", "demo", "part-01", "youtube", "--url", "https://yt/x"])
    o = client.get("/api/overview").json()
    assert o["kpi"] == {"series": 1, "parts_in_progress": 1, "waiting_for_approval": 1, "posted_this_month": 1}
    assert o["waiting"] == [{"slug": "demo", "part": "part-01", "waiting": ["stills"]}]
    assert len(o["posts_per_month"]) == 12 and o["posts_per_month"][-1]["youtube"] == 1
    assert o["disk_usage"]["demo"] > 1024
    assert o["sheet"] == []  # posted parts leave the sheet


def test_series_list_and_cover(client, lib):
    [s] = client.get("/api/series").json()
    assert (s["slug"], s["part_count"], s["cover"]) == ("demo", 1, "/api/media/demo/part-01/thumbs/thumb-1.png")
    assert s["posted"] == {"youtube": 0, "instagram": 0} and s["disk_usage"] > 0
    cli(["pick-thumbnail", "demo", "part-01", "2"])
    assert client.get("/api/series").json()[0]["cover"].endswith("thumb-2.png")


def test_series_detail(client):
    r = client.get("/api/series/demo").json()
    assert r["series"]["cast"][0]["id"] == "bob"
    [p] = r["parts"]
    assert list(p["stages"])[4] == "validate" and p["stages"]["prep"] == "pending" and p["approvals"]["stills"] is None and p["waiting"] == ["stills"]
    assert client.get("/api/series/nope").status_code == 404
    assert client.get("/api/series/..%2Fx").status_code == 404


def test_part_detail(client):
    r = client.get(P).json()
    assert r["part"]["title"] == "Pilot"
    assert r["files"]["story.md"] and r["files"]["final.mp4"] and not r["files"]["voice.mp3"]
    assert r["thumbs"] == ["thumb-1.png", "thumb-2.png", "thumb-3.png"]
    assert (r["qa"]["ok"], r["upload_md"], r["voice_duration"], r["frames_bytes"]) == (True, "Title\n", None, 100)
    assert r["part_bytes"] > r["frames_bytes"]
    assert client.get("/api/series/demo/parts/part-09").status_code == 404


def test_media_versions_change_on_rerender(client, lib):
    """a re-rendered file gets a new ?v, and media is served no-cache: the browser never shows a stale picture"""
    import os
    sheet = lib / "demo" / "part-01" / "stills-sheet.png"
    v1 = client.get(P).json()["versions"]
    assert {"stills-sheet.png", "final.mp4", "thumbs/thumb-1.png"} <= v1.keys() and "voice.mp3" not in v1
    os.utime(sheet, ns=(v1["stills-sheet.png"] + 10**9,) * 2)  # rendered again a second later
    assert client.get(P).json()["versions"]["stills-sheet.png"] != v1["stills-sheet.png"]
    assert client.get("/api/media/demo/part-01/stills-sheet.png").headers["cache-control"] == "no-cache"


# ---------------- media ----------------

def test_media_allowlist_and_traversal(client, lib):
    (lib / "demo" / "secret.txt").write_text("no")
    (lib / "outside.json").write_text("{}")
    assert client.get("/api/media/demo/part-01/stills-sheet.png").content == b"sheet"
    assert client.get("/api/media/demo/secret.txt").status_code == 404
    assert client.get("/api/media/demo/part-01/missing.png").status_code == 404
    for bad in ("/api/media/demo/../outside.json", "/api/media/demo/..%2F..%2Foutside.json",
                "/api/media/demo/%2e%2e/outside.json", "/api/media/x..y/a.json"):
        assert client.get(bad).status_code == 404, bad


def test_media_range(client):
    r = client.get("/api/media/demo/part-01/final.mp4", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206 and r.content == bytes(range(10, 20))
    assert r.headers["content-range"] == "bytes 10-19/1024"


# ---------------- actions ----------------

def test_approve_gates(client, lib):
    assert client.post(f"{P}/approve/test_render").status_code == 409  # no test-render.mp4
    r = client.post(f"{P}/approve/final")
    assert r.status_code == 409 and "finish not done" in r.json()["detail"]
    r = client.post(f"{P}/approve/stills")
    assert r.status_code == 200 and r.json()["approvals"]["stills"]["approved_at"]
    assert client.post(f"{P}/approve/thumbnail").status_code == 422


def test_approve_cast(client, lib):
    r = client.post("/api/series/demo/approve-cast", json={"cast_id": "bob"})
    assert r.status_code == 409 and "no render" in r.json()["detail"]
    rendered(lib / "demo")
    r = client.post("/api/series/demo/approve-cast", json={"cast_id": "zed"})
    assert r.status_code == 409 and "not in demo" in r.json()["detail"]
    r = client.post("/api/series/demo/approve-cast", json={"cast_id": "bob"})
    assert r.json()["cast"][0]["approved_at"]


def test_edit_cast_needs_that_members_rerender(client, lib):
    rendered(lib / "demo")
    client.post("/api/series/demo/approve-cast", json={"cast_id": "bob"})
    detail = client.get("/api/series/demo").json()
    bob, render = detail["series"]["cast"][0], detail["cast"]["bob"]
    assert render["current"] and render["idle"].startswith("/api/media/demo/cast/bob-idle.png?v=")
    r = client.put("/api/series/demo/cast/bob", json={**bob, "name": "Bobby"})  # name only: not drawn
    assert r.json()["cast"][0]["approved_at"] and client.get("/api/series/demo").json()["cast"]["bob"]["current"]
    r = client.put("/api/series/demo/cast/bob", json={**bob, "hair": {"id": "short_hair", "color": "#222222"}})
    assert r.status_code == 200 and r.json()["cast"][0]["approved_at"] is None  # new look: approval cleared
    assert not client.get("/api/series/demo").json()["cast"]["bob"]["current"]
    r = client.post("/api/series/demo/approve-cast", json={"cast_id": "bob"})
    assert r.status_code == 409 and "cast-sheet demo bob" in r.json()["detail"]  # stale render: no approving
    rendered(lib / "demo")  # re-rendered
    assert client.post("/api/series/demo/approve-cast", json={"cast_id": "bob"}).status_code == 200
    assert client.put("/api/series/demo/cast/bob", json={**bob, "hair": "crown"}).status_code == 409  # wrong slot
    assert client.put("/api/series/demo/cast/zed", json=bob).status_code == 404


def test_import_cast_updates_by_id_and_appends(client, lib):
    rendered(lib / "demo")
    client.post("/api/series/demo/approve-cast", json={"cast_id": "bob"})
    bob = client.get("/api/series/demo").json()["series"]["cast"][0]
    r = client.put("/api/series/demo/cast", json={"cast": [{**bob, "name": "Robert"}, {"id": "ann", "name": "Ann", "color": "#00ff00"}]})
    assert r.status_code == 200 and [(c["id"], c["name"]) for c in r.json()["cast"]] == [("bob", "Robert"), ("ann", "Ann")]
    assert r.json()["cast"][0]["approved_at"]  # name only: approval kept
    r = client.put("/api/series/demo/cast", json={"cast": [{**bob, "top": {**bob["top"], "color": "#000000"}}]})
    assert r.json()["cast"][0]["approved_at"] is None and len(r.json()["cast"]) == 2  # new look; ann stays
    bad = {"cast": [{**bob, "name": "Changed"}, {"id": "cy", "name": "Cy", "color": "green"}]}
    assert client.put("/api/series/demo/cast", json=bad).status_code == 409
    assert client.get("/api/series/demo").json()["series"]["cast"][0]["name"] == "Bob"  # all or nothing: not "Changed"
    dup = {"cast": [bob, bob]}
    assert "unique: bob" in client.put("/api/series/demo/cast", json=dup).json()["detail"]


def test_add_cast(client, lib):
    r = client.post("/api/series/demo/cast", json={"cast": [{"id": "ann", "name": "Ann", "color": "#00ff00"}]})
    assert r.status_code == 200 and [c["id"] for c in r.json()["cast"]] == ["bob", "ann"]
    r = client.post("/api/series/demo/cast", json={"cast": [{"id": "bob", "name": "Other Bob", "color": "#0000ff"}]})
    assert r.status_code == 409 and "unique: bob" in r.json()["detail"]
    assert client.get("/api/series/demo").json()["series"]["cast"][0]["name"] == "Bob"  # never overwritten
    bad = {"cast": [{"id": "cy", "name": "Cy", "color": "green"}]}
    assert client.post("/api/series/demo/cast", json=bad).status_code == 409
    assert client.post("/api/series/nope/cast", json={"cast": []}).status_code == 404


def test_pick_thumbnail(client, lib):
    assert client.post(f"{P}/pick-thumbnail", json={"n": 3}).json()["thumbnail_choice"] == "thumbs/thumb-3.png"
    (lib / "demo" / "part-01" / "thumbs" / "thumb-2.png").unlink()
    assert client.post(f"{P}/pick-thumbnail", json={"n": 2}).status_code == 409
    assert client.post(f"{P}/pick-thumbnail", json={"n": 4}).status_code == 422


def test_mark_posted(client):
    body = {"platform": "instagram", "url": "https://ig/1", "date": "2026-01-02"}
    assert client.post(f"{P}/mark-posted", json=body).json()["posted"]["instagram"]["url"] == "https://ig/1"
    r = client.post(f"{P}/mark-posted", json={**body, "url": "https://ig/2"})
    assert r.status_code == 409 and "--force" in r.json()["detail"]
    r = client.post(f"{P}/mark-posted", json={**body, "url": "https://ig/2", "force": True})
    assert r.json()["posted"]["instagram"]["url"] == "https://ig/2"
    assert client.post(f"{P}/mark-posted", json={**body, "url": "ftp://x", "force": True}).status_code == 409
    assert client.post(f"{P}/mark-posted", json={**body, "date": "02.01.2026", "force": True}).status_code == 409


def test_upload_md(client, lib):
    r = client.put(f"{P}/upload.md", json={"text": "New title\n#shorts\n"})
    assert r.status_code == 200 and r.json()["upload_md"] == "New title\n#shorts\n"
    assert (lib / "demo" / "part-01" / "upload.md").read_bytes() == b"New title\n#shorts\n"


def test_story_md(client, lib):
    story = "# T\n\n@set room\nHello.\n"
    r = client.put(f"{P}/story.md", json={"text": story})
    assert r.status_code == 200 and r.json()["story_md"] == story
    assert (lib / "demo" / "part-01" / "story.md").read_bytes() == story.encode()
    assert client.put("/api/series/demo/parts/part-99/story.md", json={"text": "x"}).status_code == 404


def test_create_series_and_part(client, lib):
    cast = [{"id": "ann", "name": "Ann", "color": "#00ff00"}, {"id": "cy", "name": "Cy", "color": "#0000ff", "eyes": "half_closed"}]
    r = client.post("/api/series", json={"slug": "fresh", "title": "Fresh", "cast": cast})
    assert r.status_code == 200 and [c["id"] for c in r.json()["cast"]] == ["ann", "cy"]
    assert client.post("/api/series", json={"slug": "fresh", "title": "Again"}).status_code == 409
    bad = {"slug": "other", "title": "Other", "cast": [{"id": "x", "name": "X", "color": "green"}]}
    assert client.post("/api/series", json=bad).status_code == 409 and not (lib / "other").exists()
    full = {"id": "sul", "name": "Sul", "top": {"style": "suit", "color": "#1f3a68", "accent_color": "#b71c1c"},
            "headwear": {"kind": "bowler", "color": "#111111"}, "props": [{"kind": "clipboard"}],
            "approved_at": "2026-01-01T00:00:00Z"}
    r = client.post("/api/series", json={"slug": "imported", "title": "Imported", "cast": [full]})
    sul = r.json()["cast"][0]
    assert sul["top"]["style"] == "suit" and sul["headwear"]["kind"] == "bowler" and sul["approved_at"] is None
    bad = {"slug": "other2", "title": "O", "cast": [full, {**full, "id": "x", "headwear": {"kind": "bowler", "color": "red"}}]}
    r = client.post("/api/series", json=bad)
    assert r.status_code == 409 and "cast #2 (x): headwear" in r.json()["detail"] and not (lib / "other2").exists()
    dup = {"slug": "other3", "title": "O", "cast": [full, full]}
    assert "unique: sul" in client.post("/api/series", json=dup).json()["detail"]
    r = client.post("/api/series/fresh/parts", json={"title": "One", "story": "# One\n\n@cast ann\nAnn ran.\n"})
    assert r.status_code == 200 and r.json()["part"]["id"] == "part-01"
    assert (lib / "fresh" / "part-01" / "story.md").read_text(encoding="utf-8") == "# One\n\n@cast ann\nAnn ran.\n"
    assert client.post("/api/series/fresh/parts", json={}).json()["part"]["title"] == "Part 2"
    assert client.post("/api/series/nope/parts", json={}).status_code == 404


FLAG = {"id": "flag", "name": "Flag", "shapes": [{"shape": "line", "pts": [[0, 40], [0, -120]], "width": 6},
                                                 {"shape": "rect", "pts": [[0, -120], [70, -80]], "fill": "#d84a3a"}]}


def test_custom_props(client, lib):
    r = client.get("/api/props").json()
    assert "medal" in r["builtin"] and r["custom"] == []
    assert client.put("/api/props/flag", json={**FLAG, "id": "other"}).status_code == 409
    assert client.put("/api/props/medal", json={**FLAG, "id": "medal"}).status_code == 422  # built-in name
    bad = {**FLAG, "shapes": [{"shape": "circle", "pts": [[0, 0]]}]}
    assert client.put("/api/props/flag", json=bad).status_code == 422  # circle without r
    # unknown until it exists, then any series can hold it
    hold = {"slug": "flags", "title": "Flags", "cast": [{"id": "ann", "name": "Ann", "color": "#00ff00",
                                                        "props": [{"kind": "flag", "hand": "left"}]}]}
    assert "unknown prop ann: flag" in client.post("/api/series", json=hold).json()["detail"]
    assert client.put("/api/props/flag", json=FLAG).json()["custom"][0]["id"] == "flag"
    assert client.post("/api/series", json=hold).status_code == 200
    # a new drawing clears the holder's approval; a rename alone does not
    s = json.loads((lib / "flags" / "series.json").read_text(encoding="utf-8"))
    s["cast"][0]["approved_at"] = "2026-01-01T00:00:00Z"
    (lib / "flags" / "series.json").write_text(json.dumps(s), encoding="utf-8")
    assert client.put("/api/props/flag", json={**FLAG, "name": "Banner"}).json()["cleared"] == []
    moved = {**FLAG, "shapes": [*FLAG["shapes"], {"shape": "circle", "pts": [[0, -124]], "r": 8, "fill": "#e8b923"}]}
    assert client.put("/api/props/flag", json=moved).json()["cleared"] == ["flags/ann"]
    assert client.get("/api/series/flags").json()["series"]["cast"][0]["approved_at"] is None
    # held: no delete; free: gone
    r = client.delete("/api/props/flag")
    assert r.status_code == 409 and "flags/ann" in r.json()["detail"]
    s["cast"][0]["props"] = []
    (lib / "flags" / "series.json").write_text(json.dumps(s), encoding="utf-8")
    story = lib / "demo" / "part-01" / "story.md"
    story.write_text("# T\n\n@do bob: eat flag\nHi.\n", encoding="utf-8")
    r = client.delete("/api/props/flag")
    assert r.status_code == 409 and "demo/part-01" in r.json()["detail"]
    story.write_text("# T\n\n@do bob: eat flagpole\nflag in narration is fine.\n", encoding="utf-8")
    assert client.delete("/api/props/flag").json()["custom"] == []
    assert client.delete("/api/props/flag").status_code == 404



def test_custom_sets(client, lib):
    kitchen = {"id": "kitchen", "name": "Kitchen", "kind": "indoor", "floor": "#d9c7a3", "back": "#f6e7c8",
               "pieces": [{"shape": "ball", "at": [2.5, 1.2, -2.3], "size": [0.3], "color": "#43aa8b"}]}
    r = client.get("/api/sets").json()
    assert {"id": "street", "kind": "outdoor"} in r["builtin"] and r["custom"] == []
    assert client.put("/api/sets/kitchen", json={**kitchen, "id": "other"}).status_code == 409
    assert client.put("/api/sets/room", json={**kitchen, "id": "room"}).status_code == 422  # built-in name
    assert client.put("/api/sets/kitchen", json=kitchen).json()["custom"][0]["id"] == "kitchen"
    story = lib / "demo" / "part-01" / "story.md"
    story.write_text("# T\n\n@set kitchen\nHi.\n", encoding="utf-8")
    r = client.delete("/api/sets/kitchen")
    assert r.status_code == 409 and "demo/part-01" in r.json()["detail"]
    story.write_text("# T\n\nHi.\n", encoding="utf-8")
    assert client.delete("/api/sets/kitchen").json()["custom"] == []
    assert client.delete("/api/sets/kitchen").status_code == 404

def test_voice_upload(client, lib):
    f = lib / "demo" / "part-01" / "voice.mp3"
    assert client.put(f"{P}/voice.mp3", content=b"not audio").status_code == 415 and not f.exists()
    r = client.put(f"{P}/voice.mp3", content=b"ID3first")
    assert r.status_code == 200 and r.json()["files"]["voice.mp3"] and f.read_bytes() == b"ID3first"
    assert client.put(f"{P}/voice.mp3", content=b"ID3second").status_code == 409 and f.read_bytes() == b"ID3first"
    assert client.put(f"{P}/voice.mp3?replace=true", content=b"\xff\xfbsecond").status_code == 200
    assert f.read_bytes() == b"\xff\xfbsecond"


def test_clean_frames_gate(client, lib):
    frames = lib / "demo" / "part-01" / "frames"
    assert client.post(f"{P}/clean-frames").status_code == 409 and frames.exists()
    finish_done(lib)
    assert client.post(f"{P}/clean-frames").status_code == 200 and not frames.exists()
    assert (lib / "demo" / "part-01" / "final.mp4").exists()


def test_busy_part_409(client, lib, monkeypatch):
    fake_steps(monkeypatch, {"slow": "import time; print('go', flush=True); time.sleep(60)"})
    job = client.post("/api/jobs", json={"slug": "demo", "part": "part-01", "steps": ["slow"]}).json()
    end = time.time() + 10
    while client.get(P).json()["busy"] is None and time.time() < end:
        time.sleep(0.05)
    for r in (client.post(f"{P}/approve/stills"), client.post(f"{P}/pick-thumbnail", json={"n": 1}),
              client.put(f"{P}/upload.md", json={"text": "x"}), client.post(f"{P}/clean-frames"),
              client.post("/api/series/demo/approve-cast", json={"cast_id": "bob"})):
        assert r.status_code == 409 and "running" in r.json()["detail"]
    client.delete(f"/api/jobs/{job['id']}")
    assert wait_job(client, job["id"])["status"] == "cancelled"


# ---------------- jobs ----------------

def test_job_steps_validated(client):
    for steps in (["rm -rf /"], ["run --stage nope"], [], ["render --bogus"]):
        r = client.post("/api/jobs", json={"slug": "demo", "part": "part-01", "steps": steps})
        assert r.status_code == 409, steps
    assert m.step_argv("demo", "part-01", "run --stage prep")[-5:-1] == ["demo", "part-01", "--stage", "prep"]
    assert "part-01" not in m.step_argv("demo", "part-01", "cast-sheet")
    assert m.step_argv("demo", "part-01", "cast-sheet bob")[-2] == "bob"  # one member


def test_jobs_fifo_and_output(client, monkeypatch, lib):
    log = lib / "order.txt"
    fake_steps(monkeypatch, {s: f"import time; time.sleep(0.2); open(r'{log}', 'a').write('{s}\\n'); print('{s} out')"
                             for s in ("a", "b", "c")})
    j1 = client.post("/api/jobs", json={"slug": "demo", "part": "part-01", "steps": ["a", "b"]}).json()
    j2 = client.post("/api/jobs", json={"slug": "demo", "part": "part-01", "steps": ["c"]}).json()
    assert wait_job(client, j1["id"])["status"] == "done"
    done = wait_job(client, j2["id"])
    assert log.read_text().split() == ["a", "b", "c"]
    assert done["output"] == ["c out"] and done["current_step"] == 0


def test_job_failure_stops(client, monkeypatch, lib):
    fake_steps(monkeypatch, {"bad": "print('boom'); raise SystemExit(3)", "never": f"open(r'{lib / 'ran'}', 'w')"})
    job = client.post("/api/jobs", json={"slug": "demo", "part": "part-01", "steps": ["bad", "never"]}).json()
    j = wait_job(client, job["id"])
    assert (j["status"], j["returncode"], j["output"]) == ("failed", 3, ["boom"])
    assert not (lib / "ran").exists()


def test_job_cancel_kills_tree(client, monkeypatch):
    slow = ("import subprocess, sys, time; c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            "print(c.pid, flush=True); time.sleep(60)")
    fake_steps(monkeypatch, {"slow": slow})
    job = client.post("/api/jobs", json={"slug": "demo", "part": "part-01", "steps": ["slow", "slow"]}).json()
    end = time.time() + 10
    while not (out := next(j for j in client.get("/api/jobs").json() if j["id"] == job["id"])["output"]):
        assert time.time() < end
        time.sleep(0.05)
    child = int(out[0])
    assert client.delete(f"/api/jobs/{job['id']}").json()["status"] == "cancelled"
    j = wait_job(client, job["id"])
    assert j["status"] == "cancelled" and j["current_step"] == 0
    end = time.time() + 5
    while pid_alive(child) and time.time() < end:
        time.sleep(0.05)
    assert not pid_alive(child)


# ---------------- SSE ----------------

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_sse_job_events(lib, monkeypatch):
    fake_steps(monkeypatch, {"one": "print('l1'); print('l2')", "two": "print('l3')"})
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(m.app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    while not server.started:
        time.sleep(0.02)
    got = []
    try:
        with httpx.Client(base_url=base, timeout=20) as c, c.stream("GET", "/api/events") as r:
            event = None
            for line in r.iter_lines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and event:
                    data = json.loads(line.split(":", 1)[1])
                    if event == "hello":
                        job_id = c.post("/api/jobs", json={"slug": "demo", "part": "part-01",
                                                           "steps": ["one", "two"]}).json()["id"]
                    elif data.get("id", job_id) == job_id:
                        got.append((event, data.get("line", data.get("step") if event == "job-step" else None)))
                    if event == "job-finished":
                        assert data["status"] == "done"
                        break
    finally:
        server.should_exit = True
        t.join(5)
    assert got == [("job-queued", None), ("job-started", None), ("job-step", 0), ("job-output", "l1"),
                   ("job-output", "l2"), ("part-changed", None), ("series-changed", None), ("job-step", 1),
                   ("job-output", "l3"), ("part-changed", None), ("series-changed", None), ("job-finished", None)]


# ---------------- openapi ----------------

def test_openapi_exported():
    assert m.OPENAPI.read_text(encoding="utf-8") == m.openapi_text(), "docs/openapi.json drifted: python -m api.main"


# ---------------- web app ----------------

def test_web_app_served_in_production_only(client, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (dist / "assets" / "a.js").write_text("js", encoding="utf-8")
    monkeypatch.setattr(m, "DIST", dist)
    monkeypatch.delenv("SCRIBBLE_SERVE_WEB", raising=False)
    assert client.get("/").status_code == 404  # dev: Vite serves the app
    monkeypatch.setenv("SCRIBBLE_SERVE_WEB", "1")
    assert client.get("/").text == "<html>app</html>"
    assert client.get("/assets/a.js").text == "js"
    assert client.get("/series/demo/parts/part-01").text == "<html>app</html>"  # SPA route
    assert client.get("/api/nope").status_code == 404  # unknown API paths stay 404s
    assert client.get("/api/health").json() == {"ok": True}
    assert client.get("/assets/..%2F..%2F..%2Fapi%2Fmain.py").text == "<html>app</html>"  # never outside dist


# ---------------- restart recovery ----------------

def dead_pid() -> int:
    p = subprocess.Popen([PY, "-c", "pass"])
    p.wait()
    return p.pid


def test_jobs_persist_and_resume_after_restart(client, lib):
    job = {"slug": "demo", "part": "part-01", "current_step": None, "queued_at": "2026-01-01T00:00:00Z",
           "started_at": None, "finished_at": None, "returncode": None, "output": [], "error": None}
    (lib / ".jobs.json").write_text(json.dumps([
        {**job, "id": 7, "steps": ["run --stage prep"], "status": "running", "pid": dead_pid(),
         "argv": [[PY, "-c", "print('never')"]]},
        {**job, "id": 8, "steps": ["run --stage prep"], "status": "queued", "pid": None,
         "argv": [[PY, "-c", "print('resumed')"]]},
    ]), encoding="utf-8")
    m.startup()
    jobs = {j["id"]: j for j in client.get("/api/jobs").json()}
    assert jobs[7]["status"] == "failed" and jobs[7]["error"] == "interrupted by restart"
    assert wait_job(client, 8)["output"] == ["resumed"]
    new = client.post("/api/jobs", json={"slug": "demo", "part": "part-01", "steps": ["render-stills"]}).json()
    assert new["id"] == 9  # ids continue after the saved ones
    client.delete(f"/api/jobs/{new['id']}")
    saved = {j["id"]: j for j in json.loads((lib / ".jobs.json").read_text(encoding="utf-8"))}
    assert saved[8]["status"] == "done" and saved[8]["output"] == ["resumed"] and 9 in saved


def test_startup_fails_stuck_stages_and_keeps_live_ones(client, lib, capsys):
    f = lib / "demo" / "part-01" / "part.json"
    p = load_part(f)
    p.stages.timing.status, p.stages.timing.pid = "running", dead_pid()
    p.stages.prep.status, p.stages.prep.pid = "running", os.getpid()  # this python process: still running
    p.stages.render.status = "running"  # no pid at all (a part.json from before pids were recorded)
    save_part(f, p)
    m.startup()
    p = load_part(f)
    assert (p.stages.timing.status, p.stages.timing.error) == ("failed", "interrupted")
    assert p.stages.render.status == "failed" and p.stages.prep.status == "running"
    assert "demo part-01: timing was left running: marked failed (interrupted)" in capsys.readouterr().out


def test_status_command_fails_stuck_stages(lib, capsys):
    f = lib / "demo" / "part-01" / "part.json"
    p = load_part(f)
    p.stages.shots.status, p.stages.shots.pid = "running", dead_pid()
    save_part(f, p)
    assert cli(["status", "demo"]) == 0
    assert load_part(f).stages.shots.status == "failed"
    assert "part-01 shots was left running by a process that is gone" in capsys.readouterr().out


def test_startup_stops_orphan_render_workers(client, lib):
    pdir = lib / "demo" / "part-01"
    worker = subprocess.Popen(["node", "-e", "setTimeout(() => {}, 60000)"], **render_stage.GROUP)
    try:
        (pdir / "frames" / ".render.lock").write_text(f"{dead_pid()}\n{worker.pid}", encoding="utf-8")
        m.startup()
        worker.wait(timeout=10)
        assert not (pdir / "frames" / ".render.lock").exists()
    finally:
        render_stage.kill_tree(worker)


def test_check_story(client, lib):
    (lib / "demo" / "part-01" / "story.md").write_text("# Pilot\n\n@set moon\nBob waved.\n", encoding="utf-8")
    r = client.get(f"{P}/check-story").json()
    assert r["ok"] is False and r["words"] == 2
    assert [(p["line"], p["message"].split(" (")[0]) for p in r["problems"]] == [
        (3, "unknown set 'moon'"), (4, "cast bob is not approved yet")]
    assert client.get("/api/series/demo/parts/part-09/check-story").status_code == 404


def test_cover_is_a_small_cached_jpeg(client, lib):
    from PIL import Image
    thumb = lib / "demo" / "part-01" / "thumbs" / "thumb-1.png"
    Image.new("RGB", (1080, 1920), "red").save(thumb)
    url = client.get("/api/series").json()[0]["cover"]
    assert url == "/api/media/demo/part-01/thumbs/thumb-1-360.jpg"
    small = thumb.with_name("thumb-1-360.jpg")
    with Image.open(small) as im:
        assert (im.format, im.size) == ("JPEG", (360, 640))
    made = small.stat().st_mtime_ns
    client.get("/api/series")
    assert small.stat().st_mtime_ns == made  # cached
    assert client.get(url).headers["content-type"] == "image/jpeg"
    assert client.get(f"{P}").json()["thumbs"] == ["thumb-1.png", "thumb-2.png", "thumb-3.png"]  # not a candidate


def test_approving_final_cleans_up(client, lib):
    finish_done(lib)
    d = lib / "demo" / "part-01"
    (d / "preview.mp4").write_bytes(b"p")
    r = client.post(f"{P}/approve/final")
    assert r.status_code == 200 and r.json()["approvals"]["final"]["approved_at"]
    assert not (d / "frames").exists() and not (d / "preview.mp4").exists()
    assert (d / "final.mp4").exists() and (d / "thumbs" / "thumb-1.png").exists()
    assert client.get(P).json()["frames_bytes"] == 0


def test_delete_part(client, lib):
    assert cli(["new-part", "demo", "--title", "Two"]) == 0
    r = client.delete("/api/series/demo/parts/part-02")
    assert r.status_code == 200 and r.json()["parts"] == ["part-01"]
    assert not (lib / "demo" / "part-02").exists()
    assert client.delete("/api/series/demo/parts/part-02").status_code == 404
    (lib / "demo" / "part-01" / "frames" / ".render.lock").write_text(str(os.getpid()), encoding="utf-8")
    r = client.delete(P)
    assert r.status_code == 409 and "render is running" in r.json()["detail"]
    assert (lib / "demo" / "part-01").exists()


def test_delete_series(client, lib):
    (lib / "demo" / "part-01" / "frames" / ".render.lock").write_text(str(os.getpid()), encoding="utf-8")
    r = client.delete("/api/series/demo")
    assert r.status_code == 409 and "render is running" in r.json()["detail"]
    (lib / "demo" / "part-01" / "frames" / ".render.lock").unlink()
    # Windows: a folder held open by another program (an Explorer window) can't be renamed aside: 409, nothing lost
    real = os.replace
    def held(src, dst):
        if os.path.isdir(src):
            raise PermissionError(5, "Access is denied")
        real(src, dst)
    m_replace = pytest.MonkeyPatch()
    m_replace.setattr(os, "replace", held)
    r = client.delete("/api/series/demo")
    m_replace.undo()
    assert r.status_code == 409 and "in use by another program" in r.json()["detail"] and (lib / "demo").exists()
    assert client.delete("/api/series/demo").json() == {"ok": True}
    assert not (lib / "demo").exists() and client.get("/api/series").json() == []
    assert client.delete("/api/series/demo").status_code == 404


def test_job_history_cleanup(client, lib):
    mk = lambda i, status, finished: {"id": i, "slug": "demo", "part": "part-01", "steps": ["render-stills"], "argv": [],
                                      "current_step": None, "status": status, "queued_at": "2026-01-01T00:00:00Z",
                                      "started_at": None, "finished_at": finished, "returncode": 0, "output": []}
    with m._cv:
        m.JOBS[:] = [mk(1, "done", "2026-01-05T10:00:00Z"), mk(2, "failed", "2026-02-05T10:00:00Z"),
                     mk(3, "cancelled", "2026-03-05T10:00:00Z"), mk(4, "queued", None)]
    try:
        r = client.post("/api/jobs/cleanup", json={"before": "2026-02-05"})
        assert r.status_code == 200 and [j["id"] for j in r.json()] == [2, 3, 4]      # the day itself is kept
        assert [j["id"] for j in client.post("/api/jobs/cleanup", json={}).json()] == [4]  # all history; queued stays
        assert client.post("/api/jobs/cleanup", json={"before": "05.02.2026"}).status_code == 422
    finally:
        with m._cv:
            m.JOBS.clear()  # the fake queued job must not block later tests


DOG = {"id": "dog", "name": "Dog", "rig": "quadruped",
       "joints": {"hip": [-80, -110], "shoulder": [80, -110], "neck": [100, -150]},
       "parts": {"body": [{"shape": "ellipse", "pts": [[0, -130]], "r": 120, "ry": 50, "fill": "$main"}],
                 "head": [{"shape": "circle", "pts": [[30, -40]], "r": 50, "fill": "$main"}],
                 "leg_front": [{"shape": "rect", "pts": [[-10, 0], [10, 110]], "fill": "$main"}],
                 "leg_back": [{"shape": "rect", "pts": [[-10, 0], [10, 110]], "fill": "$main"}]}}


def test_actions(client, lib):
    salute = {"id": "salute", "name": "Salute", "duration": 1.2, "loop": False,
              "keys": [{"t": 0}, {"t": 0.5, "arms": [[-16, 0], [150, 70]]}]}
    r = client.get("/api/actions").json()
    assert "wave" in r["do"] and "receive" in r["builtin"] and "receive" not in r["do"] and r["custom"] == []
    assert client.put("/api/actions/wave", json={**salute, "id": "wave"}).status_code == 422  # built-in id
    assert client.put("/api/actions/bow", json=salute).status_code == 409  # id mismatch
    assert [a["id"] for a in client.put("/api/actions/salute", json=salute).json()["custom"]] == ["salute"]
    story = lib / "demo" / "part-01" / "story.md"
    story.write_text("@set room\n@do bob: salute\nBob stood up.\n", encoding="utf-8")
    r = client.delete("/api/actions/salute")
    assert r.status_code == 409 and "demo/part-01" in r.json()["detail"]  # still used by a story
    story.write_text("Bob stood up.\n", encoding="utf-8")
    assert client.delete("/api/actions/salute").json()["custom"] == []
    assert client.delete("/api/actions/salute").status_code == 404


def test_creatures(client, lib):
    r = client.get("/api/creatures").json()
    assert {"id": "chicken", "rig": "bird"} in r["builtin"] and r["custom"] == []
    assert client.put("/api/creatures/cat", json={**DOG, "id": "cat"}).status_code == 422  # built-in id
    assert client.put("/api/creatures/dog", json={**DOG, "rig": "bird"}).status_code == 422  # wrong parts for the rig
    pets = {"slug": "pets", "title": "Pets", "cast": [{"id": "rex", "name": "Rex", "color": "#aa5500", "body": "dog"}]}
    assert "unknown body 'dog'" in client.post("/api/series", json=pets).json()["detail"]
    assert client.put("/api/creatures/dog", json=DOG).json()["custom"][0]["id"] == "dog"
    assert client.post("/api/series", json=pets).status_code == 200
    headless = {**pets, "slug": "pets2", "cast": [{**pets["cast"][0], "headless": True}]}
    assert "no stump" in client.post("/api/series", json=headless).json()["detail"]
    r = client.delete("/api/creatures/dog")
    assert r.status_code == 409 and "pets/rex" in r.json()["detail"]
    assert client.delete("/api/creatures/wolf").status_code == 404


def test_drop_old_ai_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBBLE_LIBRARY", str(tmp_path))
    f = tmp_path / "settings.json"
    assert m.drop_ai_settings() == []  # no file: nothing to do
    f.write_text(json.dumps({"provider": "gemini", "gemini_api_key": "k", "api_key": "s", "model": "x"}), encoding="utf-8")
    assert m.drop_ai_settings() and not f.exists()  # only provider keys: the file goes
    f.write_text(json.dumps({"openrouter_api_key": "k", "other": 1}), encoding="utf-8")
    m.drop_ai_settings()
    assert json.loads(f.read_text(encoding="utf-8")) == {"other": 1}  # anything else is kept
    assert m.drop_ai_settings() == []
    f.write_text("{not json", encoding="utf-8")
    assert "could not" in m.drop_ai_settings()[0]  # a broken file never stops startup
    f.write_text(json.dumps({"api_key": "s", "render_workers": 4}), encoding="utf-8")
    m.drop_ai_settings()
    assert json.loads(f.read_text(encoding="utf-8")) == {"render_workers": 4}  # render settings survive the cleanup


def test_settings(client, lib):
    r = client.get("/api/settings").json()
    none = {"youtube": "", "instagram": "", "facebook": ""}
    assert r["settings"] == {"render_workers": "auto", "force_software_gl": False, "socials": none, "brand_tags": "", "caption_model": "gemini-flash-latest"}
    assert r["workers_now"] == r["machine"]["recommended_workers"] >= 1 and len(r["examples"]) == 4
    for bad in (0, 17, "lots"):
        assert client.put("/api/settings", json={"render_workers": bad}).status_code == 422
    (lib / "settings.json").write_text(json.dumps({"keep": 1}), encoding="utf-8")
    r = client.put("/api/settings", json={"render_workers": 6, "force_software_gl": True}).json()
    assert r["settings"] == {"render_workers": 6, "force_software_gl": True, "socials": none, "brand_tags": "", "caption_model": "gemini-flash-latest"} and r["workers_now"] == 6
    r = client.put("/api/settings", json={"render_workers": 6, "socials": {"youtube": "@chan", "facebook": "page"}}).json()
    assert r["settings"]["socials"] == {"youtube": "@chan", "instagram": "", "facebook": "page"}
    assert json.loads((lib / "settings.json").read_text(encoding="utf-8"))["keep"] == 1  # unknown keys kept


def test_story_package_validate_then_import(client, lib):
    from pipeline.tests.test_package import pkg
    r = client.post("/api/packages/validate", json={"text": pkg()})
    assert r.status_code == 200 and r.json()["ok"], r.json()["errors"]
    assert not (lib / "the-liar-lantern").exists()  # dry run
    assert [p["title"] for p in r.json()["parts"]] == ["Part 1", "Part 2"]
    assert r.json()["parts"][0]["voice"].startswith("Ava") and r.json()["parts"][0]["story"]  # the review page shows both
    assert all(x["data"]["id"] == x["id"] for k in ("props", "sets", "cast") for x in r.json()[k])  # and previews each item
    r = client.post("/api/packages/import", json={"text": pkg()})
    assert r.status_code == 200
    d = client.get("/api/series/the-liar-lantern/parts/part-01").json()
    assert d["tts_script"].endswith("To be continued.\n")
    bad = client.post("/api/packages/import", json={"text": pkg().replace("<<<END>>>", "")})
    assert bad.status_code == 409 and "nothing was written" in bad.json()["detail"]


def test_wardrobe(client, lib):
    r = client.get("/api/wardrobe").json()
    assert {"id": "bowler", "name": "Bowler", "slot": "headwear"} in r["builtin"]
    assert "crown" in {w["id"] for w in r["custom"]}  # the starter wardrobe
    helm = {"id": "plume_helm", "name": "Plume helm", "slot": "headwear",
            "layers": [{"shape": "rect", "anchor": "head_top", "pts": [[-90, -40], [90, 60]], "fill": "$color"}]}
    assert client.put("/api/wardrobe/bowler", json={**helm, "id": "bowler"}).status_code == 422  # built-in id
    wear = {"slug": "helms", "title": "Helms", "cast": [{"id": "ann", "name": "Ann", "color": "#00ff00", "headwear": "plume_helm"}]}
    assert "unknown headwear 'plume_helm'" in client.post("/api/series", json=wear).json()["detail"]
    assert client.put("/api/wardrobe/plume_helm", json=helm).status_code == 200
    assert client.post("/api/series", json=wear).status_code == 200
    assert "still worn by helms/ann" in client.delete("/api/wardrobe/plume_helm").json()["detail"]
    assert client.delete("/api/wardrobe/crown").status_code == 200
    assert "crown" not in {w["id"] for w in client.get("/api/wardrobe").json()["custom"]}


# ---------------- sounds ----------------

def test_sfx_library_crud(client, lib):
    r = client.get("/api/sfx").json()
    assert len(r["sfx"]) == 14 and all(x["missing"] for x in r["sfx"]) and len(r["warnings"]) == 14
    pop = next(x for x in r["sfx"] if x["id"] == "pop")
    body = {k: pop[k] for k in ("id", "file", "name", "purpose", "tags", "anchor", "default_volume")}
    r = client.put("/api/sfx/pop", json={**body, "purpose": "pop-ups", "default_volume": 0.5}).json()
    assert next(x for x in r["sfx"] if x["id"] == "pop")["default_volume"] == 0.5
    assert (lib / "sfx" / "sfx.json").is_file()
    assert client.put("/api/sfx/boing/audio?name=Boing.mp3", content=b"not audio").status_code == 415
    assert client.put("/api/sfx/boing/audio?name=boing.exe", content=b"x").status_code == 415
    # used in a story: delete refused
    (lib / "demo" / "part-01" / "story.md").write_text("# T\n\n@sfx pop\nBob waved.\n", encoding="utf-8")
    r = client.delete("/api/sfx/pop")
    assert r.status_code == 409 and "demo/part-01" in r.json()["detail"]
    assert client.delete("/api/sfx/click").status_code == 200
    assert "click" not in [x["id"] for x in client.get("/api/sfx").json()["sfx"]]
    assert client.get("/api/sfx/pop/audio").status_code == 404  # file missing


def test_sfx_suggestions_accept_reject(client, lib):
    md = "# T\n\n@set office\nBob found the gold.\nBob waved at everyone in the office and smiled for a very long time.\n!! Bob was the traitor.\n"
    (lib / "demo" / "part-01" / "story.md").write_text(md, encoding="utf-8")
    r = client.get(f"{P}/sfx-suggestions").json()
    ids = [(s["line"], s["id"]) for s in r["suggestions"]]
    assert (4, "fahhh") in ids and (6, "riser") in ids and (6, "among_us") in ids and not r["timed"]
    hook = next(s for s in r["suggestions"] if s["id"] == "fahhh")
    r = client.post(f"{P}/sfx-suggestions", json={**hook, "accept": True}).json()
    assert (lib / "demo" / "part-01" / "story.md").read_text(encoding="utf-8").split("\n")[3:5] == ["@sfx fahhh", "Bob found the gold."]
    assert r["written"] == 1 and "fahhh" not in [s["id"] for s in r["suggestions"]]
    riser = next(s for s in r["suggestions"] if s["id"] == "riser")
    r = client.post(f"{P}/sfx-suggestions", json={**riser, "accept": False}).json()
    assert "riser" not in [s["id"] for s in r["suggestions"]]
    stale = {**riser, "line": 2}
    assert client.post(f"{P}/sfx-suggestions", json={**stale, "accept": True}).status_code == 409


def test_captions_gemini(client, lib, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert client.post("/api/captions", json={"prompt": "p"}).status_code == 409  # no key: says so, calls nothing
    r = client.put("/api/settings/gemini-key", json={"key": " sekret-k "}).json()
    assert r["gemini_key_last4"] == "et-k" and "sekret" not in json.dumps(client.get("/api/settings").json())
    client.put("/api/settings", json={"render_workers": 3})  # saving other settings keeps the key
    assert client.get("/api/settings").json()["gemini_key_last4"] == "et-k"
    sent = {}
    caps = {"youtube_title": "T", "youtube_description": "D #shorts", "youtube_pinned_comment": "C?",
            "instagram_caption": "I #reels"}

    def fake(req, timeout):
        sent.update(url=req.full_url, key=req.get_header("X-goog-api-key"), body=json.loads(req.data))
        reply = {"candidates": [{"content": {"parts": [{"text": "hmm", "thought": True}, {"text": json.dumps(caps)}]}}]}
        return contextlib.nullcontext(io.BytesIO(json.dumps(reply).encode()))
    monkeypatch.setattr(m.urllib.request, "urlopen", fake)
    assert client.post("/api/captions", json={"prompt": "write"}).json() == caps
    assert sent["key"] == "sekret-k" and sent["url"].endswith("/gemini-flash-latest:generateContent")
    assert sent["body"]["contents"][0]["parts"][0]["text"] == "write"
    # the chosen free model first; busy (503) or out of quota (429), the next free one answers
    assert client.put("/api/settings", json={"caption_model": "gemini-pro-latest"}).status_code == 422  # free only
    client.put("/api/settings", json={"caption_model": "gemini-3.5-flash"})
    tried = []

    def busy(req, timeout):
        tried.append(req.full_url.split("/")[-1].split(":")[0])
        if len(tried) < 3:
            raise urllib.error.HTTPError(req.full_url, 503 if len(tried) == 1 else 429, "x", {},
                                         io.BytesIO(b'{"error": {"message": "high demand"}}'))
        return fake(req, timeout)
    monkeypatch.setattr(m.urllib.request, "urlopen", busy)
    assert client.post("/api/captions", json={"prompt": "write"}).json() == caps
    assert tried == ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.8-flash"]
    monkeypatch.setattr(m.urllib.request, "urlopen", lambda req, timeout: (_ for _ in ()).throw(
        urllib.error.HTTPError(req.full_url, 503, "x", {}, io.BytesIO(b'{"error": {"message": "high demand"}}'))))
    r = client.post("/api/captions", json={"prompt": "write"})
    assert r.status_code == 502 and "every free model is busy" in r.json()["detail"]
    monkeypatch.setattr(m.urllib.request, "urlopen", lambda req, timeout: contextlib.nullcontext(io.BytesIO(b'{"candidates": []}')))
    assert client.post("/api/captions", json={"prompt": "write"}).status_code == 502
    assert not client.put("/api/settings/gemini-key", json={"key": ""}).json()["gemini_key_last4"]
    assert "gemini_key" not in json.loads((lib / "settings.json").read_text(encoding="utf-8"))
