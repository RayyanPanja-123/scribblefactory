"""validate: check story.json against phrases.json and the series cast. Read-only, no output file."""

from pathlib import Path

from pydantic import ValidationError

from ..schemas import PhrasesModel, SeriesModel, StoryModel
from ..io import LIBRARY_FILES, custom_moves, library_of, load_series, outdoor_sets, unknown_actions
from ..validate import validate
from .runner import StageError

INPUTS = ["story.json", "phrases.json", "../series.json", *(f"../../{f}" for f in LIBRARY_FILES)]
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
    series = load_series(part_dir.parent / "series.json")
    if unknown := unknown_actions(story, library_of(part_dir)):  # the engine would throw mid-render
        raise StageError(f"unknown action: {', '.join(unknown)} (not built in, not in library/actions.json)")
    errors = validate(story, phrases, {c.id for c in series.cast}, outdoor_sets(library_of(part_dir)),
                      custom_moves(library_of(part_dir)))
    for e in errors:
        print(f"  {e.shot_id or '-'}  {e.rule}: {e.message}")
    if errors:
        raise StageError(f"{len(errors)} validation error(s)")
    print(f"ok: {len(story.shots)} shots, {story.duration_frames} frames")
