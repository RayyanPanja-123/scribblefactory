"""audio stage: synth music + SFX from cues, mix to -14 LUFS. Real ffmpeg, temp dirs only."""

import hashlib
import shutil
import subprocess

import numpy as np
import pytest

from pipeline.scribble.cli import main
from pipeline.scribble.io import load_part, save_part
from pipeline.scribble.schemas import PartModel, StoryModel
from pipeline.scribble.stages import audio

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")

SPF = audio.SPF
CAR = {"id": "car1", "kind": "car", "start_pos": [0, 0], "facing": "right", "variant": "red"}
CAM = {"angle": "wide", "move": "push_in", "speed": 0.3}
# 6 s: office 0-60, street 60-120 with the car driving, street 120-180 with it parked
STORY = {
    "duration_frames": 180, "seed": 1234,
    "shots": [
        {"id": "s01", "start_frame": 0, "end_frame": 60, "set": "office", "phrase_range": [0, 0], "camera": CAM},
        {"id": "s02", "start_frame": 60, "end_frame": 120, "set": "street", "phrase_range": [1, 1], "camera": CAM,
         "vehicles": [{**CAR, "action": "drive", "end_pos": [0, 0]}]},
        {"id": "s03", "start_frame": 120, "end_frame": 180, "set": "street", "phrase_range": [2, 2], "camera": CAM,
         "vehicles": [{**CAR, "action": "idle"}]},
    ],
    "cues": [{"frame": 0, "kind": "music_start"}, {"frame": 20, "kind": "bark"}, {"frame": 50, "kind": "pop"},
             {"frame": 60, "kind": "whoosh"}, {"frame": 120, "kind": "music_stop"}, {"frame": 120, "kind": "low_hit"}],
}


def make_part(lib):
    d = lib / "demo" / "part-01"
    d.mkdir(parents=True)
    save_part(d / "part.json", PartModel(id="part-01", number=1, title="T"))
    (d / "story.json").write_text(StoryModel.model_validate(STORY).model_dump_json(), encoding="utf-8")
    # speech-ish: a 3 Hz syllable-gated tone
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "aevalsrc='0.3*sin(220*2*PI*t)*(0.5+0.5*sin(6*PI*t))':d=6:s=44100",
                    "-c:a", "libmp3lame", "-b:a", "128k", str(d / "voice.mp3")], check=True)
    return d


def run(lib, force=False):
    return main(["run", "demo", "part-01", "--stage", "audio", "--library", str(lib)] + (["--force"] if force else []))


VOICE_HASH = []


@pytest.fixture(scope="module")
def part(tmp_path_factory):
    lib = tmp_path_factory.mktemp("lib")
    d = make_part(lib)
    VOICE_HASH.append(hashlib.sha256((d / "voice.mp3").read_bytes()).hexdigest())
    assert run(lib) == 0
    return d


def rms(x, f0, f1):
    return float(np.sqrt(np.mean(x[f0 * SPF:f1 * SPF] ** 2)))


def test_outputs_status_and_voice_untouched(part):
    for name in audio.OUTPUTS:
        assert (part / name).stat().st_size > 1000, name
    assert load_part(part / "part.json").stages.audio.status == "done"
    assert hashlib.sha256((part / "voice.mp3").read_bytes()).hexdigest() == VOICE_HASH[0]
    music = audio.decode(part / "audio/music.wav")
    voice = audio.decode(part / "voice.mp3")
    assert len(music) == len(voice)  # music runs the voice's length


def test_deterministic(part, tmp_path):
    d = make_part(tmp_path)
    shutil.copy(part / "voice.mp3", d / "voice.mp3")  # same input bytes
    assert run(tmp_path) == 0
    for name in ("audio/music.wav", "audio/sfx.wav"):
        assert (d / name).read_bytes() == (part / name).read_bytes(), name


def test_music_follows_cues(part):
    m = audio.decode(part / "audio/music.wav")
    assert rms(m, 0, 118) > 0.05
    assert rms(m, 122, 180) < 1e-4  # stopped (30 ms fade = ~1 frame) and never restarted


def test_music_restarts_only_at_a_later_start():
    story = StoryModel.model_validate({**STORY, "cues": STORY["cues"] + [{"frame": 150, "kind": "music_start"}]})
    m = audio.render_music(story, 180 * SPF)
    assert audio.music_segments(story) == [(0, 120), (150, 180)]
    assert rms(m, 122, 150) == 0 and rms(m, 151, 180) > 0.05


def test_sfx_at_cues_and_car(part):
    s = audio.decode(part / "audio/sfx.wav")
    quiet = rms(s, 5, 15)  # nothing scheduled here
    assert quiet < 1e-4
    for f in (20, 29, 38):  # 3 yaps, 9 frames apart
        assert rms(s, f, f + 3) > 0.01, f
    assert rms(s, 50, 52) > 0.01   # pop
    assert rms(s, 57, 63) > 0.01   # whoosh around the set change
    assert rms(s, 120, 130) > 0.1  # low hit
    drive, idle = rms(s, 75, 115), rms(s, 150, 178)
    assert drive > 0.01 and 0 < idle < drive  # car putters while driving, quieter when parked


def test_breakdown_sputters_then_dies():
    shots = [*STORY["shots"][:2], {**STORY["shots"][2], "vehicles": [{**CAR, "action": "broken"}]}]
    story = StoryModel.model_validate({**STORY, "shots": shots, "cues": []})
    assert audio.breakdown_frames(story) == [120]
    assert audio.car_levels(story)[140:].max() == 0  # engine loop off once broken
    s = audio.render_sfx(story, 180 * SPF)
    assert rms(s, 120, 170) > 0.01  # sputter + backfire over the dead engine


def test_mix_loudness(part):
    lufs, tp = audio.loudness(part / "audio/mix.wav")
    assert abs(lufs - audio.TARGET_LUFS) <= 0.5
    assert tp <= -1.0


def test_skips_when_up_to_date(part, capsys):
    assert run(part.parents[1]) == 0
    assert "audio: skipped" in capsys.readouterr().out


def test_peaky_voice_still_reaches_the_target(tmp_path):
    """real speech with high peaks (the hello.wav fixture): linear loudnorm alone stops short of -14 LUFS at the
    true-peak ceiling, so the stage falls back to loudnorm's dynamic mode (its limiter)"""
    d = make_part(tmp_path)
    fixture = __import__("pathlib").Path(__file__).parent / "fixtures" / "hello.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(fixture), "-c:a", "libmp3lame", "-b:a", "128k",
                    str(d / "voice.mp3")], check=True)
    assert run(tmp_path) == 0, load_part(d / "part.json").stages.audio.error
    lufs, tp = audio.loudness(d / "audio/mix.wav")
    assert abs(lufs - audio.TARGET_LUFS) <= audio.LUFS_TOL and tp <= audio.TARGET_TP
