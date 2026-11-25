"""Sound effects: library/sfx/ (audio files) + library/sfx/sfx.json (registry), the @sfx directive, rule-based
suggestions and the ffmpeg mix of the sfx under the voice.

  @sfx <id> [volume 0-1]   alone on its line, before the narration line it belongs to (next to @do / @fx is fine)
  anchor start:        plays at that line's start
  anchor end_on_line:  ends exactly at that line's start (pre-roll: risers)
  anchor after_line:   plays once the line has been said (its last word ends)

A registry entry whose file is missing is a warning, never a crash: that sound is left out of the mix.
"""

import json
import re
import shutil
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator

from . import ff
from .io import all_parts, atomic_write_json, library_of, storage_root
from .schemas import Strict
from .stages.prep import TWIST_PREFIX, clean_markdown, spoken
from .stages.runner import StageError

SfxId = Annotated[str, Field(pattern=r"^[a-z0-9]+([_-][a-z0-9]+)*$", max_length=60)]
MAX_PER_PART = 5
MIN_GAP_S = 1.5          # suggestions: never two sfx starting closer than this
GUESS_S = 2.0            # length assumed for a sound whose file is missing (suggestion spacing only)
PEAK_UNDER_VOICE = 0.7   # a sound at volume 1 peaks at this fraction of the voice's peak
AUDIO_TYPES = {".mp3", ".wav", ".ogg", ".m4a"}
SEED = [  # (id, file, purpose, anchor)
    ("fahhh", "FAHHH.mp3", "attention grab", "after_line"),
    ("camera_flash", "Camera Flash.mp3", "smooth transition", "start"),
    ("metallic_riser", "Metallic Riser.mp3", "tension before reveal", "end_on_line"),
    ("right", "Right.mp3", "correct / positive feedback", "start"),
    ("wrong", "Wrong.mp3", "wrong / negative feedback", "start"),
    ("vine_boom", "Vine Boom.mp3", "comedy timing, reaction", "start"),
    ("bass_impact", "Bass Impact.mp3", "hype, weight before main reveal", "start"),
    ("core", "Core.mp3", "statement, emphasis", "start"),
    ("among_us", "Among Us.mp3", "unexpected reveal", "start"),
    ("riser", "Riser.mp3", "suspense before payoff", "end_on_line"),
    ("pop", "Pop.mp3", "pop-up text / UI", "start"),
    ("click", "Click.mp3", "UI elements", "start"),
    ("glitch", "Glitch.mp3", "transition between clips", "start"),
    ("money", "Money.mp3", "money / financial moments", "start"),
]


class SfxEntry(Strict):
    id: SfxId = Field(description="the name used in @sfx")
    file: str = Field(min_length=1, max_length=120, description="file name inside library/sfx/")
    name: str = Field(min_length=1, max_length=60)
    purpose: str = Field(default="", max_length=200, description="when to use it (shown to the story AI)")
    tags: list[str] = []
    anchor: Literal["start", "end_on_line", "after_line"] = "start"
    default_volume: float = Field(default=0.8, ge=0, le=1)

    @field_validator("file")
    @classmethod
    def _plain_name(cls, v):
        if Path(v).name != v or v.startswith("."):
            raise ValueError("a plain file name inside library/sfx/")
        return v


class SfxLibrary(Strict):
    schema_version: Literal[1] = 1
    sfx: list[SfxEntry] = []

    @field_validator("sfx")
    @classmethod
    def _unique(cls, v):
        ids = [x.id for x in v]
        if dupes := sorted({i for i in ids if ids.count(i) > 1}):
            raise ValueError(f"duplicate sfx ids: {', '.join(dupes)}")
        return v


def sfx_dir(library) -> Path:
    return Path(library) / "sfx"


def load_sfx(library) -> SfxLibrary:
    """library/sfx/sfx.json; none yet: the seed list (the first save writes it)"""
    f = sfx_dir(library) / "sfx.json"
    if f.is_file():
        return SfxLibrary.model_validate_json(f.read_bytes())
    return SfxLibrary(sfx=[SfxEntry(id=i, file=f, name=f.rsplit(".", 1)[0], purpose=p, anchor=a)
                           for i, f, p, a in SEED])


def save_sfx(library, lib: SfxLibrary) -> None:
    sfx_dir(library).mkdir(parents=True, exist_ok=True)
    atomic_write_json(sfx_dir(library) / "sfx.json", lib.model_dump(mode="json"))


def by_id(library) -> dict[str, SfxEntry]:
    return {x.id: x for x in load_sfx(library).sfx}


def missing_files(library) -> list[str]:
    """one warning per registry entry whose audio file is not in library/sfx/"""
    return [f"sfx {x.id}: {x.file} is missing from library/sfx/ (left out of the mix)"
            for x in load_sfx(library).sfx if not (sfx_dir(library) / x.file).is_file()]


def sfx_users(library, sfx_id: str) -> list[str]:
    """"<slug>/<part>" of every story.md with an @sfx of this id"""
    return [name for name, pdir in all_parts(library) if (f := pdir / "story.md").is_file()
            and any(d[1] == sfx_id for d in directives(f.read_text(encoding="utf-8")))]


# ---------------- the directive ----------------

def parse_sfx(arg: str, line: int, ids=None) -> tuple[str, float | None]:
    """@sfx <id> [volume 0-1] -> (id, volume or None for the entry's default). ids: the registry's ids, or None
    for the syntax only. Errors name the story.md line."""
    words = arg.split()
    vol = None
    if len(words) == 2:
        try:
            vol = float(words[1])
        except ValueError:
            vol = -1.0
    if not 1 <= len(words) <= 2 or vol is not None and not 0 <= vol <= 1:
        raise StageError(f'story.md line {line}: @sfx: expected "@sfx <id> [volume 0-1]", e.g. "@sfx riser 0.6"')
    if ids is not None and words[0] not in ids:
        raise StageError(f"story.md line {line}: @sfx: unknown sound {words[0]!r} (sounds: {', '.join(ids) or 'none'})")
    return words[0], vol


def _narration(line: str) -> bool:
    return not line.lstrip().startswith("@") and bool(clean_markdown(spoken(line)))


def directives(md: str) -> list[tuple[int, str, float | None, int | None]]:
    """(story.md line of the @sfx, id, volume, line of the narration it belongs to or None) for every well-formed
    @sfx (bad ones are check-story's to report)"""
    out, pending = [], []
    for no, line in enumerate(md.replace("\r\n", "\n").split("\n"), 1):
        s = line.strip()
        if s.startswith("@"):
            name, _, arg = s[1:].partition(" ")
            if name == "sfx":
                try:
                    pending.append((no, *parse_sfx(arg, no)))
                except StageError:
                    pass
        elif _narration(line):
            out += [(a, i, v, no) for a, i, v in pending]
            pending = []
    return out + [(a, i, v, None) for a, i, v in pending]


def line_words(md: str) -> dict[int, tuple[int, int]]:
    """story.md line number -> indices of its first and last script word (as prep's script / phrases.json count
    them)"""
    lines = md.replace("\r\n", "\n").split("\n")
    marked = [ln if ln.lstrip().startswith("@") else f"{spoken(ln)} ⟦L{no}⟧"
              for no, ln in enumerate(lines, 1)]
    marked = [ln for ln in marked if not ln.lstrip().startswith("@")]
    out, n, since = {}, 0, 0
    for tok in clean_markdown("\n".join(marked)).split():
        if m := re.fullmatch(r"⟦L([0-9]+)⟧", tok):
            if since:
                out[int(m[1])] = (n - since, n - 1)
            since = 0
        else:
            n, since = n + 1, since + 1
    return out


def line_times(md: str, words: list) -> dict[int, tuple[float, float]] | None:
    """story.md line -> (start of its first word, end of its last word) in seconds on voice-tight.wav; None when
    phrases.json is out of date"""
    first = line_words(md)
    total = len(clean_markdown("\n".join(spoken(ln) for ln in md.replace("\r\n", "\n").split("\n")
                                         if not ln.lstrip().startswith("@"))).split())
    if total != len(words):
        return None
    t = lambda w, k: w[k] if isinstance(w, dict) else getattr(w, k)  # noqa: E731
    return {no: (t(words[a], "start"), t(words[b], "end")) for no, (a, b) in first.items()}


def estimated_times(md: str, wps: float = 2.6) -> dict[int, tuple[float, float]]:
    """line (start, end) from the word count alone (no voice yet)"""
    return {no: (round(a / wps, 2), round((b + 1) / wps, 2)) for no, (a, b) in line_words(md).items()}


def play_at(anchor: str, line: tuple[float, float], duration: float) -> tuple[float, float]:
    """(delay, trim) in seconds: where the sound starts on the track and how much of its head is cut off.
    line: its (start, end). start: at the line start. end_on_line: ends at the line start; a pre-roll before 0 s
    loses its head. after_line: once the line's last word ends."""
    at = {"start": line[0], "after_line": line[1]}.get(anchor, line[0] - duration)
    return (round(at, 3), 0.0) if at >= 0 else (0.0, round(-at, 3))


# ---------------- suggestions ----------------

MONEY = re.compile(r"\b(money|coins?|gold|golden|price[sd]?|cash|dollars?|francs?|pounds?|euros?|paid|pay|pays|"
                   r"rich|fortune|bribed?|treasure|cost|costs|sold|bought|wealth)\b", re.I)
BETRAYAL = re.compile(r"\b(impostor|imposter|traitor|spy|fake|secretly|liar|lied|betray\w*|disguised?)\b", re.I)


def clip_seconds(library, entry) -> float:
    f = sfx_dir(library) / entry.file
    if not f.is_file() or not shutil.which("ffprobe"):
        return GUESS_S
    seconds = ff.duration(f)
    return GUESS_S if seconds is None else seconds


def suggest(md: str, entries: dict, times: dict[int, tuple[float, float]], first_part: bool = False, rejected=(),
            duration=lambda e: GUESS_S) -> list[dict]:
    """rule-based @sfx suggestions where the script has none: [{line, text, id, reason, at}] (line: the narration
    line to put "@sfx <id>" above; at: when the sound starts). Never more than MAX_PER_PART with the written ones,
    never two starting within MIN_GAP_S. rejected: "<id>|<line text>" keys the user turned down."""
    lines = md.replace("\r\n", "\n").split("\n")
    written = directives(md)
    has_sfx = {n for *_x, n in written if n}
    def begins(i, no):  # when the sound starts (before 0 s for a pre-roll that loses its head)
        delay, trim = play_at(entries[i].anchor, times.get(no, (0.0, 0.0)), duration(entries[i]))
        return delay - trim
    taken = [begins(i, n) for _a, i, _v, n in written if n and i in entries]
    count = len(written)

    ideas, first, prev_set, pending = [], None, None, []  # (priority, line, id, reason)
    flips = 0
    for no, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("@"):
            name, _, arg = s[1:].partition(" ")
            if name == "set":
                if prev_set is not None and arg.strip() != prev_set:
                    pending.append((3, ("camera_flash", "glitch")[flips % 2], "scene change (@set)"))
                    flips += 1
                prev_set = arg.strip()
            elif name == "fx" and arg.split()[:1] == ["lightning"]:
                pending.append((2, "bass_impact", "lightning strike"))
            continue
        if not _narration(line):
            continue
        first = first or no
        for p, i, why in pending:
            ideas.append((p, no, i, why))
        pending = []
        if TWIST_PREFIX.match(line):
            ideas.append((0, no, "riser", "suspense before the twist"))
            ideas.append((0, no, "among_us" if BETRAYAL.search(line) else "bass_impact", "the twist lands"))
        if MONEY.search(line):
            ideas.append((4, no, "money", f"money moment ({MONEY.search(line)[0].lower()})"))
    if first_part and first and first not in has_sfx:
        ideas.append((1, first, "fahhh", "hook on the first line"))

    out = []
    for _p, no, i, why in sorted(ideas, key=lambda x: (x[0], x[1])):
        text = lines[no - 1].strip()
        if i not in entries or no in has_sfx or f"{i}|{text}" in rejected or count >= MAX_PER_PART \
                or any(x["line"] == no and x["id"] == i for x in out):
            continue
        at = begins(i, no)
        if any(abs(at - t) < MIN_GAP_S for t in taken):
            continue
        taken.append(at)
        count += 1
        out.append({"line": no, "text": text, "id": i, "reason": why, "at": round(max(at, 0.0), 2)})
    return sorted(out, key=lambda x: (x["line"], x["at"]))


def insert(md: str, line: int, text: str, sfx_id: str) -> str:
    """story.md with "@sfx <id>" put directly above narration line `line`, which must still read `text`"""
    lines = md.replace("\r\n", "\n").split("\n")
    if not 1 <= line <= len(lines) or lines[line - 1].strip() != text.strip():
        raise ValueError(f"story.md line {line} changed since the suggestion: check again")
    return "\n".join([*lines[:line - 1], f"@sfx {sfx_id}", *lines[line - 1:]])


# ---------------- mixing ----------------

def mix_cmd(clips: list[dict], voice: Path, out: Path) -> list[str]:
    """ffmpeg argv: every clip {path, delay, trim, gain} placed on one track, ducked under the voice (sidechain:
    the voice squeezes the sfx while it speaks), written as 48 kHz stereo float WAV at out (the sfx alone)"""
    fmt = "aformat=sample_rates=48000:channel_layouts=stereo"
    chains = []
    for k, c in enumerate(clips, 1):
        ms = round(c["delay"] * 1000)
        trim = f"atrim=start={c['trim']:.3f}," if c["trim"] else ""
        chains.append(f"[{k}:a]{trim}asetpts=PTS-STARTPTS,{fmt},volume={c['gain']:.4f},adelay={ms}|{ms}[s{k}]")
    labels = "".join(f"[s{k}]" for k in range(1, len(clips) + 1))
    chains.append(f"{labels}amix=inputs={len(clips)}:normalize=0:duration=longest[sfx]" if len(clips) > 1
                  else "[s1]anull[sfx]")
    chains.append(f"[0:a]{fmt}[key]")
    chains.append("[sfx][key]sidechaincompress=threshold=0.05:ratio=4:attack=5:release=250[out]")
    inputs = [x for c in clips for x in ("-i", str(c["path"]))]
    return ["ffmpeg", "-hide_banner", "-nostats", "-v", "error", "-y", "-i", str(voice), *inputs,
            "-filter_complex", ";".join(chains), "-map", "[out]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le",
            str(out)]


def clips(part_dir: Path, voice_peak: float) -> list[dict]:
    """the part's @sfx as mix_cmd clips, timed from phrases.json; missing files and stale timing are warnings"""
    from .stages.audio import decode  # numpy: only when mixing
    md_f, ph_f = part_dir / "story.md", part_dir / "phrases.json"
    if not md_f.is_file() or not ph_f.is_file():
        return []
    md = md_f.read_text(encoding="utf-8")
    found = [d for d in directives(md) if d[3]]
    if not found:
        return []
    times = line_times(md, json.loads(ph_f.read_bytes())["words"])
    if times is None:
        print("warning: story.md and phrases.json disagree on the words: @sfx left out (re-run prep/timing)")
        return []
    library = library_of(part_dir)
    entries, out = by_id(library), []
    for _a, i, vol, no in found:
        e = entries.get(i)
        f = sfx_dir(library) / e.file if e else None
        if not f or not f.is_file():
            print(f"warning: sfx {i}: " + (f"{e.file} missing from library/sfx/" if e else "not in the library")
                  + ", left out")
            continue
        x = decode(f)
        peak = float(abs(x).max()) if len(x) else 0.0
        if not peak:
            continue
        delay, trim = play_at(e.anchor, times[no], len(x) / 48000)
        gain = PEAK_UNDER_VOICE * voice_peak / peak * (e.default_volume if vol is None else vol)
        out.append({"path": f, "delay": delay, "trim": trim, "gain": gain, "id": i})
    return out


def stem(part_dir: Path, voice):
    """the part's sfx as a float stereo array the voice's length (ducked under it), or None without any"""
    import numpy as np
    cs = clips(part_dir, float(np.abs(voice).max()) or 1.0)
    if not cs:
        return None
    voice_f = part_dir / "voice-tight.wav"
    out = part_dir / "audio" / ".sfx-stem.tmp.wav"
    out.parent.mkdir(exist_ok=True)
    try:
        ff.run(*mix_cmd(cs, voice_f, out), text=True, fail="ffmpeg sfx mix failed")
        from .stages.audio import decode
        x = decode(out)[:len(voice)]
    finally:
        out.unlink(missing_ok=True)
    print(f"sfx: {', '.join(c['id'] for c in cs)}")
    return np.pad(x, ((0, len(voice) - len(x)), (0, 0)))
