"""audio: synth music + SFX from story.json cues, mixed under voice-tight.wav (timing) -> audio/{music,sfx,mix}.wav.
Plus story.md's @sfx sounds from library/sfx/ (sfx.py: placed and ducked under the voice by ffmpeg).

Our own synth (numpy + stdlib wave only): the reference repo's audio kit needs scipy and is built for one story.
music.wav and sfx.wav are deterministic from story.json (seed, cues, shots) and the voice length.
"""

import io
import json
import re
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

from .. import sfx as sfx_lib
from .. import background_music
from ..io import atomic_write_bytes, replace_file
from ..schemas import StoryModel
from .runner import StageError

MUSIC_UNDER_DB = -6  # music loudness relative to the voice
BACKGROUND_UNDER_DB = -16.5  # the pack's default 15% bed under narration
SFX_UNDER_DB = -3    # SFX loudness relative to the voice
TARGET_LUFS, TARGET_TP, LUFS_TOL = -14.0, -1.0, 0.5
LOUDNORM_TP = -1.5   # aim under -1 dBTP: loudnorm's true peak lands a few tenths off its target
# a mix whose peaks stop linear loudnorm short of the target (it then quietly falls back to its dynamic mode, which
# undershoots on short parts) gets its peaks limited by these amounts in turn, until one lands on the target
PEAK_ROOM_DB = (3.0, 6.0, 9.0)

INPUTS = ["story.json", "voice-tight.wav", "story.md", "phrases.json", "../../sfx/sfx.json", "../../sfx"]
OUTPUTS = ["audio/music.wav", "audio/sfx.wav", "audio/mix.wav"]

SR, FPS = 48000, 30
SPF = SR // FPS               # samples per video frame
FADE = int(0.030 * SR)        # music stop / start fade
YAP = {"every": 9, "count": 3}  # engine/page/dog.js BARK: 3 yaps, 9 frames apart, from the cue frame
CAR_FADE_FRAMES = 8           # engine fade in / out at car shot edges
CAR_LEVEL = {"arrive": 1.0, "drive": 1.0, "leave": 1.0, "idle": 0.3, "broken": 0.0}
SCALE = [0, 2, 4, 5, 7, 9, 11]
PROGRESSIONS = [(0, 5, 3, 4), (0, 3, 4, 3), (0, 4, 5, 3), (0, 3, 0, 4)]  # scale degrees, one chord per bar
TAU = 2 * np.pi


# --- helpers ---

def _t(seconds):
    return np.arange(int(seconds * SR)) / SR


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _edges(x, attack=0.003, release=0.01):
    """short linear fade in/out so one-shots never click"""
    a, r = min(len(x), int(attack * SR)), min(len(x), int(release * SR))
    x[:a] *= np.linspace(0, 1, a, endpoint=False)
    x[len(x) - r:] *= np.linspace(1, 0, r)
    return x


def _lowpass(x, taps):
    return np.convolve(x, np.ones(taps) / taps, mode="same")


def _place(buf, x, start, gain=1.0, pan=0.0):
    """add mono x into stereo buf at sample start, equal-power pan -1..1; clipped to the buffer"""
    a, b = max(start, 0), min(start + len(x), len(buf))
    if a >= b:
        return
    seg = x[a - start:b - start] * gain
    th = (pan + 1) * np.pi / 4
    buf[a:b, 0] += seg * np.cos(th)
    buf[a:b, 1] += seg * np.sin(th)


# --- instruments ---

def _bass(f, dur):
    t = _t(dur)
    return _edges((np.sin(TAU * f * t) + 0.3 * np.sin(TAU * 2 * f * t)) * np.exp(-t / 0.3), 0.005, 0.03)


def _keys(f, dur):
    t = _t(dur)
    return _edges((np.sin(TAU * f * t) + 0.25 * np.sin(TAU * 2 * f * t) + 0.1 * np.sin(TAU * 3 * f * t))
                  * np.exp(-t / 0.2), 0.004, 0.03)


def _kick():
    t = _t(0.25)
    return _edges(np.sin(TAU * np.cumsum(50 + 90 * np.exp(-t / 0.03)) / SR) * np.exp(-t / 0.12))


def _shaker(R):
    return _edges(np.diff(R.standard_normal(int(0.06 * SR) + 1)) * np.exp(-_t(0.06) / 0.015), 0.002, 0.01)


def _snap(R):
    t = _t(0.12)
    return _edges(np.diff(_lowpass(R.standard_normal(len(t) + 1), 6)) * np.exp(-t / 0.035), 0.001, 0.01)


def music_loop(seed: int) -> np.ndarray:
    """4 bars, stereo, wrapping seamlessly: bass, chord stabs, kick / snap / shaker. Key and tempo from the seed."""
    R = np.random.default_rng(seed % 2**63)
    root = 48 + int(R.integers(0, 12))               # C3..B3
    beat = 60 / int(R.integers(100, 121))            # 100-120 BPM
    prog = PROGRESSIONS[int(R.integers(len(PROGRESSIONS)))]
    n = int(round(16 * beat * SR))
    buf = np.zeros((n + SR * 2, 2))                  # tail past the loop folds back to its start
    at = lambda b: int(round(b * beat * SR))          # noqa: E731  beat -> sample
    kick, shaker, snap = _kick(), _shaker(R), _snap(R)
    for bar, deg in enumerate(prog):
        b0 = bar * 4
        triad = [root + SCALE[(deg + k) % 7] + 12 * ((deg + k) // 7) for k in (0, 2, 4)]
        bass = triad[0] - 12
        for b, note, length in ((0, bass, 0.9), (1.5, bass, 0.4), (2, triad[2] - 12, 0.9), (3.5, bass + 12, 0.4)):
            _place(buf, _bass(_hz(note), length * beat), at(b0 + b), 0.5)
        for b in (1, 2.5, 3):  # off-beat stabs: the playful bit
            for k, note in enumerate(triad):
                _place(buf, _keys(_hz(note + 12), 0.35 * beat), at(b0 + b), 0.12, pan=(k - 1) * 0.4)
        for b in (0, 2):
            _place(buf, kick, at(b0 + b), 0.5)
        for b in (1, 3):
            _place(buf, snap, at(b0 + b), 0.25, pan=-0.2)
        for e in range(8):
            _place(buf, shaker, at(b0 + e / 2), 0.08 if e % 2 else 0.04, pan=0.35)
    loop = buf[:n].copy()
    loop[:len(buf) - n] += buf[n:]
    return loop


def music_segments(story: StoryModel) -> list[tuple[int, int]]:
    """(start, stop) frames where music plays: from music_start until the next music_stop (or the end)."""
    segs, on = [], None
    for c in sorted(story.cues, key=lambda c: c.frame):
        if c.kind == "music_start" and on is None:
            on = c.frame
        elif c.kind == "music_stop" and on is not None:
            segs.append((on, c.frame))
            on = None
    if on is not None:
        segs.append((on, story.duration_frames))
    return segs


def render_music(story: StoryModel, n: int) -> np.ndarray:
    loop, out = music_loop(story.seed), np.zeros((n, 2))
    for f0, f1 in music_segments(story):
        a, b = f0 * SPF, min(f1 * SPF + FADE, n)  # the stop fade starts at the cue
        if a >= b:
            continue
        seg = np.resize(loop, (b - a, 2))  # restart the loop from bar 1 at every music_start
        k = min(FADE, len(seg))
        seg[:k] *= np.linspace(0, 1, FADE)[:k, None]
        if f1 * SPF + FADE <= n:
            seg[-k:] *= np.linspace(1, 0, FADE)[-k:, None]
        out[a:b] = seg
    return out


def render_background_music(story: StoryModel, n: int) -> tuple[np.ndarray, float]:
    """Render @background-music cue segments and return (stereo audio, loudness volume setting)."""
    cues = sorted((c for c in story.cues if c.kind == "background_music"), key=lambda c: c.frame)
    out = np.zeros((n, 2))
    max_volume = 0.0
    for cue, nxt in zip(cues, [*cues[1:], None]):
        if cue.track is None:
            continue
        start = max(0, cue.frame * SPF)
        stop = min(n, (nxt.frame * SPF if nxt else n))
        if start >= stop:
            continue
        track = background_music.path(cue.track)
        if not track.is_file():
            raise StageError(f"background music file not found: {track}")
        sample = decode(track)
        if not len(sample):
            continue
        segment = np.resize(sample, (stop - start, 2)) * float(cue.volume or 0.0)
        fade = min(FADE, len(segment))
        segment[:fade] *= np.linspace(0, 1, fade)[:, None]
        if nxt:
            segment[-fade:] *= np.linspace(1, 0, fade)[:, None]
        out[start:stop] = segment
        max_volume = max(max_volume, float(cue.volume or 0.0))
    return out, max_volume


# --- SFX ---

def low_hit(R):
    t = _t(0.6)
    sweep = np.sin(TAU * np.cumsum(40 + 80 * np.exp(-t / 0.12)) / SR) * np.exp(-t / 0.22)
    thump = _lowpass(R.standard_normal(len(t)), 64) * 4 * np.exp(-t / 0.03)
    return _edges(np.tanh(1.5 * (sweep + thump)), 0.002, 0.05)


def whoosh(R):
    """noise through a band-pass whose centre sweeps up and back down (Chamberlin state-variable filter)"""
    t = _t(0.4)
    x = R.standard_normal(len(t))
    shape = np.sin(np.pi * t / t[-1]) ** 2
    fc = 2 * np.sin(np.pi * (300 + 2700 * shape) / SR)
    y, low, band = np.empty_like(x), 0.0, 0.0
    for i in range(len(x)):  # ponytail: per-sample Python loop, fine for 0.4 s one-shots
        low += fc[i] * band
        band += fc[i] * (x[i] - low - 0.7 * band)
        y[i] = band
    return _edges(y * shape * 0.6, 0.005, 0.02)


def pop():
    t = _t(0.1)
    return _edges(np.sin(TAU * np.cumsum(900 * (1 + t / t[-1])) / SR) * np.exp(-t / 0.025), 0.002, 0.01)


def yap(R):
    t = _t(0.13)
    f = (750 + 200 * R.random()) * (1.2 - 0.35 * t / t[-1])
    ph = TAU * np.cumsum(f) / SR
    tone = sum(np.sin(k * ph) / k for k in range(1, 7)) + 0.3 * _lowpass(R.standard_normal(len(t)), 4)
    return _edges(tone * np.exp(-t / 0.05), 0.008, 0.02)


def car_levels(story: StoryModel) -> np.ndarray:
    """per-frame engine level: driving 1, parked idle CAR_LEVEL["idle"], broken/none 0; ramped at shot edges"""
    lv = np.zeros(story.duration_frames)
    for s in story.shots:
        if s.vehicles:
            lv[s.start_frame:s.end_frame] = max(CAR_LEVEL[v.action] for v in s.vehicles)
    return _lowpass(np.pad(lv, CAR_FADE_FRAMES), CAR_FADE_FRAMES)[CAR_FADE_FRAMES:-CAR_FADE_FRAMES]


def car_engine(story: StoryModel, n: int, R) -> np.ndarray:
    lv = np.interp(np.arange(n) / SPF, np.arange(story.duration_frames), car_levels(story))
    if not lv.any():
        return np.zeros(n)
    rate = 8 + 10 * lv                                 # putts per second: slow idle, faster when driving
    putt = np.exp(-6 * (np.cumsum(rate) / SR % 1))     # each putt decays within its cycle
    body = 0.6 * np.sin(TAU * 65 * np.arange(n) / SR) + 0.8 * _lowpass(R.standard_normal(n), 24)
    return putt * body * lv


def sputter(R):
    """engine dying: putts that stumble further and further apart, then a backfire bang"""
    gaps = 0.07 * 1.4 ** np.arange(7) * (0.8 + 0.4 * R.random(7))
    starts = (np.concatenate([[0], np.cumsum(gaps)]) * SR).astype(int)
    out = np.zeros(starts[-1] + int(0.3 * SR))
    t = _t(0.06)
    for k, a in enumerate(starts[:-1]):
        body = 0.6 * np.sin(TAU * 65 * t) + 0.8 * _lowpass(R.standard_normal(len(t)), 24)
        out[a:a + len(t)] += _edges(body * np.exp(-t / 0.015)) * (1 - k / 10)
    t = _t(0.3)
    bang = np.tanh(3 * _lowpass(R.standard_normal(len(t)), 12) * np.exp(-t / 0.04))
    out[starts[-1]:] += _edges(bang, 0.001, 0.05) * 1.2
    return out


def breakdown_frames(story: StoryModel) -> list[int]:
    """start of each run of shots with a broken car: the engine dies there"""
    broken = [any(v.action == "broken" for v in s.vehicles) for s in story.shots]
    return [s.start_frame for s, b, prev in zip(story.shots, broken, [False] + broken) if b and not prev]


def whoosh_frames(story: StoryModel) -> list[int]:
    """whoosh cues plus every set change (the engine's marker wipe is centred on it)"""
    sets = [s.start_frame for p, s in zip(story.shots, story.shots[1:]) if s.set != p.set]
    return sorted({c.frame for c in story.cues if c.kind == "whoosh"} | set(sets))


def render_sfx(story: StoryModel, n: int) -> np.ndarray:
    R = np.random.default_rng((story.seed + 1) % 2**63)
    out = np.zeros((n, 2))
    for c in sorted(story.cues, key=lambda c: (c.frame, c.kind)):
        at = c.frame * SPF
        if c.kind == "low_hit":
            _place(out, low_hit(R), at, 1.0)
        elif c.kind == "pop":
            _place(out, pop(), at, 0.4)
        elif c.kind == "bark":
            for k in range(YAP["count"]):
                _place(out, yap(R), at + k * YAP["every"] * SPF, 0.45, pan=0.2)
    for f in whoosh_frames(story):
        x = whoosh(R)
        half = len(x) // 2
        _place(out, x[:half], f * SPF - half, 0.5, pan=-0.4)  # left to right, like the wipe stroke
        _place(out, x[half:], f * SPF, 0.5, pan=0.4)
    _place(out, car_engine(story, n, R), 0, 0.25)
    for f in breakdown_frames(story):
        _place(out, sputter(R), f * SPF, 0.35, pan=0.1)
    return out


# --- files and ffmpeg ---

def _ffmpeg(*args, data: bytes | None = None) -> subprocess.CompletedProcess:
    if not shutil.which("ffmpeg"):
        raise StageError("ffmpeg not found on PATH")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], input=data, capture_output=True)
    if r.returncode != 0:
        raise StageError(f"ffmpeg failed: {r.stderr.decode(errors='replace').strip()[-300:]}")
    return r


def decode(path: Path) -> np.ndarray:
    """any audio file -> float32 (n, 2) at 48 kHz"""
    r = _ffmpeg("-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-")
    return np.frombuffer(r.stdout, dtype="<f4").reshape(-1, 2)


def wav_bytes(x: np.ndarray) -> bytes:
    """stereo float (-1..1) -> 16-bit PCM WAV bytes"""
    pcm = (np.clip(x, -1, 1) * 32767).round().astype("<i2")
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return b.getvalue()


def _peak_norm(x: np.ndarray, peak=0.5) -> np.ndarray:
    m = np.abs(x).max()
    return x * (peak / m) if m > 0 else x


def loudness(path: Path) -> tuple[float, float]:
    """(integrated LUFS, true peak dBTP) via ffmpeg ebur128; silence gives (-70.0, -inf)"""
    err = _ffmpeg("-i", str(path), "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-").stderr.decode()
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    tp = re.findall(r"Peak:\s+(-?[\d.]+|-inf) dBFS", err)
    if not i or not tp:
        raise StageError(f"could not read loudness of {path.name}")
    return float(i[-1]), float(tp[-1])


def _gain(target: float, measured: float) -> float:
    return 0.0 if measured <= -69 else 10 ** ((target - measured) / 20)


def loudnorm(x: np.ndarray, out: Path) -> None:
    """two-pass ffmpeg loudnorm of float stereo x to TARGET_LUFS, written as 16-bit WAV at out"""
    raw = ["-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-"]
    data = x.astype("<f4").tobytes()
    base = f"loudnorm=I={TARGET_LUFS}:TP={LOUDNORM_TP}:LRA=20"
    err = _ffmpeg(*raw, "-af", f"{base}:print_format=json", "-f", "null", "-", data=data).stderr.decode()
    m = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    second = (f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
              f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    _ffmpeg("-v", "error", "-y", *raw, "-af", second, "-ar", str(SR), "-c:a", "pcm_s16le", str(out), data=data)


def limit_peaks(x: np.ndarray, db: float) -> np.ndarray:
    """x with its peaks held db under where they were (ffmpeg alimiter, look-ahead, no make-up gain): room for
    the linear loudnorm gain a peaky voice needs to reach the target"""
    peak = float(np.abs(x).max()) or 1.0
    lim = max(0.0625, min(1.0, peak * 10 ** (-db / 20)))  # alimiter's limit range
    r = _ffmpeg("-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                "-af", f"volume={1 / peak:.6f},alimiter=limit={lim / peak:.6f}:level=false:attack=5:release=50,"
                       f"volume={peak:.6f}", "-f", "f32le", "-", data=x.astype("<f4").tobytes())
    return np.frombuffer(r.stdout, dtype="<f4").reshape(-1, 2)


def run(part_dir: Path) -> None:
    story = StoryModel.model_validate_json((part_dir / "story.json").read_bytes())
    voice_mp3 = part_dir / "voice-tight.wav"
    if not voice_mp3.exists():
        raise StageError("voice-tight.wav not found: run --stage timing")
    n = story.duration_frames * SPF  # the video's length: the voice is cut or padded to it
    voice = decode(voice_mp3)[:n]
    voice = np.pad(voice, ((0, n - len(voice)), (0, 0)))
    d = part_dir / "audio"
    d.mkdir(exist_ok=True)
    has_background = any(c.kind == "background_music" for c in story.cues)
    if has_background:
        rendered_music, music_volume = render_background_music(story, n)
        # Keep the requested 0-1 setting meaningful after loudness matching.
        music_target = BACKGROUND_UNDER_DB + (20 * np.log10(music_volume / 0.15) if music_volume else -60)
    else:
        rendered_music, music_volume = render_music(story, n), None
        music_target = MUSIC_UNDER_DB
    atomic_write_bytes(d / "music.wav", wav_bytes(_peak_norm(rendered_music)))
    atomic_write_bytes(d / "sfx.wav", wav_bytes(_peak_norm(render_sfx(story, n))))

    v_lufs, _ = loudness(voice_mp3)
    if v_lufs <= -69:
        raise StageError("the voice is silent")
    music, sfx = decode(d / "music.wav"), decode(d / "sfx.wav")
    g_m = _gain(v_lufs + music_target, loudness(d / "music.wav")[0])
    g_s = _gain(v_lufs + SFX_UNDER_DB, loudness(d / "sfx.wav")[0])
    print(f"voice {v_lufs:.1f} LUFS; music gain {20 * np.log10(g_m or 1e-9):+.1f} dB, "
          f"sfx gain {20 * np.log10(g_s or 1e-9):+.1f} dB")

    tmp = d / ".mix.tmp.wav"  # ffmpeg writes it; replaced into mix.wav only once it measures in range
    try:
        mix = voice + g_m * music + g_s * sfx
        if (library_sfx := sfx_lib.stem(part_dir, voice)) is not None:
            mix = mix + library_sfx
        loudnorm(mix, tmp)
        lufs, tp = loudness(tmp)
        print(f"mix: {lufs:.1f} LUFS integrated, true peak {tp:.1f} dBTP")
        if abs(lufs - TARGET_LUFS) > LUFS_TOL / 2 or tp > TARGET_TP:  # peaky voice: peak ceiling before the target
            tries = [(lufs, tp, tmp.read_bytes())]
            for room in PEAK_ROOM_DB:
                loudnorm(limit_peaks(mix, room), tmp)
                lufs, tp = loudness(tmp)
                print(f"mix (peaks limited {room:.0f} dB): {lufs:.1f} LUFS integrated, true peak {tp:.1f} dBTP")
                tries.append((lufs, tp, tmp.read_bytes()))
            # the try nearest the target that keeps the peak ceiling (else simply the nearest)
            lufs, tp, best = min(tries, key=lambda t: (t[1] > TARGET_TP, abs(t[0] - TARGET_LUFS)))
            tmp.write_bytes(best)
            print(f"mix: kept {lufs:.1f} LUFS, true peak {tp:.1f} dBTP")
        if abs(lufs - TARGET_LUFS) > LUFS_TOL or tp > TARGET_TP:
            raise StageError(f"mix missed the target: {lufs:.1f} LUFS, {tp:.1f} dBTP "
                             f"(want {TARGET_LUFS:.0f} +/-{LUFS_TOL} LUFS, <= {TARGET_TP:.0f} dBTP)")
        replace_file(tmp, d / "mix.wav")
    finally:
        Path(tmp).unlink(missing_ok=True)
