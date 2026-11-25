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


# ---------------- speakers: "kai: line" ----------------

DIALOGUE = ("# Stranded\nThe ship came down hard.\n@do kai: wave\nkai: \"Everyone alive?\"\nmira: Define alive.\n"
            "!! kai: “Then we walk.”\n")


def with_cast(p, voices: dict):
    from pipeline.scribble.schemas import CastMember
    f = p.parent / "series.json"
    s = load_series(f)
    s.cast = [CastMember(id=c, name=c.title(), top={"color": "#111111"}, eyes="dots",
                         voice=TtsVoice(id=v) if v else None) for c, v in voices.items()]
    save_series(f, s)
    (p / "story.md").write_text(DIALOGUE, encoding="utf-8")
    from pipeline.scribble.stages.prep import clean_markdown, strip_directives
    (p / "script-for-tts.txt").write_text(clean_markdown(strip_directives(DIALOGUE)) + "\n", encoding="utf-8")


def test_spoken_lines_lose_speaker_and_quotes_only():
    from pipeline.scribble.stages.prep import clean_markdown, speakers, spoken, strip_directives
    assert spoken('kai: "Hi there."') == "Hi there." and spoken("!! mira: Not again.") == "Not again."
    assert spoken("Here's the catch: it works.") == "Here's the catch: it works."  # a narrator bridge stays
    assert spoken('He said "no" twice.') == 'He said "no" twice.'  # a narrator's quotes stay
    assert speakers(DIALOGUE) == {4: "kai", 5: "mira", 6: "kai"}
    assert clean_markdown(strip_directives(DIALOGUE)) == \
        "The ship came down hard. Everyone alive? Define alive. Then we walk."


def test_each_speaker_in_their_own_voice(part, server):
    url, _ = server
    use(part, url)
    with_cast(part, {"kai": "am_adam", "mira": None})  # mira has none: the narrator reads her line
    tts_stage.run(part)
    got = {i["text"]: i["voice"] for i in Kokoro.made}
    assert got == {"The ship came down hard.": "am_michael", "Everyone alive?": "am_adam",
                   "Define alive.": "am_michael", "Then we walk.": "am_adam"}
    m = json.loads((part / tts_stage.MANIFEST).read_text(encoding="utf-8"))
    assert [(ln["line"], ln["speaker"]) for ln in m["lines"]] == [(2, None), (4, "kai"), (5, "mira"), (6, "kai")]


def test_a_cast_voice_is_not_part_of_the_look_or_series_hash(part):
    with_cast(part, {"kai": None})
    before, look = series_bytes(part.parent), load_series(part.parent / "series.json").cast[0].look()
    with_cast(part, {"kai": "am_adam"})
    kai = load_series(part.parent / "series.json").cast[0]
    assert kai.voice.id == "am_adam" and kai.look() == look and series_bytes(part.parent) == before


def test_storycheck_speakers_and_voices(part):
    from pipeline.scribble.storycheck import check_story
    with_cast(part, {"kai": "af_nope"})
    db.put_settings(lib(part), {"tts_voices": ["am_adam", "am_michael"]})
    r = check_story(part)
    msgs = [x["message"] for x in r["problems"]]
    assert any(m.startswith("unknown cast id mira (") and "spoken by cast member mira" in m for m in msgs)
    assert any("kai's TTS voice 'af_nope' is not one of the server's voices" in m for m in msgs)
    with_cast(part, {"kai": "am_adam", "mira": None})
    r = check_story(part)
    assert not any("voice" in x["message"] or "unknown cast" in x["message"] for x in r["problems"])
    assert any(w["message"].startswith("mira speaks but has no TTS voice") for w in r["warnings"])


# ---------------- timing: @pause, @pace, meant gaps, one voice per phrase ----------------

BEATS = ("# Stranded\nThe ship came down hard.\n@pause 1.5\n@pace fast\nkai: Everyone alive?\nmira: Define alive.\n")


def test_pause_and_pace_shape_the_voice(part, server):
    url, _ = server
    use(part, url)
    with_cast(part, {"kai": "am_adam", "mira": "am_michael"})
    (part / "story.md").write_text(BEATS, encoding="utf-8")
    from pipeline.scribble.stages.prep import clean_markdown, strip_directives, voice_marks
    (part / "script-for-tts.txt").write_text(clean_markdown(strip_directives(BEATS)) + "\n", encoding="utf-8")
    assert voice_marks(BEATS) == {5: {"pause": 1.5, "pace": 1.15}}
    tts_stage.run(part)
    assert {i["text"]: i["speed"] for i in Kokoro.made}["Everyone alive?"] == 1.15  # @pace fast: that line only
    assert {i["text"]: i["speed"] for i in Kokoro.made}["Define alive."] == 1.0
    a, b, c = json.loads((part / tts_stage.MANIFEST).read_text(encoding="utf-8"))["lines"]
    assert b["start"] - a["end"] == pytest.approx(1.5, abs=0.002)  # @pause 1.5 before kai's line
    assert c["start"] - b["end"] == pytest.approx(0.3, abs=0.002)  # the usual gap


def test_meant_gaps_survive_and_phrases_break_at_a_new_speaker():
    from pipeline.scribble.stages.timing import gap_cuts, split_phrases
    w = lambda t, s, e: {"text": t, "start": s, "end": e}  # noqa: E731
    words = [w("Go", 0.0, 0.3), w("now", 0.35, 0.7), w("Why", 2.2, 2.5), w("not", 2.55, 2.9)]
    assert gap_cuts(words) == [(0.85, 2.05)]  # a 1.5 s pause: cut down to 0.3 s
    assert gap_cuts(words, keep_after={1}) == []  # a TTS line join (@pause): kept
    one = [w("Go", 0.0, 0.3), w("now", 0.35, 0.7), w("why", 0.8, 1.1), w("not", 1.15, 1.5)]
    assert [(p["word_start"], p["word_end"]) for p in split_phrases(one)] == [(0, 3)]
    assert [(p["word_start"], p["word_end"]) for p in split_phrases(one, breaks={1})] == [(0, 1), (2, 3)]


def test_storycheck_pause_and_pace(part):
    from pipeline.scribble.storycheck import check_story
    with_cast(part, {"kai": "am_adam", "mira": "am_adam"})
    (part / "story.md").write_text(BEATS.replace("@pause 1.5", "@pause 9"), encoding="utf-8")
    assert any("bad directive @pause 9" in x["message"] for x in check_story(part)["problems"])
    m = load_part(part / "part.json")
    m.voice_source = "recorded"
    save_part(part / "part.json", m)
    (part / "story.md").write_text(BEATS, encoding="utf-8")
    r = check_story(part)
    assert not any("@pause" in x["message"] or "@pace" in x["message"] for x in r["problems"])
    assert {w["line"] for w in r["warnings"] if "only shapes a TTS voice" in w["message"]} == {3, 4}
