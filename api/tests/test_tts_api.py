"""TTS routes: voices (online and not), preview, clips, the narrator voice, a part's voice source, voice-tts.json
lines in the part detail. The Kokoro server is the stand-in from pipeline/tests/test_tts.py."""

import json

from api.tests.test_api import client, lib  # noqa: F401 (fixtures)
from pipeline.scribble import db
from pipeline.scribble.io import load_part, load_series, part_dir_of
from pipeline.tests.test_tts import server  # noqa: F401 (fixture)


def test_voices_offline_falls_back_to_the_saved_ids(client, lib):  # noqa: F811
    r = client.get("/api/tts/voices").json()
    assert r["online"] is False and r["default"] == "am_michael"
    assert [v["id"] for v in r["voices"]] == ["am_adam", "am_fenrir", "am_michael", "am_puck"]


def test_voices_preview_and_clip_from_the_server(client, lib, server):  # noqa: F811
    url, _ = server
    db.put_settings(lib, {"tts_url": url})
    r = client.get("/api/tts/voices").json()
    assert r["online"] is True and [v["id"] for v in r["voices"]] == ["am_adam", "am_michael", "am_puck"]
    wav = client.get("/api/tts/preview", params={"voice": "am_adam", "speed": 1.1})
    assert wav.status_code == 200 and wav.headers["content-type"] == "audio/wav" and wav.content[:4] == b"RIFF"
    key = next((lib / "_tts-cache").glob("*.wav")).stem
    assert client.get(f"/api/tts/clip/{key}").content == wav.content
    assert client.get("/api/tts/clip/not-a-key").status_code == 404
    assert client.get("/api/tts/preview", params={"voice": "zz_nope"}).status_code == 503


def test_preview_without_a_server_is_a_clear_error(client, lib):  # noqa: F811
    r = client.get("/api/tts/preview", params={"voice": "am_adam"})
    assert r.status_code == 503 and "no TTS server set" in r.json()["detail"]


def test_narrator_voice_and_voice_source(client, lib):  # noqa: F811
    s = client.put("/api/series/demo/voice", json={"tts": {"id": "am_adam", "speed": 1.2}}).json()
    assert s["voice"]["tts"] == {"id": "am_adam", "speed": 1.2}
    assert "tts" not in client.put("/api/series/demo/voice", json={"tts": None}).json()["voice"]
    assert load_series(lib / "database" / "storage" / "demo" / "series.json").voice.tts is None
    p = client.put("/api/series/demo/parts/part-01/voice-source", json={"source": "tts"}).json()
    assert p["voice_source"] == "tts"
    assert client.put("/api/series/demo/parts/part-01/voice-source", json={"source": "x"}).status_code == 422
    client.put("/api/series/demo/parts/part-01/voice-source", json={"source": "recorded"})
    assert load_part(part_dir_of(lib / "database" / "storage" / "demo", "part-01") / "part.json").voice_source == "recorded"


def test_part_detail_lists_the_tts_lines(client, lib):  # noqa: F811
    d = part_dir_of(lib / "database" / "storage" / "demo", "part-01")
    assert client.get("/api/series/demo/parts/part-01").json()["tts_lines"] is None
    line = {"line": 3, "speaker": "bob", "voice": "am_adam", "speed": 1.0, "text": "Hi.", "clip": "a" * 64,
            "start": 0.0, "end": 0.5, "pause": 1.2, "pace": None}
    (d / "voice-tts.json").write_text(json.dumps({"schema_version": 1, "lines": [line]}), encoding="utf-8")
    assert client.get("/api/series/demo/parts/part-01").json()["tts_lines"] == [line]
