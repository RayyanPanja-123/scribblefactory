"""render: chunked, parallel, resumable full render -> frames/000000.png... + preview.mp4 (voice only, no music).

Frames render in chunks of CHUNK frames. Each worker is one long-lived `node engine/render.mjs --worker` process
(one browser, one driver lookup, one page build) that renders the chunks it is handed over stdin.
A finished chunk writes frames/chunks/cNNN.json {first, last, count, renderer, inputs_hash}. A chunk is skipped
on the next run only if its json, all its PNGs and the inputs hash match. If the inputs hash or the renderer
(GPU / driver / Chromium...) differs from the existing chunks, every frame is deleted and re-rendered.
Only frames/*.png, frames/chunks/, frames/test/, frames/.render.lock and the two mp4s are ever written or deleted.
Process safety: workers run in their own process group; on Ctrl+C, failure or exit each worker's whole tree
(node + Chromium) is killed. frames/.render.lock (holding the PID) stops a second render on the same part.
Also here: the test render (5 s clip with its voice slice) and the approval gates.
"""

import hashlib
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .. import settings
from ..io import LIBRARY_FILES, WARDROBE_SEED, atomic_write_bytes, atomic_write_json, load_part
from ..schemas import SeriesModel, StoryModel
from .runner import StageError
from .validate import load_model

ENGINE = Path(__file__).resolve().parents[3] / "engine"
RENDER_MJS = ENGINE / "render.mjs"
PAGE_FILES = [*sorted((ENGINE / "page").glob("*.js")), WARDROBE_SEED]  # the seed draws while the library has no wardrobe.json
FPS = 30
CHUNK = 150
TEST_FRAMES = 150  # 5 s
POLL_S = 0.5           # how often the scheduler wakes up (keeps Ctrl+C responsive)
READY_TIMEOUT_S = 120  # browser start + page build per worker
EXIT_TIMEOUT_S = 30

INPUTS = ["story.json", "phrases.json", "../series.json", *(f"../../{f}" for f in LIBRARY_FILES), "voice-tight.wav",
          *map(str, PAGE_FILES)]
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
    """sha256 over story.json, phrases.json, series.json, every library file (props, sets, creatures, actions) and the
    engine page code: anything that changes pixels."""
    h = hashlib.sha256()
    for f in [part_dir / "story.json", part_dir / "phrases.json", part_dir.parent / "series.json",
              *(part_dir.parent.parent / f for f in LIBRARY_FILES), *PAGE_FILES]:
        h.update(f.name.encode() + b"\0" + (pixel_bytes(f) if f.exists() else b"<missing>") + b"\0")
    return h.hexdigest()


def pixel_bytes(f: Path) -> bytes:
    """the file's bytes as far as pixels go: a library file's "use_for" notes (for the story AI) are left out, so
    editing a note never re-renders. A file without notes hashes as its raw bytes, so older chunks stay valid."""
    data = f.read_bytes()
    if f.name not in LIBRARY_FILES or b'"use_for"' not in data:
        return data
    strip = lambda v: ({k: strip(x) for k, x in v.items() if k != "use_for"} if isinstance(v, dict)  # noqa: E731
                       else [strip(x) for x in v] if isinstance(v, list) else v)
    return json.dumps(strip(json.loads(data)), sort_keys=True).encode()


def frame_path(frames: Path, n: int) -> Path:
    return frames / f"{n:06d}.png"


def chunk_json(frames: Path, i: int) -> Path:
    return frames / "chunks" / f"c{i:03d}.json"


def wipe_frames(frames: Path) -> None:
    """Delete rendered frames and chunk records (not stills/, test/, the lock or live worker logs)."""
    for f in [*frames.glob("[0-9]*.png"), *(frames / "chunks").glob("c[0-9][0-9][0-9].json"),
              *(frames / "chunks").glob("*.info.json")]:
        f.unlink()


def node_cmd(*args, swiftshader: bool) -> list[str]:
    node = shutil.which("node")
    if not node:
        raise StageError("node not found on PATH")
    return [node, str(RENDER_MJS), *map(str, args), *(["--swiftshader"] if swiftshader else [])]


# ---------------- processes ----------------

# own process group / session: Ctrl+C reaches only Python, which then kills each worker tree itself
GROUP = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}


def kill_pid_tree(pid: int) -> None:
    """Kill a process and everything it started (node -> Chromium). Workers lead their own group/session."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


RENDER_PROCESS = re.compile(r"^(node|chrome|chromium|chromium-browser|chrome-headless-shell|headless_shell)(\.exe)?$", re.I)
RUNNER_PROCESS = re.compile(r"^(python[0-9.]*|pythonw?)(\.exe)?$", re.I)  # the CLI running a stage or job step


def process_name(pid: int) -> str | None:
    """Executable name of a running PID (Windows: tasklist; others: ps), or None."""
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True)
        m = re.match(r'"([^"]+)","(\d+)"', r.stdout.strip())
        return m[1] if m and int(m[2]) == pid else None
    r = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True)
    return Path(r.stdout.strip()).name or None


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    kill_pid_tree(proc.pid)
    try:
        proc.wait(timeout=EXIT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        pass


def run_tree(cmd: list[str]) -> subprocess.CompletedProcess:
    """subprocess.run that kills the whole child tree if we are interrupted."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **GROUP)
    try:
        out, err = proc.communicate()
    except BaseException:
        kill_tree(proc)
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


class Worker:
    """One long-lived `render.mjs --worker`: READY <info>, then "A B" jobs in, "DONE A B" out. Events go to `events`."""

    def __init__(self, part_dir: Path, idx: int, swiftshader: bool, events: queue.Queue):
        self.idx, self.info, self.log = idx, None, part_dir / "frames" / "chunks" / f"worker{idx}.log"
        with open(self.log, "w", encoding="utf-8") as log:
            self.proc = subprocess.Popen(
                node_cmd("--part", part_dir, "--worker", "--out-dir", part_dir / "frames", swiftshader=swiftshader),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1, **GROUP)
        threading.Thread(target=self._read, args=(events,), daemon=True).start()

    def _read(self, events: queue.Queue) -> None:
        for line in self.proc.stdout:
            word, _, rest = line.strip().partition(" ")
            if word == "READY":
                events.put(("ready", self, json.loads(rest)))
            elif word == "DONE":
                first, last = map(int, rest.split())
                events.put(("done", self, first, last))
        events.put(("exit", self, self.proc.wait()))

    def send(self, first: int, last: int) -> None:
        self.proc.stdin.write(f"{first} {last}\n")
        self.proc.stdin.flush()

    def close(self) -> None:
        """No more jobs: the worker finishes and exits."""
        try:
            self.proc.stdin.close()
        except OSError:
            pass

    def wait(self) -> None:
        try:
            self.proc.wait(timeout=EXIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            pass

    def kill(self) -> None:
        kill_tree(self.proc)

    def log_tail(self) -> str:
        return self.log.read_text(encoding="utf-8", errors="replace").strip()[-400:] if self.log.exists() else ""


def start_worker(part_dir: Path, idx: int, swiftshader: bool, events: queue.Queue) -> Worker:
    return Worker(part_dir, idx, swiftshader, events)


def next_event(events: queue.Queue, timeout: float) -> tuple:
    """Blocking get in short slices, so Ctrl+C is handled promptly on Windows too."""
    end = time.monotonic() + timeout
    while True:
        try:
            return events.get(timeout=POLL_S)
        except queue.Empty:
            if time.monotonic() > end:
                raise StageError(f"no word from the render workers for {timeout:.0f} s")


# ---------------- lock ----------------

def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":  # os.kill(pid, 0) would TerminateProcess on Windows
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lock_path(part_dir: Path) -> Path:
    return part_dir / "frames" / ".render.lock"


def _lock_pids(part_dir: Path) -> list[int]:
    """[render pid, worker pids...] from the lock file ([] if none or unreadable)."""
    try:
        return [int(x) for x in lock_path(part_dir).read_text(encoding="utf-8").split()]
    except (OSError, ValueError):
        return []


def lock_owner(part_dir: Path) -> int | None:
    """PID of a live render holding this part's lock, else None."""
    pids = _lock_pids(part_dir)
    return pids[0] if pids and pid_alive(pids[0]) else None


def lock_add_workers(part_dir: Path, pids: list[int]) -> None:
    """Record worker PIDs, so a later render can stop them if this one dies without cleaning up."""
    with open(lock_path(part_dir), "a", encoding="utf-8") as f:
        f.write("".join(f"\n{p}" for p in pids))


def clear_stale_lock(part_dir: Path) -> list[str]:
    """A lock whose render is gone: stop the workers it outlived (only if the PID still is a render process: never
    a reused PID), then remove the lock. Returns what was done; [] if there is no stale lock."""
    f = lock_path(part_dir)
    if not f.exists() or lock_owner(part_dir):
        return []
    pids = _lock_pids(part_dir)
    notes = [f"removing stale render lock ({pids[0] if pids else '?'} is not running)"]
    for w in [p for p in pids[1:] if pid_alive(p)]:
        name = process_name(w)
        if name and RENDER_PROCESS.match(name):
            notes.append(f"stopping leftover render worker {w} ({name})")
            kill_pid_tree(w)
        else:
            notes.append(f"not stopping pid {w} from the stale lock: it is {name or 'unknown'}, not a render worker")
    f.unlink(missing_ok=True)
    return notes


@contextmanager
def render_lock(part_dir: Path):
    f = lock_path(part_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    pid = lock_owner(part_dir)
    if pid:
        raise StageError(f"another render is running on this part (pid {pid}); wait for it or stop it")
    for note in clear_stale_lock(part_dir):
        print(f"note: {note}")
    try:
        fd = os.open(f, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise StageError("another render started on this part just now")
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(str(os.getpid()))
    try:
        yield
    finally:
        f.unlink(missing_ok=True)


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
    digest, ranges = frames_hash(part_dir), chunk_ranges(total)
    events: queue.Queue = queue.Queue()
    pool: list = []

    def grow(n: int) -> None:
        """Start workers until there are n, and wait until each has reported its renderer."""
        new = [start_worker(part_dir, k, swiftshader, events) for k in range(len(pool), n)]
        pool.extend(new)
        if new and lock_path(part_dir).exists():
            lock_add_workers(part_dir, [w.proc.pid for w in new if hasattr(w, "proc")])
        for _ in new:
            ev = next_event(events, READY_TIMEOUT_S)
            if ev[0] == "exit":
                raise StageError(f"render worker failed to start (exit {ev[2]}): {ev[1].log_tail()}")
            ev[1].info = ev[2]
        infos = [w.info for w in pool]
        if any(i != infos[0] for i in infos):
            raise StageError(f"render workers disagree on the renderer: {infos}")

    def remaining() -> list[tuple[int, int, int]]:
        return [(i, a, b) for i, (a, b) in enumerate(ranges) if not _chunk_ok(frames, i, a, b, digest)]

    try:
        # never more workers than chunks left; one always starts, to learn the renderer (a change resets all)
        grow(max(1, min(workers, len(ranges) if force else len(remaining()))))
        info = pool[0].info
        print(f"webgl: {info['renderer']} ({info['gpu_name']})")
        reason = "--force" if force else reset_reason(frames, digest, info)
        if reason:
            print(f"re-rendering all frames: {reason}")
            wipe_frames(frames)
            (frames / "chunks").mkdir(parents=True, exist_ok=True)
        todo = remaining()
        grow(max(len(pool), min(workers, len(todo))))  # a reset can mean more work than first counted
        done = len(ranges) - len(todo)
        if done:
            print(f"resuming: {done}/{len(ranges)} chunk(s) already done")
        idle, busy, rendered, t_start = list(pool), {}, 0, time.monotonic()
        while todo or busy:
            while todo and idle:
                w = idle.pop(0)
                i, a, b = todo.pop(0)
                w.send(a, b)
                busy[w] = (i, a, b, time.monotonic())
            ev = next_event(events, READY_TIMEOUT_S + CHUNK * 10)
            if ev[0] == "exit":
                raise StageError(f"render worker {ev[1].idx} stopped (exit {ev[2]}): {ev[1].log_tail()}")
            if ev[0] != "done":
                continue
            w, (i, a, b, t0) = ev[1], busy.pop(ev[1])
            missing = [n for n in range(a, b + 1) if not frame_path(frames, n).exists()]
            if missing:
                raise StageError(f"chunk {i} finished but frames are missing: {missing[:5]}")
            atomic_write_json(chunk_json(frames, i), {"first": a, "last": b, "count": b - a + 1,
                                                      "renderer": w.info, "inputs_hash": digest})
            done += 1
            rendered += b - a + 1
            idle.append(w)
            print(f"chunk {done}/{len(ranges)} done (frames {a}-{b}, {(b - a + 1) / max(time.monotonic() - t0, 1e-3):.1f} fps)")
        for w in pool:
            w.close()
        for w in pool:
            w.wait()
        if rendered:
            secs = max(time.monotonic() - t_start, 1e-3)
            print(f"rendered {rendered} frames in {secs:.1f} s ({rendered / secs:.1f} fps overall, {len(pool)} worker(s))")
    finally:
        for w in pool:  # finished, failed or Ctrl+C: no worker (or its browser) outlives the render
            w.kill()


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

def run(part_dir: Path, workers: int | None = None, swiftshader: bool = False, force: bool = False) -> None:
    """workers None: library/settings.json (auto: recommended for this PC); swiftshader also when settings force it"""
    story = check_gate(part_dir, ("stills",))  # the test render is optional
    library = part_dir.parents[1]
    workers = workers or settings.render_workers(library)
    swiftshader = swiftshader or settings.software_gl(library)
    print(f"render: {workers} worker{'s' * (workers > 1)}{' (software GL)' * swiftshader}")
    with render_lock(part_dir):
        render_chunks(part_dir, story.duration_frames, workers, swiftshader, force)
        check_frames(part_dir / "frames", 0, story.duration_frames)
        out = encode(part_dir / "frames", 0, story.duration_frames, part_dir / "voice-tight.wav", part_dir / "preview.mp4")
    print(f"preview: {out}")


def test_render(part_dir: Path, at: float = 0.0, swiftshader: bool = False) -> Path:
    """TEST_FRAMES frames from `at` seconds (clamped to the part) -> part-NN/test-render.mp4 with its voice slice."""
    story = check_gate(part_dir, ("stills",))
    swiftshader = swiftshader or settings.software_gl(part_dir.parents[1])
    total = story.duration_frames
    count = min(TEST_FRAMES, total)
    first = max(0, min(round(at * FPS), total - count))
    test = part_dir / "frames" / "test"
    with render_lock(part_dir):
        shutil.rmtree(test, ignore_errors=True)
        test.mkdir(parents=True)
        t0 = time.monotonic()
        r = run_tree(node_cmd("--part", part_dir, "--frames", f"{first}-{first + count - 1}", "--out-dir", test,
                              "--info-out", test / "renderer.json", swiftshader=swiftshader))
        if r.returncode != 0:
            raise StageError(f"test render failed: {r.stderr.strip()[-400:]}")
        secs = max(time.monotonic() - t0, 1e-3)
        print(f"rendered frames {first}-{first + count - 1} in {secs:.1f} s ({count / secs:.1f} fps)")
        check_frames(test, first, count)
        return encode(test, first, count, voice_with_sfx(part_dir), part_dir / "test-render.mp4")


def voice_with_sfx(part_dir: Path) -> Path:
    """voice-tight.wav, or audio/voice-sfx.wav (the voice with its @sfx mixed in) when story.md has any"""
    from .. import sfx as sfx_lib  # numpy and ffmpeg only when there is a test render
    from .audio import decode, wav_bytes
    voice_f = part_dir / "voice-tight.wav"
    if not voice_f.exists():
        return voice_f  # encode reports it
    voice = decode(voice_f)
    x = sfx_lib.stem(part_dir, voice)
    if x is None:
        return voice_f
    out = part_dir / "audio" / "voice-sfx.wav"
    atomic_write_bytes(out, wav_bytes(voice + x))
    return out

