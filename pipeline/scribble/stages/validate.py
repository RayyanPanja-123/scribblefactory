"""validate: check story.json against phrases.json and the series cast. Read-only, no output file."""

from pathlib import Path

from pydantic import ValidationError

from ..schemas import PhrasesModel, SeriesModel, StoryModel
from ..validate import validate
from .runner import StageError

INPUTS = ["story.json", "phrases.json", "../series.json"]
OUTPUTS = []


def load_model(path: Path, model):
    if not path.exists():
        raise StageError(f"{path.name} not found")
    try:
        return model.model_validate_json(path.read_bytes())
    except ValidationError as e:
        raise StageError(f"{path.name} is invalid: {e}")


def run(part_dir: Path) -> None:
    story = load_model(part_dir / "story.json", StoryModel)
    phrases = load_model(part_dir / "phrases.json", PhrasesModel)
    series = load_model(part_dir.parent / "series.json", SeriesModel)
    errors = validate(story, phrases, {c.id for c in series.cast})
    for e in errors:
        print(f"  {e.shot_id or '-'}  {e.rule}: {e.message}")
    if errors:
        raise StageError(f"{len(errors)} validation error(s)")
    print(f"ok: {len(story.shots)} shots, {story.duration_frames} frames")
