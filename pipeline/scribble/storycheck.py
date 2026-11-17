"""check-story: story.md checked against its series before any voice or timing exists.

Reports, with story.md line numbers: unknown @ directives and bad arguments, unknown cast ids, sets, actions and
props, @do conflicts (actor not on stage, target with its own action, @do during @car ride, car: broken with no car,
an @do with no line to apply to or replaced before it was used), cast not approved yet, and words changed against an
existing script-for-tts.txt (an existing voice.mp3 would no longer match). Plus the word count and estimated duration.
Problems mean the pipeline would fail or produce a wrong video; warnings do not stop anything.
"""

import difflib
import re
from pathlib import Path

from .io import load_series, prop_kinds, unknown_cast_props
from .stages.prep import (DO_CAR, FX_MODES, MAX_SECONDS, TWIST_PREFIX, WPM, clean_markdown, estimate_seconds,
                          parse_do, strip_directives)
from .stages.runner import StageError
from .stages.shots import CAR_MODES, CAR_SEATS, DEFAULT_CAST_SIZE, MAX_CAST, MAX_DOGS, MAX_ON_STAGE, MAX_RUNNERS, parse_crowd

WORLD_JS = Path(__file__).resolve().parents[2] / "engine" / "page" / "world.js"
DIRECTIVES = ("set", "cast", "dogs", "car", "fx", "do", "crowd", "runners")
LINE_PREFIX = re.compile(r"^story\.md line [0-9]+: ")


def engine_sets() -> list[str]:
    """the set names the engine can build (engine/page/world.js SETS: one list, read, never copied)"""
    m = re.search(r"export const SETS = \[([^\]]*)\]", WORLD_JS.read_text(encoding="utf-8"))
    return re.findall(r'"([a-z_]+)"', m[1])


def _words_by_line(md: str) -> list[int]:
    """story.md line number of each script word, or [] when a line-by-line read disagrees with the whole-file one
    (markdown spanning lines). ponytail: per-line approximation, enough to point at the edited line."""
    out = []
    for no, line in enumerate(md.replace("\r\n", "\n").split("\n"), 1):
        if not line.lstrip().startswith("@"):
            out += [no] * len(clean_markdown(TWIST_PREFIX.sub(r"\1", line)).split())
    return out if len(out) == len(clean_markdown(strip_directives(md)).split()) else []


def _changed_words(old: list[str], new: list[str], lines: list[int]) -> list[tuple[int | None, str]]:
    found = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        was, now = " ".join(old[i1:i2]) or "(nothing)", " ".join(new[j1:j2]) or "(nothing)"
        at = min(j1, len(new) - 1)
        found.append((lines[at] if lines and at >= 0 else None, f"word {j1 + 1}: {was!r} -> {now!r}"))
    return found


def check_story(part_dir: Path) -> dict:
    """{"ok", "problems": [{"line", "message"}], "warnings": [...], "words", "seconds"}"""
    problems, warnings = [], []
    bad = lambda line, msg: problems.append({"line": line, "message": msg})
    story = part_dir / "story.md"
    if not story.is_file():
        bad(None, "story.md not found")
        return {"ok": False, "problems": problems, "warnings": warnings, "words": 0, "seconds": 0.0}
    md = story.read_text(encoding="utf-8")
    series = load_series(part_dir.parent / "series.json")
    library = part_dir.parent.parent
    props, sets = prop_kinds(library), engine_sets()
    ids = [c.id for c in series.cast]
    if not ids:
        bad(None, f"series {series.slug} has no cast: add some with cast-add")
    for u in unknown_cast_props(series.cast, library):
        bad(None, f"cast holds a prop that is neither built in nor in library/props.json: {u}")

    cast, car, pending_do = tuple(ids[:DEFAULT_CAST_SIZE]), "off", None
    first_seen: dict[str, int] = {}  # cast id -> first line it is on stage
    for no, line in enumerate(md.replace("\r\n", "\n").split("\n"), 1):
        s = line.strip()
        if s.startswith("@"):
            name, _, arg = s[1:].partition(" ")
            arg = arg.strip()
            try:
                if name not in DIRECTIVES:
                    bad(no, f"unknown directive @{name} (use {', '.join('@' + d for d in DIRECTIVES)})")
                elif name == "set":
                    if arg not in sets:
                        bad(no, f"unknown set {arg!r} (sets: {', '.join(sets)})")
                elif name == "cast":
                    new = tuple(x.strip() for x in arg.split(",") if x.strip())
                    unknown = [x for x in new if x not in ids]
                    if not new:
                        bad(no, "@cast needs at least one cast id")
                    elif unknown:
                        bad(no, f"unknown cast id {', '.join(unknown)} (series cast: {', '.join(ids) or '-'})")
                    elif len(new) > MAX_CAST:
                        bad(no, f"@cast: {len(new)} on stage, at most {MAX_CAST} fit ({MAX_ON_STAGE} in front, "
                                f"{MAX_ON_STAGE} behind; split the scene, or use @crowd for a group in the background)")
                    else:
                        cast = new
                elif name == "dogs" and not (arg.isdigit() and int(arg) <= MAX_DOGS):
                    bad(no, f"@dogs takes 0-{MAX_DOGS}, got {arg!r}")
                elif name == "runners" and not (arg.isdigit() and int(arg) <= MAX_RUNNERS):
                    bad(no, f"@runners takes 0-{MAX_RUNNERS}, got {arg!r}")
                elif name == "fx" and arg not in FX_MODES:
                    bad(no, f"@fx takes {' | '.join(FX_MODES)}, got {arg!r}")
                elif name == "car":
                    if arg in CAR_MODES:
                        car = arg
                    else:
                        bad(no, f"@car takes {' | '.join(CAR_MODES)}, got {arg!r}")
                elif name == "crowd":
                    parse_crowd(arg, no)
                elif name == "do":
                    clauses = parse_do(arg, no, ids, props)
                    if pending_do:
                        bad(pending_do[0], f"@do is replaced by the @do on line {no} before any text line uses it")
                    pending_do = (no, clauses)
            except StageError as e:
                bad(no, LINE_PREFIX.sub("", str(e)))
            continue
        if not clean_markdown(TWIST_PREFIX.sub(r"\1", line)):
            continue  # blank, heading or other markup without spoken words
        for cid in cast:  # riders too: they are on screen
            first_seen.setdefault(cid, no)
        if car == "ride" and len(cast) > CAR_SEATS:
            bad(no, f"@car ride: {len(cast)} riders in @cast ({', '.join(cast)}), the car seats {CAR_SEATS}")
        if pending_do:
            _check_do(*pending_do, cast, car, bad)
            pending_do = None
    if pending_do:
        bad(pending_do[0], "@do has no text line after it to apply to")

    approved = {c.id for c in series.cast if c.approved_at}
    for cid, no in first_seen.items():
        if cid in ids and cid not in approved:
            bad(no, f"cast {cid} is not approved yet (cast-sheet {series.slug}, then approve-cast {series.slug} {cid})")

    script = clean_markdown(strip_directives(md))
    words = script.split()
    if not words:
        bad(None, "story.md has no body text (only a title?)")
    old_script = part_dir / "script-for-tts.txt"
    if old_script.is_file() and (old := old_script.read_text(encoding="utf-8").split()) != words:
        voice = (part_dir / "voice.mp3").is_file()
        for line, msg in _changed_words(old, words, _words_by_line(md)):
            if voice:
                bad(line, f"changed since voice.mp3 was recorded: {msg} (re-record the voice, or undo the edit)")
            else:
                warnings.append({"line": line, "message": f"changed since script-for-tts.txt: {msg} (prep rewrites it)"})
    seconds = round(estimate_seconds(script), 1)
    if seconds > MAX_SECONDS:
        warnings.append({"line": None, "message": f"estimated {seconds} s is over {MAX_SECONDS} s"})
    return {"ok": not problems, "problems": problems, "warnings": warnings, "words": len(words), "seconds": seconds}


def _check_do(line: int, clauses, cast: tuple, car: str, bad) -> None:
    """the @do checks that need the stage: who is on it and whether a car is"""
    named = {w for c in clauses for w in c.who}
    for c in clauses:
        if c.who == (DO_CAR,):
            if car == "off":
                bad(line, "@do car: broken, but there is no car on stage (bring one with @car arrive or ride)")
            continue
        if car == "ride":
            bad(line, "@do: not while @car ride, except \"car: broken\" (the cast is seated in the car)")
            return
        for w in c.who + ((c.target,) if c.target else ()):
            if w not in cast:
                bad(line, f"@do: {w} is not on stage on this line (@cast {', '.join(cast)})")
        if c.target in named:
            bad(line, f"@do: {c.target} is the target of {c.action} and has its own action too")


def report(result: dict) -> str:
    """plain text for the CLI"""
    at = lambda x: f"line {x['line']}: " if x["line"] else ""
    out = [f"problem: {at(p)}{p['message']}" for p in result["problems"]]
    out += [f"warning: {at(w)}{w['message']}" for w in result["warnings"]]
    out.append(f"words: {result['words']}, estimated duration: {result['seconds']} s at {WPM} wpm")
    n = len(result["problems"])
    out.append("ready" if result["ok"] else f"{n} problem{'s' * (n != 1)}")
    return "\n".join(out)
