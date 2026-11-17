"""finish: frames + audio/mix.wav (+ burned-in captions from phrases.json) -> final.mp4, then QA -> qa.json.

Captions: phrases split into chunks of <= CAP_MAX_WORDS words (never inside a name), one ASS event per word so
the word being spoken is yellow. Rendered by ffmpeg's subtitles filter (libass) with the vendored font only.
QA failure fails the stage but keeps final.mp4 for inspection.
"""

import math
import re
import shutil
import subprocess
from pathlib import Path

from ..io import atomic_write_json, atomic_write_text, load_part, replace_file
from ..schemas import PhrasesModel, SeriesModel, StoryModel
from .audio import loudness
from .import_check import probe_duration
from .render import FPS, check_frames
from .runner import StageError
from .timing import _can_break_after, _capitalised
from .validate import load_model

INPUTS = ["frames/chunks", "audio/mix.wav", "phrases.json", "../series.json"]
OUTPUTS = ["final.mp4", "qa.json"]  # + captions.ass when the series has captions on
FONTS = Path(__file__).resolve().parents[3] / "assets" / "fonts"

# --- encode ---
CRF, PRESET, AUDIO_BITRATE, AUDIO_RATE = 18, "slow", "192k", 48000

# --- captions ---
W, H = 1080, 1920
CAP_FONT = "Fredoka One"
CAP_SIZE = 72
CAP_OUTLINE = 6
CAP_SHADOW = 3
CAP_MAX_WORDS = 5
CAP_LINE_CHARS = 18        # a chunk longer than this breaks onto 2 lines (never more)
CAP_FIT_CHARS = 24         # ~chars of Fredoka One at CAP_SIZE in the caption width; longer lines shrink to fit
CAP_HOLD = 0.15            # seconds a chunk stays after its last word, never into the next chunk
CAP_BASELINE = 0.68        # of frame height
CAP_MARGIN_L = round(0.10 * W)  # 80% max width, and clear of the right-hand UI (15%)
CAP_MARGIN_R = round(0.15 * W)
WHITE, YELLOW = "&H00FFFFFF", "&H004AD5FF"  # ASS colours are &HAABBGGRR; yellow = #ffd54a
SHADOW = "&H80000000"

# --- QA ---
QA_FREEZE_S = 1.0
QA_FREEZE_NOISE = "-60dB"
QA_BLACK_S = 0.2
QA_SCAN_CROP = 0.55        # freeze / black scan the top 55% of the frame, above the captions (they'd mask both)
QA_DURATION_TOL = 0.1
QA_LUFS, QA_LUFS_TOL, QA_TRUE_PEAK = -14.0, 1.0, -1.0


# ---------------- captions ----------------

def caption_text(word: str) -> str:
    """trailing commas and periods dropped ("..." kept); ASS override characters removed"""
    if not (word.endswith("...") or word.endswith("…")):
        word = word.rstrip(",.")
    return re.sub(r"[{}\\]", "", word)


def _splits_name(words, i) -> bool:
    return _capitalised(words[i]["text"]) and _capitalised(words[i + 1]["text"])


def chunk_words(words: list[dict], a: int, b: int) -> list[tuple[int, int]]:
    """split words a..b (inclusive) into balanced chunks of <= CAP_MAX_WORDS. A cut never goes inside a name and
    avoids going right after an article/preposition (the timing stage's rules); a name too long to fit gets
    cut at the limit."""
    out = []
    while b - a + 1 > CAP_MAX_WORDS:
        left = b - a + 1
        target = a + math.ceil(left / math.ceil(left / CAP_MAX_WORDS)) - 1  # last word of an even share
        window = range(a, a + CAP_MAX_WORDS)                                  # cuts that keep the chunk <= max
        for ok in (lambda i: _can_break_after(words, i), lambda i: not _splits_name(words, i), lambda i: True):
            cuts = [i for i in window if ok(i)]
            if cuts:
                cut = min(cuts, key=lambda i: (abs(i - target), -i))
                break
        out.append((a, cut))
        a = cut + 1
    out.append((a, b))
    return out


def chunks(phrases: PhrasesModel) -> list[dict]:
    """caption chunks: {first, last (word indices), start, end}; end = last word end + hold, cut at the next start"""
    words = [w.model_dump() for w in phrases.words]
    spans = [c for p in phrases.phrases for c in chunk_words(words, p.word_start, p.word_end)]
    out = []
    for k, (a, b) in enumerate(spans):
        end = words[b]["end"] + CAP_HOLD
        if k + 1 < len(spans):
            end = min(end, words[spans[k + 1][0]]["start"])
        out.append({"first": a, "last": b, "start": words[a]["start"], "end": max(end, words[b]["end"])})
    return out


def line_break(words: list[dict], idx: list[int], texts: list[str]) -> int | None:
    """index (into idx) of the word that starts line 2, or None when the chunk fits one line; max 2 lines.
    Same rules as chunk cuts (no name split, not after an article), then the most even split."""
    if len(" ".join(texts)) <= CAP_LINE_CHARS or len(texts) < 2:
        return None
    even = lambda k: abs(len(" ".join(texts[:k])) - len(" ".join(texts[k:])))  # noqa: E731
    for ok in (lambda i: _can_break_after(words, i), lambda i: not _splits_name(words, i), lambda i: True):
        ks = [k for k in range(1, len(idx)) if ok(idx[k - 1])]
        if ks:
            return min(ks, key=even)


def _fit(lines: list[str]) -> str:
    """font-size override shrinking a line longer than CAP_FIT_CHARS to fit the caption width, else ''"""
    longest = max(map(len, lines))
    return f"{{\\fs{CAP_SIZE * CAP_FIT_CHARS // longest}}}" if longest > CAP_FIT_CHARS else ""


def _ts(seconds: float) -> str:
    cs = round(seconds * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def ass(phrases: PhrasesModel) -> str:
    """the libass script: per chunk, one event per word, that word in yellow until the next word starts"""
    margin_v = round(H * (1 - CAP_BASELINE))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, \
MarginV, Encoding
Style: Caption,{CAP_FONT},{CAP_SIZE},{WHITE},{WHITE},&H00000000,{SHADOW},0,0,0,0,100,100,0,0,1,{CAP_OUTLINE},\
{CAP_SHADOW},2,{CAP_MARGIN_L},{CAP_MARGIN_R},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    words, events = phrases.words, []
    wd = [w.model_dump() for w in words]
    for c in chunks(phrases):
        idx = list(range(c["first"], c["last"] + 1))
        texts = [caption_text(words[i].text) for i in idx]
        br = line_break(wd, idx, texts)  # one break per chunk (plain text): the layout never jumps between words
        fit = _fit([" ".join(texts)] if br is None else [" ".join(texts[:br]), " ".join(texts[br:])])
        for k, i in enumerate(idx):
            t0 = c["start"] if k == 0 else words[i].start
            t1 = c["end"] if k == len(idx) - 1 else words[idx[k + 1]].start
            if round(t1 * 100) <= round(t0 * 100) and k < len(idx) - 1:
                continue  # zero-length at centisecond precision: the next word takes over at once
            hl = [f"{{\\1c{YELLOW}&}}{t}{{\\1c{WHITE}&}}" if j == k else t for j, t in enumerate(texts)]
            text = fit + (" ".join(hl) if br is None else " ".join(hl[:br]) + "\\N" + " ".join(hl[br:]))
            events.append(f"Dialogue: 0,{_ts(t0)},{_ts(t1)},Caption,,0,0,0,,{text}")
    return head + "\n".join(events) + "\n"


# ---------------- ffmpeg ----------------

def _ffmpeg(*args) -> subprocess.CompletedProcess:
    if not shutil.which("ffmpeg"):
        raise StageError("ffmpeg not found on PATH")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise StageError(f"ffmpeg failed: {r.stderr.strip()[-400:]}")
    return r


def has_libass() -> bool:
    return bool(re.search(r"^\s*\S+\s+subtitles\s", _ffmpeg("-filters").stdout, re.M))


def _filter_path(p: Path) -> str:
    """a path as a quoted filtergraph option value (Windows drive colons escaped)"""
    return "'" + p.resolve().as_posix().replace(":", "\\:").replace("'", "\\'") + "'"


def subtitles_filter(captions: Path) -> str:
    return f"subtitles=filename={_filter_path(captions)}:fontsdir={_filter_path(FONTS)}"


def encode(part_dir: Path, frames: int, captions: Path | None) -> None:
    """frames/%06d.png + audio/mix.wav (+ burned-in captions) -> final.mp4, atomically"""
    out, tmp = part_dir / "final.mp4", part_dir / ".final.tmp.mp4"
    vf = ["-vf", subtitles_filter(captions)] if captions else []
    try:
        _ffmpeg("-v", "error", "-y", "-framerate", FPS, "-i", part_dir / "frames" / "%06d.png",
                "-i", part_dir / "audio" / "mix.wav", "-map", "0:v", "-map", "1:a", "-frames:v", frames,
                "-t", f"{frames / FPS:.3f}", *vf,
                "-c:v", "libx264", "-profile:v", "high", "-preset", PRESET, "-crf", CRF, "-pix_fmt", "yuv420p",
                "-r", FPS, "-s", f"{W}x{H}", "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", AUDIO_RATE,
                "-movflags", "+faststart", tmp)
        replace_file(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------- QA ----------------

def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "default=nw=1",
                        str(path)], capture_output=True, text=True)
    return dict(line.split("=", 1) for line in r.stdout.split() if "=" in line)


def _spans(log: str, kind: str, total: float) -> list[tuple[float, float]]:
    """(start, end) of freeze / black spans from freezedetect / blackdetect logs; open spans run to the end"""
    if kind == "freeze":
        starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", log)]
        ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", log)]
    else:
        pairs = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)
        starts, ends = [float(a) for a, _ in pairs], [float(b) for _, b in pairs]
    return list(zip(starts, ends + [total] * (len(starts) - len(ends))))


def scan(path: Path, total: float) -> tuple[float, float]:
    """longest frozen and longest black span (seconds), scanning the frame above the captions"""
    log = _ffmpeg("-i", path, "-map", "0:v", "-vf",
                  f"crop=iw:ih*{QA_SCAN_CROP}:0:0,freezedetect=n={QA_FREEZE_NOISE}:d={QA_FREEZE_S},"
                  f"blackdetect=d={QA_BLACK_S}", "-f", "null", "-").stderr
    longest = lambda spans: round(max([b - a for a, b in spans], default=0.0), 3)  # noqa: E731
    return longest(_spans(log, "freeze", total)), longest(_spans(log, "black", total))


def caption_check(phrases: PhrasesModel, cs: list[dict]) -> str | None:
    """None if every word is in exactly one chunk, chunks don't overlap and hold <= CAP_MAX_WORDS; else why"""
    seen = [i for c in cs for i in range(c["first"], c["last"] + 1)]
    if seen != list(range(len(phrases.words))):
        return "words not covered exactly once, in order"
    if any(c["last"] - c["first"] + 1 > CAP_MAX_WORDS for c in cs):
        return f"a chunk has more than {CAP_MAX_WORDS} words"
    if any(a["end"] > b["start"] for a, b in zip(cs, cs[1:])):
        return "chunks overlap"
    return None


def qa(part_dir: Path, story: StoryModel, phrases: PhrasesModel, captions_on: bool) -> dict:
    final = part_dir / "final.mp4"
    p = probe(final)
    num, den = (p.get("r_frame_rate") or "0/1").split("/")
    fps, duration = float(num) / float(den), float(p.get("duration", 0))
    voice = probe_duration(part_dir / "voice.mp3")
    frozen, black = scan(final, duration)
    lufs, tp = loudness(final)
    cap = caption_check(phrases, chunks(phrases)) if captions_on else None

    def check(ok, value, want):
        return {"ok": bool(ok), "value": value, "want": want}
    checks = {
        "resolution": check(p.get("width") == str(W) and p.get("height") == str(H),
                            f"{p.get('width')}x{p.get('height')}", f"{W}x{H}"),
        "fps": check(abs(fps - FPS) < 0.01, round(fps, 3), FPS),
        "frame_count": check(p.get("nb_frames") == str(story.duration_frames), int(p.get("nb_frames", 0)),
                             story.duration_frames),
        "duration": check(abs(duration - voice) <= QA_DURATION_TOL, round(duration, 3),
                          f"{voice:.3f} +/-{QA_DURATION_TOL}"),
        "frozen": check(frozen <= QA_FREEZE_S, frozen, f"<= {QA_FREEZE_S} s"),
        "black": check(black <= QA_BLACK_S, black, f"<= {QA_BLACK_S} s"),
        "loudness": check(abs(lufs - QA_LUFS) <= QA_LUFS_TOL, lufs, f"{QA_LUFS} +/-{QA_LUFS_TOL} LUFS"),
        "true_peak": check(tp <= QA_TRUE_PEAK, tp, f"<= {QA_TRUE_PEAK} dBTP"),
        "captions": check(cap is None, cap or ("ok" if captions_on else "off"), "every word once, no overlaps"),
    }
    return {"ok": all(c["ok"] for c in checks.values()), "checks": checks}


# ---------------- entry ----------------

def check_gate(part_dir: Path) -> None:
    stages = load_part(part_dir / "part.json").stages
    waiting = [n for n in ("render", "audio") if getattr(stages, n).status != "done"]
    if waiting:
        slug, part = part_dir.parent.name, part_dir.name
        raise StageError(f"{' and '.join(waiting)} not done yet: "
                         + "; ".join(f"render {slug} {part}" if n == "render" else f"run {slug} {part} --stage audio"
                                     for n in waiting))


def run(part_dir: Path) -> None:
    check_gate(part_dir)
    story = load_model(part_dir / "story.json", StoryModel)
    phrases = load_model(part_dir / "phrases.json", PhrasesModel)
    captions_on = load_model(part_dir.parent / "series.json", SeriesModel).style.captions
    check_frames(part_dir / "frames", 0, story.duration_frames)
    if not (part_dir / "audio" / "mix.wav").exists():
        raise StageError("audio/mix.wav not found: run --stage audio")

    captions = part_dir / "captions.ass"
    if captions_on:
        if not has_libass():
            raise StageError("this ffmpeg has no libass (subtitles filter): install a build with --enable-libass")
        atomic_write_text(captions, ass(phrases))
    else:
        captions.unlink(missing_ok=True)  # stale from when captions were on
    print(f"captions: {'on' if captions_on else 'off'}")
    encode(part_dir, story.duration_frames, captions if captions_on else None)

    report = qa(part_dir, story, phrases, captions_on)
    atomic_write_json(part_dir / "qa.json", report)
    for name, c in report["checks"].items():
        print(f"  {'ok  ' if c['ok'] else 'FAIL'} {name}: {c['value']} (want {c['want']})")
    if not report["ok"]:
        failed = [n for n, c in report["checks"].items() if not c["ok"]]
        raise StageError(f"QA failed: {', '.join(failed)} (final.mp4 kept for inspection; see qa.json)")
    print(f"final: {part_dir / 'final.mp4'}")
