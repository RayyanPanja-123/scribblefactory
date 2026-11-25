"""The tts stage against a stand-in Kokoro server (stdlib http.server, the /v1 job API): cache, a model change, retries,
refusals, a server that is down, the recorded voice kept, and the TTS fields leaving every older hash alone."""

import hashlib
import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from pipeline.scribble import db, settings, tts
from pipeline.scribble.io import load_part, load_series, save_part, save_series, series_bytes
from pipeline.scribble.schemas import TtsVoice
from pipeline.scribble.stages import tts as tts_stage
from pipeline.scribble.stages.runner import StageError
from pipeline.tests.helpers import new_part

STORY = "# The ocean war\nThe emperor marched to the sea.\n@cam wide\n!! And the ocean did not notice.\n"
SCRIPT = "The emperor marched to the sea.\n\nAnd the ocean did not notice.\n"


def clip(text: str) -> bytes:
    """a deterministic 24 kHz mono clip per text, ~50 ms per character"""
    seed = hashlib.sha256(text.encode()).digest()
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(bytes(seed[i % 32] & 0x3F for i in range(len(text) * 2400)))
    return out.getvalue()


class Kokoro(BaseHTTPRequestHandler):
    """/health, /v1/voices, /v1/jobs: a job shows "running" on its first poll, then "done"; am_puck is listed but
    every job with it is refused"""
    made: list = []      # every item synthesized
    jobs: dict = {}
    fail_posts = 0       # answer this many job submissions with 500 first
    model = "aaaa"

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"status": "ok", "model_sha256": Kokoro.model, "voices_sha256": "vvvv"})
        if self.path == "/v1/voices":
            return self._json(200, [{"id": v} for v in ("am_adam", "am_michael", "am_puck")])
        parts = self.path.split("/")  # /v1/jobs/<id>[/items/<item>/audio]
        job = Kokoro.jobs[parts[3]]
        if len(parts) == 7:
            return self._send(200, job["audio"][parts[5]], "audio/wav")
        job["polls"] += 1
        done = job["polls"] > 1
        self._json(200, {"job_id": parts[3], "status": "done" if done else "running",
                         "progress": {"done": len(job["items"]) if done else 0, "total": len(job["items"])},
                         "items": [{"id": i["id"], "status": "done" if done else "running",
                                    "sha256": hashlib.sha256(job["audio"][i["id"]]).hexdigest() if done else None,
                                    "error": None} for i in job["items"]]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if Kokoro.fail_posts:
            Kokoro.fail_posts -= 1
            return self._json(500, {"detail": "busy"})
        bad = [i["id"] for i in body["items"] if i["voice"] not in ("am_adam", "am_michael")]
        if bad:
            return self._json(400, {"error": {"code": "unknown_voice", "message": "Unsupported voice",
                                              "items": [{"item_id": b, "errors": ["no"]} for b in bad]}})
        jid = hashlib.sha256(body["idempotency_key"].encode()).hexdigest()[:12]
        if jid not in Kokoro.jobs:
            Kokoro.made += body["items"]
            Kokoro.jobs[jid] = {"items": body["items"], "polls": 0,
                                "audio": {i["id"]: clip(i["text"] + Kokoro.model) for i in body["items"]}}
        self._json(202, {"job_id": jid, "status": "queued"})

    def _json(self, code, d):
        self._send(code, json.dumps(d).encode(), "application/json")

    def _send(self, code, data, kind):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def server(monkeypatch):
    Kokoro.made, Kokoro.jobs, Kokoro.fail_posts, Kokoro.model = [], {}, 0, "aaaa"
    monkeypatch.setattr(tts, "BACKOFF_S", 0)
    monkeypatch.setattr(tts, "POLL_S", 0)
    s = ThreadingHTTPServer(("127.0.0.1", 0), Kokoro)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}", s
    s.shutdown()
    s.server_close()


@pytest.fixture
def part(tmp_path):
    p = new_part(tmp_path)
    (p / "story.md").write_text(STORY, encoding="utf-8")
    (p / "script-for-tts.txt").write_text(SCRIPT, encoding="utf-8")
    m = load_part(p / "part.json")
    m.voice_source = "tts"
    save_part(p / "part.json", m)
    return p


def lib(p):
    return p.parents[3]


def use(p, url):
    db.put_settings(lib(p), {"tts_url": url})


def test_recorded_part_is_left_alone(tmp_path):
    p = new_part(tmp_path)
    tts_stage.run(p)
    assert not (p / "voice.mp3").exists() and not (p / tts_stage.MANIFEST).exists()
    assert "voice_source" not in json.dumps(load_part(p / "part.json").model_dump(mode="json"))
    assert "tts" not in load_part(p / "part.json").model_dump(mode="json")["stages"]


def test_one_job_then_all_cached_without_the_server(part, server):
    url, srv = server
    use(part, url)
    tts_stage.run(part)
    assert sorted(i["text"] for i in Kokoro.made) == ["And the ocean did not notice.", "The emperor marched to the sea."]
    assert len(Kokoro.jobs) == 1
    s = settings.load(lib(part))
    assert s["tts_voices"] == ["am_adam", "am_michael", "am_puck"] and s["tts_server_fp"] == "aaaa:vvvv"
    first = (part / "voice.mp3").read_bytes()
    m = json.loads((part / tts_stage.MANIFEST).read_text(encoding="utf-8"))
    assert [ln["line"] for ln in m["lines"]] == [2, 4] and {ln["voice"] for ln in m["lines"]} == {"am_michael"}
    a, b = m["lines"]
    assert a["end"] + 0.3 == pytest.approx(b["start"], abs=0.002)  # the gap; never overlapping
    from pipeline.scribble import ff
    assert ff.duration(part / "voice.mp3") == pytest.approx(b["end"], abs=0.1)  # plays, as import_check needs
    srv.shutdown()  # cached: no server needed (the last fingerprint is kept), and the same mp3 bytes again
    tts_stage.run(part)
    assert (part / "voice.mp3").read_bytes() == first


def test_a_new_model_makes_the_clips_again(part, server):
    url, _ = server
    use(part, url)
    before = tts_stage.extra_inputs(part)
    tts_stage.run(part)
    first = (part / "voice.mp3").read_bytes()
    assert tts_stage.extra_inputs(part) != before  # the fingerprint seen: part of the stage's hash
    Kokoro.model = "bbbb"
    tts_stage.run(part)
    assert len(Kokoro.made) == 4 and (part / "voice.mp3").read_bytes() != first


def test_series_voice_and_speed_reach_the_server(part, server):
    url, _ = server
    use(part, url)
    f = part.parent / "series.json"
    s = load_series(f)
    s.voice.tts = TtsVoice(id="am_adam", speed=1.2)
    save_series(f, s)
    tts_stage.run(part)
    assert {(i["voice"], i["speed"]) for i in Kokoro.made} == {("am_adam", 1.2)}


def test_server_down_writes_nothing(part, server):
    url, srv = server
    srv.shutdown()
    srv.server_close()
    use(part, url)
    (part / "voice.mp3").write_bytes(b"ID3 a recording")
    with pytest.raises(StageError, match="not answering"):
        tts_stage.run(part)
    assert (part / "voice.mp3").read_bytes() == b"ID3 a recording"
    assert not (part / tts_stage.RECORDED).exists() and not (part / tts_stage.MANIFEST).exists()


def test_a_recording_is_kept_never_overwritten(part, server):
    url, _ = server
    use(part, url)
    (part / "voice.mp3").write_bytes(b"ID3 a recording")
    tts_stage.run(part)
    assert (part / tts_stage.RECORDED).read_bytes() == b"ID3 a recording"
    assert (part / "voice.mp3").read_bytes() != b"ID3 a recording"
    tts_stage.run(part)  # its own voice.mp3 now: replaced, nothing else moved
    (part / "voice.mp3").write_bytes(b"ID3 another recording")
    with pytest.raises(StageError, match="already exists"):
        tts_stage.run(part)


def test_retries_a_busy_server_and_refuses_unknown_voices(part, server):
    url, _ = server
    use(part, url)
    Kokoro.fail_posts = 2
    tts_stage.run(part)
    assert len(Kokoro.made) == 2  # submitted on the third try
    cfg = tts.config(lib(part))
    with pytest.raises(StageError, match="unknown TTS voice 'af_heart'"):
        tts.clips(lib(part), [("Hi.", "af_heart", 1.0)], cfg)
    with pytest.raises(StageError, match=r"refused POST .*Unsupported voice"):  # listed, but the server says no
        tts.clips(lib(part), [("Hi.", "am_puck", 1.0)], cfg)


def test_no_server_set_is_a_clear_error(part):
    with pytest.raises(StageError, match="no TTS server set"):
        tts_stage.run(part)


def test_tts_fields_leave_series_hashes_alone(part):
    f = part.parent / "series.json"
    before = series_bytes(part.parent)
    s = load_series(f)
    s.voice.tts = TtsVoice(id="am_adam")
    save_series(f, s)
    assert series_bytes(part.parent) == before
    assert load_series(f).voice.tts.id == "am_adam"  # stored all the same
    s.voice.tts = None
    assert "tts" not in s.model_dump(mode="json")["voice"]
