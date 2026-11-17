"""finish (captions, encode, QA), thumbnails, and the posting CLI commands. Tiny synthetic parts in temp dirs."""

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone

import pytest

from pipeline.scribble.cli import main
from pipeline.scribble.io import load_part, load_series, save_part, save_series
from pipeline.scribble.schemas import PartModel, PhrasesModel, SeriesModel, Stage, StoryModel, Style, Voice
from pipeline.scribble.stages import finish, prep, shots, thumbnails
from pipeline.scribble.stages.runner import StageError

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                  reason="ffmpeg/ffprobe not on PATH")

FRAMES = 60  # 2 s
TEXT = "Old John Smith ran far, then he stopped. Really? Yes... the end."
ACTOR = {"action": "talk", "start_pos": [0, 0], "facing": "camera", "expression": "neutral"}
CAM = {"move": "push_in", "speed": 0.3}
STORY = {"duration_frames": FRAMES, "seed": 7, "shots": [
    {"id": "s01", "start_frame": 0, "end_frame": 20, "set": "office", "phrase_range": [0, 0],
     "camera": {**CAM, "angle": "close"}, "actors": [{**ACTOR, "cast_id": "bob"}]},
    {"id": "s02", "start_frame": 20, "end_frame": 40, "set": "office", "phrase_range": [1, 1],
     "camera": {**CAM, "angle": "wide"}, "actors": [{**ACTOR, "cast_id": "bob"}, {**ACTOR, "cast_id": "amy"}]},
    {"id": "s03", "start_frame": 40, "end_frame": 60, "set": "office", "phrase_range": [2, 2], "twist": True,
     "camera": {**CAM, "angle": "low"},
     "actors": [{**ACTOR, "cast_id": "bob"}, {**ACTOR, "cast_id": "amy", "expression": "surprised"}]},
]}


def phrases(text=TEXT, ranges=((0, 6), (7, 7), (8, 11)), step=0.155) -> PhrasesModel:
    """TEXT: 12 words over ~1.9 s; phrase 0 has 7 words, so it splits into 2 caption chunks"""
    words, t = [], 0.0
    for w in text.split():
        words.append({"text": w, "start": round(t, 3), "end": round(t + step * 0.8, 3)})
        t += step
    return PhrasesModel(duration=round(t + 0.1, 3), words=words, phrases=[
        {"text": "", "start": words[a]["start"], "end": words[b]["end"], "word_start": a, "word_end": b}
        for a, b in ranges])


def story(**changes) -> StoryModel:
    return StoryModel.model_validate({**STORY, **changes})


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def tone(path, amp):
    ff("-f", "lavfi", "-i", f"aevalsrc='{amp}*sin(440*2*PI*t)':d=2:s=48000:c=stereo", path)


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    lib = tmp_path_factory.mktemp("tpl")
    sd = lib / "demo"
    pd = sd / "part-01"
    (pd / "frames" / "chunks").mkdir(parents=True)
    (pd / "audio").mkdir()
    save_series(sd / "series.json", SeriesModel(slug="demo", title="Demo Tales", created_at=datetime.now(timezone.utc),
                                                parts=["part-01", "part-02"], voice=Voice(voice_name="v"),
                                                style=Style(preset="default")))
    part = PartModel(id="part-01", number=1, title="T")
    part.stages.render = Stage(status="done")
    part.stages.audio = Stage(status="done")
    save_part(pd / "part.json", part)
    (pd / "story.json").write_text(StoryModel.model_validate(STORY).model_dump_json(), encoding="utf-8")
    (pd / "phrases.json").write_text(phrases().model_dump_json(), encoding="utf-8")
    (pd / "script-for-tts.txt").write_text(TEXT + "\n", encoding="utf-8")
    ff("-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30", "-frames:v", FRAMES, "-start_number", 0,
       pd / "frames" / "%06d.png")
    ff("-f", "lavfi", "-i", "color=black:s=1080x1920", "-frames:v", 1, lib / "black.png")
    (pd / "frames" / "chunks" / "c000.json").write_text('{"first": 0, "last": 59}', encoding="utf-8")
    tone(pd / "audio" / "mix.wav", 0.21)  # stereo: ~ -14 LUFS, -13.5 dBTP
    ff("-i", pd / "audio" / "mix.wav", "-c:a", "libmp3lame", pd / "voice.mp3")
    return lib


@pytest.fixture
def lib(template, tmp_path, monkeypatch):
    monkeypatch.setattr(finish, "PRESET", "ultrafast")
    shutil.copytree(template, tmp_path / "lib")
    return tmp_path / "lib"


def pdir(lib):
    return lib / "demo" / "part-01"


def cli(lib, *args):
    return main([*args, "--library", str(lib)])


def stage(lib, *args):
    return cli(lib, "run", "demo", "part-01", "--stage", *args)


def qa(lib):
    return json.loads((pdir(lib) / "qa.json").read_text(encoding="utf-8"))


# ---------------- captions ----------------

def test_caption_text():
    assert [finish.caption_text(w) for w in ["far,", "stopped.", "Really?", "Yes...", "wow!", "a{b}\\c"]] == \
        ["far", "stopped", "Really?", "Yes...", "wow!", "abc"]


def test_chunks_max_words_names_and_timing():
    p = phrases()
    cs = finish.chunks(p)
    assert [(c["first"], c["last"]) for c in cs] == [(0, 3), (4, 6), (7, 7), (8, 11)]  # "John Smith" kept together
    assert finish.caption_check(p, cs) is None
    words = p.words
    for a, b in zip(cs, cs[1:]):
        assert a["end"] <= b["start"]                                   # never overlaps the next chunk
        assert a["end"] == min(words[a["last"]].end + finish.CAP_HOLD, b["start"])
    assert cs[-1]["end"] == pytest.approx(words[-1].end + finish.CAP_HOLD)  # last one holds fully


def test_chunk_never_splits_a_name():
    words = [{"text": w} for w in "we met King Charles Edward Albert Smith today".split()]
    for a, b in finish.chunk_words(words, 0, len(words) - 1):
        assert b - a + 1 <= finish.CAP_MAX_WORDS
    cuts = [b for _, b in finish.chunk_words(words, 0, len(words) - 1)][:-1]
    assert all(not finish._splits_name(words, i) for i in cuts)


def test_ass_file():
    text = finish.ass(phrases(), story(), ["none"] * 12)  # no effects: one event per word
    assert text.startswith("[Script Info]") and "[V4+ Styles]" in text and "[Events]" in text
    assert f"Style: Caption,{finish.CAP_FONT},{finish.CAP_SIZE}," in text
    events = [x for x in text.splitlines() if x.startswith("Dialogue:")]
    assert len(events) == 12  # one per word, its word highlighted
    assert all(e.count(f"\\1c{finish.YELLOW}&") == 1 for e in events)
    assert "far," not in text and "stopped." not in text and "Yes..." in text and "Really?" in text
    assert all(e.count("\\N") <= 1 for e in events)


def test_subtitles_filter_escapes_windows_paths(tmp_path):
    f = finish.subtitles_filter(tmp_path / "captions.ass")
    assert f.startswith("subtitles=filename='") and ":fontsdir='" in f
    assert "\\:" in f or ":" not in str(tmp_path)


# ---------------- finish + QA ----------------

def test_finish_gate(lib):
    part = load_part(pdir(lib) / "part.json")
    part.stages.audio = Stage(status="pending")
    save_part(pdir(lib) / "part.json", part)
    with pytest.raises(StageError, match="audio not done yet"):
        finish.run(pdir(lib))
    assert stage(lib, "finish") == 1
    assert not (pdir(lib) / "final.mp4").exists()


@needs_ffmpeg
def test_finish_ok(lib, capsys):
    assert stage(lib, "finish") == 0
    d = pdir(lib)
    report = qa(lib)
    assert report["ok"], report
    assert (d / "captions.ass").exists() and (d / "final.mp4").stat().st_size > 10_000
    part = load_part(d / "part.json")
    assert part.stages.finish.status == "done" and part.approvals.final.approved_at is None  # never approves
    # frame count off: QA sees it (no re-encode needed)
    story = StoryModel.model_validate({**STORY, "duration_frames": FRAMES + 1})
    assert not finish.qa(d, story, phrases(), True)["checks"]["frame_count"]["ok"]


@needs_ffmpeg
def test_qa_catches_frozen_segment(lib):
    frames = pdir(lib) / "frames"
    for n in range(11, 50):  # 1.3 s of the same frame
        shutil.copy(frames / "000010.png", frames / f"{n:06d}.png")
    assert stage(lib, "finish") == 1
    assert not qa(lib)["checks"]["frozen"]["ok"]
    assert (pdir(lib) / "final.mp4").exists()  # kept for inspection
    assert load_part(pdir(lib) / "part.json").stages.finish.status == "failed"


@needs_ffmpeg
def test_qa_catches_black_segment(lib):
    for n in range(20, 35):  # 0.5 s black
        shutil.copy(lib / "black.png", pdir(lib) / "frames" / f"{n:06d}.png")
    assert stage(lib, "finish") == 1
    checks = qa(lib)["checks"]
    assert not checks["black"]["ok"] and checks["frozen"]["ok"]


@needs_ffmpeg
def test_qa_catches_loudness(lib):
    tone(pdir(lib) / "audio" / "mix.wav", 0.05)  # ~ -29 LUFS
    assert stage(lib, "finish") == 1
    checks = qa(lib)["checks"]
    assert not checks["loudness"]["ok"] and checks["true_peak"]["ok"]


@needs_ffmpeg
def test_captions_off(lib, monkeypatch):
    calls = []
    real = finish._ffmpeg
    monkeypatch.setattr(finish, "_ffmpeg", lambda *a: calls.append(a) or real(*a))
    (pdir(lib) / "captions.ass").write_text("stale", encoding="utf-8")
    assert cli(lib, "set-captions", "demo", "off") == 0
    assert load_series(lib / "demo" / "series.json").style.captions is False
    assert stage(lib, "finish") == 0
    encode = next(a for a in calls if "libx264" in a)
    assert not any("subtitles=" in str(x) for x in encode)
    assert not (pdir(lib) / "captions.ass").exists()
    assert qa(lib)["checks"]["captions"]["value"] == "off"
    # the setting is part of the inputs hash: back on -> finish runs again
    assert cli(lib, "set-captions", "demo", "on") == 0
    assert stage(lib, "finish") == 0
    assert (pdir(lib) / "captions.ass").exists()


# ---------------- thumbnails ----------------

def test_pick_frames():
    story = StoryModel.model_validate(STORY)
    assert thumbnails.pick_frames(story) == [49, 29, 49]  # twist s03, first wide s02, most actors + expressive s03
    no_twist = StoryModel.model_validate({**STORY, "shots": [{**s, "twist": False} for s in STORY["shots"]]})
    assert thumbnails.pick_frames(no_twist)[0] == FRAMES // 2


def test_thumbnails_and_upload_md(lib):
    d = pdir(lib)
    assert stage(lib, "thumbnails") == 0
    for k, n in enumerate([49, 29, 49], 1):
        assert (d / "thumbs" / f"thumb-{k}.png").read_bytes() == (d / "frames" / f"{n:06d}.png").read_bytes()
    text = (d / "upload.md").read_text(encoding="utf-8")
    assert "## YouTube" in text and "## Instagram" in text
    assert text.count("Title: Demo Tales — Part 1") == 2
    assert text.count("Old John Smith ran far, then he stopped. Part 1 of 2.") == 2
    assert text.count(thumbnails.HASHTAGS) == 2
    (d / "upload.md").write_text("my edits", encoding="utf-8")
    assert stage(lib, "thumbnails", "--force") == 0
    assert (d / "upload.md").read_text(encoding="utf-8") == "my edits"


# ---------------- CLI ----------------

def test_pick_thumbnail(lib):
    assert cli(lib, "pick-thumbnail", "demo", "part-01", "2") == 1  # no thumbs yet
    assert stage(lib, "thumbnails") == 0
    assert cli(lib, "pick-thumbnail", "demo", "part-01", "2") == 0
    assert load_part(pdir(lib) / "part.json").thumbnail_choice == "thumbs/thumb-2.png"


def test_mark_posted(lib):
    args = ("mark-posted", "demo", "part-01", "youtube")
    assert cli(lib, *args, "--url", "not a url") == 1
    assert cli(lib, *args, "--url", "https://youtu.be/a", "--date", "2026-11-01") == 0
    post = load_part(pdir(lib) / "part.json").posted.youtube
    assert (post.url, post.posted_at) == ("https://youtu.be/a", datetime(2026, 11, 1, tzinfo=timezone.utc))
    assert cli(lib, *args, "--url", "https://youtu.be/b") == 1  # refuses to overwrite
    assert load_part(pdir(lib) / "part.json").posted.youtube.url == "https://youtu.be/a"
    assert cli(lib, *args, "--url", "https://youtu.be/b", "--force") == 0
    post = load_part(pdir(lib) / "part.json").posted.youtube
    assert post.url == "https://youtu.be/b" and post.posted_at.date() == datetime.now(timezone.utc).date()
    assert cli(lib, "mark-posted", "demo", "part-01", "instagram", "--url", "https://instagram.com/p/x") == 0
    assert load_part(pdir(lib) / "part.json").posted.instagram.url == "https://instagram.com/p/x"


@needs_ffmpeg
def test_clean_frames(lib, capsys):
    d = pdir(lib)
    assert cli(lib, "clean-frames", "demo", "part-01") == 1  # no final yet
    assert (d / "frames").exists()
    assert stage(lib, "finish") == 0
    assert stage(lib, "thumbnails") == 0
    (d / "preview.mp4").write_bytes(b"preview")
    before = {p.relative_to(d) for p in d.rglob("*") if "frames" not in p.parts}
    capsys.readouterr()
    assert cli(lib, "clean-frames", "demo", "part-01") == 0
    assert "MB freed" in capsys.readouterr().out
    assert not (d / "frames").exists()
    assert {p.relative_to(d) for p in d.rglob("*")} == before  # everything else kept


def test_first_sentence_skips_ellipsis():
    assert thumbnails.first_sentence("It was bad... so bad. Then more.") == "It was bad... so bad."
    assert thumbnails.first_sentence("Really?  Yes.") == "Really?"


# ---------------- caption effects ----------------

def events(text, at=None):
    """Dialogue lines, or only those starting at h:mm:ss.cc `at`"""
    return [x for x in text.splitlines() if x.startswith("Dialogue:") and (at is None or x.split(",")[1] == at)]


def body(event):
    return event.split(",,0,0,0,,", 1)[1]


def plain_story(**changes):
    """STORY without the twist (for phrase sets that don't have its phrase 2)"""
    return story(shots=[{**s, "twist": False} for s in STORY["shots"]], **changes)


def test_fx_pop_default():
    text = finish.ass(phrases(), plain_story())
    first = [e for e in events(text) if e.split(",")[1] < "0:00:00.20"]  # chunk 1's first 6 frames
    scales = [int(m[1]) for e in first if (m := re.match(r"\{\\fscx(\d+)\\fscy\1\}", body(e)))]
    assert scales[0] == 80 and set(scales) == {80, 90, 110, 105}  # 80 -> 110 -> 100 (100 needs no tag)
    assert r"\pos" not in text and r"\frz" not in text  # no drop / shake without a twist or emphasis


def test_fx_twist_drop_and_shake_at_low_hit():
    st = story(cues=[{"frame": 40, "kind": "low_hit"}])
    ph = phrases()
    plan = finish.plan_fx(ph, st, [None] * 12)
    assert [p["entrance"] for p in plan] == ["pop", "pop", "pop", "drop"]  # twist = phrase 2 = chunk 4
    assert plan[3]["shakes"] == [{"start": 40, "frames": round(finish.FX_SHAKE_S * 30)}]
    calm = finish.ass(ph, story())  # no low_hit: the drop alone
    assert body(events(calm, "0:00:01.24")[0]).startswith(r"{\pos(513,1106)}")  # chunk 4 appears 200 px high
    assert any(r"\pos(513,1276)" in e for e in events(calm))                     # ... and bounces
    text = finish.ass(ph, st)
    shook = [e for e in events(text) if r"\frz" in e]
    assert len(shook) >= 8 and all("0:00:01.33" <= e.split(",")[1] < "0:00:01.70" for e in shook)  # 0.35 s


def test_fx_punch_and_shake_rate_limit():
    ph = phrases("He took a nap then chased the dogs", ((0, 3), (4, 7)), step=0.2)
    plan = finish.plan_fx(ph, plain_story(), [None] * 8)
    assert [ph.words[i].text for p in plan for i in p["punch"]] == ["nap", "chased", "dogs"]
    assert [s["start"] for p in plan for s in p["shakes"]] == [18]  # nap at 0.6 s; the others within 2 s: dropped
    text = finish.ass(ph, plain_story())
    nap = [e for e in events(text) if r"\fscx130\fscy130" in e]
    assert nap and rf"\1c{finish.RED}&}}nap" in nap[0]
    assert any(rf"\1c{finish.YELLOW}&}}nap" in e for e in events(text))  # settles back to yellow


def test_fx_shake_gap_allows_later_shakes():
    ph = phrases("nap " + "x " * 12 + "nap", ((0, 13),), step=0.2)
    shakes = [s["start"] for p in finish.plan_fx(ph, plain_story(), [None] * 14) for s in p["shakes"]]
    assert shakes == [0, 78]  # 2.6 s apart: both kept


def test_fx_directive_override():
    md = ("# T\n\n@fx none\n@set office\nOld John Smith ran far, then he stopped.\n@fx shake\nReally?\n"
          "Yes... the end.\n")
    assert "@" not in prep.strip_directives(md)
    ov = finish.fx_overrides(md, 12)
    assert ov == ["none"] * 8 + ["shake"] + [None] * 3
    plan = finish.plan_fx(phrases(), story(cues=[{"frame": 40, "kind": "low_hit"}]), ov)
    assert [p["entrance"] for p in plan] == [None, None, None, "pop"]  # the override beats the twist drop
    assert plan[3]["shakes"] == [{"start": 38, "frames": round(finish.FX_SHAKE_S * 30)}]  # at the chunk, not low_hit
    words, _ = shots.tag_words(md, ["bob"], ["bob"])  # the shot planner accepts @fx
    assert len(words) == 12
    with pytest.raises(StageError):
        shots.tag_words("@fx wobble\nhi", ["bob"], ["bob"])


def test_fx_deterministic():
    st = story(cues=[{"frame": 40, "kind": "low_hit"}])
    assert finish.ass(phrases(), st) == finish.ass(phrases(), st)


@needs_ffmpeg
def test_finish_reruns_only_for_what_it_uses(lib, capsys):
    assert stage(lib, "finish") == 0 and stage(lib, "thumbnails") == 0
    first = (pdir(lib) / "captions.ass").read_bytes()
    sf = lib / "demo" / "series.json"
    series = load_series(sf)
    series.parts.append("part-03")  # a new part ...
    save_series(sf, series)
    assert cli(lib, "approve", "demo", "part-01", "stills") == 0  # ... and an approval (not final: that cleans up)
    capsys.readouterr()
    assert stage(lib, "finish") == 0
    assert "finish: skipped" in capsys.readouterr().out
    assert stage(lib, "finish", "--force") == 0
    assert (pdir(lib) / "captions.ass").read_bytes() == first  # same captions.ass bytes
