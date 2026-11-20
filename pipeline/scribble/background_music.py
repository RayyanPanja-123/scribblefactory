"""Named background music tracks used by the @background-music story directive."""

from pathlib import Path

from .stages.runner import StageError

TRACKS = {
    "monkeys-spinning-monkeys": "01-monkeys-spinning-monkeys.mp3",
    "comedy-quirky-sneaky": "02-comedy-quirky-sneaky-music-starostin.mp3",
    "sneaky-snitch": "03-sneaky-snitch.mp3",
    "cartoon-pizzicato": "04-cartoon-pizzicato.mp3",
    "fluffing-a-duck": "05-fluffing-a-duck.mp3",
    "scheming-weasel-faster": "06-scheming-weasel-faster.mp3",
    "funny-comedy-quirky": "07-funny-comedy-quirky-background-music-inplusmusic.mp3",
}
DEFAULT_VOLUME = 0.15


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
