"""thumbnails: 3 caption-free candidates copied from rendered frames -> thumbs/thumb-1..3.png; upload.md if missing.

Candidates: 1 middle of the twist shot, 2 middle of the first wide shot, 3 middle of the shot with the most actors
(ties: most expressive, then earliest). A missing twist / wide shot falls back to the middle of the part.
No text overlay. upload.md is the user's to edit: created once, never overwritten.
"""

import re
from pathlib import Path

from ..io import atomic_write_bytes, atomic_write_text
from ..schemas import SeriesModel, Shot, StoryModel
from .render import frame_path
from .runner import StageError
from .validate import load_model

INPUTS = ["story.json", "frames/chunks"]
OUTPUTS = ["thumbs/thumb-1.png", "thumbs/thumb-2.png", "thumbs/thumb-3.png", "upload.md"]
HASHTAGS = "#shorts #stickman #history"
EXPRESSIVE = {"surprised", "angry", "react"}  # expressions, plus the react action


def _mid(s: Shot) -> int:
    return (s.start_frame + s.end_frame - 1) // 2


def pick_frames(story: StoryModel) -> list[int]:
    middle = story.duration_frames // 2
    twist = next((s for s in story.shots if s.twist), None)
    wide = next((s for s in story.shots if s.camera.angle == "wide"), None)
    crowd = max(story.shots, key=lambda s: (len(s.actors),
                                            sum(a.expression in EXPRESSIVE or a.action in EXPRESSIVE for a in s.actors),
                                            -s.start_frame))
    return [_mid(twist) if twist else middle, _mid(wide) if wide else middle, _mid(crowd)]


def first_sentence(text: str) -> str:
    text = " ".join(text.split())
    m = re.match(r".*?(?<!\.)[.!?](?!\.)(?=\s|$)", text)  # an ellipsis doesn't end the sentence
    return m.group(0) if m else text


def upload_text(series: SeriesModel, number: int, script: str) -> str:
    title = f"{series.title} — Part {number}"
    body = f"Title: {title}\n\n{first_sentence(script)} Part {number} of {len(series.parts)}.\n\n{HASHTAGS}\n"
    return f"# {title}\n\n## YouTube\n\n{body}\n## Instagram\n\n{body}"


def run(part_dir: Path) -> None:
    story = load_model(part_dir / "story.json", StoryModel)
    frames, thumbs = part_dir / "frames", part_dir / "thumbs"
    thumbs.mkdir(exist_ok=True)
    for k, n in enumerate(pick_frames(story), 1):
        src = frame_path(frames, n)
        if not src.exists():
            raise StageError(f"frame {n} not found ({src}): render the part first (frames are needed until "
                             f"thumbnails are made)")
        atomic_write_bytes(thumbs / f"thumb-{k}.png", src.read_bytes())
        print(f"thumb-{k}: frame {n}")

    upload = part_dir / "upload.md"
    if upload.exists():
        print("upload.md exists, kept")
        return
    script = part_dir / "script-for-tts.txt"
    if not script.exists():
        raise StageError("script-for-tts.txt not found (run prep)")
    series = load_model(part_dir.parent / "series.json", SeriesModel)
    number = int(part_dir.name.removeprefix("part-"))
    atomic_write_text(upload, upload_text(series, number, script.read_text(encoding="utf-8")))
    print("upload.md written")
