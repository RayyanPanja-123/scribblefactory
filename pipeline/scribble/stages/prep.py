"""prep: story.md -> script-for-tts.txt (plain text for pasting into freetts.ai).

story.md directives (one per line) are stripped from the script:
  @set office        set for the following lines
  @cast bob, karen   cast on stage for the following lines
  @dogs 4            dog pack size (0-6) for the following lines
  @fx drop           caption effect for the next line's chunks: drop | shake | pop | none
  @fx lightning [id] one lightning strike at the next line (near cast id, or whoever holds prop id)
  @weather rain heavy  weather until the next @weather or @set: clear | rain | snow | fog | wind | storm
                     [light | medium | heavy, default medium]; @set starts the set's default_weather (else clear)
  @mood tense        scene tone until the next @mood or @set: tense | dark | flashback | bright | off (see parse_mood)
  @do fred: collapse actions for the next line's shots, overriding keyword guessing (see parse_do)
  @look mike: headless  a cast member's named look from the next line on (default: its own; see parse_look)
  @hold mike: trident  a prop in a cast member's hand from the next line on, over its look's (see parse_hold)
  @ride charro: charro-horse  a person rides a creature from the next line on, until "@ride charro: none" or the
                     end of the part; it stays mounted across @set changes (see parse_ride)
  @face mike: angry  a cast member's face for the next line only (see parse_face)
  @cam close push_in fast  the camera for the next line's first shot (see parse_cam)
  @crowd cheer 10    crowd extras behind the stage: cheer | angry | gasp | neutral [N, default 8, max 12] | off
  @runners 4         background runner extras (0-6)
  @item ship: saucer sky right  a World Item on stage until "@item ship: remove" or a set change (see parse_item);
                     "@item ship: state landed" changes its state; "@do ship: fly left" flies it across the next line
  @sfx riser 0.6     a sound effect (library/sfx/sfx.json id, optional volume 0-1) for the next line (see sfx.py)
  @background-music <track> [volume]  a named music bed from assets/music/stickman-history-shorts; use off to stop
  !! text            this line is the twist (prefix stripped, text kept)
  kai: text          kai (a cast id) says this line; quotes around it are optional and dropped. "!! kai: text" for
                     a spoken twist. Every other text line is the narrator's
"""

import re
from pathlib import Path
from typing import NamedTuple, get_args

from ..io import (CREATURE_HINT, CREATURE_SLOTS, LIBRARY_FILES, atomic_write_text, custom_actions, library_of, load_series, series_exists,
                  prop_kinds)
from ..schemas import (ITEM_ACTIONS, ITEM_KEYWORDS, BuiltinProp, CamAngle, CamMove, Expression, Intensity, ItemLayer, Mood, Weather, WeatherKind,
                       actions_with)
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
MOODS = get_args(Mood)
EXPRESSIONS = get_args(Expression)

QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'",
                        "“": '"', "”": '"', "„": '"', "‟": '"'})


TWIST_PREFIX = re.compile(r"^([ \t]*)!![ \t]+")
SPEAKER = re.compile(r"^([ \t]*)([a-z0-9]+(?:-[a-z0-9]+)*):[ \t]+")  # "kai: line": a lowercase cast id first
SAID = re.compile(r'^[ \t]*["“„‟](.*)["”‟][ \t]*$')                     # kai: "line": the quotes go


def spoken(line: str) -> str:
    """a text line as spoken: without the twist marker, the speaker and the quotes around a speaker's words (a
    narrator line is only stripped of its "!!", as it always was)"""
    line = TWIST_PREFIX.sub(r"\1", line)
    if not (m := SPEAKER.match(line)):
        return line
    rest = line[m.end():]
    return m[1] + (q[1] if (q := SAID.match(rest)) else rest)


def speaker(line: str) -> str | None:
    """the cast id that says this text line, or None (the narrator)"""
    m = SPEAKER.match(TWIST_PREFIX.sub(r"\1", line))
    return m[2] if m else None


def speakers(md: str) -> dict[int, str]:
    """story.md line number -> the cast id that says it (narrator lines left out)"""
    return {no: s for no, line in enumerate(md.replace("\r\n", "\n").split("\n"), 1)
            if not _is_directive(line) and (s := speaker(line))}


PACE = {"slow": 0.85, "fast": 1.15}  # @pace: the next line's TTS speed, times its voice's own
MAX_PAUSE = 3.0                     # @pause <seconds>: the silence before the next line in a TTS voice


def parse_pause(arg: str, line: int) -> float:
    try:
        s = float(arg)
    except ValueError:
        s = -1.0
    if not 0 <= s <= MAX_PAUSE:
        raise StageError(f"story.md line {line}: bad directive @pause {arg} (use @pause <seconds 0-{MAX_PAUSE:g}>, "
                         "e.g. @pause 1.2: the silence before the next line in a TTS voice)")
    return s


def parse_pace(arg: str, line: int) -> float:
    if arg not in PACE:
        raise StageError(f"story.md line {line}: bad directive @pace {arg} (use @pace {' | '.join(PACE)}: the next "
                         "line spoken slower or faster in a TTS voice)")
    return PACE[arg]


def voice_marks(md: str) -> dict[int, dict]:
    """story.md line number -> {"pause": s, "pace": x} from the @pause / @pace lines before it (text lines with words
    that have any)"""
    out, pending = {}, {}
    for no, line in enumerate(md.replace("\r\n", "\n").split("\n"), 1):
        s = line.strip()
        if s.startswith("@"):
            name, _, arg = s[1:].partition(" ")
            if name == "pause":
                pending["pause"] = parse_pause(arg.strip(), no)
            elif name == "pace":
                pending["pace"] = parse_pace(arg.strip(), no)
        elif pending and clean_markdown(spoken(line)):
            out[no], pending = pending, {}
    return out


MARKER = "⟦{}⟧"  # a token for the n-th @ line, "!" before a twist line, "/" after the line an @do applies to
MARKER_RE = re.compile("^⟦([0-9]+|!|/|L[0-9]+)⟧$")

# @do <cast>[, <cast>]: <action> [<target>|<prop>] [, <cast>: <action> ...]
DO_ACTIONS = actions_with("do")  # built in; plus the library's custom actions (io.custom_actions)
DO_CAR = "car"            # "@do car: broken": the car on stage breaks down
ITEM_MOVES = ("fly", "drive")  # "@do <item tag>: fly left | right": the item crosses the next line (shots.py)
ITEM_LAYERS = get_args(ItemLayer)
ITEM_SPOTS = ("left", "center", "right", "far-left", "far-right")
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
    library's custom actions (io.custom_actions), which take no prop and at most one target to face / move toward.
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
        if act in ITEM_MOVES:  # a World Item's path; the tag is checked against the items on stage (shots, check-story)
            if len(who) != 1 or args[:1] not in (["left"], ["right"]) or len(args) > 2 or args[1:] not in ([], ["slow"], ["fast"]):
                bad(f'an item move takes one item, a direction and maybe a speed, e.g. "ship: {act} left [slow | fast]"')
            out.append(DoClause(who, act, target=args[0], prop=args[1] if len(args) == 2 else None))  # prop: the speed
            who_txt = nxt
            continue
        if act in ITEM_ACTIONS:  # an interaction with a World Item: its tag (checked against the items on stage later)
            if len(args) != 1:
                bad(f'{act} takes one item, e.g. "{act} crystal" (the @item tag)')
            if cast_ids is not None and (bad_who := [w for w in who if w not in cast_ids]):
                bad(f"unknown cast id {bad_who[0]!r} (series cast: {', '.join(cast_ids)}; add with cast-add)")
            if len(who) != 1:
                bad(f"{act}: one cast member at a time")
            if who[0] in seen:
                bad(f"{who[0]} is given two actions")
            seen.add(who[0])
            out.append(DoClause(who, act, target=args[0]))
            who_txt = nxt
            continue
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
            if len(args) == 2 and not named and cast_ids is not None and len(other := [w for w in args if w not in cast_ids]) == 1:
                bad(f"unknown prop {other[0]!r} (props: {', '.join(props)})")  # "give trident amy": name the missing prop
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
        elif act in actions and len(args) == 1:  # a custom action aimed at someone: faces / moves toward them
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



def parse_look(arg: str, line: int, looks_of=None, creatures=None) -> tuple[tuple[str, ...], str]:
    """@look <cast>[, <cast>]: <look> -> (cast ids, look name); "default" is the cast member's own look. looks_of:
    cast id -> its look names (series.json), or None to check the syntax only. creatures: io.creature_wardrobe (the
    non-humanoids and what of their wardrobe is not drawn). Errors name the story.md line."""
    def bad(msg):
        raise StageError(f"story.md line {line}: @look: {msg}")
    who_txt, sep, name = arg.partition(":")
    who, name = tuple(w.strip() for w in who_txt.split(",") if w.strip()), name.strip()
    if not sep or not who or not name or " " in name:
        bad('expected "@look <cast>: <look>", e.g. "@look mike: headless" (or "@look mike: default")')
    for w in who if looks_of is not None else ():
        if w not in looks_of:
            bad(f"unknown cast id {w!r} (series cast: {', '.join(looks_of)})")
        rig, worn = (creatures or {}).get(w, (None, {}))
        if worn.get(name):
            bad(f"{w} is a {rig}, not a humanoid: look {name!r} puts on {', '.join(worn[name])}, and {CREATURE_HINT}")
        if name != "default" and name not in looks_of[w]:
            bad(f"{w} has no look {name!r} (its looks: {', '.join(['default', *looks_of[w]])}; add one under "
                f'"looks" in its series.json cast entry'
                + (f"; {w} is a {rig}: a look can change its colours, flame, stump or its {', '.join(CREATURE_SLOTS)} items)" if rig else ")"))
    return who, name


# what a rider can do in the saddle (upper body only); any other action falls back to idle (storycheck warns)
RIDE_ACTIONS = ("idle", "talk", "point", "wave", "react", "gasp", "angry", "cheer", "give", "receive")


def parse_ride(arg: str, line: int, cast_ids=None, creatures=None) -> tuple[str, str | None]:
    """@ride <rider>: <creature> | none -> (rider, mount cast id, or None to get off). cast_ids: the series cast, or
    None to check the syntax only. creatures: cast id -> anything, for the cast members that are not humanoids (the
    only mounts; a rider must be a humanoid). Errors name the story.md line."""
    def bad(msg):
        raise StageError(f"story.md line {line}: @ride: {msg}")
    rider, sep, mount = (x.strip() for x in arg.partition(":"))
    if not sep or not rider or not mount or " " in rider or " " in mount:
        bad('expected "@ride <rider>: <creature>", e.g. "@ride charro: charro-horse" (or "@ride charro: none")')
    if cast_ids is not None:
        creatures = creatures or {}
        for w in (rider, mount) if mount != "none" else (rider,):
            if w not in cast_ids:
                bad(f"unknown cast id {w!r} (series cast: {', '.join(cast_ids)})")
        if rider in creatures:
            bad(f"{rider} is not a humanoid: only people ride")
        if mount != "none" and mount not in creatures:
            bad(f"{mount} is a humanoid, not a creature to ride (creatures in the cast: {', '.join(creatures) or 'none'})")
    return rider, None if mount == "none" else mount


def ride(rides: dict, rider: str, mount: str | None, line: int) -> dict:
    """the rides (rider -> mount) after one @ride. Refused: getting on while already riding (get off first with
    "none"), or a mount that already has a rider (one rider per creature)."""
    if mount is None:
        return {k: v for k, v in rides.items() if k != rider}
    if rider in rides and rides[rider] != mount:
        raise StageError(f"story.md line {line}: @ride: {rider} already rides {rides[rider]} (\"@ride {rider}: none\" first)")
    if (other := next((r for r, m in rides.items() if m == mount and r != rider), None)):
        raise StageError(f"story.md line {line}: @ride: {mount} already carries {other} (one rider per creature)")
    return {**rides, rider: mount}


def parse_hold(arg: str, line: int, cast_ids=None, props=None, handless=None) -> tuple[tuple[str, ...], str, str | None]:
    """@hold <cast>[, <cast>]: <prop> [left | right] -> (cast ids, hand, prop kind or None for an empty hand).
    "none" empties the hand, "none" without a hand both hands ("both"). Kept for the rest of the part, over the look's
    props. cast_ids / props: the series cast and prop kinds, or None to check the syntax only. handless: cast id ->
    "a <rig>" for creatures without hands. Errors name the story.md line."""
    def bad(msg):
        raise StageError(f"story.md line {line}: @hold: {msg}")
    who_txt, sep, rest = arg.partition(":")
    who, words = tuple(w.strip() for w in who_txt.split(",") if w.strip()), rest.split()
    if not sep or not who or not 1 <= len(words) <= 2 or (len(words) == 2 and words[1] not in ("left", "right")):
        bad('expected "@hold <cast>: <prop> [left | right]", e.g. "@hold ethan: flip-phone" (or "@hold ethan: none")')
    kind, hand = words[0], words[1] if len(words) == 2 else ("both" if words[0] == "none" else "right")
    for w in who if cast_ids is not None else ():
        if w not in cast_ids:
            bad(f"unknown cast id {w!r} (series cast: {', '.join(cast_ids)})")
        if w in (handless or {}):
            bad(f"{w} is {handless[w]} (no hands) and cannot hold things")
    if kind != "none" and props is not None and kind not in props:
        bad(f"unknown prop {kind!r} (props: {', '.join(props)})")
    return who, hand, None if kind == "none" else kind


CAM_ANGLES, CAM_MOVES = get_args(CamAngle), (*get_args(CamMove), "hold")
CAM_DUTCH = 25  # @cam dutch: at most this many degrees either way


def parse_cam(arg: str, line: int) -> dict:
    """@cam [angle] [move | hold] [fast] [shake] [dutch <deg>], in any order, at least one -> only the parts given:
    {angle, move, fast: True, shake: True, dutch: degrees}. The shot planner applies them to the next line's first
    shot and keeps its own choice for the rest."""
    toks, out = arg.split(), {}
    usage = (f'expected "@cam [{" | ".join(CAM_ANGLES)}] [{" | ".join(CAM_MOVES)}] [fast] [shake] '
             f'[dutch <-{CAM_DUTCH}..{CAM_DUTCH}>]", e.g. "@cam close push_in fast"')
    if not toks:
        raise StageError(f"story.md line {line}: @cam: {usage}")
    i = 0
    while i < len(toks):
        t = toks[i]
        key = "angle" if t in CAM_ANGLES else "move" if t in CAM_MOVES else t if t in ("fast", "shake", "dutch") else None
        if key is None:
            raise StageError(f"story.md line {line}: @cam: unknown {t!r} ({usage})")
        if key in out:
            both = f" ({out[key]!r} and {t!r})" if key in ("angle", "move") else ""
            raise StageError(f"story.md line {line}: @cam: {key} given twice{both}")
        if key == "dutch":
            deg = toks[i + 1] if i + 1 < len(toks) else ""
            try:
                out["dutch"] = float(deg)
            except ValueError:
                raise StageError(f"story.md line {line}: @cam: dutch needs degrees, e.g. \"dutch 12\" "
                                 f"(-{CAM_DUTCH}..{CAM_DUTCH})") from None
            if not -CAM_DUTCH <= out["dutch"] <= CAM_DUTCH:
                raise StageError(f"story.md line {line}: @cam: dutch {deg} is outside -{CAM_DUTCH}..{CAM_DUTCH}")
            i += 2
            continue
        out[key] = t if key in ("angle", "move") else True
        i += 1
    return out


class ItemOp(NamedTuple):
    """one @item line: op "place" (object, layer or None: the item's own, spot, state or None), "state" or "remove" """
    tag: str
    op: str
    object: str | None = None
    layer: str | None = None
    spot: str = "center"
    state: str | None = None


def parse_item(arg: str, line: int, objects=None, cast_ids=()) -> ItemOp:
    """@item <tag>: <object> [layer] [spot] [state] | state <state> | remove. objects: World Item id -> WorldObject
    (io.world_object_kinds; None: check the syntax only); a placed object must be a card. The tag names the item in
    later @item and @do lines; it may not be a cast id. Errors name the story.md line."""
    def bad(msg):
        raise StageError(f"story.md line {line}: @item: {msg}")
    tag, sep, rest = arg.partition(":")
    tag, words = tag.strip(), rest.split()
    if not sep or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", tag) or not words:
        bad('expected "@item <tag>: <item> [layer] [spot] [state]", "@item <tag>: state <state>" or '
            '"@item <tag>: remove", e.g. "@item ship: saucer sky right"')
    if tag in cast_ids or tag == DO_CAR:
        bad(f"{tag!r} is a cast id or the car: give the item its own tag")
    if words == ["remove"]:
        return ItemOp(tag, "remove")
    if words[0] == "state":
        if len(words) != 2:
            bad('state takes one state, e.g. "@item pod: state open"')
        return ItemOp(tag, "state", state=words[1])
    if words[0] in ITEM_KEYWORDS:
        bad(f"{words[0]} takes no item before it")
    obj, layer, spot, state = words[0], None, None, None
    for w in words[1:]:
        if w in ITEM_LAYERS and layer is None:
            layer = w
        elif w in ITEM_SPOTS and spot is None:
            spot = w
        elif w not in ITEM_LAYERS + ITEM_SPOTS and state is None:
            state = w
        else:
            bad(f"unexpected {w!r} (layers: {', '.join(ITEM_LAYERS)}; spots: {', '.join(ITEM_SPOTS)}; one state)")
    if objects is not None:
        o = objects.get(obj)
        if o is None:
            bad(f"unknown World Item {obj!r} (items: {', '.join(objects) or 'none yet: add one on the World Items page'})")
        if o.look != "card":
            bad(f"{obj} is built from set pieces: place it in a set (only card items go on stage with @item)")
        if state is not None and state not in o.states:
            bad(f"{obj} has no state {state!r} (states: {', '.join(o.states) or 'none'})")
    return ItemOp(tag, "place", obj, layer, spot or "center", state)


def item_state_ok(op: ItemOp, line: int, objects, placed: dict) -> None:
    """an "@item <tag>: state <s>" line: the tag is on stage and its item has that state. placed: tag -> object id"""
    if op.tag not in placed:
        raise StageError(f"story.md line {line}: @item: {op.tag} is not on stage (place it first: "
                         f"@item {op.tag}: <item>)")
    o = objects.get(placed[op.tag]) if objects is not None else None
    if o is not None and op.state not in o.states:
        raise StageError(f"story.md line {line}: @item: {placed[op.tag]} has no state {op.state!r} "
                         f"(states: {', '.join(o.states) or 'none'})")


def parse_face(arg: str, line: int, cast_ids=None) -> dict[str, str]:
    """@face <cast>[, <cast>]: <expression> -> {cast id: expression} for the next narration line. cast_ids: the
    series cast, or None to check the syntax only. Errors name the story.md line."""
    who_txt, sep, face = arg.partition(":")
    who, face = [w.strip() for w in who_txt.split(",") if w.strip()], face.strip()
    if not sep or not who or face not in EXPRESSIONS:
        raise StageError(f'story.md line {line}: @face: expected "@face <cast>: <{" | ".join(EXPRESSIONS)}>", '
                         'e.g. "@face caligula: angry"')
    for w in who if cast_ids is not None else ():
        if w not in cast_ids:
            raise StageError(f"story.md line {line}: @face: unknown cast id {w!r} (series cast: {', '.join(cast_ids)})")
    return dict.fromkeys(who, face)


def parse_weather(arg: str, line: int) -> Weather | None:
    """@weather <type> [intensity] -> Weather, or None for clear. Errors name the story.md line."""
    kind, *rest = arg.split() or [""]
    if kind not in WEATHER_KINDS or len(rest) > 1 or any(r not in INTENSITIES for r in rest) or kind == "clear" and rest:
        raise StageError(f"story.md line {line}: bad directive @weather {arg.strip()} (use @weather "
                         f"{' | '.join(WEATHER_KINDS)} [{' | '.join(INTENSITIES)}, default medium]; clear takes none)")
    return None if kind == "clear" else Weather(kind=kind, intensity=rest[0] if rest else "medium")


def parse_mood(arg: str, line: int) -> str | None:
    """@mood <tense|dark|flashback|bright|off> -> the mood, or None for neutral (off). Errors name the story.md line."""
    word = arg.strip()
    if word not in (*MOODS, "off"):
        raise StageError(f"story.md line {line}: bad directive @mood {word} (use @mood {' | '.join(MOODS)} | off)")
    return None if word == "off" else word


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
    return "\n".join(spoken(line) for line in lines if not _is_directive(line))


def mark_directives(md: str) -> tuple[str, list[tuple[int, str]]]:
    """Like strip_directives, but leaves a marker token where each directive was.

    Returns (text, [(line number, directive without the @)]). Run clean_markdown on the text: it yields the
    same words as prep's script plus the marker tokens, and markers inside dropped blocks vanish with them. Every text
    line ends in an "L<line number>" marker: the words before it are that story.md line's.
    """
    out, found, close = [], [], False
    for no, line in enumerate(md.replace("\r\n", "\n").split("\n"), 1):
        if _is_directive(line):
            out.append(MARKER.format(len(found)))
            found.append((no, line.strip()[1:]))
            close = close or line.strip()[1:].split(None, 1)[:1] in (["do"], ["face"], ["cam"])
        else:
            twist = TWIST_PREFIX.match(line)
            line = spoken(line)
            if twist:  # "!! [kai:] text" -> "⟦!⟧ text", as a twist line always was
                line = re.sub(r"^([ \t]*)", lambda m: m[1] + MARKER.format("!") + " ", line, count=1)
            if line.strip():
                line = f"{line} {MARKER.format(f'L{no}')}"
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


def respell(text: str, pronunciations: dict[str, str]) -> str:
    """the voice's text: each whole word in pronunciations (case-sensitive) swapped for its respelling, punctuation
    kept ("Negro." -> "Neh-groh.")"""
    for word, say in pronunciations.items():
        text = re.sub(rf"(?<![\w-]){re.escape(word)}(?![\w-])", lambda _: say, text)
    return text


def pronunciations(part_dir: Path) -> dict[str, str]:
    """the series' voice.pronunciations ({} without a series)"""
    return load_series(part_dir.parent / "series.json").voice.pronunciations if series_exists(part_dir.parent) else {}


def extra_inputs(part_dir: Path) -> dict:
    """the only series.json field prep uses (hashed instead of the whole file: approvals, new parts don't count)"""
    return {"pronunciations": pronunciations(part_dir)}


def estimate_seconds(text: str) -> float:
    return len(text.split()) / WPM * 60


def run(part_dir: Path) -> None:
    story = part_dir / "story.md"
    if not story.exists():
        raise StageError("story.md not found")
    md = story.read_text(encoding="utf-8")
    check_do(md, prop_kinds(library_of(part_dir)), custom_actions(library_of(part_dir)))
    text = clean_markdown(strip_directives(md))
    if not text:
        raise StageError("story.md has no body text (only a title?)")
    atomic_write_text(part_dir / "script-for-tts.txt", respell(text, pronunciations(part_dir)) + "\n")
    secs = estimate_seconds(text)
    print(f"words: {len(text.split())}, estimated duration: {secs:.1f} s at {WPM} wpm")
    if secs > MAX_SECONDS:
        print(f"warning: estimated {secs:.1f} s is over {MAX_SECONDS} s")
