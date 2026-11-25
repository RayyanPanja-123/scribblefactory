"""The job queue: one in-process worker running CLI subprocesses. Jobs persist to the job table (db.py), so a
restart resumes the queue (main.startup). busy() / check_no_jobs(): what a running job blocks.

Each step runs apart from the API (api/jobstep.py, its own process group) and writes its output to
<library>/_jobs/<job>-<step>.log, its exit code to <log>.rc. The worker follows the log, so a restarting API (dev
reload) leaves a running step alone: the new API re-attaches to it (load_jobs) and the job carries on."""

import itertools
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from datetime import date, datetime

from fastapi import HTTPException, APIRouter
from pydantic import BaseModel

from api.core import JOB_COMMANDS, KEEP_JOBS, OUTPUT_LINES, ROOT, lib, part_path, series_path
from api.events import publish
from api.models import Job
from sqlalchemy.exc import SQLAlchemyError

from pipeline.scribble import cli, db
from pipeline.scribble.io import load_part, load_series, part_dir_of, storage_root, sync_files
from pipeline.scribble.schemas import utcnow
from pipeline.scribble.stages import render as render_stage
from pipeline.scribble.stages.runner import recover_stuck

router = APIRouter()


def busy(slug: str, part: str | None = None) -> str | None:
    """why this part (or, part None, any part of the series) can't be touched now, else None"""
    for j in list(JOBS):
        if j["status"] == "running" and j["slug"] == slug and part in (None, j["part"]):
            return f"job {j.get('tag', j['id'])} is running on {slug} {j['part']}"
    if part:
        pid = render_stage.lock_owner(part_dir_of(storage_root(lib()) / slug, part))
        if pid:
            return f"a render is running on {slug} {part} (pid {pid})"
    return None


def check_free(slug: str, part: str | None = None) -> None:
    if why := busy(slug, part):
        raise HTTPException(409, f"{why}; wait for it or cancel it")


def check_no_jobs() -> None:
    """props.json feeds every render: no changes while one runs (its chunks would mix two drawings)"""
    if run := next((j for j in list(JOBS) if j["status"] == "running"), None):
        raise HTTPException(409, f"job {run.get('tag', run['id'])} is running on {run['slug']} {run['part']}; wait for it or cancel it")


# One in-process worker. Jobs persist to the job table (one transaction) on every state change, so a restart resumes the
# queue (see startup). Output lines are saved with them, not streamed to disk line by line.

JOBS: list[dict] = []
_procs: dict[int, subprocess.Popen] = {}
_cv = threading.Condition()
_ids = itertools.count(1)
_worker: threading.Thread | None = None


def series_code(title: str, fallback: str = "series") -> str:
    """A readable uppercase code from a series title, e.g. TRWDWOTO."""
    words = re.findall(r"[A-Za-z]+", title)
    code = "".join(word[0] for word in words).upper()
    if not code:
        code = "".join(re.findall(r"[A-Za-z]", fallback)).upper()
    return code or "SERIES"


def job_tag(slug: str, part: str) -> str:
    """Stable human-facing tag: series initials + three-digit part number."""
    d = series_path(slug)
    title = load_series(d / "series.json").title
    number = load_part(part_dir_of(d, part) / "part.json").number
    return f"{series_code(title, slug)}{number:03d}"


class JobRequest(BaseModel):
    slug: str
    part: str
    steps: list[str]  # CLI commands without slug/part, e.g. "run --stage audio", "render-stills", "render --force"


def step_argv(slug: str, part: str, step: str) -> list[str]:
    """CLI subprocess for one step. Raises ValueError for anything but the job commands."""
    words = shlex.split(step)
    if not words or words[0] not in JOB_COMMANDS:
        raise ValueError(f"step {step!r}: must start with one of {', '.join(sorted(JOB_COMMANDS))}")
    argv = [words[0], slug] + ([part] if words[0] != "cast-sheet" else []) + words[1:]
    try:
        cli.build_parser().parse_args(argv)  # validate stage names and flags now, not halfway through the job
    except SystemExit:
        raise ValueError(f"step {step!r}: invalid arguments")
    return [sys.executable, "-m", "pipeline.scribble.cli", *argv, f"--library={lib().resolve()}"]


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def public(job: dict) -> dict:
    return {**{k: v for k, v in job.items() if k not in ("argv", "pid")}, "output": list(job["output"])}


_save_lock = threading.Lock()


def save_jobs() -> None:
    with _save_lock:
        db.save_jobs(lib(), [{**public(j), "argv": j["argv"], "pid": j.get("pid")} for j in list(JOBS)])


def step_log(job: dict, step: int) -> Path:
    return lib() / "_jobs" / f"{job['id']}-{step}.log"


def _alive(pid: int | None) -> bool:
    return bool(pid) and render_stage.pid_alive(pid) and bool(
        render_stage.RUNNER_PROCESS.match(render_stage.process_name(pid) or ""))


def load_jobs() -> list[str]:
    """the job table -> JOBS. A job left running by the last API process is picked up again when its step still runs
    (or ended meanwhile: its exit code is in the log's .rc): the worker follows the step's log and carries on with the
    rest. One whose step is gone without an exit code failed ("interrupted by restart"). Queued jobs stay queued and the
    worker picks them up. Returns notes."""
    global _ids
    notes = []
    try:
        saved = db.load_jobs(lib())
    except (OSError, SQLAlchemyError) as e:
        return [f"could not read the jobs: {e}"]
    for j in saved:
        # Jobs written before tags were introduced are still valid history. Derive their tag once
        # from the current series title and keep it in the persisted record from then on.
        if not j.get("tag"):
            try:
                j["tag"] = job_tag(j["slug"], j["part"])
            except (HTTPException, OSError, ValueError, KeyError):
                # A finished job can outlive a deleted series; preserve that history with a
                # deterministic slug-based fallback rather than failing API startup.
                number = int(j["part"].removeprefix("part-"))
                j["tag"] = f"{series_code(j['slug'])}{number:03d}"
        j["output"] = deque(j.get("output", []), maxlen=OUTPUT_LINES)
        if j["status"] == "running":
            step = j.get("current_step") or 0
            log = step_log(j, step)
            if log.is_file() and (_alive(j.get("pid")) or Path(f"{log}.rc").is_file()):
                j["adopt"] = True  # the worker follows its log again (before any queued job)
                notes.append(f"job {j['id']} ({j['slug']} {j['part']}): step {step + 1} still running, picked up again")
                continue
            j.update(status="failed", error="interrupted by restart", finished_at=_iso(utcnow()), pid=None)
            notes.append(f"job {j['id']} ({j['slug']} {j['part']}) was running: marked failed (interrupted by restart)")
    with _cv:
        JOBS[:] = saved
        _ids = itertools.count(max((j["id"] for j in saved), default=0) + 1)
        if any(j["status"] == "queued" or j.get("adopt") for j in saved):
            if n := sum(j["status"] == "queued" for j in saved):
                notes.append(f"resuming {n} queued job(s)")
            _start_worker()
            _cv.notify()
    if saved:
        save_jobs()
    return notes


@router.post("/api/jobs", response_model=Job)
def submit_job(body: JobRequest):
    part_path(body.slug, body.part)
    if not body.steps:
        raise HTTPException(409, "steps is empty")
    try:
        argv = [step_argv(body.slug, body.part, s) for s in body.steps]
    except ValueError as e:
        raise HTTPException(409, str(e))
    job = {"id": next(_ids), "tag": job_tag(body.slug, body.part), "slug": body.slug, "part": body.part,
           "steps": body.steps, "argv": argv,
           "current_step": None, "status": "queued", "queued_at": _iso(utcnow()), "started_at": None,
           "finished_at": None, "returncode": None, "output": deque(maxlen=OUTPUT_LINES), "error": None, "pid": None}
    with _cv:
        JOBS.append(job)
        _start_worker()
        _cv.notify()
    save_jobs()
    publish("job-queued", public(job))
    return public(job)


@router.get("/api/jobs", response_model=list[Job])
def list_jobs():
    return [public(j) for j in list(JOBS)]


class JobCleanup(BaseModel):
    before: date | None = None  # delete finished jobs that finished before this day (UTC); None: every finished job


@router.post("/api/jobs/cleanup", response_model=list[Job])
def cleanup_jobs(body: JobCleanup):
    """delete job history; queued and running jobs are never touched. Returns the jobs that are left."""
    cut = body.before.isoformat() if body.before else None
    with _cv:
        gone = [j for j in JOBS if j["status"] not in ("queued", "running")
                and (cut is None or (j["finished_at"] or j["queued_at"])[:10] < cut)]
        for j in gone:
            JOBS.remove(j)
    save_jobs()
    publish("jobs-cleaned", {"removed": len(gone)})
    return list_jobs()


@router.delete("/api/jobs/{job_id}", response_model=Job)
def cancel_job(job_id: int):
    with _cv:
        job = next((j for j in JOBS if j["id"] == job_id), None)
        if job is None:
            raise HTTPException(404, f"job {job_id} not found")
        if job["status"] not in ("queued", "running"):
            raise HTTPException(409, f"job {job_id} already {job['status']}")
        was_queued = job["status"] == "queued"
        job["status"] = "cancelled"
        proc = _procs.get(job_id)
    if proc:
        render_stage.kill_tree(proc)  # the worker sees the exit and finishes the job as cancelled
    elif not was_queued and job.get("pid"):
        render_stage.kill_pid_tree(job["pid"])  # a step picked up after a restart: no Popen, its process tree
    elif was_queued:
        job["finished_at"] = _iso(utcnow())
        publish("job-finished", _brief(job))
    save_jobs()
    return public(job)


def _brief(job: dict) -> dict:
    return {k: job[k] for k in ("id", "slug", "part", "status", "current_step", "returncode", "finished_at")}


def _start_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_work, name="jobs", daemon=True)
        _worker.start()


def _work() -> None:
    while True:
        with _cv:
            while not (job := next((j for j in JOBS if j.get("adopt")), None)
                       or next((j for j in JOBS if j["status"] == "queued"), None)):
                _cv.wait()
            adopt = job.pop("adopt", False)
            if not adopt:
                job["status"], job["started_at"] = "running", _iso(utcnow())
        save_jobs()
        publish("job-started", _brief(job))
        _run(job, adopt)
        try:  # the files the job made or changed: their stored_file rows
            sync_files(storage_root(lib()) / job["slug"])
        except Exception as e:  # never fails the job
            job["output"].append(f"note: stored files not synced: {e}")
        job["finished_at"], job["pid"] = _iso(utcnow()), None
        publish("job-finished", _brief(job))
        with _cv:  # keep the last KEEP_JOBS finished jobs
            done = [j for j in JOBS if j["status"] not in ("queued", "running")]
            for j in done[:-KEEP_JOBS]:
                JOBS.remove(j)
        save_jobs()


POLL_S = 0.25  # how often the worker reads a step's log


def _follow(job: dict, i: int, log: Path, running, pos: int = 0) -> int:
    """publish the step's log lines as they come until the step ends; its exit code (-1: killed, no .rc written)"""
    rc, buf = Path(f"{log}.rc"), b""
    while True:
        ended = rc.is_file() or not running()  # read once more after it ends: its last lines
        with open(log, "rb") as f:
            f.seek(pos)
            data = f.read()
        pos += len(data)
        *lines, buf = (buf + data).split(b"\n")
        if ended and buf:
            lines, buf = [*lines, buf], b""
        for raw in lines:
            line = raw.decode("utf-8", "replace").rstrip("\r")
            job["output"].append(line)
            publish("job-output", {"id": job["id"], "step": i, "line": line})
        if ended:
            return int(rc.read_text().strip() or -1) if rc.is_file() else -1
        time.sleep(POLL_S)


def _run(job: dict, adopt: bool = False) -> None:
    """the job's steps in order. adopt: picked up after an API restart, its current step already running (or ended):
    follow that step's log from where it is now, then carry on with the rest"""
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    first = (job["current_step"] or 0) if adopt else 0
    try:
        for i, argv in enumerate(job["argv"][first:], first):
            job["current_step"] = i
            log = step_log(job, i)
            publish("job-step", {"id": job["id"], "step": i, "command": job["steps"][i]})
            if adopt and i == first:  # not our child: follow it by pid. Its lines from while the API was away are in
                pid = job["pid"]       # the log; the saved output has them up to the restart only
                job["output"].append("(the API restarted: picked this step up again)")
                rc = _follow(job, i, log, lambda: _alive(pid), pos=log.stat().st_size)
            else:
                with _cv:
                    if job["status"] == "cancelled":
                        return
                    log.parent.mkdir(exist_ok=True)
                    for f in (log, Path(f"{log}.rc")):
                        f.unlink(missing_ok=True)
                    proc = subprocess.Popen([sys.executable, "-m", "api.jobstep", str(log), *argv], cwd=ROOT, env=env,
                                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, **render_stage.GROUP)
                    _procs[job["id"]] = proc
                    job["pid"] = proc.pid
                save_jobs()
                while not log.exists() and proc.poll() is None:  # the wrapper creates it first thing
                    time.sleep(0.05)
                log.touch()
                rc = _follow(job, i, log, lambda: proc.poll() is None)
                proc.wait()
            with _cv:
                _procs.pop(job["id"], None)
            job["returncode"] = rc
            _finish_step(job)
            if job["status"] == "cancelled":
                return
            if rc != 0:
                job["status"] = "failed"
                return
        job["status"] = "done"
    finally:
        if job["status"] != "running":  # the output is saved with the job: its logs can go
            for f in (lib() / "_jobs").glob(f"{job['id']}-*"):
                f.unlink(missing_ok=True)


def _finish_step(job: dict) -> None:
    """after a step: a cancelled one never got to mark its stage or drop its lock; the pages refresh"""
    if job["status"] == "cancelled" and job["part"]:
        d = part_dir_of(storage_root(lib()) / job["slug"], job["part"])
        notes = render_stage.clear_stale_lock(d) + [f"{n}: cancelled, marked failed" for n in recover_stuck(d)]
        job["output"] += notes
    publish("part-changed", {"slug": job["slug"], "part": job["part"]})
    publish("series-changed", {"slug": job["slug"]})
