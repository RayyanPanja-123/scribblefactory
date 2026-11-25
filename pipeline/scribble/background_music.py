"""Named background music tracks used by the @background-music story directive."""

from pathlib import Path

from .stages.runner import StageError

TRACKS = {
    # moods: what the story AI and the editor pick from first
    "calm": "01-monkeys-spinning-monkeys.mp3",   # the world at ease
    "mysterious": "03-sneaky-snitch.mp3",        # something unexpected happened, or is building up
    "funny": "05-fluffing-a-duck.mp3",           # a funny moment
    "scary": "08-darkling.mp3",                  # exploring the unknown
    "monkeys-spinning-monkeys": "01-monkeys-spinning-monkeys.mp3",
    "comedy-quirky-sneaky": "02-comedy-quirky-sneaky-music-starostin.mp3",
    "sneaky-snitch": "03-sneaky-snitch.mp3",
    "cartoon-pizzicato": "04-cartoon-pizzicato.mp3",  # retired (a dud): kept only for parts that already use it
    "fluffing-a-duck": "05-fluffing-a-duck.mp3",
    "scheming-weasel-faster": "06-scheming-weasel-faster.mp3",
    "funny-comedy-quirky": "07-funny-comedy-quirky-background-music-inplusmusic.mp3",
    "darkling": "08-darkling.mp3",
}
DEFAULT_VOLUME = 0.5  # about 6 dB under the voice (audio.BACKGROUND_UNDER_DB is the 0.15 level)


def parse(arg: str, line: int) -> tuple[str | None, float]:
    """Parse ``@background-music <track> [volume]`` or ``off``."""
    words = arg.split()
    if words == ["off"]:
        return None, 0.0
    if not 1 <= len(words) <= 2 or words[0] not in TRACKS:
        raise StageError(f"story.md line {line}: @background-music expected one of "
                         f"{', '.join(TRACKS)} [volume 0-1], or off")
    try:
        volume = DEFAULT_VOLUME if len(words) == 1 else float(words[1])
    except ValueError:
        raise StageError(f"story.md line {line}: @background-music volume must be 0-1") from None
    if not 0 <= volume <= 1:
        raise StageError(f"story.md line {line}: @background-music volume must be 0-1")
    return words[0], volume


def path(track: str) -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "music" / "stickman-history-shorts" / TRACKS[track]


# --- the "Attach Background Music" button: a mood per story.md line, from its @face / @do directives ---

MOOD_OF = {  # expressions and actions; anything else is calm
    "scary": {"scared", "run", "evil"},
    "mysterious": {"suspicious", "worried", "shocked", "confused", "surprised", "thinking", "guilty", "gasp"},
    "funny": {"happy", "cheer", "cheeky", "excited", "laughing", "wink", "smug", "love", "embarrassed", "deadpan",
              "annoyed", "facepalm_ready", "dizzy", "drunk", "crazy", "angry", "furious"},
}
RANK = ("scary", "mysterious", "funny")  # a line with several moods takes the first of these


def _mood(directives: list[str]) -> str:
    words = set()
    for d in directives:
        name, _, arg = d[1:].partition(" ")
        if name in ("face", "do"):  # "@face you: scared, zib: happy" / "@do you: run, zib: walk"
            words |= {w.strip(":,") for w in arg.replace(",", " ").split()}
    return next((m for m in RANK if words & MOOD_OF[m]), "calm")


def score(md: str) -> str:
    """story.md with its @background-music lines replaced by mood cues: one before a line's directive block wherever
    the mood changes. A new mood needs two lines in a row, so one odd face never flips the music.
    ponytail: keyword rules from faces/actions; an AI pass over the text would read the story better."""
    lines = [l for l in md.split("\n") if not l.startswith("@background-music")]
    blocks, start = [], 0  # (block start, text line index) for each narration line
    for i, l in enumerate(lines):
        s = l.strip()
        if not s or s.startswith("#"):
            start = i + 1
        elif not s.startswith("@"):
            blocks.append((start, i))
            start = i + 1
    raw = [_mood([lines[j].strip() for j in range(a, t)]) for a, t in blocks]
    cues, mood = {}, None
    for k, m in enumerate(raw):
        if m != mood and (mood is None or (k + 1 < len(raw) and raw[k + 1] == m)):
            cues[blocks[k][0]] = mood = m
    for at in sorted(cues, reverse=True):
        lines.insert(at, f"@background-music {cues[at]}")
    return "\n".join(lines)


if __name__ == "__main__":
    md = "# T\n\n@face a: happy\nOne.\n@face a: scared\nTwo.\n@face a: happy\nThree.\n@do a: run\nFour.\n@face a: scared\nFive.\n@background-music sneaky-snitch\nSix."
    out = score(md)
    assert out.count("@background-music") == 2 and "sneaky-snitch" not in out, out
    assert out.index("@background-music funny") < out.index("@face a: happy")  # above the block, first line funny
    assert out.index("@background-music scary") < out.index("@do a: run")  # one scared line (Two) never flipped it
    print("ok")
