"""The "In This Town" voice effect (voicefx.py) on a real ffmpeg run; skipped without the rubberband filter."""
import math
import shutil
import struct
import subprocess
import wave

import pytest

from pipeline.scribble import voicefx
from pipeline.scribble.schemas import TtsVoice, VoiceFx

HAS = shutil.which("ffmpeg") and b"rubberband" in subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True).stdout


def tone(path, hz=130, secs=1.0, amp=0.6):
    n = int(24000 * secs)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * amp * math.sin(2 * math.pi * hz * i / 24000))) for i in range(n)))


def info(path):
    with wave.open(str(path)) as w:
        raw = w.readframes(w.getnframes())
        return w.getframerate(), w.getnchannels(), w.getnframes() / w.getframerate(), max(abs(v) for v in struct.unpack(f"<{len(raw) // 2}h", raw))


def test_off_means_the_raw_clip(tmp_path):
    raw = tmp_path / "a.wav"
    assert voicefx.process(raw, None, tmp_path) == raw
    assert voicefx.process(raw, VoiceFx(enabled=False), tmp_path) == raw


def test_fx_is_left_out_of_a_plain_voice():
    assert "fx" not in TtsVoice(id="am_adam").model_dump(mode="json")
    assert TtsVoice(id="am_adam", fx=VoiceFx()).model_dump(mode="json")["fx"]["pitch"] == -1.5


@pytest.mark.skipif(not HAS, reason="ffmpeg with rubberband not found")
def test_slower_same_format_no_clipping_cached(tmp_path):
    raw = tmp_path / "a.wav"
    tone(raw, amp=0.95)
    out = voicefx.process(raw, VoiceFx(), tmp_path)
    rate, ch, secs, peak = info(out)
    assert (rate, ch) == (24000, 1)
    assert 1.0 / 0.94 * 0.95 < secs < 1.0 / 0.94 * 1.08  # 0.94x tempo: about 6 % longer
    assert peak < 32767 * 0.92  # limited, never clipped
    assert voicefx.process(raw, VoiceFx(), tmp_path) == out  # the cache, not a second run
    assert voicefx.process(raw, VoiceFx(pitch=-3), tmp_path) != out  # other settings, other clip
