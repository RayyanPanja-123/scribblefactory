"""The tts stage against a stand-in Kokoro server (stdlib http.server): cache, retries, refusals, a server that is
down, the recorded voice kept, and the TTS fields leaving every older hash alone."""

import hashlib
import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from pipeline.scribble import db, tts
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
    calls: list = []
    fail_next = 0  # answer this many calls with 500 first

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Kokoro.calls.append(body)
        if Kokoro.fail_next:
            Kokoro.fail_next -= 1
            return self._send(500, b'{"detail":"busy"}', "application/json")
        if body["voice"] not in ("am_adam", "am_michael"):
            return self._send(400, b'{"detail":"Unsupported voice"}', "application/json")
        self._send(200, clip(body["text"]), "audio/wav")

    def _send(self, code, data, kind):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    Kokoro.calls, Kokoro.fail_next = [], 0
    s = ThreadingHTTPServer(("127.0.0.1", 0), Kokoro)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}", s
    s.shutdown()
    s.server_close()


@pytest.fixture
def part(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "BACKOFF_S", 0)
    p = new_part(tmp_path)
    (p / "story.md").write_text(STORY, encoding="utf-8")
    (p / "script-for-tts.txt").write_text(SCRIPT, encoding="utf-8")
    m = load_part(p / "part.json")
    m.voice_source = "tts"
    save_part(p / "part.json", m)
    return p


def use(p, url, **more):
    db.put_settings(p.parents[3], {"tts_url": url, "tts_voices": ["am_adam", "am_michael"], **more})


def test_recorded_part_is_left_alone(tmp_path):
    p = new_part(tmp_path)
    tts_stage.run(p)
    assert not (p / "voice.mp3").exists() and not (p / tts_stage.MANIFEST).exists()
    assert "voice_source" not in json.dumps(load_part(p / "part.json").model_dump(mode="json"))
    assert "tts" not in load_part(p / "part.json").model_dump(mode="json")["stages"]


def test_one_clip_per_line_then_all_cached_without_the_server(part, server):
    url, srv = server
    use(part, url)
    tts_stage.run(part)
    assert [c["text"] for c in sorted(Kokoro.calls, key=lambda c: c["text"])] == \
        ["And the ocean did not notice.", "The emperor marched to the sea."]
    first = (part / "voice.mp3").read_bytes()
    m = json.loads((part / tts_stage.MANIFEST).read_text(encoding="utf-8"))
    assert [ln["line"] for ln in m["lines"]] == [2, 4] and {ln["voice"] for ln in m["lines"]} == {"am_michael"}
    a, b = m["lines"]
    assert a["end"] + 0.3 == pytest.approx(b["start"], abs=0.002)  # the gap; never overlapping
    from pipeline.scribble import ff
    assert ff.duration(part / "voice.mp3") == pytest.approx(b["end"], abs=0.1)  # plays, as import_check needs
    srv.shutdown()  # cached: no server needed, and the same mp3 bytes again
    tts_stage.run(part)
    assert (part / "voice.mp3").read_bytes() == first


def test_series_voice_and_speed_reach_the_server(part, server):
    url, _ = server
    use(part, url)
    f = part.parent / "series.json"
    s = load_series(f)
    s.voice.tts = TtsVoice(id="am_adam", speed=1.2)
    save_series(f, s)
    tts_stage.run(part)
    assert {(c["voice"], c["speed"]) for c in Kokoro.calls} == {("am_adam", 1.2)}


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
    Kokoro.fail_next = 2
    tts_stage.run(part)
    assert len(Kokoro.calls) == 4  # 2 lines, 2 busy answers retried
    with pytest.raises(StageError, match="unknown TTS voice 'af_heart'"):
        tts.clips(part.parents[3], [("Hi.", "af_heart", 1.0)], tts.config(part.parents[3]))
    use(part, url, tts_voices=["am_adam", "am_puck"])
    with pytest.raises(StageError, match="refused voice 'am_puck'"):
        tts.clips(part.parents[3], [("Hi.", "am_puck", 1.0)], tts.config(part.parents[3]))


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
