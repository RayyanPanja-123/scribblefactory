"""render stage: chunking, workers, resume, resets, lock, gates, frame check. Engine and ffmpeg are faked."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.scribble.cli import main
from pipeline.scribble import db
from pipeline.scribble.io import load_part
from pipeline.scribble.stages import render
from pipeline.scribble.stages.runner import StageError

FIX = Path(__file__).parent / "fixtures" / "story"
class PartDir(type(Path())):
    """the part folder, plus .state shared with the fakes"""


GPU = {"renderer": "gpu", "gpu_name": "Test GPU", "driver": "1.0", "chromium": "1", "playwright": "1"}


@pytest.mark.parametrize("total,size,want", [
    (1, 150, [(0, 0)]),
    (150, 150, [(0, 149)]),
    (151, 150, [(0, 149), (150, 150)]),
    (228, 150, [(0, 149), (150, 227)]),
    (450, 150, [(0, 149), (150, 299), (300, 449)]),
    (10, 4, [(0, 3), (4, 7), (8, 9)]),
    (0, 150, []),
])
def test_chunk_ranges(total, size, want):
    got = render.chunk_ranges(total, size)
    assert got == want
    assert sum(b - a + 1 for a, b in got) == total


class FakeWorker:
    """Stands in for a long-lived render.mjs worker: ready at once; a job writes its PNGs and reports done at once,
    or makes the worker die (state["fail"]) or raises KeyboardInterrupt while it is handed out (state["interrupt"])."""

    def __init__(self, part_dir, idx, events, state):
        self.idx, self.info, self.events, self.state, self.frames = idx, None, events, state, part_dir / "frames"
        state["starts"] += 1
        events.put(("ready", self, dict(state["info"])))

    def send(self, first, last):
        self.state["calls"].append((first, last))
        if (first, last) in self.state["interrupt"]:
            raise KeyboardInterrupt
        if (first, last) in self.state["fail"]:
            self.events.put(("exit", self, 1))
            return
        if self.state["lost"] > 0:  # GPU reset: the context is lost, the worker dies
            self.state["lost"] -= 1
            self.lost = True
            self.events.put(("exit", self, 1))
            return
        for n in range(first, last + 1):
            render.frame_path(self.frames, n).write_bytes(b"png")
        self.events.put(("done", self, first, last))

    def close(self):
        pass

    def wait(self):
        pass

    def kill(self):
        self.state["killed"] += 1

    def log_tail(self):
        return "error: WebGL context lost (GPU reset or out of memory)" if getattr(self, "lost", False) else "worker log"


@pytest.fixture
def part(tmp_path, monkeypatch):
    """library/office-nap/part-01 with the fixture story (180 frames = 2 chunks of 150 / 30 with CHUNK=150),
    approvals in place, fake workers, fake ffmpeg."""
    lib = tmp_path / "lib"
    sd = lib / "office-nap"
    pd = sd / "part-01"
    pd.mkdir(parents=True)
    series = json.loads((FIX / "series.json").read_text())
    for c in series["cast"]:
        c["approved_at"] = "2026-11-16T10:00:00Z"
    (sd / "series.json").write_text(json.dumps(series))
    for f in ("story.json", "phrases.json"):
        shutil.copy(FIX / f, pd / f)
    (pd / "voice.mp3").write_bytes(b"voice")
    (pd / "story.md").write_text("# Pilot\n\nBob works.\n")
    part = {"schema_version": 1, "id": "part-01", "number": 1, "title": "Pilot",
            "approvals": {"stills": {"approved_at": "2026-11-16T10:00:00Z"}}}
    (pd / "part.json").write_text(json.dumps(part))

    state = {"info": dict(GPU), "calls": [], "fail": set(), "interrupt": set(), "starts": 0, "killed": 0, "lost": 0}

    monkeypatch.setattr(render, "start_worker", lambda part_dir, idx, swiftshader, events: FakeWorker(part_dir, idx, events, state))
    monkeypatch.setattr(render, "POLL_S", 0.01)
    monkeypatch.setenv("SCRIBBLE_LIBRARY", str(lib))
    pd = PartDir(pd)
    pd.state = state
    return pd


def cli_render(*extra):
    return main(["render", "office-nap", "part-01", *extra])


def test_full_render_writes_chunks_frames_and_preview(part, capsys):
    assert cli_render() == 0
    frames = part / "frames"
    assert sorted(p.name for p in frames.glob("*.png"))[:2] == ["000000.png", "000001.png"]
    assert len(list(frames.glob("*.png"))) == 180
    c1 = json.loads((frames / "chunks" / "c001.json").read_text())
    assert (c1["first"], c1["last"], c1["count"], c1["renderer"]) == (150, 179, 30, GPU)
    assert c1["inputs_hash"] == render.frames_hash(part)
    before = render.frames_hash(part)
    for kind in ("sets", "actions"):  # every library catalog changes pixels: editing one re-renders
        db.put_catalogs(part.parent.parent, {kind: [{"id": "x"}]})
        assert render.frames_hash(part) != before
        before = render.frames_hash(part)
        db.put_catalogs(part.parent.parent, {kind: []})
    out = capsys.readouterr().out
    assert "chunk 1/2 done" in out and "chunk 2/2 done" in out and "fps overall" in out
    assert load_part(part / "part.json").stages.render.status == "done"


def test_resume_skips_finished_chunks(part, capsys):
    part.state["fail"] = {(150, 179)}  # second chunk dies: render fails after chunk 0
    assert cli_render() == 1
    assert load_part(part / "part.json").stages.render.status == "failed"
    assert (part / "frames" / "chunks" / "c000.json").exists()
    part.state["fail"], part.state["calls"] = set(), []
    assert cli_render() == 0
    assert part.state["calls"] == [(150, 179)]  # only the unfinished chunk
    assert "resuming: 1/2 chunk(s) already done" in capsys.readouterr().out


def test_partial_chunk_rerenders(part):
    assert cli_render() == 0
    (part / "frames" / "000160.png").unlink()  # one frame of chunk 1 lost
    part.state["calls"] = []
    render.run(part)  # the stage itself (the CLI would report "up to date": chunks exist, inputs unchanged)
    assert part.state["calls"] == [(150, 179)]
    assert render.frame_path(part / "frames", 160).exists()


def test_hash_change_rerenders_everything(part, capsys):
    assert cli_render() == 0
    stale = part / "frames" / "000005.png"
    stale.write_bytes(b"old")
    story = json.loads((part / "story.json").read_text())
    story["seed"] = 7
    (part / "story.json").write_text(json.dumps(story))
    part.state["calls"] = []
    assert cli_render() == 0
    assert part.state["calls"] == [(0, 149), (150, 179)]
    assert stale.read_bytes() == b"png"
    assert "re-rendering all frames: inputs changed" in capsys.readouterr().out


def test_renderer_change_rerenders_everything(part, capsys):
    assert cli_render() == 0
    part.state["info"] = {**GPU, "driver": "2.0"}
    part.state["calls"] = []
    render.run(part)
    assert part.state["calls"] == [(0, 149), (150, 179)]
    assert "re-rendering all frames: renderer changed (driver: 1.0 -> 2.0)" in capsys.readouterr().out


def test_frame_count_check_fails_on_missing_frames(part):
    frames = part / "frames"
    frames.mkdir()
    for n in range(180):
        if n != 42:
            render.frame_path(frames, n).write_bytes(b"png")
    with pytest.raises(StageError, match=r"1 of 180 frames missing \(first: \[42\]\)"):
        render.check_frames(frames, 0, 180)
    render.frame_path(frames, 42).write_bytes(b"png")
    render.check_frames(frames, 0, 180)


def test_user_files_untouched(part):
    before = {f: (part / f).read_bytes() for f in ("story.md", "voice.mp3")}
    approvals = load_part(part / "part.json").approvals
    stills = part / "frames" / "stills"
    stills.mkdir(parents=True)
    (stills / "s01.png").write_bytes(b"still")
    assert cli_render() == 0
    assert cli_render("--force") == 0
    assert {f: (part / f).read_bytes() for f in before} == before
    assert load_part(part / "part.json").approvals == approvals
    assert (stills / "s01.png").read_bytes() == b"still"


# ---------------- gates ----------------

@pytest.mark.parametrize("cmd,clear,msg", [
    (["render"], "stills", "not approved yet: stills"),
])
def test_gates_need_approvals(part, capsys, cmd, clear, msg):
    pj = json.loads((part / "part.json").read_text())
    pj["approvals"][clear] = {"approved_at": None}
    (part / "part.json").write_text(json.dumps(pj))
    assert main([*cmd, "office-nap", "part-01"]) == 1
    assert msg in capsys.readouterr().err
    assert part.state["calls"] == []
    assert load_part(part / "part.json").stages.render.status == "pending"


@pytest.mark.parametrize("cmd", [["render"]])
def test_gates_need_cast_approval(part, capsys, cmd):
    sj = part.parent / "series.json"
    s = json.loads(sj.read_text())
    s["cast"][1]["approved_at"] = None
    sj.write_text(json.dumps(s))
    assert main([*cmd, "office-nap", "part-01"]) == 1
    assert "cast not approved: amy" in capsys.readouterr().err

def test_ctrl_c_kills_workers_marks_failed_and_resumes(part):
    from pipeline.scribble.stages.runner import run_stage
    part.state["interrupt"] = {(150, 179)}  # the user hits Ctrl+C while the second chunk is handed out
    with pytest.raises(KeyboardInterrupt):
        run_stage(part, "render", lambda d: render.run(d, workers=1), inputs=render.INPUTS, outputs=render.OUTPUTS)
    assert part.state["killed"] == 1  # every worker tree killed
    assert load_part(part / "part.json").stages.render.status == "failed"
    assert not render.lock_path(part).exists()  # lock released
    part.state["interrupt"], part.state["calls"] = set(), []
    assert cli_render() == 0
    assert part.state["calls"] == [(150, 179)]


def test_killed_worker_leftovers_do_not_reset(part, capsys):
    """A hard-killed worker leaves cNNN.info.json / .log and some PNGs but no chunk record: resume, don't reset."""
    part.state["fail"] = {(150, 179)}
    assert cli_render() == 1
    chunks = part / "frames" / "chunks"
    (chunks / "c001.info.json").write_text(json.dumps(GPU))  # leftover from the killed worker
    render.frame_path(part / "frames", 150).write_bytes(b"half")
    part.state["fail"], part.state["calls"] = set(), []
    assert cli_render() == 0
    assert part.state["calls"] == [(150, 179)]
    assert "re-rendering all frames" not in capsys.readouterr().out


# ---------------- long-lived workers ----------------

def test_one_browser_per_worker_not_per_chunk(part):
    assert cli_render("--workers", "1") == 0
    assert part.state["calls"] == [(0, 149), (150, 179)] and part.state["starts"] == 1
    part.state["starts"] = 0
    assert cli_render("--force", "--workers", "5") == 0
    assert part.state["starts"] == 2  # never more workers than chunks


def test_chunk_record_shape_unchanged(part):
    assert cli_render() == 0
    for i, (a, b) in enumerate([(0, 149), (150, 179)]):
        c = json.loads(render.chunk_json(part / "frames", i).read_text())
        assert set(c) == {"first", "last", "count", "renderer", "inputs_hash"}
        assert (c["first"], c["last"], c["count"], c["renderer"]) == (a, b, b - a + 1, GPU)


def test_failed_worker_stops_render_and_kills_all(part, capsys):
    part.state["fail"] = {(0, 149)}
    assert cli_render() == 1
    assert part.state["killed"] == 2
    assert "render worker 0 stopped (exit 1): worker log" in load_part(part / "part.json").stages.render.error
    assert not render.lock_path(part).exists()


def test_gpu_reset_restarts_worker_and_retries_chunk(part, capsys):
    part.state["lost"] = 2  # two context losses: each worker is replaced, every chunk still lands
    assert cli_render("--workers", "1") == 0
    assert len(list((part / "frames").glob("*.png"))) == 180
    assert part.state["starts"] == 3
    assert "WebGL context lost (GPU reset), starting a new one (2/3)" in capsys.readouterr().out


def test_gpu_resets_give_up_after_the_limit(part):
    part.state["lost"] = render.GPU_RESETS + 1
    assert cli_render("--workers", "1") == 1
    assert "WebGL context lost" in load_part(part / "part.json").stages.render.error


# ---------------- lock ----------------

def test_lock_refuses_second_render(part, capsys):
    lock = render.lock_path(part)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()))  # a live process holds it
    assert cli_render() == 1
    assert f"another render is running on office-nap part-01 (pid {os.getpid()})" in capsys.readouterr().err
    assert part.state["starts"] == 0
    assert load_part(part / "part.json").stages.render.status == "pending"  # the running render's status untouched
    with pytest.raises(StageError, match="another render is running"):
        render.run(part)
    assert lock.read_text() == str(os.getpid())  # not ours: left alone


def test_stale_lock_is_removed_with_a_note(part, capsys):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    lock = render.lock_path(part)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(dead.pid))
    assert render.lock_owner(part) is None
    assert cli_render() == 0
    assert f"removing stale render lock ({dead.pid} is not running)" in capsys.readouterr().out
    assert not lock.exists()


def test_pid_alive():
    assert render.pid_alive(os.getpid())
    assert not render.pid_alive(0) and not render.pid_alive(-5)


def _stale_lock_with(part, worker_cmd):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    proc = subprocess.Popen(worker_cmd, **render.GROUP)
    lock = render.lock_path(part)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"{dead.pid}\n{proc.pid}")
    return proc


@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")
def test_stale_lock_stops_leftover_node_worker(part, capsys):
    orphan = _stale_lock_with(part, [shutil.which("node"), "-e", "setTimeout(() => {}, 60000)"])
    try:
        assert cli_render() == 0
        assert f"stopping leftover render worker {orphan.pid} (node" in capsys.readouterr().out
        orphan.wait(timeout=10)
        assert not render.pid_alive(orphan.pid)
    finally:
        render.kill_tree(orphan)


def test_stale_lock_never_kills_a_reused_pid(part, capsys):
    other = _stale_lock_with(part, [sys.executable, "-c", "import time; time.sleep(60)"])  # PID now some python
    try:
        assert cli_render() == 0
        out = capsys.readouterr().out
        assert f"not stopping pid {other.pid} from the stale lock: it is python" in out
        assert render.pid_alive(other.pid)
    finally:
        render.kill_tree(other)


def test_process_name():
    assert "python" in render.process_name(os.getpid()).lower()
    assert render.RENDER_PROCESS.match("node.exe") and render.RENDER_PROCESS.match("chrome-headless-shell.exe")
    assert render.RENDER_PROCESS.match("chrome") and not render.RENDER_PROCESS.match("python.exe")


# ---------------- worker count ----------------

def test_workers_capped_to_remaining_chunks(part):
    part.state["fail"] = {(150, 179)}
    assert cli_render() == 1  # chunk 0 done, chunk 1 left
    part.state.update(fail=set(), starts=0, calls=[])
    assert cli_render("--workers", "5") == 0
    assert (part.state["starts"], part.state["calls"]) == (1, [(150, 179)])


def test_nothing_left_still_checks_renderer_with_one_worker(part, capsys):
    assert cli_render() == 0
    part.state.update(starts=0, calls=[])
    render.run(part, workers=4)  # all chunks done, same renderer
    assert (part.state["starts"], part.state["calls"]) == (1, [])
    part.state.update(starts=0, info={**GPU, "driver": "9.9"})
    render.run(part, workers=4)  # renderer changed: everything again, pool grows to the work
    assert part.state["starts"] == 2 and part.state["calls"] == [(0, 149), (150, 179)]
    assert "renderer changed (driver: 1.0 -> 9.9)" in capsys.readouterr().out


def test_workers_default_from_settings_and_flag_wins(part, capsys):
    (part.parents[1] / "settings.json").write_text(json.dumps({"render_workers": 1}))
    assert cli_render() == 0
    assert part.state["starts"] == 1 and "render: 1 worker" in capsys.readouterr().out
    part.state["starts"] = 0
    assert cli_render("--force", "--workers", "5") == 0
    assert part.state["starts"] == 2  # explicit flag beats the setting (capped to the 2 chunks)


def test_use_for_notes_never_change_the_frames_hash(tmp_path):
    import json as _json
    from pipeline.scribble.stages.render import pixel_bytes
    raw = _json.dumps({"props": [{"id": "staff", "name": "Staff", "shapes": []}]}).encode()
    assert pixel_bytes("props.json", raw) == raw  # no notes: the raw bytes, so frames rendered before notes stay valid
    noted = lambda note: _json.dumps({"props": [{"id": "staff", "name": "Staff", "use_for": note, "shapes": []}]}).encode()  # noqa: E731
    a = pixel_bytes("props.json", noted("a wizard's staff"))
    assert pixel_bytes("props.json", noted("any magic moment")) == a
    assert pixel_bytes("props.json", noted("any magic moment").replace(b'"shapes": []', b'"shapes": [1]')) != a  # the drawing counts
