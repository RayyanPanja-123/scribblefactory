"""library/settings.json: defaults, validation of what's read, and the per-PC recommendation."""
import json

from pipeline.scribble import settings as s


def test_recommend_clamps():
    assert s.recommend(8, 16, "NVIDIA GeForce RTX 3070") == 4  # half the threads
    assert s.recommend(64, 256, "NVIDIA GeForce RTX 4090") == s.MAX_AUTO
    assert s.recommend(16, 4, "NVIDIA GeForce RTX 3070") == 2  # RAM: 1.5 GB a worker
    assert s.recommend(32, 64, None) == 2  # GPU not known yet: safe until the first render reports it
    assert s.recommend(16, 32, "ANGLE (Intel, Intel(R) UHD Graphics 620)") == 2  # integrated GPU
    assert s.recommend(16, 32, "SwiftShader (software)") == 2
    assert s.recommend(1, None, None) == 1  # never 0


def test_load_defaults_and_workers(tmp_path):
    assert s.load(tmp_path) == s.DEFAULTS  # no file
    (tmp_path / "settings.json").write_text("{broken")
    assert s.load(tmp_path) == s.DEFAULTS
    (tmp_path / "settings.json").write_text(json.dumps({"render_workers": 6, "force_software_gl": True, "x": 1}))
    assert s.load(tmp_path) == {"render_workers": 6, "force_software_gl": True,  # unknown keys ignored
                                "socials": {"youtube": "", "instagram": "", "facebook": ""}}
    assert s.render_workers(tmp_path) == 6 and s.software_gl(tmp_path)
    for bad in (0, 17, True, "9"):  # out of range or wrong type: auto
        (tmp_path / "settings.json").write_text(json.dumps({"render_workers": bad}))
        assert 1 <= s.render_workers(tmp_path) <= s.MAX_AUTO and not s.software_gl(tmp_path)


def test_socials_trimmed_and_filled(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"socials": {"youtube": " @chan ", "tiktok": "x"}}))
    assert s.load(tmp_path)["socials"] == {"youtube": "@chan", "instagram": "", "facebook": ""}
    (tmp_path / "settings.json").write_text(json.dumps({"socials": "nope"}))
    assert s.load(tmp_path)["socials"] == {"youtube": "", "instagram": "", "facebook": ""}
