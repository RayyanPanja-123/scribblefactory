import json
import shutil
import subprocess

import pytest

from pipeline.scribble import sfx
from pipeline.scribble.stages.runner import StageError
from pipeline.scribble.storycheck import check_story
from pipeline.tests.test_storycheck import setup

ENTRIES = {e.id: e for e in sfx.load_sfx("/nonexistent").sfx}  # the seed


def test_seed_registry():
    assert len(ENTRIES) == 14
    assert ENTRIES["riser"].anchor == ENTRIES["metallic_riser"].anchor == "end_on_line"
    assert ENTRIES["camera_flash"].file == "Camera Flash.mp3" and ENTRIES["camera_flash"].anchor == "start"


def test_parse_directive():
    assert sfx.parse_sfx("riser", 3) == ("riser", None)
    assert sfx.parse_sfx("pop 0.5", 3, ENTRIES) == ("pop", 0.5)
    for bad in ("", "pop loud", "pop 1.5", "pop 0.5 x"):
        with pytest.raises(StageError, match="line 3: @sfx: expected"):
            sfx.parse_sfx(bad, 3)
    with pytest.raises(StageError, match="line 7: @sfx: unknown sound 'boing'"):
        sfx.parse_sfx("boing", 7, ENTRIES)


MD = """# T

@set office
@sfx fahhh
@fx shake
Bob found gold.
Amy laughed.
@sfx riser 0.4
!! It was fake.
"""


def test_directives_belong_to_next_line():
    assert sfx.directives(MD) == [(4, "fahhh", None, 6), (8, "riser", 0.4, 9)]
    assert sfx.directives("Hi.\n@sfx pop\n") == [(2, "pop", None, None)]


def test_line_times_from_phrases():
    words = [{"start": s, "end": round(s + 0.2, 2)} for s in (0.0, 0.3, 0.6, 1.0, 1.4, 2.0, 2.3, 2.6)]  # Bob found gold. Amy laughed. It was fake.
    assert sfx.line_times(MD, words) == {6: (0.0, 0.8), 7: (1.0, 1.6), 9: (2.0, 2.8)}
    assert sfx.line_times(MD, words[:-1]) is None  # stale timing


def test_anchor_timing():
    line = (5.0, 7.5)
    assert sfx.play_at("start", line, 2.0) == (5.0, 0.0)
    assert sfx.play_at("end_on_line", line, 2.0) == (3.0, 0.0)  # ends exactly at the line start
    assert sfx.play_at("after_line", line, 2.0) == (7.5, 0.0)  # once the line has been said
    assert sfx.play_at("end_on_line", (1.0, 2.0), 2.5) == (0.0, 1.5)  # pre-roll before 0 s loses its head
    assert ENTRIES["fahhh"].anchor == "after_line"


STORY = """# T

@set office
Bob counted the money.
@set street
@fx lightning
Amy ran outside.
Bob followed.
Amy stopped.
!! Bob was a traitor all along.
"""


def starts_every(md, step):
    return {no: (i * step, i * step + step / 2) for i, no in enumerate(sorted(sfx.line_words(md)))}


def test_suggestion_rules():
    got = sfx.suggest(STORY, ENTRIES, starts_every(STORY, 3.0), first_part=True)
    # camera_flash (set change) would start with the lightning's bass_impact on line 7: within 1.5 s, so dropped
    # fahhh plays after its line, so the same line's start still has room for money
    assert [(s["line"], s["id"]) for s in got] == [(4, "money"), (4, "fahhh"), (7, "bass_impact"), (10, "riser"), (10, "among_us")]
    calm = STORY.replace("@fx lightning\n", "")
    got = sfx.suggest(calm, ENTRIES, starts_every(calm, 3.0), first_part=True)
    assert (6, "camera_flash") in [(s["line"], s["id"]) for s in got]
    assert all(s["text"] for s in got)
    # not part 1: no hook; the money line gets money instead
    got = sfx.suggest(STORY, ENTRIES, starts_every(STORY, 3.0))
    assert (4, "money") in [(s["line"], s["id"]) for s in got] and "fahhh" not in [s["id"] for s in got]


def test_suggestion_limit_spacing_and_rejections():
    # lines 0.5 s apart: the riser (2 s pre-roll) and the twist hit are the only ones far enough apart
    got = sfx.suggest(STORY, ENTRIES, starts_every(STORY, 0.5), first_part=True)
    ats = sorted(s["at"] for s in got)
    assert all(b - a >= sfx.MIN_GAP_S for a, b in zip(ats, ats[1:]))
    # written ones count toward the limit of 5
    written = STORY.replace("Bob followed.", "@sfx pop\nBob followed.").replace("Amy stopped.", "@sfx click\n@sfx wrong\n@sfx core\nAmy stopped.")
    assert len(sfx.suggest(written, ENTRIES, starts_every(written, 3.0), first_part=True)) == 1
    # a line that already has an sfx gets none; rejected ones never come back
    got = sfx.suggest(STORY, ENTRIES, starts_every(STORY, 3.0), first_part=True, rejected={"fahhh|Bob counted the money."})
    assert "fahhh" not in [s["id"] for s in got]


def test_insert():
    out = sfx.insert(STORY, 8, "Bob followed.", "pop")
    assert out.split("\n")[7:9] == ["@sfx pop", "Bob followed."]
    with pytest.raises(ValueError, match="changed"):
        sfx.insert(STORY, 8, "Amy stopped.", "pop")


def test_mix_cmd():
    clips = [{"path": "a.mp3", "delay": 1.25, "trim": 0.0, "gain": 0.5},
             {"path": "b.mp3", "delay": 0.0, "trim": 0.4, "gain": 1.0}]
    cmd = sfx.mix_cmd(clips, "voice.wav", "out.wav")
    assert cmd[cmd.index("-i") + 1] == "voice.wav" and cmd[-1] == "out.wav"
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "[1:a]asetpts" in graph and "volume=0.5000,adelay=1250|1250[s1]" in graph
    assert "[2:a]atrim=start=0.400," in graph and "adelay=0|0[s2]" in graph
    assert "[s1][s2]amix=inputs=2:normalize=0" in graph
    assert "[sfx][key]sidechaincompress" in graph and cmd[cmd.index("-map") + 1] == "[out]"
    one = sfx.mix_cmd(clips[:1], "v.wav", "o.wav")
    assert "[s1]anull[sfx]" in one[one.index("-filter_complex") + 1]


def test_missing_files_warn_not_crash(tmp_path):
    assert len(sfx.missing_files(tmp_path)) == 14
    (tmp_path / "sfx").mkdir()
    (tmp_path / "sfx" / "Pop.mp3").write_bytes(b"x")
    assert not any("Pop.mp3" in w for w in sfx.missing_files(tmp_path))


def test_check_story(tmp_path):
    pdir = setup(tmp_path, "# T\n\n@set office\n@cast bob, amy\n@sfx pop\n@sfx boing\nBob waved.\n" + "@sfx click\n" * 12
                 + "Amy waved.\n@sfx pop\n")
    r = check_story(pdir)
    msgs = [(p["line"], p["message"]) for p in r["problems"]]
    assert (6, "@sfx: unknown sound 'boing' (sounds: " + ", ".join(ENTRIES) + ")") in msgs
    assert any(line == 19 and "at most 12 per part" in m for line, m in msgs)
    assert (21, "@sfx has no narration line after it to play on") in msgs
    assert any(w["line"] == 5 and "Pop.mp3 is missing" in w["message"] for w in r["warnings"])


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")
def test_stem_mixes_under_the_voice(tmp_path):
    import numpy as np
    pdir = setup(tmp_path, "# T\n\n@set office\n@cast bob\nBob waved.\n@sfx pop\nAmy waved.\n")
    tone = lambda f, s, out: subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",  # noqa: E731
                                             f"sine=frequency={f}:duration={s}", "-ar", "48000", "-ac", "2", str(out)], check=True)
    tone(220, 3, pdir / "voice-tight.wav")
    (tmp_path / "sfx").mkdir()
    tone(880, 0.3, tmp_path / "sfx" / "Pop.mp3")
    (pdir / "phrases.json").write_text(json.dumps({"words": [{"start": s, "end": s + 0.4} for s in (0.0, 0.5, 2.0, 2.5)]}))
    from pipeline.scribble.stages.audio import decode
    voice = decode(pdir / "voice-tight.wav")
    x = sfx.stem(pdir, voice)
    assert x.shape == voice.shape
    assert np.abs(x[:int(1.9 * 48000)]).max() < 1e-3          # silent before its line
    assert 0 < np.abs(x[int(2.0 * 48000):]).max() < np.abs(voice).max()  # plays at 2 s, under the voice peak


def test_package_validates_sfx_ids(tmp_path):
    from pipeline.scribble import package
    from pipeline.tests.test_package import pkg, script
    good = script("Part 1", "x").replace("@cast ava, ben", "@cast ava, ben\n@sfx fahhh")
    r = package.parse(pkg(script1=good), tmp_path)
    assert r["ok"], r["errors"]
    assert any("FAHHH.mp3 is missing" in w["message"] for w in r["warnings"])
    text = pkg(script1=good.replace("@sfx fahhh", "@sfx boing"))
    e = next(e for e in package.parse(text, tmp_path)["errors"] if "boing" in e["message"])
    assert e["section"] == "PART 1 SCRIPT" and text.split("\n")[e["line"] - 1] == "@sfx boing"
