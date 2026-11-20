"""Voiceover enhancer for Scribble Saga: voice EQ + compression, comedic pauses, emphasis, optional SFX, -14 LUFS master.

  .venv/Scripts/python.exe tools/voiceover/enhance.py "D:/personal/short-animations/audios/My Voiceover.mp3"
      --markers FILE   per-voiceover markers (default: "<input name>.toml" next to the input, if it exists)
      --out DIR        output folder (default: "output" next to the input)
      --no-sfx         leave the sound-effects layer out

Writes <name>_enhanced.wav (24-bit, input sample rate), <name>_enhanced.mp3 and <name>_enhanced_report.md.
The input is only ever read. Run once without markers: the report lists the transcript with timestamps and every
silence, so you can pick the punchlines. Sound settings: default.toml (a markers file can override any key).

Markers (all times are on the ORIGINAL voiceover; a marker uses `phrase` [+ `occurrence`], or seconds):
  [[pause]]     phrase | at        seconds = 0.7          gap before the phrase grows to this; never shrinks
  [[emphasis]]  phrase | start+end gain_db, speed (0.9 = slower), pitch_semitones, radio (0..1 wet)
  [[sfx]]       phrase | at        file, anchor = start|end|after, gain_db, offset
                                   (end: the sound ENDS where the phrase starts, for risers)
Phrases are matched word by word against a local faster-whisper transcript (models/faster-whisper-base.en).
"""

import argparse
import json
import logging
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
WHISPER_DIR = HERE.parents[1] / "models" / "faster-whisper-base.en"
FRAME_S = 0.01  # analysis frame for silence / quiet-point search
FADE_S = 0.005  # edge fade around inserted silence and processed segments
RAMP_S = 0.03   # emphasis gain fades in/out over this, so boosts never click
KEYS = {
    "pause": {"phrase", "occurrence", "at", "seconds"},
    "emphasis": {"phrase", "occurrence", "start", "end", "gain_db", "speed", "pitch_semitones", "radio"},
    "sfx": {"phrase", "occurrence", "at", "file", "anchor", "gain_db", "offset"},
}
log = logging.getLogger("voiceover")


class EnhanceError(Exception):
    pass


# --- ffmpeg I/O: audio travels as raw float32 through pipes, so nothing touches disk until export ---

def ffmpeg(args, data=None, loglevel="error"):
    io = {"input": data} if data is not None else {"stdin": subprocess.DEVNULL}
    try:
        p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", loglevel, *args],
                           capture_output=True, **io)
    except FileNotFoundError:
        raise EnhanceError("ffmpeg not found on PATH") from None
    if p.returncode:
        raise EnhanceError(f"ffmpeg failed: {p.stderr.decode(errors='replace')[-800:]}")
    return p.stdout, p.stderr.decode(errors="replace")


def probe(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                              "stream=sample_rate,channels,codec_name,bit_rate:format=duration", "-of", "json",
                              str(path)], capture_output=True, check=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise EnhanceError(f"ffprobe could not read {path}: {e}") from None
    info = json.loads(out)
    if not info.get("streams"):
        raise EnhanceError(f"no audio stream in {path}")
    s = info["streams"][0]
    return {"sr": int(s["sample_rate"]), "ch": int(s["channels"]), "codec": s.get("codec_name"),
            "bitrate": s.get("bit_rate"), "duration": float(info["format"]["duration"])}


def raw_in(sr, ch):
    return ["-f", "f32le", "-ar", str(sr), "-ac", str(ch), "-i", "pipe:0"]


def decode(path, sr, ch):
    out, _ = ffmpeg(["-i", str(path), "-f", "f32le", "-ar", str(sr), "-ac", str(ch), "pipe:1"])
    return np.frombuffer(out, np.float32).reshape(-1, ch).copy()


def filt(x, sr, chain):
    out, _ = ffmpeg([*raw_in(sr, x.shape[1]), "-af", chain, "-f", "f32le", "-ar", str(sr), "pipe:1"],
                    x.astype(np.float32).tobytes())
    return np.frombuffer(out, np.float32).reshape(-1, x.shape[1]).copy()


def encode(x, sr, path, codec):
    ffmpeg([*raw_in(sr, x.shape[1]), *codec, "-y", str(path)], x.astype(np.float32).tobytes())


def measure(x, sr):
    """EBU R128 integrated loudness, LRA, true peak (dBTP) and sample peak (dBFS)"""
    _, err = ffmpeg([*raw_in(sr, x.shape[1]), "-af", "ebur128=peak=true", "-f", "null", "-"],
                    x.astype(np.float32).tobytes(), loglevel="info")
    summary = err[err.rfind("Summary:"):]
    num = lambda key: float(re.search(rf"{key}:\s+(-?[\d.]+|-inf)", summary).group(1))  # noqa: E731
    peak = float(np.abs(x).max()) if len(x) else 0.0
    return {"lufs": num("I"), "lra": num("LRA"), "true_peak": num("Peak"),
            "peak": 20 * np.log10(peak) if peak > 0 else -float("inf"), "duration": len(x) / sr}


# --- analysis ---

def frame_db(x, sr):
    hop = int(sr * FRAME_S)
    n = len(x) // hop
    mono = x[:n * hop].mean(axis=1).reshape(n, hop)
    return 10 * np.log10((mono ** 2).mean(axis=1) + 1e-12)


def silences(x, sr, db, min_s):
    """[(start, end)] seconds of runs quieter than db, at least min_s long"""
    quiet = np.concatenate([[False], frame_db(x, sr) < db, [False]])
    edges = np.flatnonzero(np.diff(quiet.astype(int)))
    return [(a * FRAME_S, b * FRAME_S) for a, b in zip(edges[::2], edges[1::2]) if (b - a) * FRAME_S >= min_s]


def quietest(x, sr, t, radius):
    """the quietest frame centre within t +/- radius seconds: where a cut or splice is least audible"""
    db = frame_db(x, sr)
    a, b = max(0, int((t - radius) / FRAME_S)), min(len(db), int((t + radius) / FRAME_S) + 1)
    if a >= b:
        return min(max(t, 0.0), len(x) / sr)
    return (a + int(np.argmin(db[a:b])) + 0.5) * FRAME_S


def transcribe(path):
    """[{text, start, end}] words, deterministic (temperature 0)"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise EnhanceError("transcription needs faster-whisper: run with the project venv (.venv/Scripts/python.exe)")
    if not WHISPER_DIR.exists():
        raise EnhanceError(f"whisper model missing in {WHISPER_DIR}: run setup.sh")
    audio = decode(path, 16000, 1)[:, 0]
    model = WhisperModel(str(WHISPER_DIR), device="cpu", compute_type="int8", local_files_only=True)
    segments, _ = model.transcribe(audio, word_timestamps=True, temperature=0.0, beam_size=5)
    return [{"text": w.word.strip(), "start": w.start, "end": w.end} for s in segments for w in s.words]


def norm(word):
    return re.sub(r"[^a-z0-9]", "", word.lower())


def find_phrase(words, phrase, occurrence=1):
    want = [norm(t) for t in phrase.split() if norm(t)]
    toks = [norm(w["text"]) for w in words]
    hits = [i for i in range(len(toks) - len(want) + 1) if want and toks[i:i + len(want)] == want]
    if len(hits) < occurrence:
        raise EnhanceError(f'phrase "{phrase}" found {len(hits)}x (wanted occurrence {occurrence}); '
                           "check the transcript in the report")
    i = hits[occurrence - 1]
    return words[i]["start"], words[i + len(want) - 1]["end"]


def span(m, words):
    """a marker's (start, end) seconds on the original timeline"""
    if "phrase" in m:
        if words is None:
            raise EnhanceError(f'phrase marker "{m["phrase"]}" needs a transcript (faster-whisper unavailable)')
        return find_phrase(words, m["phrase"], m.get("occurrence", 1))
    if "at" in m:
        return float(m["at"]), float(m["at"])
    if "start" in m and "end" in m:
        return float(m["start"]), float(m["end"])
    raise EnhanceError(f"marker needs phrase, at, or start+end: {m}")


# --- processing ---

def voice_chain(cfg):
    eq, comp, f = cfg["eq"], cfg["compressor"], []
    if eq["enabled"]:
        f.append(f"highpass=f={eq['highpass_hz']}")
        f += [f"equalizer=f={b['freq']}:t=q:w={b['q']}:g={b['gain_db']}" for b in eq["bands"]]
        f.append(f"treble=f={eq['air_shelf']['freq']}:g={eq['air_shelf']['gain_db']}")
    if comp["enabled"]:
        f.append(f"acompressor=threshold={10 ** (comp['threshold_db'] / 20):.5f}:ratio={comp['ratio']}"
                 f":attack={comp['attack_ms']}:release={comp['release_ms']}"
                 f":makeup={10 ** (comp['makeup_db'] / 20):.4f}:knee=2.8")
    if eq["enabled"] and eq["deesser"] > 0:
        f.append(f"deesser=i={eq['deesser']}")
    return ",".join(f)


def pause_plan(rules, words, sil, x, sr, max_pause):
    """[(insert_at_s, seconds)]: each gap before a marked phrase grows to its target length; never shrinks"""
    plan = {}
    for r in rules:
        t, _ = span(r, words)
        target = min(float(r["seconds"]), max_pause)
        near = [(a, b) for a, b in sil if abs(b - t) < 0.25 or a <= t <= b]
        if near:
            a, b = min(near, key=lambda s: abs(s[1] - t))
            at, have = quietest(x, sr, (a + b) / 2, (b - a) / 2), b - a
        else:
            at, have = quietest(x, sr, t, 0.08), 0.0
            level = frame_db(x, sr)[min(int(at / FRAME_S), len(x) // int(sr * FRAME_S) - 1)]
            log.warning('no silence before "%s": cutting in at its quietest point (%.0f dB)', r.get("phrase", t), level)
        key = round(at, 2)
        if target - have > 0.005 and target - have > plan.get(key, (0, 0))[1]:
            plan[key] = (at, target - have)
        log.info("pause %-34s %.2fs -> %.2fs", f'"{r.get("phrase", t)}"'[:34], have, max(have, target))
    return sorted(plan.values())


def segment_fx(seg, sr, fx):
    """emphasis on one slice: speed/pitch (rubberband, formants kept), radio blend, then a ramped gain boost"""
    y = seg
    speed, semis = float(fx.get("speed", 1)), float(fx.get("pitch_semitones", 0))
    if speed != 1 or semis:
        y = filt(y, sr, f"rubberband=tempo={speed}:pitch={2 ** (semis / 12):.6f}:formant=preserved")
    if radio := float(fx.get("radio", 0)):
        wet = filt(y, sr, "highpass=f=350,lowpass=f=3200,volume=6dB,asoftclip=type=tanh,volume=-6dB")
        rms = lambda a: np.sqrt((a ** 2).mean()) + 1e-9  # noqa: E731
        y = (1 - radio) * y + radio * wet * (rms(y) / rms(wet))
    if gain := float(fx.get("gain_db", 0)):
        r = min(int(RAMP_S * sr), len(y) // 2)
        env = np.full(len(y), 10 ** (gain / 20))
        env[:r] = np.linspace(1, env[0], r)
        env[len(y) - r:] = np.linspace(env[0], 1, r)
        y = y * env[:, None]
    return y.astype(np.float32)


def assemble(x, sr, inserts, segments):
    """splice silences and processed segments in -> (audio, timemap original_s -> output_s)"""
    items = sorted([(int(t * sr), 0, int(s * sr)) for t, s in inserts] +
                   [(int(a * sr), 1, (int(b * sr), fx)) for a, b, fx in segments], key=lambda i: i[:2])
    out, ox, oy, splices, pos, olen = [], [0.0], [0.0], [], 0, 0
    for p, kind, val in items:
        if p < pos:
            raise EnhanceError(f"markers overlap at {p / sr:.2f}s (emphasis spans and pauses must not cross)")
        out.append(x[pos:p])
        olen += p - pos
        pos = p
        ox.append(p), oy.append(olen)
        if kind == 0:
            out.append(np.zeros((val, x.shape[1]), np.float32))
            splices += [olen, olen + val]
            olen += val
            ox.append(p + 0.5), oy.append(olen)
        else:
            end, fx = val
            seg = segment_fx(x[p:end], sr, fx)
            out.append(seg)
            splices += [olen, olen + len(seg)] if len(seg) != end - p else []
            olen += len(seg)
            pos = end
            ox.append(end), oy.append(olen)
    out.append(x[pos:])
    ox.append(len(x)), oy.append(olen + len(x) - pos)
    y = np.concatenate(out)
    f = int(FADE_S * sr)
    for s in splices:  # short fades either side of every splice point: no clicks
        y[max(0, s - f):s] *= np.linspace(1, 0, s - max(0, s - f))[:, None]
        y[s:s + f] *= np.linspace(0, 1, len(y[s:s + f]))[:, None]
    tm = lambda t: float(np.interp(t * sr, ox, oy)) / sr  # noqa: E731
    return y, tm


def resolve_sfx(name, dirs):
    p = Path(name)
    for c in [p] if p.is_absolute() else [d / p for d in dirs]:
        if c.is_file():
            return c
    return None


def mix_sfx(y, sr, rules, words, tm, dirs, default_gain):
    """add each sound under the voice; its peak sits gain_db below the voice peak. Missing file = warning."""
    voice_peak, done = float(np.abs(y).max()), []
    for r in rules:
        path = resolve_sfx(r["file"], dirs)
        if path is None:
            log.warning("sfx %s not found in %s: skipped", r["file"], ", ".join(map(str, dirs)))
            continue
        s = decode(path, sr, y.shape[1])
        if not len(s) or not np.abs(s).max():
            log.warning("sfx %s is silent: skipped", r["file"])
            continue
        a, b = span(r, words)
        anchor = r.get("anchor", "start")
        t = {"start": tm(a), "after": tm(b), "end": tm(a) - len(s) / sr}.get(anchor)
        if t is None:
            raise EnhanceError(f"sfx anchor must be start, end or after: {anchor}")
        gain = r.get("gain_db", default_gain)
        s = s * (voice_peak * 10 ** (gain / 20) / np.abs(s).max())
        i = int(round((t + float(r.get("offset", 0))) * sr))
        s, i = s[max(0, -i):], max(0, i)
        if i + len(s) > len(y):  # a tail past the end extends the track rather than being cut off
            y = np.concatenate([y, np.zeros((i + len(s) - len(y), y.shape[1]), np.float32)])
        y[i:i + len(s)] += s
        done.append(f"{path.name} at {i / sr:.2f}s (anchor {anchor}: {r.get('phrase', r.get('at'))!r}, {gain} dB)")
        log.info("sfx %s", done[-1])
    return y, done


def master(y, sr, target, tp_max, margin):
    """gain to target LUFS, then a 4x-oversampled limiter (true-peak safe); retried until both land"""
    m = measure(y, sr)
    gain, ceiling = target - m["lufs"], tp_max - margin
    for _ in range(6):
        z = filt(y * 10 ** (gain / 20), sr, f"aresample={sr * 4},alimiter=limit={10 ** (ceiling / 20):.5f}"
                 f":attack=5:release=50:level=0,aresample={sr}")
        m = measure(z, sr)
        log.info("master: gain %+.2f dB, ceiling %.1f dBFS -> %.2f LUFS, %.2f dBTP", gain, ceiling, m["lufs"],
                 m["true_peak"])
        if m["true_peak"] <= tp_max - margin / 2 and abs(m["lufs"] - target) <= 0.3:
            return z, gain, ceiling
        if m["true_peak"] > tp_max - margin / 2:
            ceiling -= 0.5
        gain += target - m["lufs"]
    log.warning("master did not converge; using last attempt (%.2f LUFS, %.2f dBTP)", m["lufs"], m["true_peak"])
    return z, gain, ceiling


# --- config, report, main ---

def merge(base, over):
    for k, v in over.items():
        base[k] = merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return base


def load_config(markers):
    with open(HERE / "default.toml", "rb") as f:
        cfg = tomllib.load(f)
    if markers:
        try:
            with open(markers, "rb") as f:
                merge(cfg, tomllib.load(f))
        except tomllib.TOMLDecodeError as e:
            raise EnhanceError(f"{markers}: {e}") from None
    for kind, allowed in KEYS.items():
        for m in cfg.get(kind, []) if isinstance(cfg.get(kind), list) else []:
            if extra := set(m) - allowed:
                raise EnhanceError(f"[[{kind}]] unknown key(s) {sorted(extra)}; allowed: {sorted(allowed)}")
    return cfg


def fmt_m(m):
    return (f"{m['duration']:.2f} s | {m['lufs']:.1f} LUFS | true peak {m['true_peak']:.2f} dBTP | "
            f"sample peak {m['peak']:.2f} dBFS | LRA {m['lra']:.1f} LU")


def write_report(path, inp, info, before, after_wav, after_mp3, sil, words, ops):
    lines = [f"# {inp.stem}: audio report", "",
             f"Input: `{inp}` ({info['codec']}, {info['sr']} Hz, {info['ch']} ch, {info['bitrate']} bit/s)", "",
             "| | duration | integrated | true peak | sample peak | LRA |", "|---|---|---|---|---|---|"]
    for name, m in (("original", before), ("enhanced WAV", after_wav), ("enhanced MP3", after_mp3)):
        lines.append(f"| {name} | {m['duration']:.2f} s | {m['lufs']:.1f} LUFS | {m['true_peak']:.2f} dBTP "
                     f"| {m['peak']:.2f} dBFS | {m['lra']:.1f} LU |")
    lines += ["", "## Processing applied", "", *[f"{i}. {op}" for i, op in enumerate(ops, 1)], "",
              f"## Silences in the original ({len(sil)})", "", "| start | end | length |", "|---|---|---|",
              *[f"| {a:.2f} | {b:.2f} | {b - a:.2f} |" for a, b in sil]]
    if words:
        lines += ["", "## Transcript (original timeline, for markers)", ""]
        line, t0 = [], words[0]["start"]
        for w in words:
            t0 = w["start"] if t0 is None else t0
            line.append(w["text"])
            if re.search(r"[.?!]$", w["text"]):
                lines.append(f"- `{t0:6.2f}` {' '.join(line)}")
                line, t0 = [], None
        if line:
            lines.append(f"- `{t0:6.2f}` {' '.join(line)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def enhance(inp, markers=None, out_dir=None, use_sfx=True):
    inp = Path(inp).resolve()
    if not inp.is_file():
        raise EnhanceError(f"input not found: {inp}")
    if markers is None and (auto := inp.with_suffix(".toml")).is_file():
        markers = auto
    markers = Path(markers).resolve() if markers else None
    cfg = load_config(markers)
    out_dir = Path(out_dir).resolve() if out_dir else inp.parent / "output"
    base = out_dir / f"{inp.stem}_enhanced"
    wav, mp3, report = base.with_suffix(".wav"), base.with_suffix(".mp3"), base.parent / f"{base.name}_report.md"
    if inp in (wav, mp3, report):
        raise EnhanceError("output would overwrite the input; pick another --out")
    out_dir.mkdir(parents=True, exist_ok=True)

    info = probe(inp)
    sr, ch = info["sr"], info["ch"]
    log.info("input %s: %s, %d Hz, %d ch, %.2f s", inp.name, info["codec"], sr, ch, info["duration"])
    log.info("markers: %s", markers or "none (voice processing + master only)")
    x = decode(inp, sr, ch)
    before = measure(x, sr)
    log.info("original: %s", fmt_m(before))
    pc = cfg["pauses"]
    sil = silences(x, sr, pc["silence_db"], pc["min_silence_s"])
    gaps = [b - a for a, b in sil]
    if gaps:
        log.info("silences: %d, %.2f-%.2f s (median %.2f s)", len(gaps), min(gaps), max(gaps), np.median(gaps))

    pause_rules, emph_rules = list(cfg.get("pause", [])), list(cfg.get("emphasis", []))
    sfx_rules = list(cfg.get("sfx", [])) if use_sfx and cfg["sound_effects"]["enabled"] else []
    try:
        words = transcribe(inp)
        log.info("transcript: %d words", len(words))
    except EnhanceError as e:
        if any("phrase" in m for m in pause_rules + emph_rules + sfx_rules) or pc["min_sentence_pause"] > 0:
            raise
        log.warning("%s (no transcript in the report)", e)
        words = None

    ops = []
    chain = voice_chain(cfg)
    y = x
    if chain:
        y = filt(x, sr, chain)[:len(x)]
        y = np.pad(y, ((0, len(x) - len(y)), (0, 0)))
        ops.append(f"voice chain (ffmpeg): `{chain}`")

    if pc["min_sentence_pause"] > 0 and words:
        pause_rules += [{"at": nxt["start"], "seconds": pc["min_sentence_pause"]}
                        for w, nxt in zip(words, words[1:]) if re.search(r"[.?!]$", w["text"])]
    inserts = pause_plan(pause_rules, words, sil, x, sr, pc["max_pause"])
    ops += [f"pause: +{s:.2f} s silence at {t:.2f} s (original timeline)" for t, s in inserts]
    segments = []
    for m in emph_rules:
        a, b = span(m, words)
        a, b = quietest(x, sr, a - 0.02, 0.05), quietest(x, sr, b + 0.02, 0.05)  # cut where it is quiet
        fx = {k: m[k] for k in ("gain_db", "speed", "pitch_semitones", "radio") if k in m}
        segments.append((a, b, fx))
        ops.append(f"emphasis {m.get('phrase', '')!r} {a:.2f}-{b:.2f} s: {fx}")
    y, tm = assemble(y, sr, inserts, sorted(segments, key=lambda s: s[0]))

    if sfx_rules:
        dirs = [d for d in (markers.parent if markers else None, (HERE / cfg["sound_effects"]["dir"]).resolve()) if d]
        y, done = mix_sfx(y, sr, sfx_rules, words, tm, dirs, cfg["sound_effects"]["default_gain_db"])
        ops += [f"sfx: {d}" for d in done]
    elif cfg.get("sfx") and not use_sfx:
        ops.append("sfx layer skipped (--no-sfx)")

    mc = cfg["master"]
    y, gain, ceiling = master(y, sr, mc["target_lufs"], mc["true_peak_db"], mc["mp3_margin_db"])
    ops.append(f"master: gain {gain:+.2f} dB to {mc['target_lufs']} LUFS, 4x-oversampled limiter at {ceiling:.1f} dBFS")

    encode(y, sr, wav, ["-c:a", "pcm_s24le"])
    encode(y, sr, mp3, ["-c:a", "libmp3lame", "-b:a", mc["mp3_bitrate"]])
    ops.append(f"export: WAV 24-bit / MP3 {mc['mp3_bitrate']} at {sr} Hz")
    after_wav, after_mp3 = measure(y, sr), measure(decode(mp3, sr, ch), sr)
    for name, m in (("WAV", after_wav), ("MP3", after_mp3)):
        log.info("enhanced %s: %s", name, fmt_m(m))
        if m["true_peak"] > mc["true_peak_db"]:
            log.warning("%s true peak %.2f dBTP is above %.1f: raise mp3_margin_db", name, m["true_peak"],
                        mc["true_peak_db"])
    write_report(report, inp, info, before, after_wav, after_mp3, sil, words, ops)
    log.info("wrote %s\n      %s\n      %s", wav, mp3, report)
    return wav, mp3, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input")
    ap.add_argument("--markers")
    ap.add_argument("--out")
    ap.add_argument("--no-sfx", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    try:
        enhance(a.input, a.markers, a.out, not a.no_sfx)
    except EnhanceError as e:
        log.error("%s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
