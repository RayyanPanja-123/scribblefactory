"""check-story: story.md checked against its series before any voice or timing exists.

Reports, with story.md line numbers: unknown @ directives and bad arguments, unknown cast ids, sets, actions and
props, @do conflicts (actor not on stage, target with its own action, @do during @car ride, car: broken with no car,
an @do with no line to apply to or replaced before it was used), cast not approved yet, and words changed against an
existing script-for-tts.txt (an existing voice.mp3 would no longer match). Plus the word count and estimated duration:
words / the words per second measured over the library's finished parts (qa.json runtime; FALLBACK_WPS without any),
plus the tail and the silent end screen, with a warning over MAX_RUNTIME_S. And warnings when narration opens on a
date or backstory, or ends on a spoken sign-off (the end screen says "Follow for more"; the voice never does).
Problems mean the pipeline would fail or produce a wrong video; warnings do not stop anything.
"""

import difflib
import json
import re
from pathlib import Path

from . import sfx as sfx_lib
from .io import cast_body_problems, custom_actions, load_series, prop_kinds, set_kinds, unknown_cast_props, wardrobe_slots
from .stages.finish import MAX_RUNTIME_S
from .stages.prep import (DO_CAR, FX_LIGHTNING, FX_MODES, MAX_LIGHTNING, TWIST_PREFIX, clean_markdown, parse_do,
                          parse_face, parse_lightning, parse_look, parse_weather, strip_directives)
from .stages.runner import StageError
from .stages.shots import (ACTION_FACE, CAR_MODES, CAR_SEATS, DEFAULT_CAST_SIZE, EXPRESSIONS, MAX_CAST, MAX_DOGS, MAX_ON_STAGE,
                           MAX_RUNNERS, parse_crowd, parse_crowd_look, parse_crowd_weapon, token)
from .validate import END_SCREEN_S, TAIL_S

DIRECTIVES = ("set", "cast", "dogs", "car", "fx", "do", "look", "crowd", "crowd-look", "crowd-weapon", "runners", "weather", "sfx", "face")
LINE_PREFIX = re.compile(r"^story\.md line [0-9]+: ")
FALLBACK_WPS = 2.6  # words per second before any part has been finished
# a first line that opens on a date or backstory instead of the hook
SLOW_OPEN = re.compile(r"^\W*(once upon|(in|on|by|during|back in) (the (year|summer|winter|spring|autumn|fall) (of )?)?"
                       r"(the )?(early |late )?(\d{3,4}|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
                       r"eighteen|nineteen|twenty|january|february|march|april|may|june|july|august|september|"
                       r"october|november|december)\b)", re.I)


def measured_wps(library: Path) -> float:
    """words per second of speech over every finished part's qa.json runtime, else FALLBACK_WPS"""
    words = seconds = 0.0
    for f in library.glob("*/part-*/qa.json"):
        try:
            r = json.loads(f.read_bytes()).get("runtime") or {}
            words, seconds = words + r["words"], seconds + r["speech_seconds"]
        except (ValueError, KeyError, TypeError):
            continue
    return words / seconds if words and seconds else FALLBACK_WPS


def estimate_runtime(words: int, wps: float) -> float:
    """seconds of video for this many words: the speech, the short tail, then the silent end screen"""
    return round(words / wps + TAIL_S + END_SCREEN_S, 1)


def slow_open(md: str) -> tuple[int, str] | None:
    """(line number, text) of the first narration line when it opens on a date or backstory, else None"""
    for no, line in enumerate(md.replace("\r\n", "\n").split("\n"), 1):
        if line.lstrip().startswith("@"):
            continue
        text = clean_markdown(TWIST_PREFIX.sub(r"\1", line))
        if text:
            return (no, text) if SLOW_OPEN.match(text) else None
    return None


# a closing line that asks for a follow or teases the next part: the end screen does that now, silently
SIGN_OFF = re.compile(r"to be continued|on my (profile|channel|page)|\bpart (\d+|one|two|three|four|five|six|seven|"
                      r"eight|nine|ten|next)\b.*\b(up|out|coming|next)\b|follow (me )?for (more|part)", re.I)


def spoken_sign_off(md: str) -> tuple[int, str] | None:
    """(line number, text) of the last narration line when it is a sign-off ("To be continued.", "Part two is on my
    profile."), else None"""
    last = None
    for no, line in enumerate(md.replace("\r\n", "\n").split("\n"), 1):
        if not line.lstrip().startswith("@") and (text := clean_markdown(TWIST_PREFIX.sub(r"\1", line))):
            last = (no, text)
    return last if last and SIGN_OFF.search(last[1]) else None


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
        return {"ok": False, "problems": problems, "warnings": warnings, "words": 0, "seconds": 0.0, "wps": FALLBACK_WPS}
    md = story.read_text(encoding="utf-8")
    series = load_series(part_dir.parent / "series.json")
    library = part_dir.parent.parent
    props, sets, actions = prop_kinds(library), list(set_kinds(library)), custom_actions(library)
    ids = [c.id for c in series.cast]
    if not ids:
        bad(None, f"series {series.slug} has no cast: add some with cast-add")
    for u in unknown_cast_props(series.cast, library):
        bad(None, f"cast holds a prop that is neither built in nor in library/props.json: {u}")
    for u in cast_body_problems(series.cast, library):
        bad(None, f"cast body: {u}")

    sounds = sfx_lib.by_id(library)
    cast, car, pending_do, pending_strike, strikes = tuple(ids[:DEFAULT_CAST_SIZE]), "off", None, None, 0
    pending_sfx, n_sfx, pending_face = [], 0, None
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
                elif name == "fx" and arg.split()[:1] == [FX_LIGHTNING]:
                    target = parse_lightning(arg, no, ids, props)
                    strikes += 1
                    if strikes == MAX_LIGHTNING + 1:
                        bad(no, f"@fx lightning: at most {MAX_LIGHTNING} per part (keep it for the big beats)")
                    if pending_strike:
                        bad(pending_strike[0], f"@fx lightning is replaced by the one on line {no} before any text "
                                               "line uses it")
                    pending_strike = (no, target)
                elif name == "fx" and arg not in FX_MODES:
                    bad(no, f"@fx takes {' | '.join(FX_MODES)} | lightning [target], got {arg!r}")
                elif name == "weather":
                    parse_weather(arg, no)
                elif name == "face":
                    parse_face(arg, no, ids)
                    pending_face = no
                elif name == "sfx":
                    sid, _vol = sfx_lib.parse_sfx(arg, no, list(sounds))
                    n_sfx += 1
                    if n_sfx == sfx_lib.MAX_PER_PART + 1:
                        bad(no, f"@sfx: at most {sfx_lib.MAX_PER_PART} per part (only where the moment needs one)")
                    if not (sfx_lib.sfx_dir(library) / sounds[sid].file).is_file():
                        warnings.append({"line": no, "message": f"@sfx {sid}: {sounds[sid].file} is missing from "
                                                                 "library/sfx/ (left out of the mix)"})
                    pending_sfx.append(no)
                elif name == "car":
                    if arg in CAR_MODES:
                        car = arg
                    else:
                        bad(no, f"@car takes {' | '.join(CAR_MODES)}, got {arg!r}")
                elif name == "crowd":
                    parse_crowd(arg, no)
                elif name == "crowd-look":
                    parse_crowd_look(arg, no, wardrobe_slots(library))
                elif name == "crowd-weapon":
                    parse_crowd_weapon(arg, no, props)
                elif name == "look":
                    parse_look(arg, no, {c.id: list(c.looks) for c in series.cast})
                elif name == "do":
                    clauses = parse_do(arg, no, ids, props, actions)
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
        pending_sfx, pending_face = [], None
        if pending_strike:
            if pending_strike[1] in ids and pending_strike[1] not in cast:
                bad(pending_strike[0], f"@fx lightning: {pending_strike[1]} is not on stage on the next line "
                                       f"(@cast {', '.join(cast)})")
            pending_strike = None
    if pending_do:
        bad(pending_do[0], "@do has no text line after it to apply to")
    if pending_strike:
        bad(pending_strike[0], "@fx lightning has no text line after it to strike on")
    if pending_face:
        bad(pending_face, "@face has no narration line after it")
    for no in pending_sfx:
        bad(no, "@sfx has no narration line after it to play on")

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
    if hook := slow_open(md):
        warnings.append({"line": hook[0], "message": "the first line opens on a date or backstory: lead with the twist "
                                                     "or the most surprising claim, and move the date to line two"})
    if end := spoken_sign_off(md):
        warnings.append({"line": end[0], "message": "the last line is a sign-off: drop it. Every part ends on a silent "
                                                    "\"Follow for more\" screen; the voice never asks for a follow"})
    if not problems:
        warnings += staging(md, series, library, part_dir.name)
    wps = measured_wps(library)
    seconds = estimate_runtime(len(words), wps)
    if seconds > MAX_RUNTIME_S:
        cut = round((seconds - MAX_RUNTIME_S) * wps)
        warnings.append({"line": None, "message": f"estimated {seconds} s is {seconds - MAX_RUNTIME_S:.1f} s over "
                                                  f"{MAX_RUNTIME_S} s ({len(words)} words at {wps:.2f} words/s): "
                                                  f"cut about {cut} words"})
    return {"ok": not problems, "problems": problems, "warnings": warnings, "words": len(words), "seconds": seconds,
            "wps": round(wps, 2)}


STAGING = ("do", "look", "face", "fx", "crowd", "dogs", "runners", "car", "weather", "sfx")
MIN_STAGING = 10  # directives besides @set and @cast (STORY_GUIDE.md section 5)


def staging(md: str, series, library: Path, part: str) -> list[dict]:
    """How fully the script uses the library and the directives: warnings starting "staging: ", for the writer (and
    the story AI the warnings are pasted back to). Never problems: a sparse script still renders."""
    out = []
    note = lambda line, msg: out.append({"line": line, "message": f"staging: {msg}"})  # noqa: E731
    lines = md.replace("\r\n", "\n").split("\n")
    names = {token(c.name): c for c in series.cast}
    used = {d: 0 for d in STAGING}
    narration, pending, flat = 0, {}, []  # pending: cast id -> face set by @do / @face for the next line
    for no, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("@"):
            name, _, arg = s[1:].partition(" ")
            if name in used:
                used[name] += 1
            who, _, what = arg.partition(":")
            for w in (x.strip() for x in who.split(",")):
                if name == "face" or (name == "do" and what.split()[:1] and what.split()[0] in ACTION_FACE):
                    pending[w] = True
            continue
        text = clean_markdown(TWIST_PREFIX.sub(r"\1", line))
        if not text:
            continue
        narration += 1
        toks = [token(w) for w in text.split()]
        subject = next((names[t] for t in toks if t in names), None)
        if subject and subject.default_expression != "neutral" and subject.id not in pending \
                and not any(t in EXPRESSIONS for t in toks):
            flat.append((no, subject))
        pending = {}
    rich = sum(used.values())
    if rich < MIN_STAGING:
        note(None, f"{rich} directives besides @set and @cast; aim for {MIN_STAGING} or more (@do, @look, @face, "
                   "@crowd, @weather, @fx, @sfx): without them every shot is people standing and talking")
    if narration and used["do"] * 3 < narration:
        note(None, f"{used['do']} @do in {narration} narration lines: give a physical beat every second or third line")
    if flat:
        who = sorted({f"{c.id} ({c.default_expression})" for _, c in flat})
        note(flat[0][0], f"line{'s' * (len(flat) > 1)} {', '.join(str(n) for n, _ in flat[:6])}"
                         f"{' ...' if len(flat) > 6 else ''}: no mood word, emotional @do or @face, so the face is the "
                         f"default one: {', '.join(who)}. Add a mood word (angry, laughed, sobbed...) or @face where "
                         "the moment has a feeling")
    if not used["sfx"]:
        note(None, "no @sfx: 2 to 4 sound effects where the moment needs one (the Review tab suggests some)")
    # the series' unused looks and the library's unused custom actions, over every part's story.md
    series_md = "\n".join(f.read_text(encoding="utf-8") for f in sorted((library / series.slug).glob("part-*/story.md")))
    looked = {(w.strip(), look.strip()) for ln in series_md.split("\n") if ln.strip().startswith("@look ")
              for who, _, look in [ln.strip()[6:].partition(":")] for w in who.split(",")}
    on_stage = {c.id for t in map(token, clean_markdown(strip_directives(md)).split()) if (c := names.get(t))}
    idle_looks = [f"{c.id}: {k}" for c in series.cast if c.id in on_stage for k in c.looks if (c.id, k) not in looked]
    if idle_looks:
        note(None, f"looks never switched on in this series: {', '.join(idle_looks)} (@look <cast>: <look>)")
    acted = {w for ln in series_md.split("\n") if ln.strip().startswith("@do ") for w in ln.replace(",", " ").split()}
    idle_actions = [a for a in custom_actions(library) if a not in acted]
    if idle_actions:
        note(None, f"custom actions never used in this series: {', '.join(idle_actions[:8])} (@do <cast>: <action>)")
    return out


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
    out.append(f"words: {result['words']}, estimated duration: {result['seconds']} s at {result['wps']} words/s")
    n = len(result["problems"])
    out.append("ready" if result["ok"] else f"{n} problem{'s' * (n != 1)}")
    return "\n".join(out)
