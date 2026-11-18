"""Write docs/schemas/*.schema.json from the models. Run: python -m pipeline.scribble.schemas.export"""

import json
from pathlib import Path

from . import ActionLibrary, CreatureLibrary, PartModel, PhrasesModel, PropLibrary, SeriesModel, SetLibrary, StoryModel

OUT_DIR = Path(__file__).resolve().parents[3] / "docs" / "schemas"
MODELS = {"series.schema.json": SeriesModel, "part.schema.json": PartModel, "phrases.schema.json": PhrasesModel,
          "story.schema.json": StoryModel, "props.schema.json": PropLibrary,
          "sets.schema.json": SetLibrary, "creatures.schema.json": CreatureLibrary,
          "actions.schema.json": ActionLibrary}


def render() -> dict[str, str]:
    return {name: json.dumps(m.model_json_schema(), indent=2, sort_keys=True) + "\n" for name, m in MODELS.items()}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in render().items():
        (OUT_DIR / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT_DIR / name}")


if __name__ == "__main__":
    main()
