"""prep: story.md -> script-for-tts.txt (plain text for pasting into freetts.ai).

story.md directives (one per line) are stripped from the script:
  @set office        set for the following lines
  @cast bob, karen   cast on stage for the following lines
  @dogs 4            dog pack size (0-6) for the following lines
  @fx drop           caption effect for the next line's chunks: drop | shake | pop | none
  @fx lightning [id] one lightning strike at the next line (near cast id, or whoever holds prop id)
  @weather rain heavy  weather until the next @weather or @set: clear | rain | snow | fog | wind | storm
                     [light | medium | heavy, default medium]; @set starts the set's default_weather (else clear)
  @do fred: collapse actions for the next line's shots, overriding keyword guessing (see parse_do)
  @look mike: headless  a cast member's named look from the next line on (default: its own; see parse_look)
  @crowd cheer 10    crowd extras behind the stage: cheer | angry | gasp | neutral [N, default 8, max 12] | off
  @runners 4         background runner extras (0-6)
  @sfx riser 0.6     a sound effect (library/sfx/sfx.json id, optional volume 0-1) for the next line (see sfx.py)
  !! text            this line is the twist (prefix stripped, text kept)
"""

import re
from pathlib import Path
from typing import NamedTuple, get_args

from ..io import LIBRARY_FILES, atomic_write_text, custom_actions, prop_kinds
from ..schemas import BuiltinProp, Intensity, Weather, WeatherKind, actions_with
from .runner import StageError

INPUTS = ["story.md", *(f"../../{f}" for f in LIBRARY_FILES)]
OUTPUTS = ["script-for-tts.txt"]
WPM = 150
MAX_SECONDS = 90  # parts may run ~70 s
FX_MODES = ("drop", "shake", "pop", "none")  # @fx: read by finish (captions); the shot planner ignores it
FX_LIGHTNING = "lightning"                  # @fx lightning [target]: read by the shot planner (engine), not finish
MAX_LIGHTNING = 3                           # strikes per part
WEATHER_KINDS = ("clear", *get_args(WeatherKind))
INTENSITIES = get_args(Intensity)

QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'",
                        "“": '"', "”": '"', "„": '"', "‟": '"'})


TWIST_PREFIX = re.compile(r"^([ \t]*)!![ \t]+")
MARKER = "⟦{}⟧"  # a token for the n-th @ line, "!" before a twist line, "/" after the line an @do applies to
MARKER_RE = re.compile("^⟦([0-9]+|!|/)⟧$")

# @do <cast>[, <cast>]: <action> [<target>|<prop>] [, <cast>: <action> ...]
DO_ACTIONS = actions_with("do")  # built in; plus the library's custom actions (io.custom_actions)
DO_CAR = "car"            # "@do car: broken": the car on stage breaks down
BUILTIN_PROPS = get_args(BuiltinProp)
HOLDERS = {"carry": (2, 2), "support": (1, 2)}


class DoClause(NamedTuple):
    who: tuple[str, ...]
    action: str
    target: str | None = None
    prop: str | None = None


def parse_do(arg: str, line: int, cast_ids=None, props=BUILTIN_PROPS, actions=()) -> list[DoClause]:
    """Parse an @do directive (the text after "@do"). With cast_ids, cast and targets must be in the series too.
    props: the prop kinds eat / give may name (io.prop_kinds: built-ins + library/props.json). actions: the
    library's custom actions (io.custom_actions), in-place moves that take no target or prop.
    Errors name the story.md line."""
    def bad(msg):
        raise StageError(f"story.md line {line}: @do: {msg}")
    segs = arg.split(":")
    if len(segs) < 2:
        bad('expected "@do <cast>: <action> [<target>|<prop>]", e.g. "@do fred: collapse"')
    out, seen, who_txt = [], set(), segs[0]
    for k, body in enumerate(segs[1:], 1):
        nxt = ""
        if k < len(segs) - 1:  # action words end at the first comma; the next clause's cast list follows
            body, sep, nxt = body.partition(",")
            if not sep:
                bad('separate clauses with a comma, e.g. "@do fred: lie, amy: wave"')
        who = tuple(w.strip() for w in who_txt.split(",") if w.strip())
        words = body.split()
        if not who or not words:
            bad('each clause needs a cast id and an action, e.g. "fred: collapse"')
        act, args = words[0], words[1:]
        if DO_CAR in who:
            if who != (DO_CAR,) or act != "broken" or args:
                bad(f'the car only takes "car: broken" (got "{", ".join(who)}: {body.strip()}")')
            out.append(DoClause(who, act))
            who_txt = nxt
            continue
        if act not in DO_ACTIONS and act not in actions:
            bad(f"unknown action {act!r} (use {', '.join(sorted(DO_ACTIONS | set(actions)))}, or car: broken)")
        target = prop = None
        if act == "eat":
            if len(args) > 1:
                bad('eat takes one prop, e.g. "eat apple"')
            prop = args[0] if args else "apple"
        elif act == "give":
            named = [w for w in args if w in props]
            if len(args) != 2 or len(named) != 1:
                bad(f'give needs a prop and a target, e.g. "give medal fred" (props: {", ".join(props)})')
            prop, target = named[0], next(w for w in args if w != named[0])
        elif act in HOLDERS:
            lo, hi = HOLDERS[act]
            if len(args) != 1:
                bad(f'{act} needs one target, e.g. "{act} thomas"')
            if not lo <= len(who) <= hi:
                bad(f"{act} needs {lo if lo == hi else f'{lo}-{hi}'} cast before the colon, got {len(who)}")
            target = args[0]
        elif args:
            bad(f"{act} takes no target or prop (got {' '.join(args)!r})")
        if prop is not None and prop not in props:
            bad(f"unknown prop {prop!r} (props: {', '.join(props)})")
        if target is not None and target in who:
            bad(f"{target} cannot {act} itself")
        for w in who + ((target,) if target else ()):
            if cast_ids is not None and w not in cast_ids:
                role = "target" if w == target else "cast id"
                bad(f"unknown {role} {w!r} (series cast: {', '.join(cast_ids)}; add with cast-add)")
        for w in who:
            if w in seen:
                bad(f"{w} is given two actions")
            seen.add(w)
        out.append(DoClause(who, act, target, prop))
        who_txt = nxt
    return out



def parse_look(arg: str, line: int, looks_of=None) -> tuple[tuple[str, ...], str]:
    """@look <cast>[, <cast>]: <look> -> (cast ids, look name); "default" is the cast member's own look. looks_of:
    cast id -> its look names (series.json), or None to check the syntax only. Errors name the story.md line."""
    def bad(msg):
        raise StageError(f"story.md line {line}: @look: {msg}")
    who_txt, sep, name = arg.partition(":")
    who, name = tuple(w.strip() for w in who_txt.split(",") if w.strip()), name.strip()
    if not sep or not who or not name or " " in name:
        bad('expected "@look <cast>: <look>", e.g. "@look mike: headless" (or "@look mike: default")')
    for w in who if looks_of is not None else ():
        if w not in looks_of:
            bad(f"unknown cast id {w!r} (series cast: {', '.join(looks_of)})")
        if name != "default" and name not in looks_of[w]:
            bad(f"{w} has no look {name!r} (its looks: {', '.join(['default', *looks_of[w]])}; add one under "
                f'"looks" in its series.json cast entry)')
    return who, name


def parse_weather(arg: str, line: int) -> Weather | None:
    """@weather <type> [intensity] -> Weather, or None for clear. Errors name the story.md line."""
    kind, *rest = arg.split() or [""]
    if kind not in WEATHER_KINDS or len(rest) > 1 or any(r not in INTENSITIES for r in rest) or kind == "clear" and rest:
        raise StageError(f"story.md line {line}: bad directive @weather {arg.strip()} (use @weather "
                         f"{' | '.join(WEATHER_KINDS)} [{' | '.join(INTENSITIES)}, default medium]; clear takes none)")
    return None if kind == "clear" else Weather(kind=kind, intensity=rest[0] if rest else "medium")


def parse_lightning(arg: str, line: int, cast_ids=None, props=BUILTIN_PROPS) -> str | None:
    """@fx lightning [cast id | prop id] (arg: the text after "@fx") -> the target or None. With cast_ids, the target
    must be a series cast id or a prop kind."""
    words = arg.split()
    if words[:1] != [FX_LIGHTNING] or len(words) > 2:
        raise StageError(f'story.md line {line}: @fx lightning takes one optional target, e.g. "@fx lightning zeus"')
    target = words[1] if len(words) == 2 else None
    if target and cast_ids is not None and target not in cast_ids and target not in props:
        raise StageError(f"story.md line {line}: @fx lightning: {target!r} is neither a cast id "
                         f"({', '.join(cast_ids)}) nor a prop ({', '.join(props)})")
    return target


def _is_directive(line: str) -> bool:
    return line.lstrip().startswith("@")


def strip_directives(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    return "\n".join(TWIST_PREFIX.sub(r"\1", line) for line in lines if not _is_directive(line))


def mark_directives(md: str) -> tuple[str, list[tuple[int, str]]]:
    """Like strip_directives, but leaves a marker token where each directive was.

    Returns (text, [(line number, directive without the @)]). Run clean_markdown on the text: it yields the
    same words as prep's script plus the marker tokens, and markers inside dropped blocks vanish with them.
    """
    out, found, close = [], [], False
    for no, line in enumerate(md.replace("\r\n", "\n").split("\n"), 1):
        if _is_directive(line):
            out.append(MARKER.format(len(found)))
            found.append((no, line.strip()[1:]))
            close = close or line.strip()[1:].split(None, 1)[:1] == ["do"]
        else:
            line = TWIST_PREFIX.sub(lambda m: m[1] + MARKER.format("!") + " ", line)
            if close and line.strip():  # an @do covers exactly the next text line
                line, close = f"{line} {MARKER.format('/')}", False
            out.append(line)
    return "\n".join(out), found


def check_do(md: str, props=BUILTIN_PROPS, actions=()) -> None:
    """syntax, actions and props of every @do line (cast ids are checked by the shots stage)"""
    for no, d in mark_directives(md)[1]:
        name, _, arg = d.partition(" ")
        if name == "do":
            parse_do(arg, no, props=props, actions=actions)


def clean_markdown(md: str) -> str:
    s = md.replace("\r\n", "\n")
    s = re.sub(r"^ {0,3}(```|~~~).*?^ {0,3}\1[^\n]*$", "", s, flags=re.M | re.S)  # fenced code: dropped
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<[^>\n]+>", "", s)                                              # HTML tags
    s = re.sub(r"^ {0,3}#{1,6}([ \t].*)?$", "", s, flags=re.M)                   # headings: dropped
    s = re.sub(r"^ {0,3}([-*_])( *\1){2,} *$", "", s, flags=re.M)                # horizontal rules
    s = re.sub(r"^ {0,3}\[[^\]]+\]:.*$", "", s, flags=re.M)                      # link reference definitions
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)                                   # images: dropped
    s = re.sub(r"\[([^\]]*)\](\([^)]*\)|\[[^\]]*\])", r"\1", s)                  # links: keep text
    s = re.sub(r"`([^`]*)`", r"\1", s)                                           # inline code: keep text
    s = re.sub(r"^[ \t]*>+ ?", "", s, flags=re.M)                                # blockquotes
    s = re.sub(r"^[ \t]*([-*+]|\d+[.)])[ \t]+", "", s, flags=re.M)               # list markers
    s = re.sub(r"(\*\*|__|~~)(.+?)\1", r"\2", s)                                 # bold, strike
    s = re.sub(r"\*(.+?)\*", r"\1", s)                                           # italic *
    s = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", s)                                # italic _ (not snake_case)
    s = s.translate(QUOTES)
    paragraphs = (" ".join(p.split()) for p in re.split(r"\n\s*\n", s))
    return "\n\n".join(p for p in paragraphs if p)


def estimate_seconds(text: str) -> float:
    return len(text.split()) / WPM * 60


def run(part_dir: Path) -> None:
    story = part_dir / "story.md"
    if not story.exists():
        raise StageError("story.md not found")
    md = story.read_text(encoding="utf-8")
    check_do(md, prop_kinds(part_dir.parent.parent), custom_actions(part_dir.parent.parent))
    text = clean_markdown(strip_directives(md))
    if not text:
        raise StageError("story.md has no body text (only a title?)")
    atomic_write_text(part_dir / "script-for-tts.txt", text + "\n")
    secs = estimate_seconds(text)
    print(f"words: {len(text.split())}, estimated duration: {secs:.1f} s at {WPM} wpm")
    if secs > MAX_SECONDS:
        print(f"warning: estimated {secs:.1f} s is over {MAX_SECONDS} s")
