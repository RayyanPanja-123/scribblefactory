import shutil
import subprocess

import pytest

from pipeline.scribble.cli import main
from pipeline.scribble.io import load_part, save_part
from pipeline.scribble.schemas import PartModel
from pipeline.scribble.stages import import_check, prep
from pipeline.scribble.stages.prep import clean_markdown
from pipeline.scribble.stages.runner import run_stage

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                  reason="ffmpeg/ffprobe not on PATH")

STORY = """# The Stapler

Some **bold** and *italic* and _under_ text, snake_case_name stays.
A [link](http://x.com), a [ref link][1], ![img](a.png)and `code`.

[1]: http://example.com

- item one
- item two
1. first

> quoted “smart” ‘quotes’

<div>html</div> <!-- comment -->

```
code block dropped
```

---

Last    line
   continues here.
"""

CLEAN = """Some bold and italic and under text, snake_case_name stays. A link, a ref link, and code.

item one item two first

quoted "smart" 'quotes'

html

Last line continues here."""


@pytest.fixture
def part(tmp_path):
    d = tmp_path / "part-01"
    d.mkdir()
    save_part(d / "part.json", PartModel(id="part-01", number=1, title="T"))
    return d


def run(part, mod, force=False):
    return run_stage(part, mod.__name__.rsplit(".", 1)[1], mod.run, force=force,
                     inputs=mod.INPUTS, outputs=mod.OUTPUTS)


def stage(part, name):
    return getattr(load_part(part / "part.json").stages, name)


# --- prep ---

def test_clean_markdown():
    assert clean_markdown(STORY) == CLEAN


def test_prep_writes_script_and_estimate(part, capsys):
    (part / "story.md").write_text(STORY, encoding="utf-8")
    assert run(part, prep) == "done"
    assert (part / "script-for-tts.txt").read_text(encoding="utf-8") == CLEAN + "\n"
    out = capsys.readouterr().out
    assert "words: 29, estimated duration: 11.6 s" in out
    assert "warning" not in out
    s = stage(part, "prep")
    assert s.status == "done" and s.started_at and s.finished_at and s.inputs_hash and s.error is None


def test_prep_warns_over_90s(part, capsys):
    (part / "story.md").write_text("word " * 200, encoding="utf-8")  # 80 s: fine (parts may run ~70 s)
    assert run(part, prep) == "done"
    assert "warning" not in capsys.readouterr().out
    (part / "story.md").write_text("word " * 240, encoding="utf-8")  # 96 s
    assert run(part, prep) == "done"
    assert "warning: estimated 96.0 s is over 90 s" in capsys.readouterr().out


def test_prep_empty_body_fails(part):
    (part / "story.md").write_text("# Pilot\n\n", encoding="utf-8")
    assert run(part, prep) == "failed"
    s = stage(part, "prep")
    assert s.status == "failed" and "no body text" in s.error and s.finished_at
    assert not (part / "script-for-tts.txt").exists()


def test_prep_skip_edit_force(part, capsys):
    (part / "story.md").write_text("Hello there.", encoding="utf-8")
    assert run(part, prep) == "done"
    assert run(part, prep) == "skipped"
    assert "prep: skipped (up to date)" in capsys.readouterr().out
    (part / "story.md").write_text("Hello again.", encoding="utf-8")
    assert run(part, prep) == "done"
    assert (part / "script-for-tts.txt").read_text() == "Hello again.\n"
    assert run(part, prep, force=True) == "done"
    (part / "script-for-tts.txt").unlink()  # missing output: re-run even though inputs match
    assert run(part, prep) == "done"


def test_failure_after_success_clears_hash(part):
    (part / "story.md").write_text("Hello.", encoding="utf-8")
    run(part, prep)
    (part / "story.md").write_text("# only a title", encoding="utf-8")
    assert run(part, prep) == "failed"
    assert stage(part, "prep").inputs_hash is None


def test_unexpected_exception_marks_failed(part):
    def boom(_):
        raise RuntimeError("kaput")
    assert run_stage(part, "prep", boom) == "failed"
    assert stage(part, "prep").error == "kaput"


# --- import_check ---

def mp3(path, expr, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"aevalsrc='{expr}':d={seconds}:s=44100", "-c:a", "libmp3lame", "-b:a", "128k", str(path)],
                   check=True)


TONE = "0.5*sin(440*2*PI*t)"


def with_script(part, words):
    (part / "script-for-tts.txt").write_text(" ".join(["word"] * words) + "\n", encoding="utf-8")


@needs_ffmpeg
def test_import_check_pass(part, capsys):
    mp3(part / "voice.mp3", TONE, 5)
    with_script(part, 12)  # 4.8 s estimate
    assert run(part, import_check) == "done"
    out = capsys.readouterr().out
    assert "duration: 5.0 s" in out and "warning" not in out
    assert run(part, import_check) == "skipped"


@needs_ffmpeg
def test_import_check_warns_internal_silence(part, capsys):
    mp3(part / "voice.mp3", f"if(between(t,2,5),0,{TONE})", 7)
    with_script(part, 17)
    assert run(part, import_check) == "done"
    out = capsys.readouterr().out
    assert "warning: internal silence 3.0 s" in out
    assert "leading" not in out and "trailing" not in out


@needs_ffmpeg
def test_import_check_warns_edges_and_estimate(part, capsys):
    mp3(part / "voice.mp3", f"if(lt(t,2)+gt(t,6),0,{TONE})", 8)
    with_script(part, 40)  # 16 s estimate vs 8 s
    assert run(part, import_check) == "done"
    out = capsys.readouterr().out
    assert "warning: leading silence 2.0 s" in out
    assert "warning: trailing silence 2.0 s" in out
    assert "differs from prep estimate 16.0 s" in out


@needs_ffmpeg
def test_import_check_corrupt_fails(part):
    (part / "voice.mp3").write_bytes(b"definitely not audio " * 500)
    assert run(part, import_check) == "failed"
    s = stage(part, "import_check")
    assert s.status == "failed" and s.error


def test_import_check_missing_fails(part):
    assert run(part, import_check) == "failed"
    assert stage(part, "import_check").error == "voice.mp3 not found"


@needs_ffmpeg
def test_user_files_untouched(part):
    (part / "story.md").write_text(STORY, encoding="utf-8")
    mp3(part / "voice.mp3", TONE, 3)
    before = {n: (part / n).read_bytes() for n in ("story.md", "voice.mp3")}
    for mod in (prep, import_check, prep, import_check):
        run(part, mod, force=True)
    assert {n: (part / n).read_bytes() for n in before} == before


# --- CLI ---

def test_cli_run_exit_codes(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBBLE_LIBRARY", str(tmp_path))
    main(["new-series", "cat", "--title", "Cat"])
    main(["new-part", "cat"])
    assert main(["run", "cat", "part-01", "--stage", "prep"]) == 1  # template story: empty body
    (tmp_path / "database" / "storage" / "cat" / "part-01" / "story.md").write_text("Once upon a time.", encoding="utf-8")
    assert main(["run", "cat", "part-01", "--stage", "prep"]) == 0
    assert main(["run", "cat", "part-01", "--stage", "prep"]) == 0  # skipped
    assert main(["run", "cat", "part-01", "--stage", "prep", "--force"]) == 0
    assert main(["run", "cat", "part-09", "--stage", "prep"]) == 1
    assert main(["run", "cat", "../x", "--stage", "prep"]) == 1
