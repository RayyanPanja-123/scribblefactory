"""prep: story.md -> script-for-tts.txt (plain text for pasting into freetts.ai)."""

import re
from pathlib import Path

from ..io import atomic_write_text
from .runner import StageError

INPUTS = ["story.md"]
OUTPUTS = ["script-for-tts.txt"]
WPM = 150
MAX_SECONDS = 60

QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'",
                        "“": '"', "”": '"', "„": '"', "‟": '"'})


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
    text = clean_markdown(story.read_text(encoding="utf-8"))
    if not text:
        raise StageError("story.md has no body text (only a title?)")
    atomic_write_text(part_dir / "script-for-tts.txt", text + "\n")
    secs = estimate_seconds(text)
    print(f"words: {len(text.split())}, estimated duration: {secs:.1f} s at {WPM} wpm")
    if secs > MAX_SECONDS:
        print(f"warning: estimated {secs:.1f} s is over {MAX_SECONDS} s")
