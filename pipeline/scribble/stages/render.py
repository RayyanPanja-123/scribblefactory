"""render: chunked, parallel, resumable full render -> frames/000000.png... + preview.mp4 (voice only, no music).

Frames render in chunks of CHUNK frames; each worker is its own `node engine/render.mjs --frames A-B` process.
A finished chunk writes frames/chunks/cNNN.json {first, last, count, renderer, inputs_hash}. A chunk is skipped
on the next run only if its json, all its PNGs and the inputs hash match. If the inputs hash or the renderer
(GPU / driver / Chromium...) differs from the existing chunks, every frame is deleted and re-rendered.
Only frames/*.png, frames/chunks/, frames/test/ and the two mp4s are ever written or deleted.
Also here: the test render (5 s clip with its voice slice) and the approval gates.
"""

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from ..io import atomic_write_json, load_part
from ..schemas import SeriesModel, StoryModel
from .runner import StageError
from .validate import load_model

ENGINE = Path(__file__).resolve().parents[3] / "engine"
RENDER_MJS = ENGINE / "render.mjs"
PAGE_FILES = sorted((ENGINE / "page").glob("*.js"))
FPS = 30
CHUNK = 150
WORKERS = 2
TEST_FRAMES = 150  # 5 s
POLL_S = 0.2

INPUTS = ["story.json", "phrases.json", "../series.json", "voice.mp3", *map(str, PAGE_FILES)]
OUTPUTS = ["preview.mp4"]


# ---------------- gates ----------------

def unapproved_cast(story: StoryModel, series: SeriesModel) -> list[str]:
    approved = {c.id for c in series.cast if c.approved_at}
    return [c for c in dict.fromkeys(a.cast_id for s in story.shots for a in s.actors) if c not in approved]


def check_gate(part_dir: Path, needs: tuple[str, ...]) -> StoryModel:
    """Approvals the render needs, and every on-stage cast member approved. Returns the story."""
    slug, part = part_dir.parent.name, part_dir.name
    approvals = load_part(part_dir / "part.json").approvals
    missing = [n for n in needs if not getattr(approvals, n).approved_at]
    if missing:
        raise StageError(f"not approved yet: {', '.join(missing)} (approve {slug} {part} {missing[0]})")
    story = load_model(part_dir / "story.json", StoryModel)
    waiting = unapproved_cast(story, load_model(part_dir.parent / "series.json", SeriesModel))
    if waiting:
        raise StageError(f"cast not approved: {', '.join(waiting)} (cast-sheet {slug}, then approve-cast {slug} <id>)")
    return story


# ---------------- chunks ----------------

def chunk_ranges(total: int, size: int = CHUNK) -> list[tuple[int, int]]:
    """[(first, last)] inclusive, covering 0..total-1; the last chunk may be short."""
    return [(a, min(a + size, total) - 1) for a in range(0, total, size)]


def frames_hash(part_dir: Path) -> str:
    """sha256 over story.json, phrases.json, series.json and the engine page code: anything that changes pixels."""
    h = hashlib.sha256()
    for f in [part_dir / "story.json", part_dir / "phrases.json", part_dir.parent / "series.json", *PAGE_FILES]:
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def frame_path(frames: Path, n: int) -> Path:
    return frames / f"{n:06d}.png"


def chunk_json(frames: Path, i: int) -> Path:
    return frames / "chunks" / f"c{i:03d}.json"


def wipe_frames(frames: Path) -> None:
    """Delete rendered frames and chunk records (not stills/ or test/)."""
    for f in frames.glob("[0-9]*.png"):
        f.unlink()
    shutil.rmtree(frames / "chunks", ignore_errors=True)


def node_cmd(*args, swiftshader: bool) -> list[str]:
    node = shutil.which("node")
    if not node:
        raise StageError("node not found on PATH")
    return [node, str(RENDER_MJS), *map(str, args), *(["--swiftshader"] if swiftshader else [])]


def probe(part_dir: Path, swiftshader: bool) -> dict:
    """Renderer info the engine would use right now (GPU or SwiftShader fallback, driver, Chromium...)."""
    out = part_dir / "frames" / "chunks" / "probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(node_cmd("--probe", "--info-out", out, swiftshader=swiftshader), capture_output=True, text=True)
    if r.returncode != 0:
        raise StageError(f"render.mjs --probe failed: {r.stderr.strip()[-300:]}")
    print(r.stdout.strip())
    info = json.loads(out.read_text(encoding="utf-8"))
    out.unlink()
    return info


def start_chunk(part_dir: Path, i: int, first: int, last: int, swiftshader: bool):
    """Popen of one worker rendering frames first..last; its output goes to frames/chunks/cNNN.log."""
    chunks = part_dir / "frames" / "chunks"
    log = open(chunks / f"c{i:03d}.log", "w", encoding="utf-8")
    try:
        return subprocess.Popen(node_cmd("--part", part_dir, "--frames", f"{first}-{last}", "--out-dir", part_dir / "frames",
                                         "--info-out", chunks / f"c{i:03d}.info.json", swiftshader=swiftshader),
                                stdout=log, stderr=subprocess.STDOUT)
    finally:
        log.close()  # the child keeps its own handle


def _log_tail(frames: Path, i: int) -> str:
    f = frames / "chunks" / f"c{i:03d}.log"
    return f.read_text(encoding="utf-8", errors="replace").strip()[-400:] if f.exists() else ""


def _chunk_ok(frames: Path, i: int, first: int, last: int, digest: str) -> bool:
    f = chunk_json(frames, i)
    if not f.exists():
        return False
    c = json.loads(f.read_text(encoding="utf-8"))
    return ((c.get("first"), c.get("last"), c.get("inputs_hash")) == (first, last, digest)
            and all(frame_path(frames, n).exists() for n in range(first, last + 1)))


def reset_reason(frames: Path, digest: str, info: dict) -> str | None:
    """Why existing chunks can't be reused (inputs or renderer changed), or None."""
    for f in sorted((frames / "chunks").glob("c[0-9][0-9][0-9].json")):  # chunk records only, not *.info.json
        c = json.loads(f.read_text(encoding="utf-8"))
        if c.get("inputs_hash") != digest:
            return "inputs changed (story, phrases, series or engine code)"
        if c.get("renderer") != info:
            old = c.get("renderer") or {}
            changed = [k for k in sorted(set(old) | set(info)) if old.get(k) != info.get(k)]
            return f"renderer changed ({', '.join(f'{k}: {old.get(k)} -> {info.get(k)}' for k in changed)})"
    return None


def render_chunks(part_dir: Path, total: int, workers: int, swiftshader: bool, force: bool) -> None:
    frames = part_dir / "frames"
    (frames / "chunks").mkdir(parents=True, exist_ok=True)
    digest, info = frames_hash(part_dir), probe(part_dir, swiftshader)
    reason = "--force" if force else reset_reason(frames, digest, info)
    if reason:
        print(f"re-rendering all frames: {reason}")
        wipe_frames(frames)
        (frames / "chunks").mkdir(parents=True, exist_ok=True)
    ranges = chunk_ranges(total)
    todo = [(i, a, b) for i, (a, b) in enumerate(ranges) if not _chunk_ok(frames, i, a, b, digest)]
    done = len(ranges) - len(todo)
    if done:
        print(f"resuming: {done}/{len(ranges)} chunk(s) already done")
    running, rendered, t_start = {}, 0, time.monotonic()
    try:
        while todo or running:
            while todo and len(running) < workers:
                i, a, b = todo.pop(0)
                running[i] = (start_chunk(part_dir, i, a, b, swiftshader), a, b, time.monotonic())
            time.sleep(POLL_S)
            for i, (proc, a, b, t0) in list(running.items()):
                if proc.poll() is None:
                    continue
                del running[i]
                if proc.returncode != 0:
                    raise StageError(f"chunk {i} (frames {a}-{b}) failed (exit {proc.returncode}): {_log_tail(frames, i)}")
                missing = [n for n in range(a, b + 1) if not frame_path(frames, n).exists()]
                if missing:
                    raise StageError(f"chunk {i} finished but frames are missing: {missing[:5]}")
                info_file = frames / "chunks" / f"c{i:03d}.info.json"
                chunk_info = json.loads(info_file.read_text(encoding="utf-8"))
                info_file.unlink()
                atomic_write_json(chunk_json(frames, i), {"first": a, "last": b, "count": b - a + 1,
                                                          "renderer": chunk_info, "inputs_hash": digest})
                done += 1
                rendered += b - a + 1
                print(f"chunk {done}/{len(ranges)} done (frames {a}-{b}, {(b - a + 1) / max(time.monotonic() - t0, 1e-3):.1f} fps)")
    finally:
        for proc, *_ in running.values():  # failure or Ctrl+C: stop the other workers
            proc.terminate()
            proc.wait()
    if rendered:
        secs = max(time.monotonic() - t_start, 1e-3)
        print(f"rendered {rendered} frames in {secs:.1f} s ({rendered / secs:.1f} fps overall, {workers} worker(s))")


def check_frames(frames: Path, first: int, count: int) -> None:
    missing = [n for n in range(first, first + count) if not frame_path(frames, n).exists()]
    if missing:
        raise StageError(f"{len(missing)} of {count} frames missing (first: {missing[:5]}); render again")


# ---------------- encoding ----------------

def encode(frames: Path, first: int, count: int, voice: Path, out: Path) -> Path:
    """frames first..first+count-1 + the matching voice slice -> H.264 yuv420p 30 fps mp4, written atomically."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise StageError("ffmpeg not found on PATH")
    if not voice.exists():
        raise StageError(f"{voice.name} not found")
    tmp = out.with_name(f".{out.stem}.tmp.mp4")
    r = subprocess.run([ffmpeg, "-y", "-v", "error", "-framerate", str(FPS), "-start_number", str(first),
                        "-i", str(frames / "%06d.png"), "-ss", f"{first / FPS:.3f}", "-t", f"{count / FPS:.3f}",
                        "-i", str(voice), "-map", "0:v", "-map", "1:a", "-frames:v", str(count),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-crf", "18",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise StageError(f"ffmpeg failed: {r.stderr.strip()[-400:]}")
    os.replace(tmp, out)
    return out


# ---------------- entry points ----------------

def run(part_dir: Path, workers: int = WORKERS, swiftshader: bool = False, force: bool = False) -> None:
    story = check_gate(part_dir, ("stills", "test_render"))
    render_chunks(part_dir, story.duration_frames, workers, swiftshader, force)
    check_frames(part_dir / "frames", 0, story.duration_frames)
    out = encode(part_dir / "frames", 0, story.duration_frames, part_dir / "voice.mp3", part_dir / "preview.mp4")
    print(f"preview: {out}")


def test_render(part_dir: Path, at: float = 0.0, swiftshader: bool = False) -> Path:
    """TEST_FRAMES frames from `at` seconds (clamped to the part) -> part-NN/test-render.mp4 with its voice slice."""
    story = check_gate(part_dir, ("stills",))
    total = story.duration_frames
    count = min(TEST_FRAMES, total)
    first = max(0, min(round(at * FPS), total - count))
    test = part_dir / "frames" / "test"
    shutil.rmtree(test, ignore_errors=True)
    test.mkdir(parents=True)
    t0 = time.monotonic()
    r = subprocess.run(node_cmd("--part", part_dir, "--frames", f"{first}-{first + count - 1}", "--out-dir", test,
                                "--info-out", test / "renderer.json", swiftshader=swiftshader),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise StageError(f"test render failed: {r.stderr.strip()[-400:]}")
    secs = max(time.monotonic() - t0, 1e-3)
    print(f"rendered frames {first}-{first + count - 1} in {secs:.1f} s ({count / secs:.1f} fps)")
    check_frames(test, first, count)
    return encode(test, first, count, part_dir / "voice.mp3", part_dir / "test-render.mp4")

