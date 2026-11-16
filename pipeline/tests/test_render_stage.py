"""render stage: chunking, resume, resets, gates, frame check. The engine and ffmpeg are faked (no browser here)."""

import json
import shutil
from pathlib import Path

import pytest

from pipeline.scribble.cli import main
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


class FakeProc:
    """Stands in for a render.mjs worker: writes its PNGs and info file at once, exits 0."""

    def __init__(self, frames, first, last, info_out, info, fail):
        self.returncode = None
        if not fail:
            for n in range(first, last + 1):
                render.frame_path(frames, n).write_bytes(b"png")
            Path(info_out).write_text(json.dumps(info))
        self._rc = 1 if fail else 0

    def poll(self):
        self.returncode = self._rc
        return self._rc

    def terminate(self):
        pass

    def wait(self):
        return self._rc


@pytest.fixture
def part(tmp_path, monkeypatch):
    """library/office-nap/part-01 with the fixture story (180 frames = 2 chunks of 150 / 30 with CHUNK=150),
    approvals in place, fake engine, fake probe, fake ffmpeg."""
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
            "approvals": {"stills": {"approved_at": "2026-11-16T10:00:00Z"},
                          "test_render": {"approved_at": "2026-11-16T10:00:00Z"}}}
    (pd / "part.json").write_text(json.dumps(part))

    state = {"info": dict(GPU), "calls": [], "fail": set()}

    def fake_start(part_dir, i, first, last, swiftshader):
        state["calls"].append((first, last))
        info_out = part_dir / "frames" / "chunks" / f"c{i:03d}.info.json"
        return FakeProc(part_dir / "frames", first, last, info_out, state["info"], (first, last) in state["fail"])

    def fake_encode(frames, first, count, voice, out):
        out.write_bytes(b"mp4")
        return out

    monkeypatch.setattr(render, "start_chunk", fake_start)
    monkeypatch.setattr(render, "probe", lambda part_dir, swiftshader: dict(state["info"]))
    monkeypatch.setattr(render, "encode", fake_encode)
    monkeypatch.setattr(render, "POLL_S", 0)
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
    assert (part / "preview.mp4").read_bytes() == b"mp4"
    out = capsys.readouterr().out
    assert "chunk 1/2 done" in out and "chunk 2/2 done" in out and "fps overall" in out
    assert load_part(part / "part.json").stages.render.status == "done"


def test_resume_skips_finished_chunks(part, capsys):
    part.state["fail"] = {(150, 179)}  # second chunk dies: render fails after chunk 0
    assert cli_render() == 1
    assert load_part(part / "part.json").stages.render.status == "failed"
    assert (part / "frames" / "chunks" / "c000.json").exists()
    assert not (part / "preview.mp4").exists()
    part.state["fail"], part.state["calls"] = set(), []
    assert cli_render() == 0
    assert part.state["calls"] == [(150, 179)]  # only the unfinished chunk
    assert "resuming: 1/2 chunk(s) already done" in capsys.readouterr().out


def test_partial_chunk_rerenders(part):
    assert cli_render() == 0
    (part / "frames" / "000160.png").unlink()  # one frame of chunk 1 lost
    part.state["calls"] = []
    render.run(part)  # the stage itself (the CLI would report "up to date": preview.mp4 exists, inputs unchanged)
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
    (["render"], "test_render", "not approved yet: test_render"),
    (["test-render"], "stills", "not approved yet: stills"),
])
def test_gates_need_approvals(part, capsys, cmd, clear, msg):
    pj = json.loads((part / "part.json").read_text())
    pj["approvals"][clear] = {"approved_at": None}
    (part / "part.json").write_text(json.dumps(pj))
    assert main([*cmd, "office-nap", "part-01"]) == 1
    assert msg in capsys.readouterr().err
    assert part.state["calls"] == []
    assert load_part(part / "part.json").stages.render.status == "pending"


@pytest.mark.parametrize("cmd", [["render"], ["test-render"]])
def test_gates_need_cast_approval(part, capsys, cmd):
    sj = part.parent / "series.json"
    s = json.loads(sj.read_text())
    s["cast"][1]["approved_at"] = None
    sj.write_text(json.dumps(s))
    assert main([*cmd, "office-nap", "part-01"]) == 1
    assert "cast not approved: amy" in capsys.readouterr().err


def test_test_render_clamps_start(part, monkeypatch):
    calls = []

    class R:
        returncode, stderr = 0, ""

    def fake_run(cmd, **kw):
        a, b = map(int, cmd[cmd.index("--frames") + 1].split("-"))
        out = Path(cmd[cmd.index("--out-dir") + 1])
        for n in range(a, b + 1):
            render.frame_path(out, n).write_bytes(b"png")
        calls.append((a, b))
        return R()

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    monkeypatch.setattr(render.shutil, "which", lambda name: name)
    assert main(["test-render", "office-nap", "part-01", "--at", "4"]) == 0  # 4 s = frame 120, but only 180 frames
    assert calls == [(30, 179)]
    assert (part / "test-render.mp4").read_bytes() == b"mp4"
    assert main(["test-render", "office-nap", "part-01"]) == 0
    assert calls[-1] == (0, 149)


def test_ctrl_c_stops_workers_marks_failed_and_resumes(part, monkeypatch):
    from pipeline.scribble.stages.runner import run_stage
    terminated = []

    class Interrupted(FakeProc):
        def poll(self):
            raise KeyboardInterrupt

        def terminate(self):
            terminated.append(True)

    real_start = render.start_chunk

    def start(part_dir, i, first, last, swiftshader):
        if first == 150:  # second chunk: the user hits Ctrl+C while it renders
            return Interrupted(part_dir / "frames", first, last, part_dir / "x", {}, fail=True)
        return real_start(part_dir, i, first, last, swiftshader)

    monkeypatch.setattr(render, "start_chunk", start)
    monkeypatch.setattr(render, "WORKERS", 1)
    with pytest.raises(KeyboardInterrupt):
        run_stage(part, "render", lambda d: render.run(d, workers=1), inputs=render.INPUTS, outputs=render.OUTPUTS)
    assert terminated == [True]
    assert load_part(part / "part.json").stages.render.status == "failed"
    monkeypatch.setattr(render, "start_chunk", real_start)
    part.state["calls"] = []
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
