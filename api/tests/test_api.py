import json
import socket
import sys
import threading
import time

import httpx2 as httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

import api.main as m
from pipeline.scribble.cli import main as cli
from pipeline.scribble.io import load_part, save_part
from pipeline.scribble.stages.render import pid_alive

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
    cli(["mark-posted", "demo", "part-01", "youtube", "--url", "https://yt/x"])
    o = client.get("/api/overview").json()
    assert o["kpi"] == {"series": 1, "parts_in_progress": 1, "waiting_for_approval": 1, "posted_this_month": 1}
    assert o["waiting"] == [{"slug": "demo", "part": "part-01", "waiting": ["stills"]}]
    assert len(o["posts_per_month"]) == 12 and o["posts_per_month"][-1]["youtube"] == 1
    assert o["disk_usage"]["demo"] > 1024


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
    assert client.get("/api/series/demo/parts/part-09").status_code == 404


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
    assert client.post("/api/series/demo/approve-cast", json={"cast_id": "bob"}).status_code == 409  # no sheet
    (lib / "demo" / "cast-sheet.png").write_bytes(b"c")
    r = client.post("/api/series/demo/approve-cast", json={"cast_id": "zed"})
    assert r.status_code == 409 and "not in demo" in r.json()["detail"]
    r = client.post("/api/series/demo/approve-cast", json={"cast_id": "bob"})
    assert r.json()["cast"][0]["approved_at"]


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
