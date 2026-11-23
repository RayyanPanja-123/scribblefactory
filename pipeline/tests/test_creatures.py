import json
import subprocess
from pathlib import Path

import pytest

from pipeline.scribble.io import (cast_body_problems, creature_bodies, delete_creature, load_creatures, load_series,
                                  save_creature, save_series)
from pipeline.scribble.schemas import (BUILTIN_CREATURES, RIG_PARTS, CastMember, CustomCreature, SeriesModel)

ROOT = Path(__file__).resolve().parents[2]
DOG = {"id": "dog", "name": "Dog", "rig": "quadruped",
       "joints": {"hip": [-80, -110], "shoulder": [80, -110], "neck": [100, -150]},
       "parts": {"body": [{"shape": "ellipse", "pts": [[0, -130]], "r": 120, "ry": 50, "fill": "$main"}],
                 "head": [{"shape": "circle", "pts": [[30, -40]], "r": 50, "fill": "$main"}],
                 "leg_front": [{"shape": "rect", "pts": [[-10, 0], [10, 110]], "fill": "$main"}],
                 "leg_back": [{"shape": "rect", "pts": [[-10, 0], [10, 110]], "fill": "$main"}]}}


def test_engine_rigs_and_builtins_match_the_schema():
    """engine/page/creatures.js and the schema each keep the rig parts and the built-in list: they must agree"""
    js = ("import('./engine/page/creatures.js').then((m) => console.log(JSON.stringify({rigs: Object.fromEntries("
          "Object.entries(m.RIGS).map(([k, v]) => [k, v.parts])), builtin: Object.fromEntries(m.BUILTIN.map((c) => "
          "[c.id, [c.rig, !!c.parts.stump]]))})))")
    out = json.loads(subprocess.run(["node", "-e", js], cwd=ROOT, capture_output=True, text=True, check=True).stdout)
    assert out["rigs"] == RIG_PARTS
    assert {k: tuple(v) for k, v in out["builtin"].items()} == BUILTIN_CREATURES


def test_creature_must_fit_its_rig():
    CustomCreature.model_validate(DOG)
    for change, msg in [({"rig": "bird"}, "not a bird part"), ({"parts": {**DOG["parts"], "tail": []}, "joints": {**DOG["joints"], "tail": [0, 0]}}, "1 to 60"),
                        ({"joints": {"hip": [0, 0], "neck": [0, 0]}}, "shoulder missing"),
                        ({"joints": {**DOG["joints"], "tail": [0, 0]}}, "not used"), ({"id": "cat"}, "built-in")]:
        with pytest.raises(ValueError, match=msg):
            CustomCreature.model_validate({**DOG, **change})
    with pytest.raises(ValueError, match="needs leg_back"):
        CustomCreature.model_validate({**DOG, "parts": {k: v for k, v in DOG["parts"].items() if k != "leg_back"}})


def test_humanoid_is_a_stickman_with_a_build():
    giant = CustomCreature.model_validate({"id": "giant", "name": "Giant", "rig": "humanoid", "build": {"leg": 1.3, "head_color": "#d9a066"}})
    assert giant.build.leg == 1.3 and giant.build.arm == 1
    assert CustomCreature.model_validate({"id": "kid", "name": "Kid", "rig": "humanoid"}).build.head == 1  # default build
    for bad, msg in [({"parts": DOG["parts"]}, "no parts"), ({"build": {"leg": 2}}, "less than or equal"),
                     ({"id": "human"}, "built-in"), ({"id": "stickman"}, "built-in")]:
        with pytest.raises(ValueError, match=msg):
            CustomCreature.model_validate({"id": "x", "name": "X", "rig": "humanoid", **bad})
    with pytest.raises(ValueError, match="humanoid only"):
        CustomCreature.model_validate({**DOG, "build": {}})


def _series(tmp_path, body, approved=True):
    s = SeriesModel.model_validate({"slug": "pets", "title": "Pets", "created_at": "2026-11-18T10:00:00Z",
                                    "voice": {"voice_name": ""}, "style": {"preset": "default"},
                                    "cast": [{"id": "rex", "name": "Rex", "top": {"color": "#aa5500"}, "eyes": "dots",
                                              "body": body, "approved_at": "2026-11-18T10:00:00Z" if approved else None}]})
    (tmp_path / "database" / "storage" / "pets").mkdir(parents=True)
    save_series(tmp_path / "database" / "storage" / "pets" / "series.json", s)
    return tmp_path / "database" / "storage" / "pets" / "series.json"


def test_library_save_clears_approvals_and_delete_is_refused_while_used(tmp_path):
    dog = CustomCreature.model_validate(DOG)
    assert save_creature(tmp_path, dog) == []
    f = _series(tmp_path, "dog")
    assert creature_bodies(tmp_path)["dog"] == ("quadruped", False)
    assert save_creature(tmp_path, dog.model_copy(update={"name": "Doggo"})) == []  # a new name keeps the look
    assert save_creature(tmp_path, dog.model_copy(update={"accent": "#000000"})) == ["pets/rex"]
    assert load_series(f).cast[0].approved_at is None
    with pytest.raises(ValueError, match="pets/rex"):
        delete_creature(tmp_path, "dog")
    f.unlink()
    delete_creature(tmp_path, "dog")
    assert load_creatures(tmp_path).creatures == []


def test_cast_body_problems(tmp_path):
    cast = [CastMember(id="a", name="A", top={"color": "#111111"}, eyes="dots", body="unicorn"),
            CastMember(id="b", name="B", top={"color": "#111111"}, eyes="dots", body="dog", headless=True),
            CastMember(id="c", name="C", top={"color": "#111111"}, eyes="dots", body="chicken", headless=True)]
    save_creature(tmp_path, CustomCreature.model_validate(DOG))
    problems = cast_body_problems(cast, tmp_path)
    assert len(problems) == 2 and "unknown body 'unicorn'" in problems[0] and "no stump" in problems[1]
