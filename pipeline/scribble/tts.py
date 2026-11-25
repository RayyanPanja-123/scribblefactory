"""The Kokoro TTS server (settings tts_url), its job API (server guide: <tts_url>/guide-for-ai-agents):
POST /v1/jobs {items: [{id, text, voice, speed}], idempotency_key} -> job_id; GET /v1/jobs/<id> to poll; each done
item's WAV (24 kHz mono 16-bit, the same bytes for the same request) from GET /v1/jobs/<id>/items/<item>/audio.
GET /v1/voices lists the voices (the old POST /tts takes only 4 of them), GET /health the model and voices hashes.

Clips are cached in <library>/_tts-cache/<key>.wav, key = sha256 of text, voice, speed, the server's model and voices
hashes (from /health, remembered in settings tts_server_fp) and settings tts_model_tag: a line made once is never
fetched again, a new model makes every line again by itself, and a fully cached script needs no server at all."""

import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from . import db, settings
from .stages.runner import StageError

CACHE_DIR = "_tts-cache"
RETRIES = 3               # tries per request on a timeout, a dropped connection or a 5xx
BACKOFF_S = 1.0           # doubled after each failed try
TIMEOUT_S = 30            # per request
POLL_S = 1.0              # between job status polls
STALL_S = 180             # a job whose progress has not moved for this long has failed
MAX_ITEMS = 500           # per job (the server's limit)
SAMPLE_RATE = 24000       # what the server sends; every clip is checked against it


def config(library) -> dict:
    s = settings.load(Path(library))
    url = str(s["tts_url"] or "").strip().rstrip("/")
    if not url:
        raise StageError("no TTS server set: scribble tts-settings --url http://<host>:<port>")
    return {"url": url, "voices": list(s["tts_voices"]), "default": s["tts_voice"], "gap": float(s["tts_line_gap"]),
            "tag": str(s["tts_model_tag"]), "fp": str(s["tts_server_fp"])}


def clip_key(text: str, voice: str, speed: float, cfg: dict) -> str:
    return hashlib.sha256(json.dumps([text, voice, round(speed, 3), cfg["fp"], cfg["tag"]]).encode()).hexdigest()


def cache_dir(library) -> Path:
    return Path(library) / CACHE_DIR


def call(url: str, method: str = "GET", body=None, tries: int = RETRIES) -> bytes:
    """one request's body, retried on a timeout, a dropped connection or a 5xx. StageError on a refusal (4xx: no
    retry) or once the tries are spent."""
    data = json.dumps(body).encode() if body is not None else None
    wait, last = BACKOFF_S, None
    for n in range(tries):
        req = urllib.request.Request(url, data, {"Content-Type": "application/json"} if data else {}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise StageError(f"TTS server refused {method} {url}: {e.code} {refusal(e.read())}") from None
            last = f"{e.code} {e.reason}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = str(getattr(e, "reason", e))
        if n + 1 < tries:
            time.sleep(wait)
            wait *= 2
    raise StageError(f"TTS server {url.split('/v1/')[0].split('/health')[0]} not answering after {tries} tries: {last}")


def refusal(body: bytes) -> str:
    """the server's error, readable: {"error": {"message", "items": [{"item_id", "errors"}]}} or {"detail"}"""
    try:
        d = json.loads(body)
    except ValueError:
        return body.decode(errors="replace")[:200]
    e = d.get("error") if isinstance(d, dict) else None
    if isinstance(e, dict):
        items = "; ".join(f"{i.get('item_id')}: {', '.join(i.get('errors') or [])}" for i in e.get("items") or [])
        return f"{e.get('message')}" + (f" ({items})" if items else "")
    return str(d.get("detail", d) if isinstance(d, dict) else d)[:300]


def server_state(library, cfg: dict) -> bool:
    """ask /health and /v1/voices (one quick try each): the model fingerprint and the voice list go into settings and
    cfg. False when the server does not answer (cached clips still work: cfg keeps the last fingerprint)."""
    try:
        h = json.loads(call(f"{cfg['url']}/health", tries=1))
        voices = [v["id"] for v in json.loads(call(f"{cfg['url']}/v1/voices", tries=1))]
    except StageError:
        return False
    fp = f"{h.get('model_sha256', '')}:{h.get('voices_sha256', '')}"
    if (fp, voices) != (cfg["fp"], cfg["voices"]):
        db.put_settings(Path(library), {"tts_server_fp": fp, "tts_voices": voices})
        cfg["fp"], cfg["voices"] = fp, voices
    return True


def check_wav(data: bytes, what: str) -> None:
    try:
        with wave.open(io.BytesIO(data)) as w:
            ok = (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (SAMPLE_RATE, 1, 2)
    except (wave.Error, EOFError) as e:
        raise StageError(f"TTS server sent no WAV for {what}: {e}") from None
    if not ok:
        raise StageError(f"TTS clip for {what} is not {SAMPLE_RATE} Hz mono 16-bit")


def save(p: Path, data: bytes) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)  # whole or not at all


def run_job(cfg: dict, todo: dict[str, tuple[str, str, float]], d: Path, done_before: int, total: int) -> int:
    """one job for these {key: (text, voice, speed)}: submit, poll, save each clip as it is done. The idempotency key
    is the job's content, so a re-run after a crash picks the same job up again. Returns the clips saved."""
    items = [{"id": k[:32], "text": t, "voice": v, "speed": s} for k, (t, v, s) in todo.items()]
    by_id = {k[:32]: k for k in todo}
    idem = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()[:40]
    job = json.loads(call(f"{cfg['url']}/v1/jobs", "POST", {"items": items, "idempotency_key": idem}))
    status_url = f"{cfg['url']}/v1/jobs/{job['job_id']}"
    saved, moved_at = set(), time.monotonic()
    while True:
        st = json.loads(call(status_url))
        for it in st["items"]:
            if it["status"] == "done" and it["id"] not in saved:
                data = call(f"{status_url}/items/{it['id']}/audio")
                text = todo[by_id[it["id"]]][0]
                if it.get("sha256") and hashlib.sha256(data).hexdigest() != it["sha256"]:
                    raise StageError(f"TTS clip for {text[:60]!r} arrived damaged (sha256 differs)")
                check_wav(data, repr(text[:60]))
                save(d / f"{by_id[it['id']]}.wav", data)
                saved.add(it["id"])
                moved_at = time.monotonic()
                print(f"line {done_before + len(saved)}/{total}", flush=True)
        failed = [it for it in st["items"] if it["status"] == "failed"]
        if failed:
            raise StageError("TTS server failed " + "; ".join(
                f"{todo[by_id[it['id']]][0][:60]!r}: {it.get('error')}" for it in failed[:3]))
        if st["status"] == "cancelled":
            raise StageError(f"TTS job {job['job_id']} was cancelled on the server")
        if len(saved) == len(items):
            return len(saved)
        if time.monotonic() - moved_at > STALL_S:
            raise StageError(f"TTS job {job['job_id']} made no progress for {STALL_S} s "
                             f"({st['progress']['done']}/{st['progress']['total']} done)")
        time.sleep(POLL_S)


def clips(library, lines: list[tuple[str, str, float]], cfg: dict) -> list[Path]:
    """the cached clip of each (text, voice, speed), fetching the missing ones in jobs of MAX_ITEMS. Each clip is
    written whole as it arrives, so a failure keeps the finished ones and leaves no partial file."""
    online = server_state(library, cfg)
    for _, voice, _ in lines:
        if voice not in cfg["voices"]:
            raise StageError(f"unknown TTS voice {voice!r} (the server's voices: scribble tts-voices)")
    d = cache_dir(library)
    keys = [clip_key(t, v, s, cfg) for t, v, s in lines]
    todo = {k: line for k, line in zip(keys, lines) if not (d / f"{k}.wav").is_file()}  # repeated lines: once
    if not todo:
        print(f"tts: all {len(lines)} lines cached")
        return [d / f"{k}.wav" for k in keys]
    if not online:
        raise StageError(f"TTS server {cfg['url']} not answering, and {len(todo)} of {len(lines)} lines are not "
                         "cached yet")
    d.mkdir(parents=True, exist_ok=True)
    print(f"tts: {len(lines) - len(todo)} of {len(lines)} lines cached, fetching {len(todo)} from {cfg['url']}")
    batch, done = list(todo.items()), 0
    for i in range(0, len(batch), MAX_ITEMS):
        done += run_job(cfg, dict(batch[i:i + MAX_ITEMS]), d, done, len(todo))
    return [d / f"{k}.wav" for k in keys]


EDGE_LEVEL = 300         # |sample| below this at a clip's start or end is its silence...
EDGE_KEEP_S = 0.02       # ...trimmed to this much, so the gap between two lines is the gap asked for


def trim(pcm: bytes) -> bytes:
    """a clip without its leading and trailing silence (EDGE_KEEP_S of it left at each end)"""
    import array
    x = array.array("h", pcm)
    first = next((i for i, v in enumerate(x) if abs(v) > EDGE_LEVEL), None)
    if first is None:
        return pcm
    last = next(i for i in range(len(x) - 1, -1, -1) if abs(x[i]) > EDGE_LEVEL)
    keep = round(EDGE_KEEP_S * SAMPLE_RATE)
    return x[max(0, first - keep):min(len(x), last + 1 + keep)].tobytes()


def stitch(paths: list[Path], gaps: list[float]) -> tuple[bytes, list[tuple[float, float]]]:
    """the clips, their edge silence trimmed, one after another with gaps[i] seconds of silence before clip i (the
    first clip starts at 0): (WAV bytes, [(start, end) per clip]). Clips never overlap: each starts after the previous
    one's end plus its gap."""
    frames, spans, at = [], [], 0
    for i, p in enumerate(paths):
        with wave.open(str(p)) as w:
            pcm = trim(w.readframes(w.getnframes()))
        if i:
            silence = b"\0\0" * round(gaps[i] * SAMPLE_RATE)
            frames.append(silence)
            at += len(silence) // 2
        spans.append((round(at / SAMPLE_RATE, 3), round((at + len(pcm) // 2) / SAMPLE_RATE, 3)))
        frames.append(pcm)
        at += len(pcm) // 2
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"".join(frames))
    return out.getvalue(), spans
