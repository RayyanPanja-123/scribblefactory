"""finish: frames + audio/mix.wav (+ burned-in captions from phrases.json) -> final.mp4, then QA -> qa.json.

Captions: phrases split into chunks of <= CAP_MAX_WORDS words (never inside a name), one ASS event per word: words
stamp in as they are said (later ones drawn transparent, so the layout never moves), the newest yellow. Effects (pop, drop, shake, punch) are written as one event per video frame while
they animate: \\t restarts with every event, so it can't carry an animation across the per-word events.
Rendered by ffmpeg's subtitles filter (libass) with the vendored font only.
End screen (every part): story.json's end_card text ("Follow for more") and the handles from library/settings.json on
black, drawn by Pillow and overlaid from its start frame (just after the last word) to the end. Nothing is spoken there.
QA also records the runtime (seconds, words) and warns when it is over MAX_RUNTIME_S; that never fails the stage.
QA failure fails the stage but keeps final.mp4 for inspection.
"""

import json
import math
import random
import re
import subprocess
from pathlib import Path

from .. import ff
from .. import settings
from ..io import atomic_write_json, atomic_write_text, library_of, load_part, replace_file
from ..schemas import PhrasesModel, SeriesModel, StoryModel
from .audio import loudness
from .prep import FX_MODES, TWIST_PREFIX, _is_directive, clean_markdown, strip_directives
from .render import FPS, check_frames
from .runner import StageError
from .shots import token
from .timing import _can_break_after, _capitalised
from .validate import load_model
from ..validate import END_SCREEN_S

INPUTS = ["frames/chunks", "audio/mix.wav", "phrases.json", "story.json", "story.md"]
OUTPUTS = ["final.mp4", "qa.json"]  # + captions.ass when the series has captions on
FONTS = Path(__file__).resolve().parents[3] / "assets" / "fonts"

# --- encode ---
CRF, PRESET, AUDIO_BITRATE, AUDIO_RATE = 18, "slow", "192k", 48000

# --- captions ---
CAP_FONT = "Fredoka One"
CAP_SIZE = 90
CAP_OUTLINE = 7
CAP_SHADOW = 4
CAP_MAX_WORDS = 5
CAP_LINE_CHARS = 15        # a chunk longer than this breaks onto 2 lines (never more)
CAP_FIT_CHARS = 19         # ~chars of Fredoka One at CAP_SIZE in the caption width; longer lines shrink to fit
CAP_HOLD = 0.15            # seconds a chunk stays after its last word, never into the next chunk
CAP_BASELINE = {1920: 0.745, 1080: 0.88}  # of frame height, by height: 9:16 lower third (above the Shorts UI), 16:9 low
CAP_MARGIN_L, CAP_MARGIN_R = 0.10, 0.15   # of frame width: 75% max width, and clear of the right-hand UI (15%)
WHITE, YELLOW = "&H00FFFFFF", "&H004AD5FF"  # ASS colours are &HAABBGGRR; yellow = #ffd54a
SHADOW = "&H80000000"
RED = "&H004F5AFF"         # #ff5a4f

# --- caption effects (per video frame; seeded from story.json) ---
FX_POP = (80, 90, 100, 110, 105, 100)                     # chunk scale % per frame: 80 -> 110 -> 100
FX_DROP = (-200, -170, -120, -50, 0, -30, -36, -22, 0, -10, -6, 0)  # chunk y offset px per frame: fall, 2 bounces
FX_SHAKE_S, FX_SHAKE_PX, FX_SHAKE_DEG = 0.35, 10, 3      # twist / @fx shake: jitter, decaying to 0
FX_EMPHASIS_SHAKE_S = 0.2                                 # the short shake after a punch word
FX_SHAKE_GAP_S = 2.0                                      # auto shakes at least this far apart
FX_PUNCH = (115, 130, 126, 118, 110, 105, 102, 100)      # punch word scale % per frame
FX_PUNCH_RED_FRAMES = 4                                   # red this long, then back to yellow / white
FX_STAMP = (150, 125, 92, 104, 100)                       # each word as it is said: slams down from big, settles
EMPHASIS = {"collapsed", "chased", "furious", "banned", "poison", "rat", "nap", "cramps", "dogs", "lift", "fake",
            "joke", "gold"}

# --- QA ---
QA_FREEZE_S = 1.0
QA_FREEZE_NOISE = "-60dB"
QA_BLACK_S = 0.2
QA_DURATION_TOL = 0.1
QA_LUFS, QA_LUFS_TOL, QA_TRUE_PEAK = -14.0, 1.0, -1.0
MIN_RUNTIME_S, MAX_RUNTIME_S = 30, 35  # every part runs 30 to 35 s: warn outside that

# --- end screen (every part: silent, after the last word) ---
CARD_SIZE = 76             # headline ("Follow for more") px
HANDLE_SIZE = 50           # each handle line px
HANDLE_COLOR = (242, 193, 78, 255)  # the wipe's marker yellow
CARD_Y = 0.5               # of frame height: the text block's vertical centre (the card is black and covers the captions)
SOCIAL_NAMES = {"youtube": "YouTube", "instagram": "Instagram", "facebook": "Facebook"}
END_SCREEN_FRAMES = round(END_SCREEN_S * FPS)  # appended after the story's last frame


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


def _cs(seconds: float) -> int:
    """centiseconds, floored: a frame at n/FPS always falls in the event that starts at n/FPS"""
    return math.floor(seconds * 100 + 1e-6)


def _ts(seconds: float) -> str:
    cs = _cs(seconds)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _frame(seconds: float) -> int:
    """first video frame shown at or after this time"""
    return math.ceil(seconds * FPS - 1e-6)


# ---------------- caption effects ----------------

def fx_overrides(md: str, n_words: int) -> list[str | None]:
    """per word: the "@fx <mode>" that covers it (the line after the directive), else None.
    Words come out exactly as prep's script has them, so they index phrases.json's words."""
    lines, pending = [], None
    for line in md.replace("\r\n", "\n").split("\n"):
        if _is_directive(line):
            name, _, arg = line.strip()[1:].partition(" ")
            if name == "fx" and arg.strip() in FX_MODES:
                pending = arg.strip()
            continue
        line = TWIST_PREFIX.sub(r"\1", line)
        if pending and line.strip():  # markers on their own lines: they survive clean_markdown as tokens
            lines += [f"⟦fx:{pending}⟧", line, "⟦/fx⟧"]
            pending = None
        else:
            lines.append(line)
    modes, mode = [], None
    for tok in clean_markdown("\n".join(lines)).split():
        if tok.startswith("⟦fx:"):
            mode = tok[4:-1]
        elif tok == "⟦/fx⟧":
            mode = None
        else:
            modes.append(mode)
    if len(modes) != n_words:
        print(f"warning: story.md has {len(modes)} words, phrases.json {n_words}: @fx ignored (re-run prep/timing)")
        return [None] * n_words
    return modes


def _shake(start: int, seconds: float) -> dict:
    return {"start": start, "frames": max(1, round(seconds * FPS))}


def plan_fx(phrases: PhrasesModel, story: StoryModel, overrides: list[str | None]) -> list[dict]:
    """per chunk: {"entrance": "pop" | "drop" | None, "stamp": bool, "shakes": [{start, frames}], "punch": [word index]}.
    Auto: every word stamps in as it is said; the twist shot's first chunk drops and shakes from the low_hit cue;
    emphasis words punch with a short shake; auto shakes keep FX_SHAKE_GAP_S apart. "@fx" on a line replaces all of
    that for its chunks: drop, shake (pop + shake), pop, none (words still appear one by one, without any effect)."""
    cs = chunks(phrases)
    plan = [{"entrance": None, "stamp": True, "shakes": [], "punch": []} for _ in cs]
    by_first = {c["first"]: k for k, c in enumerate(cs)}
    forced, wanted = [], []  # (frame, chunk index, seconds)
    for k, c in enumerate(cs):
        mode = overrides[c["first"]]
        if mode:
            plan[k]["entrance"] = None if mode == "none" else "drop" if mode == "drop" else "pop"
            plan[k]["stamp"] = mode != "none"
            if mode == "shake":
                forced.append((_frame(c["start"]), k, FX_SHAKE_S))
            continue
        for i in range(c["first"], c["last"] + 1):
            if token(phrases.words[i].text) in EMPHASIS:
                plan[k]["punch"].append(i)
                wanted.append((_frame(phrases.words[i].start), k, FX_EMPHASIS_SHAKE_S))
    for shot in (s for s in story.shots if s.twist):
        k = by_first.get(phrases.phrases[shot.phrase_range[0]].word_start)
        if k is None or overrides[cs[k]["first"]]:
            continue
        plan[k]["entrance"] = "drop"
        for cue in story.cues:
            if cue.kind == "low_hit" and shot.start_frame <= cue.frame < shot.end_frame:
                forced.append((max(cue.frame, _frame(cs[k]["start"])), k, FX_SHAKE_S))
    kept = []
    for f, k, secs in sorted(forced) + sorted(wanted):  # forced ones always stay; auto ones only with room
        if (f, k, secs) in forced or all(abs(f - g) >= FX_SHAKE_GAP_S * FPS for g, _ in kept):
            kept.append((f, k))
            plan[k]["shakes"].append(_shake(f, secs))
    return plan


def fx_state(c: dict, fx: dict, n: int, seed: int) -> tuple[float, int, int, float, dict]:
    """at video frame n: chunk scale %, x / y offset px, rotation deg, {word: (scale %, red)} for stamping and punch
    words (a punch replaces the stamp; the chunk's first word doesn't stamp under a pop / drop entrance)"""
    i = max(n - _frame(c["start"]), 0)
    scale, dx, dy, rot = 100, 0, 0, 0.0
    if fx["entrance"] == "pop" and i < len(FX_POP):
        scale = FX_POP[i]
    elif fx["entrance"] == "drop" and i < len(FX_DROP):
        dy = FX_DROP[i]
    for s in fx["shakes"]:
        j = n - s["start"]
        if 0 <= j < s["frames"]:
            R, decay = random.Random(f"{seed}:shake:{s['start']}:{j}"), 1 - j / s["frames"]
            dx += round(R.uniform(-1, 1) * FX_SHAKE_PX * decay)
            dy += round(R.uniform(-1, 1) * FX_SHAKE_PX * decay)
            rot += round(R.uniform(-1, 1) * FX_SHAKE_DEG * decay, 1)
    punch = {}
    for w in _stamped(c, fx):
        j = n - _frame(c["words"][w]["start"])
        if 0 <= j < len(FX_STAMP) and FX_STAMP[j] != 100:
            punch[w] = (FX_STAMP[j], False)
    for w in fx["punch"]:
        j = n - _frame(c["words"][w]["start"])
        if 0 <= j < len(FX_PUNCH):
            punch[w] = (FX_PUNCH[j], j < FX_PUNCH_RED_FRAMES)
    return scale, dx, dy, rot, punch


def _stamped(c: dict, fx: dict) -> list[int]:
    if not fx["stamp"]:
        return []
    return [i for i in range(c["first"] + (1 if fx["entrance"] else 0), c["last"] + 1) if i not in fx["punch"]]


def _animated_frames(c: dict, fx: dict) -> set[int]:
    f0 = _frame(c["start"])
    out = set()
    for w in _stamped(c, fx):
        out |= set(range(_frame(c["words"][w]["start"]), _frame(c["words"][w]["start"]) + len(FX_STAMP)))
    if fx["entrance"]:
        out |= set(range(f0, f0 + len(FX_POP if fx["entrance"] == "pop" else FX_DROP)))
    for s in fx["shakes"]:
        out |= set(range(s["start"], s["start"] + s["frames"]))
    for w in fx["punch"]:
        out |= set(range(_frame(c["words"][w]["start"]), _frame(c["words"][w]["start"]) + len(FX_PUNCH)))
    return out


def ass(phrases: PhrasesModel, story: StoryModel, overrides: list[str | None] | None = None) -> str:
    """the libass script: per chunk, one event per word (words appear as they are said, the newest yellow), split
    into one event per video frame while an effect animates"""
    W, H = story.width, story.height
    margin_v, ml, mr = round(H * (1 - CAP_BASELINE[H])), round(CAP_MARGIN_L * W), round(CAP_MARGIN_R * W)
    base_x, base_y = ml + (W - ml - mr) // 2, H - margin_v  # where \an2 puts it
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
{CAP_SHADOW},2,{ml},{mr},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    words, events = phrases.words, []
    wd = [w.model_dump() for w in words]
    overrides = overrides or [None] * len(words)
    for c, fx in zip(chunks(phrases), plan_fx(phrases, story, overrides)):
        c = {**c, "words": wd}
        idx = list(range(c["first"], c["last"] + 1))
        texts = [caption_text(words[i].text) for i in idx]
        br = line_break(wd, idx, texts)  # one break per chunk (plain text): the layout never jumps between words
        fit = _fit([" ".join(texts)] if br is None else [" ".join(texts[:br]), " ".join(texts[br:])])
        # word k is highlighted from its start (the chunk start for the first) to the next word's start
        starts = [c["start"]] + [words[i].start for i in idx[1:]]
        cuts = {c["start"], c["end"], *(t for t in starts if c["start"] < t < c["end"])}
        for n in _animated_frames(c, fx):
            cuts |= {t for t in (n / FPS, (n + 1) / FPS) if c["start"] < t < c["end"]}
        cuts = sorted(cuts)
        for a, b in zip(cuts, cuts[1:]):
            if _cs(b) <= _cs(a):
                continue  # shorter than a centisecond: the next event takes over at once
            k = max(j for j, t in enumerate(starts) if t <= a + 1e-9)
            scale, dx, dy, rot, punch = fx_state(c, fx, _frame(a), story.seed)
            parts = []
            for j, (i, t) in enumerate(zip(idx, texts)):
                colour = YELLOW if j == k else WHITE
                if j > k:  # not said yet: invisible, but it holds its place so the line never shifts
                    parts.append(("{\\alpha&HFF&}" if j == k + 1 else "") + t)
                elif i in punch:
                    s = round(scale * punch[i][0] / 100)
                    parts.append(f"{{\\fscx{s}\\fscy{s}\\1c{RED if punch[i][1] else colour}&}}{t}"
                                 f"{{\\fscx{scale}\\fscy{scale}\\1c{WHITE}&}}")
                elif colour == YELLOW:
                    parts.append(f"{{\\1c{YELLOW}&}}{t}{{\\1c{WHITE}&}}")
                else:
                    parts.append(t)
            tags = (f"\\pos({base_x + dx},{base_y + dy})" if dx or dy else "") + (f"\\frz{rot:g}" if rot else "") \
                + (f"\\fscx{scale}\\fscy{scale}" if scale != 100 else "")
            text = fit + (f"{{{tags}}}" if tags else "") \
                + (" ".join(parts) if br is None else " ".join(parts[:br]) + "\\N" + " ".join(parts[br:]))
            events.append(f"Dialogue: 0,{_ts(a)},{_ts(b)},Caption,,0,0,0,,{text}")
    return head + "\n".join(events) + "\n"


# ---------------- end card ----------------

def end_card_png(text: str, socials: dict, out: Path, size: tuple[int, int] = (1080, 1920)) -> None:
    """the silent closing screen: black, size (width, height), the headline (text) in big white letters and, under it, one line per
    filled-in handle ("YouTube  @name"), the block centred at CARD_Y"""
    from PIL import Image, ImageDraw, ImageFont

    font = lambda size: ImageFont.truetype(str(FONTS / "FredokaOne-Regular.ttf"), size)  # noqa: E731
    lines = [(text, font(CARD_SIZE), (255, 255, 255, 255))] + [
        (f"{SOCIAL_NAMES[k]}  {v}", font(HANDLE_SIZE), HANDLE_COLOR) for k, v in socials.items() if v]
    boxes = [f.getbbox(t) for t, f, _ in lines]
    gaps = [CARD_SIZE] + [HANDLE_SIZE * 3 // 5] * (len(lines) - 2)  # a wider gap under the headline
    height = sum(y1 - y0 for _, y0, _, y1 in boxes) + sum(gaps[:len(lines) - 1])
    W, H = size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    y = round(H * CARD_Y) - height // 2
    for i, ((t, f, fill), (x0, y0, x1, y1)) in enumerate(zip(lines, boxes)):
        d.text((W // 2 - (x1 - x0) // 2 - x0, y - y0), t, font=f, fill=fill)
        y += y1 - y0 + (gaps[i] if i < len(gaps) else 0)
    img.save(out)


# ---------------- ffmpeg ----------------

def _ffmpeg(*args) -> subprocess.CompletedProcess:
    return ff.run("ffmpeg", "-hide_banner", "-nostats", *args, text=True, fail="ffmpeg failed")


def has_libass() -> bool:
    return bool(re.search(r"^\s*\S+\s+subtitles\s", _ffmpeg("-filters").stdout, re.M))


def _filter_path(p: Path) -> str:
    """a path as a quoted filtergraph option value (Windows drive colons escaped)"""
    return "'" + p.resolve().as_posix().replace(":", "\\:").replace("'", "\\'") + "'"


def subtitles_filter(captions: Path) -> str:
    return f"subtitles=filename={_filter_path(captions)}:fontsdir={_filter_path(FONTS)}"


def encode(part_dir: Path, frames: int, captions: Path | None, card: Path | None = None,
           size: tuple[int, int] = (1080, 1920)) -> None:
    """frames/%06d.png + audio/mix.wav (+ burned-in captions), then the end screen png held for END_SCREEN_FRAMES
    with silence under it -> final.mp4"""
    out, tmp = part_dir / "final.mp4", part_dir / ".final.tmp.mp4"
    total = frames + (END_SCREEN_FRAMES if card else 0)
    chain = [f"[0:v]{subtitles_filter(captions)}[c]"] if captions else []
    if card:  # both halves to one pixel format and aspect, then joined; the audio padded with silence to the end
        chain += [f"[{'c' if captions else '0:v'}]format=yuv420p,setsar=1[v0]",
                  f"[2:v]format=yuv420p,setsar=1,fps={FPS},trim=end_frame={END_SCREEN_FRAMES}[v1]",
                  "[v0][v1]concat=n=2:v=1:a=0[c]", f"[1:a]apad=whole_dur={total / FPS:.3f}[a]"]
    graph = ["-filter_complex", ";".join(chain), "-map", "[c]"] if chain else ["-map", "0:v"]
    try:
        _ffmpeg("-v", "error", "-y", "-framerate", FPS, "-i", part_dir / "frames" / "%06d.png",
                "-i", part_dir / "audio" / "mix.wav",
                *(["-loop", "1", "-framerate", FPS, "-t", f"{END_SCREEN_FRAMES / FPS:.3f}", "-i", card] if card else []),
                *graph, "-map", "[a]" if card else "1:a", "-frames:v", total, "-t", f"{total / FPS:.3f}",
                "-c:v", "libx264", "-profile:v", "high", "-preset", PRESET, "-crf", CRF, "-pix_fmt", "yuv420p",
                "-r", FPS, "-s", f"{size[0]}x{size[1]}", "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", AUDIO_RATE,
                "-movflags", "+faststart", tmp)
        replace_file(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------- QA ----------------

def probe(path: Path) -> dict:
    r = ff.run("ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "default=nw=1", path, text=True)
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


def scan(frames: Path, count: int) -> tuple[float, float]:
    """longest frozen and longest black span (seconds) in the rendered frames final.mp4 is made from: the
    caption-free picture (moving captions would hide a frozen or black picture, and no crop can dodge them
    when the only motion is a character inside the caption band)"""
    total = count / FPS
    log = _ffmpeg("-framerate", FPS, "-i", frames / "%06d.png", "-frames:v", count, "-vf",
                  f"freezedetect=n={QA_FREEZE_NOISE}:d={QA_FREEZE_S},blackdetect=d={QA_BLACK_S}",
                  "-f", "null", "-").stderr
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
    frozen, black = scan(part_dir / "frames", story.duration_frames)
    lufs, tp = loudness(final)
    cap = caption_check(phrases, chunks(phrases)) if captions_on else None
    want_n = story.duration_frames + (END_SCREEN_FRAMES if story.end_card else 0)  # the story, then the end screen
    want_s = want_n / FPS

    def check(ok, value, want):
        return {"ok": bool(ok), "value": value, "want": want}
    W, H = story.width, story.height
    checks = {
        "resolution": check(p.get("width") == str(W) and p.get("height") == str(H),
                            f"{p.get('width')}x{p.get('height')}", f"{W}x{H}"),
        "fps": check(abs(fps - FPS) < 0.01, round(fps, 3), FPS),
        "frame_count": check(p.get("nb_frames") == str(want_n), int(p.get("nb_frames", 0)), want_n),
        "duration": check(abs(duration - want_s) <= QA_DURATION_TOL, round(duration, 3),
                          f"{want_s:.3f} +/-{QA_DURATION_TOL}"),
        "frozen": check(frozen <= QA_FREEZE_S, frozen, f"<= {QA_FREEZE_S} s"),
        "black": check(black <= QA_BLACK_S, black, f"<= {QA_BLACK_S} s"),
        "loudness": check(abs(lufs - QA_LUFS) <= QA_LUFS_TOL, lufs, f"{QA_LUFS} +/-{QA_LUFS_TOL} LUFS"),
        "true_peak": check(tp <= QA_TRUE_PEAK, tp, f"<= {QA_TRUE_PEAK} dBTP"),
        "captions": check(cap is None, cap or ("ok" if captions_on else "off"), "every word once, no overlaps"),
    }
    return {"ok": all(c["ok"] for c in checks.values()), "checks": checks,
            **runtime(duration, len(phrases.words), phrases.words[-1].end)}


def runtime(seconds: float, words: int, speech: float) -> dict:
    """qa.json's runtime record (check-story measures words per second from it) and the length warning (outside
    MIN_RUNTIME_S..MAX_RUNTIME_S)"""
    over, under = round(seconds - MAX_RUNTIME_S, 1), round(MIN_RUNTIME_S - seconds, 1)
    per = words / speech if speech else 0
    warn = [f"runtime {seconds:.1f} s is {over} s over {MAX_RUNTIME_S} s ({words} words): cut about "
            f"{math.ceil(over * per)} words"] if over > 0 else [
           f"runtime {seconds:.1f} s is {under} s under {MIN_RUNTIME_S} s ({words} words): add about "
           f"{math.ceil(under * per)} words"] if under > 0 else []
    return {"runtime": {"seconds": round(seconds, 3), "words": words, "speech_seconds": speech}, "warnings": warn}


# ---------------- upload.md (the user's to edit: created once, never overwritten) ----------------

HASHTAGS = "#shorts #stickman #history"


def first_sentence(text: str) -> str:
    text = " ".join(text.split())
    m = re.match(r".*?(?<!\.)[.!?](?!\.)(?=\s|$)", text)  # an ellipsis doesn't end the sentence
    return m.group(0) if m else text


def upload_text(series: SeriesModel, number: int, script: str) -> str:
    title = f"{series.title} — Part {number}"
    body = f"Title: {title}\n\n{first_sentence(script)} Part {number} of {len(series.parts)}.\n\n{HASHTAGS}\n"
    return f"# {title}\n\n## YouTube\n\n{body}\n## Instagram\n\n{body}"


def write_upload_md(part_dir: Path) -> None:
    upload, script = part_dir / "upload.md", part_dir / "story.md"  # story.md: the narration as written, not respelled
    if upload.exists():
        print("upload.md exists, kept")
        return
    if not script.exists():
        print("upload.md: no story.md to write it from, skipped")
        return
    series = load_model(part_dir.parent / "series.json", SeriesModel)
    number = int(part_dir.name.removeprefix("part-"))
    atomic_write_text(upload, upload_text(series, number, clean_markdown(strip_directives(script.read_text(encoding="utf-8")))))
    print("upload.md written")


# ---------------- entry ----------------

def check_gate(part_dir: Path) -> None:
    stages = load_part(part_dir / "part.json").stages
    waiting = [n for n in ("render", "audio") if getattr(stages, n).status != "done"]
    if waiting:
        slug, part = part_dir.parent.name, part_dir.name
        raise StageError(f"{' and '.join(waiting)} not done yet: "
                         + "; ".join(f"render {slug} {part}" if n == "render" else f"run {slug} {part} --stage audio"
                                     for n in waiting))


def extra_inputs(part_dir: Path) -> dict:
    """the only series.json field finish uses (hashed instead of the whole file: approvals, new parts don't count), and
    the end screen's handles (library/settings.json: a changed handle re-runs finish, nothing else)"""
    f = part_dir.parent / "series.json"
    return {"captions": json.loads(f.read_bytes()).get("style", {}).get("captions", True) if f.exists() else None,
            "socials": settings.load(library_of(part_dir))["socials"]}


def run(part_dir: Path) -> None:
    check_gate(part_dir)
    story = load_model(part_dir / "story.json", StoryModel)
    phrases = load_model(part_dir / "phrases.json", PhrasesModel)
    captions_on = load_model(part_dir.parent / "series.json", SeriesModel).style.captions
    md = part_dir / "story.md"
    overrides = fx_overrides(md.read_text(encoding="utf-8"), len(phrases.words)) if md.exists() else None
    check_frames(part_dir / "frames", 0, story.duration_frames)
    if not (part_dir / "audio" / "mix.wav").exists():
        raise StageError("audio/mix.wav not found: run --stage audio")

    captions = part_dir / "captions.ass"
    if captions_on:
        if not has_libass():
            raise StageError("this ffmpeg has no libass (subtitles filter): install a build with --enable-libass")
        atomic_write_text(captions, ass(phrases, story, overrides))
    else:
        captions.unlink(missing_ok=True)  # stale from when captions were on
    print(f"captions: {'on' if captions_on else 'off'}")
    card = part_dir / "end-card.png"
    if story.end_card:
        socials = settings.load(library_of(part_dir))["socials"]
        end_card_png(story.end_card.text, socials, card, (story.width, story.height))
        handles = ", ".join(v for v in socials.values() if v) or "no handles set (Settings)"
        print(f"end screen: {story.end_card.text} ({handles})")
    else:
        card.unlink(missing_ok=True)
        print("end screen: none")
    encode(part_dir, story.duration_frames, captions if captions_on else None, card if story.end_card else None,
           (story.width, story.height))

    report = qa(part_dir, story, phrases, captions_on)
    atomic_write_json(part_dir / "qa.json", report)
    for name, c in report["checks"].items():
        print(f"  {'ok  ' if c['ok'] else 'FAIL'} {name}: {c['value']} (want {c['want']})")
    if not report["ok"]:
        failed = [n for n, c in report["checks"].items() if not c["ok"]]
        raise StageError(f"QA failed: {', '.join(failed)} (final.mp4 kept for inspection; see qa.json)")
    for w in report["warnings"]:
        print(f"warning: {w}")
    print(f"final: {part_dir / 'final.mp4'}")
    write_upload_md(part_dir)
