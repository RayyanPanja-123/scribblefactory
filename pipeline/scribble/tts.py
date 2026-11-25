"""The Kokoro TTS server (settings tts_url): POST /tts {text, voice, speed} -> a 24 kHz mono 16-bit WAV, the same bytes
for the same request. No voice list, no version, no timestamps (probe notes: .scribble/tts-probe/results.md).

Clips are cached in <library>/_tts-cache/<key>.wav, key = sha256 of text, voice, speed, server url and
settings tts_model_tag: a line made once is never fetched again, and a cached script needs no server at all."""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import settings
from .stages.runner import StageError

CACHE_DIR = "_tts-cache"
PARALLEL = 3              # the server answers 3 calls in ~6 s that take ~13 s one after another
RETRIES = 3               # tries per clip on a timeout, a dropped connection or a 5xx
BACKOFF_S = 1.0           # doubled after each failed try
TIMEOUT_S = 60            # per call, plus a second per 20 characters (a 400-char line takes ~8 s)
SAMPLE_RATE = 24000       # what the server sends; every clip is checked against it


def config(library) -> dict:
    s = settings.load(Path(library))
    url = str(s["tts_url"] or "").strip().rstrip("/")
    if not url:
        raise StageError("no TTS server set: scribble tts-settings --url http://<host>:<port>")
    return {"url": url, "voices": list(s["tts_voices"]), "default": s["tts_voice"], "gap": float(s["tts_line_gap"]),
            "tag": str(s["tts_model_tag"])}


def clip_key(text: str, voice: str, speed: float, cfg: dict) -> str:
    return hashlib.sha256(json.dumps([text, voice, round(speed, 3), cfg["url"], cfg["tag"]]).encode()).hexdigest()


def cache_dir(library) -> Path:
    return Path(library) / CACHE_DIR


def fetch(url: str, text: str, voice: str, speed: float) -> bytes:
    """one clip's WAV bytes. StageError on a refused request (400 / 422: no retry) or once the retries are spent."""
    body = json.dumps({"text": text, "voice": voice, "speed": speed}).encode()
    wait, last = BACKOFF_S, None
    for _ in range(RETRIES):
        req = urllib.request.Request(f"{url}/tts", body, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S + len(text) / 20) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500:
                detail = e.read().decode(errors="replace")[:200]
                raise StageError(f"TTS server refused voice {voice!r} for {text[:60]!r}: {e.code} {detail}") from None
            last = f"{e.code} {e.reason}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = str(getattr(e, "reason", e))
        time.sleep(wait)
        wait *= 2
    raise StageError(f"TTS server {url} not answering after {RETRIES} tries: {last}")


def check_wav(data: bytes, what: str) -> None:
    import io
    try:
        with wave.open(io.BytesIO(data)) as w:
            ok = (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (SAMPLE_RATE, 1, 2)
    except (wave.Error, EOFError) as e:
        raise StageError(f"TTS server sent no WAV for {what}: {e}") from None
    if not ok:
        raise StageError(f"TTS clip for {what} is not {SAMPLE_RATE} Hz mono 16-bit")


def clips(library, lines: list[tuple[str, str, float]], cfg: dict) -> list[Path]:
    """the cached clip of each (text, voice, speed), fetching the missing ones (PARALLEL at a time). Each clip is
    written whole (tmp + replace) as it arrives, so a failure keeps the finished ones and leaves no partial file."""
    for _, voice, _ in lines:
        if voice not in cfg["voices"]:
            raise StageError(f"unknown TTS voice {voice!r} (known: {', '.join(cfg['voices'])}; "
                             "find more with scribble tts-voices --probe)")
    d = cache_dir(library)
    paths = [d / f"{clip_key(t, v, s, cfg)}.wav" for t, v, s in lines]
    todo = {p: line for p, line in zip(paths, lines) if not p.is_file()}
    if todo:
        d.mkdir(parents=True, exist_ok=True)
        print(f"tts: {len(lines) - len(todo)} of {len(lines)} lines cached, fetching {len(todo)} from {cfg['url']}")
        with ThreadPoolExecutor(PARALLEL) as ex:
            jobs = {ex.submit(fetch, cfg["url"], *line): p for p, line in todo.items()}
            try:
                for n, job in enumerate(as_completed(jobs), 1):
                    data, p = job.result(), jobs[job]
                    check_wav(data, repr(todo[p][0][:60]))
                    tmp = p.with_suffix(".tmp")
                    tmp.write_bytes(data)
                    os.replace(tmp, p)
                    print(f"line {n}/{len(todo)}", flush=True)
            except BaseException:
                for j in jobs:
                    j.cancel()
                raise
    else:
        print(f"tts: all {len(lines)} lines cached")
    return paths


def stitch(paths: list[Path], gap: float) -> tuple[bytes, list[tuple[float, float]]]:
    """the clips one after another with gap seconds of silence between them: (WAV bytes, [(start, end) per clip]).
    Clips never overlap: each starts after the previous one's end plus the gap."""
    import io
    frames, spans, at = [], [], 0
    silence = b"\0\0" * round(gap * SAMPLE_RATE)
    for i, p in enumerate(paths):
        with wave.open(str(p)) as w:
            pcm = w.readframes(w.getnframes())
        if i:
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


def probe_voices(url: str, candidates: list[str]) -> list[str]:
    """the candidate ids the server takes (a 1-word line each; it has no voice list)"""
    ok = []
    for v in candidates:
        try:
            fetch(url, "Hi.", v, 1.0)
            ok.append(v)
        except StageError as e:
            if "refused" not in str(e):
                raise
    return ok


# the voice ids of Kokoro v1.0 (54) and v0.19: what probe_voices tries
KOKORO_VOICES = (
    "af_alloy af_aoede af_bella af_heart af_jessica af_kore af_nicole af_nova af_river af_sarah af_sky am_adam am_echo "
    "am_eric am_fenrir am_liam am_michael am_onyx am_puck am_santa bf_alice bf_emma bf_isabella bf_lily bm_daniel "
    "bm_fable bm_george bm_lewis ef_dora em_alex em_santa ff_siwis hf_alpha hf_beta hm_omega hm_psi if_sara im_nicola "
    "jf_alpha jf_gongitsune jf_nezumi jf_tebukuro jm_kumo pf_dora pm_alex pm_santa zf_xiaobei zf_xiaoni zf_xiaoxiao "
    "zf_xiaoyi zm_yunjian zm_yunxi zm_yunxia zm_yunyang af").split()
