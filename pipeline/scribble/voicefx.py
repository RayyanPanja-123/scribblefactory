"""Voice effect on TTS clips (schemas VoiceFx, preset "In This Town": calm, low, warm, deadpan narration).

One ffmpeg filter chain per clip, run after the TTS server's WAV and before the clips are stitched, so the stitched
voice, its clip times (voice-tts.json) and every later stage already see the processed length:
  rubberband   pitch down and tempo down, formant preserved (the voice stays the same person)
  equalizer    lower-mid warmth;  treble  softer top end
  acompressor  gentle compression;  asoftclip  very light tanh saturation;  alimiter  no clipping
Loudness is levelled once over the whole voice by the tts stage (a 2 s clip is too short to measure).
Processed clips are cached in <library>/_tts-cache/fx/<sha256 of clip + settings>.wav."""

import hashlib
import json
import os
from pathlib import Path

from . import ff
from .schemas import VoiceFx

CHAIN_VERSION = 1       # bump when the chain below changes: every processed clip is made again
WARM_HZ, WARM_DB = 200, 5.0   # warmth 1.0 at full intensity: this much lower-mid boost
HIGH_HZ, HIGH_DB = 5000, 6.0  # ...and this much cut above HIGH_HZ
RATIO, THRESHOLD, MAKEUP = 3.0, 0.1, 1.5  # compressor at full intensity (threshold is linear: -20 dB)
DRIVE = 0.3             # saturation drive added at full intensity
LIMIT = 0.89            # about -1 dBFS
LOUDNORM = "loudnorm=I=-18:TP=-2:LRA=7"  # the whole voice, once: consistent loudness
SAMPLE_RATE = 24000


def active(fx: VoiceFx | None) -> bool:
    return fx is not None and fx.enabled


def chain(fx: VoiceFx) -> str:
    """the ffmpeg -af string for these settings"""
    k = fx.intensity
    f = []
    pitch, tempo = 2 ** (fx.pitch * k / 12), fx.speed
    if abs(pitch - 1) > 1e-4 or abs(tempo - 1) > 1e-4:
        f.append(f"rubberband=tempo={tempo:.4f}:pitch={pitch:.4f}:formant=preserved:pitchq=quality")
    warm, soft = WARM_DB * fx.warmth * k, HIGH_DB * fx.warmth * k
    if warm > 0.05:
        f += [f"equalizer=f={WARM_HZ}:t=q:w=0.9:g={warm:.2f}", f"treble=g=-{soft:.2f}:f={HIGH_HZ}"]
    if k > 0:
        f += [f"acompressor=threshold={THRESHOLD}:ratio={1 + (RATIO - 1) * k:.2f}:attack=20:release=200:makeup={MAKEUP}"]
        d = 1 + DRIVE * k
        f += [f"volume={d:.3f}", "asoftclip=type=tanh", f"volume={1 / d:.3f}"]
    f += [f"alimiter=limit={LIMIT}:level=false", f"aresample={SAMPLE_RATE}"]
    return ",".join(f)


def process(raw: Path, fx: VoiceFx | None, cache: Path) -> Path:
    """raw (a 24 kHz mono WAV) through the effect; raw itself when there is none. Cached, written whole."""
    if not active(fx):
        return raw
    key = hashlib.sha256(json.dumps([raw.stem, fx.model_dump(mode="json"), CHAIN_VERSION]).encode()).hexdigest()
    out = cache / "fx" / f"{key}.wav"
    if out.is_file():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.wav")
    try:
        ff.run("ffmpeg", "-v", "error", "-y", "-i", raw, "-af", chain(fx), "-ac", "1", "-ar", SAMPLE_RATE,
               "-c:a", "pcm_s16le", tmp, fail="the voice effect failed (needs ffmpeg with the rubberband filter)")
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out
