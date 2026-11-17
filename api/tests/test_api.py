import json
import os
import socket
import subprocess
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
from pipeline.scribble.stages import render as render_stage
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
    assert r["part_bytes"] > r["frames_bytes"]
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
    bad = {"slug": "other2", "title": "O", "cast": [full, {**full, "id": "x", "headwear": {"kind": "bowler"}}]}
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
    assert client.delete("/api/props/flag").json()["custom"] == []
    assert client.delete("/api/props/flag").status_code == 404


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
