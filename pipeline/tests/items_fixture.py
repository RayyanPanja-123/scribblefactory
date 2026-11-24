"""World Item test fixtures (not library items): an escape pod (open / close, enter / exit), a bench (sit) and a
crystal (pickup / drop, held as the glow-crystal prop), plus a story using all of them. Used by test_items.py and
write_part() builds a renderable part from them (engine tests, stills)."""

import json
from pathlib import Path

from pipeline.scribble.schemas import CustomProp, WorldObject
from pipeline.scribble.stages import shots
from pipeline.tests.test_shots import SERIES, phrases_for

# anchors / seats match the engine drawers (engine/page/items.js pod, bench, crystal) at these sizes
POD = WorldObject(id="escape-pod", name="Escape pod", category="vehicle", look="card", draw="pod", size=1.6, layer="stage",
                  states=["closed", "open"], capabilities=["open", "close", "enter", "move"],
                  anchors={"handle": (0.27, 0.46)}, seats=[(0.0, 0.62)], clip_y=0.8)
BENCH = WorldObject(id="bench", name="Bench", category="furniture", look="card", draw="bench", size=0.6, layer="stage",
                    capabilities=["sit"], anchors={"seat": (0.0, 0.33)})
CRYSTAL = WorldObject(id="glow-crystal", name="Glow crystal", category="scifi", look="card", draw="crystal", size=0.45,
                      layer="stage", capabilities=["carry"], carry_mode="one-hand", anchors={"pickup": (0.0, 0.2)},
                      prop="glow-crystal", anims=[{"kind": "pulse", "amp": 0.06, "hz": 0.8}])
GLOW = CustomProp(id="glow-crystal", name="Glow crystal", shapes=[
    {"shape": "poly", "pts": [[-14, 0], [-8, -46], [0, -70], [8, -46], [14, 0]], "fill": "#7cf2ff", "width": 6}])
OBJECTS = {o.id: o for o in (POD, BENCH, CRYSTAL)}

STORY = """# Items

@set street
@cast bob
@item gem: glow-crystal
Bob found a glowing stone on the ground.
@do bob: pickup gem
Bob picked it up.
@item seat: bench
There was a bench.
@do bob: sit seat
Bob sat down to think it over.
@item pod: escape-pod
Then an escape pod landed.
@do bob: open pod
He opened the hatch.
@do bob: enter pod
He climbed inside.
@do pod: fly right
And the pod flew off with him, high over the rooftops.
"""


def plan(md=STORY):
    ph = phrases_for(md)
    return shots.plan(md, ph, SERIES, 1, objects=OBJECTS), ph


def write_part(root: Path, md=STORY) -> Path:
    """root/<library>: objects.json, props.json and a series with one planned part (story.json, phrases.json)"""
    story, ph = plan(md)
    (root / "objects.json").write_text(json.dumps({"schema_version": 1, "objects": [o.model_dump(mode="json") for o in OBJECTS.values()]}))
    (root / "props.json").write_text(json.dumps({"schema_version": 1, "props": [GLOW.model_dump(mode="json")]}))
    series = root / "demo"
    part = series / "part-01"
    part.mkdir(parents=True, exist_ok=True)
    (series / "series.json").write_text(SERIES.model_dump_json())
    (part / "story.json").write_text(json.dumps(story.model_dump(mode="json")))
    (part / "phrases.json").write_text(ph.model_dump_json())
    return part


if __name__ == "__main__":
    import sys
    print(write_part(Path(sys.argv[1])))
