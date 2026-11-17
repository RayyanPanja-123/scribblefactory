"""Build a fake library for dashboard screenshots. Never writes to the real library/.

Run from the repo root: .venv/Scripts/python web/scripts/make-demo-library.py [OUT_DIR]
OUT_DIR defaults to a new temp dir; it must be empty or missing and outside library/. Prints the path.

4 series with cover thumbs (shot stills from library/marathon-1904 when present, read-only; else flat colour
placeholders), one part with a running stage, one with a failed stage, posts on YouTube and Instagram spread over
the last 12 months, and exactly 3 approvals waiting.
"""

import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline.scribble.io import atomic_write_text, save_part, save_series  # noqa: E402
from pipeline.scribble.schemas import (CastMember, PartModel, Post, SeriesModel, Style, Voice,  # noqa: E402
                                       utcnow)

STILLS = ROOT / "library" / "marathon-1904" / "part-01" / "frames" / "stills"
THUMB = (270, 480)  # 9:16, small: the dashboard shows covers at ~220 px wide
STAGES = ["prep", "import_check", "timing", "shots", "validate", "render", "audio", "finish", "thumbnails"]
NOW = utcnow()

# slug, title, status, cast [(id, name, colour, approved)], parts, frames bytes per part, cover tint
SERIES = [
    ("great-emu-war", "The Great Emu War", "active",
     [("major", "Major Meredith", "#2f6b3a", True), ("emu", "Emu", "#6b5a4a", True)], 8, 22_000_000, "#c9a46b"),
    ("office-cat", "The Office Cat", "active",
     [("karen", "Karen", "#e35b4f", True), ("bob", "Bob", "#4f7cf7", True), ("cat", "Mittens", "#f2b84b", False)],
     10, 9_000_000, "#9ec1d9"),
    ("lighthouse", "The Last Lighthouse Keeper", "complete",
     [("keeper", "Agnes", "#1f3b5c", True)], 6, 4_000_000, "#6d8fa8"),
    ("moon-diner", "Moon Diner", "draft",
     [("cook", "Cook", "#ffffff", False), ("alien", "Zib", "#3fbf7f", False)], 2, 1_000_000, "#3b2f55"),
]


def stills() -> list[Path]:
    return sorted(STILLS.glob("s*.png")) if STILLS.is_dir() else []


def write_thumbs(pdir: Path, sources: list[Path], tint: str, rng: random.Random) -> None:
    (pdir / "thumbs").mkdir()
    for n in (1, 2, 3):
        if sources:
            img = Image.open(rng.choice(sources)).convert("RGB")
            img = img.resize(THUMB)
        else:
            img = Image.new("RGB", THUMB, tint)
        img.save(pdir / "thumbs" / f"thumb-{n}.png", optimize=True)


def stage_states(p: PartModel, done_upto: int, last: str | None = None, error: str | None = None) -> None:
    """stages [0, done_upto) done; the next one gets `last` (running / failed)"""
    for i, name in enumerate(STAGES):
        st = getattr(p.stages, "validate_" if name == "validate" else name)
        if i < done_upto:
            st.status, st.started_at, st.finished_at = "done", NOW - timedelta(days=1), NOW - timedelta(days=1)
        elif i == done_upto and last:
            st.status, st.started_at, st.error = last, NOW - timedelta(minutes=12), error


def build(out: Path) -> None:
    rng = random.Random(7)
    sources = stills()
    posted_offsets = iter(rng.sample(range(0, 330), 40))  # days ago, spread over ~11 months
    for slug, title, status, cast, n_parts, frame_bytes, tint in SERIES:
        d = out / slug
        d.mkdir(parents=True)
        series = SeriesModel(
            slug=slug, title=title, status=status, created_at=NOW - timedelta(days=200),
            voice=Voice(voice_name="Brian"), style=Style(preset="default", locked=status != "draft"),
            cast=[CastMember(id=i, name=nm, top={"color": c}, eyes="dots",
                             approved_at=NOW - timedelta(days=30) if ok else None) for i, nm, c, ok in cast],
            parts=[f"part-{n:02d}" for n in range(1, n_parts + 1)])
        save_series(d / "series.json", series)
        for n in range(1, n_parts + 1):
            pid = f"part-{n:02d}"
            pdir = d / pid
            pdir.mkdir()
            part = PartModel(id=pid, number=n, title=f"Part {n}")
            finished = status == "complete" or n <= n_parts - 2
            if finished:
                stage_states(part, len(STAGES))
                for a in ("stills", "test_render", "final"):
                    getattr(part.approvals, a).approved_at = NOW - timedelta(days=20)
                part.thumbnail_choice = f"thumbs/thumb-{rng.randint(1, 3)}.png"
                yt = NOW - timedelta(days=next(posted_offsets))
                part.posted.youtube = Post(url=f"https://youtube.com/shorts/{slug}{n}", posted_at=yt)
                if rng.random() < 0.7:
                    part.posted.instagram = Post(url=f"https://instagram.com/reel/{slug}{n}",
                                                 posted_at=yt + timedelta(days=rng.randint(0, 3)))
            write_thumbs(pdir, sources, tint, rng)
            (pdir / "story.md").write_text(f"# Part {n}\n\nDemo story.\n", encoding="utf-8")
            (pdir / "frames").mkdir()
            with open(pdir / "frames" / "frames.bin", "wb") as f:
                f.truncate(frame_bytes)  # disk usage without writing the bytes
            save_part(pdir / "part.json", part)

    # the unfinished parts: 1 running, 1 failed, 3 waiting for approval
    def edit(slug, pid, fn):
        f = out / slug / pid / "part.json"
        p = PartModel.model_validate_json(f.read_bytes())
        fn(p, f.parent)
        save_part(f, p)

    def running(p, pdir):  # mid-render
        stage_states(p, 5, "running")
        p.approvals.stills.approved_at = p.approvals.test_render.approved_at = NOW - timedelta(days=1)

    def failed(p, pdir):
        stage_states(p, 6, "failed", "ffmpeg: audio/mix.wav: loudness -9.8 LUFS, want -14")

    def wait_stills(p, pdir):
        stage_states(p, 5)
        (pdir / "stills-sheet.png").write_bytes((pdir / "thumbs" / "thumb-1.png").read_bytes())

    def wait_test(p, pdir):
        stage_states(p, 5)
        p.approvals.stills.approved_at = NOW - timedelta(days=2)
        (pdir / "stills-sheet.png").write_bytes((pdir / "thumbs" / "thumb-1.png").read_bytes())
        (pdir / "test-render.mp4").write_bytes(b"\0" * 1024)

    def wait_final(p, pdir):
        stage_states(p, len(STAGES))
        p.approvals.stills.approved_at = p.approvals.test_render.approved_at = NOW - timedelta(days=3)
        (pdir / "final.mp4").write_bytes(b"\0" * 1024)

    edit("great-emu-war", "part-07", wait_final)
    edit("great-emu-war", "part-08", running)
    edit("office-cat", "part-09", failed)
    edit("office-cat", "part-10", wait_test)
    edit("moon-diner", "part-01", wait_stills)
    edit("moon-diner", "part-02", lambda p, pdir: stage_states(p, 1))
    atomic_write_text(out / "README.txt", "Demo library from web/scripts/make-demo-library.py. Safe to delete.\n")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="scribble-demo-"))
    out = out.resolve()
    real = (ROOT / "library").resolve()
    if out == real or out.is_relative_to(real):
        sys.exit(f"refusing to write inside the real library ({real})")
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    build(out)
    print(out)


if __name__ == "__main__":
    main()
