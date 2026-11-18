"""scribblefactory CLI. Run: python -m pipeline.scribble.cli <command> [--library DIR]

Exit codes: 0 ok, 1 user error or stage failed, 2 not implemented.
"""

import argparse
import functools
import os
import re
import shutil
import subprocess
import sys
from typing import get_args
from datetime import datetime, timezone
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from . import sheet, storycheck
from .io import (atomic_write_json, cast_body_problems, cast_files, cast_key, cast_render_current, load_part, load_series, prop_kinds, replace_file, save_part,
                 save_series, unknown_cast_props)
from .schemas import CastMember, Expression, PartId, PartModel, Post, SeriesModel, Slug, Stages, StoryModel, Style, Voice, utcnow
from .stages import STAGES
from .stages import render as render_stage
from .stages.runner import StageError, recover_stuck, run_stage

RENDER = Path(__file__).resolve().parents[2] / "engine" / "render.mjs"
CAST_SHEET_COLS = 18   # one row per cast member: idle, walk, talk, 8 expressions, stagger, lie, eat, give, carried,
                       # cheer, angry mood (engine/render.mjs POSES)
STILLS_SHEET_COLS = 6


class UserError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse defaults to exit 2, which we reserve for "not implemented"
        self.print_usage(sys.stderr)
        self.exit(1, f"error: {message}\n")


def library_root(args) -> Path:
    return Path(args.library or os.environ.get("SCRIBBLE_LIBRARY") or "library")


def series_dir(args) -> Path:
    try:
        TypeAdapter(Slug).validate_python(args.slug)  # also blocks path tricks like ../x
    except ValidationError:
        raise UserError(f"invalid slug {args.slug!r}: use lowercase a-z, 0-9 and single dashes")
    return library_root(args) / args.slug


def cmd_new_series(args) -> int:
    d = series_dir(args)
    if (d / "series.json").exists():
        raise UserError(f"{d / 'series.json'} already exists, not overwriting")
    # voice_name and style preset are placeholders: fill them with set-voice / set-style.
    series = SeriesModel(slug=args.slug, title=args.title, created_at=utcnow(),
                         voice=Voice(voice_name=""), style=Style(preset="default"))
    d.mkdir(parents=True, exist_ok=True)  # an interrupted earlier run may have left the folder
    save_series(d / "series.json", series)
    print(f"created {d / 'series.json'}")
    return 0


def load_existing_series(args) -> tuple[Path, SeriesModel]:
    f = series_dir(args) / "series.json"
    if not f.exists():
        raise UserError(f"series {args.slug!r} not found at {f.parent}")
    return f, load_series(f)


def cmd_cast_add(args) -> int:
    f, series = load_existing_series(args)
    if any(c.id == args.id for c in series.cast):
        raise UserError(f"cast id {args.id!r} already exists in {args.slug}")
    new = CastMember(id=args.id, name=args.name, top={"color": args.color}, eyes=args.eyes, body=args.body,
                     headless=args.headless == "yes")
    if problems := cast_body_problems([new], library_root(args)):
        raise UserError(problems[0])
    series.cast.append(new)
    save_series(f, series)
    print(f"added {args.id} to {args.slug} cast")
    return 0


def cmd_cast_edit(args) -> int:
    f, series = load_existing_series(args)
    i = next((i for i, c in enumerate(series.cast) if c.id == args.id), None)
    if i is None:
        raise UserError(f"cast id {args.id!r} not in {args.slug} (cast: {', '.join(c.id for c in series.cast) or '-'})")
    # flag -> (section, field) of the cast entry; section None = top level
    fields = {"name": (None, "name"), "eyes": (None, "eyes"), "default_expression": (None, "default_expression"),
              "top": ("top", "style"), "top_color": ("top", "color"), "accent": ("top", "accent_color"),
              "number": ("top", "number"), "headwear": ("headwear", "kind"), "headwear_color": ("headwear", "color"),
              "legwear": ("legwear", "kind"), "legwear_color": ("legwear", "color"),
              "props": (None, "props"), "body": (None, "body"), "headless": (None, "headless")}
    changes = {k: getattr(args, k) for k in fields if getattr(args, k) is not None}
    if not changes:
        raise UserError("nothing to change: give at least one of " + ", ".join(f"--{k.replace('_', '-')}" for k in fields))
    old = series.cast[i]
    data = old.model_dump()
    for k, v in changes.items():
        section, name = fields[k]
        (data[section] if section else data)[name] = None if v == "none" and name in ("accent_color", "number") else v
    if args.props is not None:
        data["props"] = parse_props(args.props)
    if args.headless is not None:
        data["headless"] = args.headless == "yes"
    if args.body and args.headless is None:
        data["headless"] = False  # a new body starts with its head on (the new one may have no stump)
    new = CastMember.model_validate(data)  # validates colours, kinds, number
    if problems := cast_body_problems([new], library_root(args)):
        raise UserError(problems[0])
    if unknown := unknown_cast_props([new], library_root(args)):
        raise UserError(f"unknown prop {unknown[0].split(': ')[1]!r} (props: {', '.join(prop_kinds(library_root(args)))})")
    if new.look() != old.look() and old.approved_at:
        new.approved_at = None
        print(f"note: {args.id}'s look changed, so its approval was cleared: re-render it (cast-sheet {args.slug} {args.id}), "
              f"then approve-cast {args.slug} {args.id}")
    series.cast[i] = new
    # write directly: save_series would restore the approval cleared above (it only ever adds approvals)
    atomic_write_json(f, series.model_dump(mode="json"))
    print(f"updated {args.id}: {', '.join(f'{k}={v}' for k, v in changes.items())}")
    return 0


def parse_props(text: str) -> list[dict]:
    """--props "clipboard:right,stopwatch:left" | "none" -> [{"kind", "hand"}] (the schema checks kinds and hands)"""
    if text.strip() == "none":
        return []
    out = []
    for item in filter(None, (x.strip() for x in text.split(","))):
        kind, _, hand = item.partition(":")
        if not hand:
            raise UserError(f"--props: {item!r} needs a hand, e.g. {kind}:right")
        out.append({"kind": kind.strip(), "hand": hand.strip()})
    if not out:
        raise UserError('--props: give "kind:hand,..." or none')
    return out


def cmd_set_voice(args) -> int:
    f, series = load_existing_series(args)
    series.voice.voice_name = args.name
    save_series(f, series)
    print(f"{args.slug} voice: {args.name}")
    return 0


def cmd_set_style(args) -> int:
    f, series = load_existing_series(args)
    if series.style.locked:
        raise UserError(f"{args.slug} style is locked ({series.style.preset!r}), not changing it")
    series.style.preset = args.preset
    save_series(f, series)
    print(f"{args.slug} style: {args.preset}")
    return 0


def part_folders(d: Path) -> list[str]:
    """Sorted part-NN folder names on disk."""
    return sorted(f.name for f in d.iterdir() if f.is_dir() and re.fullmatch(r"part-[0-9]{2}", f.name))


def cmd_new_part(args) -> int:
    d = series_dir(args)
    if not (d / "series.json").exists():
        raise UserError(f"series {args.slug!r} not found at {d}")
    series = load_series(d / "series.json")
    # Count folders too, so a part folder left by an interrupted run is never reused.
    number = max([int(p[5:]) for p in series.parts + part_folders(d)], default=0) + 1
    if number > 99:
        raise UserError("series already has part-99; parts are limited to 99")
    pid = f"part-{number:02d}"
    title = args.title or f"Part {number}"
    pdir = d / pid
    pdir.mkdir()
    save_part(pdir / "part.json", PartModel(id=pid, number=number, title=title))
    try:
        with open(pdir / "story.md", "x", encoding="utf-8", newline="\n") as f:
            f.write(f"# {title}\n\n")
    except FileExistsError:
        pass
    series.parts.append(pid)
    save_series(d / "series.json", series)
    print(f"created {pdir}")
    return 0


def move_aside(src: Path, dst: Path) -> None:
    """rename a folder away (retried); on Windows it fails while any program has it or a file in it open"""
    try:
        replace_file(src, dst)
    except PermissionError:
        raise UserError(f"{src.name} is in use by another program (a File Explorer window open on it, a video "
                        "playing it, an editor?); close it and try again")


def cmd_delete_part(args) -> int:
    """Delete a part: its folder (story.md, voice.mp3, videos, frames: everything) and its entry in series.json.
    Dry run unless --yes. Other parts keep their numbers."""
    pdir = part_dir(args)
    if render_stage.lock_owner(pdir):
        raise UserError(f"a render is running on {args.slug} {args.part}; wait for it or stop it")
    f, series = load_existing_series(args)
    size = sum(x.stat().st_size for x in pdir.rglob("*") if x.is_file())
    files = sorted(x.name for x in pdir.iterdir())
    if not args.yes:
        print(f"would delete {pdir} ({size / 1e6:.1f} MB: {', '.join(files)}) and remove {args.part} from "
              f"series.json; add --yes to delete")
        return 0
    # rename aside first (atomic), then series.json, then the files: never a listed part with half its files gone
    trash = pdir.with_name(f".deleted-{args.part}-{utcnow():%Y%m%d%H%M%S}")
    move_aside(pdir, trash)
    try:
        series.parts = [x for x in series.parts if x != args.part]
        save_series(f, series)
    except BaseException:
        os.replace(trash, pdir)
        raise
    shutil.rmtree(trash, ignore_errors=True)
    if trash.exists():
        print(f"note: could not delete every file of {trash.name} (in use?); it is no longer a part, delete it later")
    print(f"deleted {args.slug} {args.part} ({size / 1e6:.1f} MB freed)")
    return 0


def cmd_delete_series(args) -> int:
    """Delete a series: its whole folder (every part, story, voice, video, the cast sheet). Dry run unless --yes.
    Custom props live in library/props.json and are kept."""
    f, series = load_existing_series(args)
    d = f.parent
    running = [p for p in part_folders(d) if render_stage.lock_owner(d / p)]
    if running:
        raise UserError(f"a render is running on {args.slug} {running[0]}; wait for it or stop it")
    size = sum(x.stat().st_size for x in d.rglob("*") if x.is_file())
    if not args.yes:
        print(f"would delete {d} ({size / 1e6:.1f} MB: {len(series.parts)} part(s), cast of {len(series.cast)}); "
              f"add --yes to delete")
        return 0
    trash = d.with_name(f".deleted-{args.slug}-{utcnow():%Y%m%d%H%M%S}")
    move_aside(d, trash)  # one atomic step: from here the series is gone from the library
    shutil.rmtree(trash, ignore_errors=True)
    if trash.exists():
        print(f"note: could not delete every file of {trash.name} (in use?); delete it later")
    print(f"deleted series {args.slug} ({size / 1e6:.1f} MB freed)")
    return 0


def _date(dt) -> str:
    return dt.strftime("%Y-%m-%d") if dt else "-"


def cmd_status(args) -> int:
    d = series_dir(args)
    if not (d / "series.json").exists():
        raise UserError(f"series {args.slug!r} not found at {d}")
    s = load_series(d / "series.json")
    for pid in s.parts:
        if (d / pid / "part.json").exists():
            for name in recover_stuck(d / pid):
                print(f"note: {pid} {name} was left running by a process that is gone: marked failed (interrupted)")
    print(f"{s.title} ({s.slug})  status: {s.status}  parts: {len(s.parts)}")
    print(f"voice: {s.voice.voice_name or '-'}  style: {s.style.preset} ({'locked' if s.style.locked else 'unlocked'})")
    cast = [f"{c.id} ({c.top.color}, {c.eyes}, "
            + (f"approved {_date(c.approved_at)})" if c.approved_at else "-)") for c in s.cast]
    print(f"cast: {', '.join(cast) or '-'}")
    if s.parts:
        _print_table(d, s.parts)
    for name in part_folders(d):
        if name not in s.parts:
            print(f"warning: orphan folder {name} (not in series.json)")
    return 0


def _print_table(d: Path, parts: list[str]) -> None:
    stages = list(Stages.model_fields)
    header = ["part", "title"] + [Stages.model_fields[n].alias or n for n in stages] \
        + ["stills", "test_render", "final", "youtube", "instagram"]
    rows = [header]
    for pid in parts:
        f = d / pid / "part.json"
        if not f.exists():
            rows.append([pid, "(part.json missing)"] + [""] * (len(header) - 2))
            continue
        p = load_part(f)
        rows.append([p.id, p.title]
                    + [getattr(p.stages, n).status for n in stages]
                    + [_date(getattr(p.approvals, n).approved_at) for n in ("stills", "test_render", "final")]
                    + [_date(post.posted_at if post else None) for post in (p.posted.youtube, p.posted.instagram)])
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())


def part_dir(args) -> Path:
    try:
        TypeAdapter(PartId).validate_python(args.part)
    except ValidationError:
        raise UserError(f"invalid part {args.part!r}: expected part-NN")
    pdir = series_dir(args) / args.part
    if not (pdir / "part.json").exists():
        raise UserError(f"part {args.part!r} not found at {pdir}")
    return pdir


def cmd_run(args) -> int:
    pdir = part_dir(args)
    stage = STAGES[args.stage]
    result = run_stage(pdir, args.stage, stage.run, force=args.force, inputs=stage.INPUTS, outputs=stage.OUTPUTS,
                       extra=getattr(stage, "extra_inputs", None))
    return 1 if result == "failed" else 0


def gate(pdir: Path, needs: tuple[str, ...]) -> None:
    """Approvals and the render lock, checked before a render as user errors (the stage status stays untouched)."""
    pid = render_stage.lock_owner(pdir)
    if pid:
        raise UserError(f"another render is running on {pdir.parent.name} {pdir.name} (pid {pid}); wait for it or stop it")
    try:
        render_stage.check_gate(pdir, needs)
    except StageError as e:
        raise UserError(str(e))


def cmd_check_story(args) -> int:
    pdir = part_dir(args)
    result = storycheck.check_story(pdir)
    print(storycheck.report(result))
    return 0 if result["ok"] else 1


def cmd_render(args) -> int:
    pdir = part_dir(args)
    gate(pdir, ("stills", "test_render"))
    fn = functools.partial(render_stage.run, workers=args.workers, swiftshader=args.swiftshader, force=args.force)
    result = run_stage(pdir, "render", fn, force=args.force, inputs=render_stage.INPUTS, outputs=render_stage.OUTPUTS)
    return 1 if result == "failed" else 0


def cmd_test_render(args) -> int:
    pdir = part_dir(args)
    gate(pdir, ("stills",))
    try:
        out = render_stage.test_render(pdir, at=args.at, swiftshader=args.swiftshader)
    except StageError as e:
        raise UserError(str(e))
    print(f"test render: {out}")
    return 0


def run_engine(*args) -> None:
    """node engine/render.mjs <args>; its output streams straight to the terminal."""
    node = shutil.which("node")
    if not node:
        raise UserError("node not found on PATH")
    r = subprocess.run([node, str(RENDER), *map(str, args)])
    if r.returncode != 0:
        raise UserError(f"render.mjs failed (exit {r.returncode})")


def cmd_cast_sheet(args) -> int:
    f, series = load_existing_series(args)
    if not series.cast:
        raise UserError(f"{args.slug} has no cast: add some with cast-add")
    known = {c.id: c for c in series.cast}
    if unknown := [i for i in args.ids if i not in known]:
        raise UserError(f"cast id {unknown[0]!r} not in {args.slug} (cast: {', '.join(known)})")
    todo = [known[i] for i in dict.fromkeys(args.ids)] or series.cast
    # the looks as the engine reads them now, not as they may be edited mid-render
    keys = {c.id: cast_key(c) for c in todo}
    frames, out = f.parent / "cast-frames", f.parent / "cast"
    frames.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    batch = frames / "batch.json"
    atomic_write_json(batch, [["--series", str(f.parent), "--cast-sheet", "--cast", c.id] for c in todo])
    try:
        run_engine("--batch", batch)  # one browser for all of them
    except UserError as e:
        failed = e
    else:
        failed = None
    done = []
    for c in todo:  # each member whose job finished has a manifest (the engine empties its folder first)
        d, files = frames / c.id, cast_files(f.parent, c.id)
        if not (d / "manifest.json").is_file():
            continue
        sheet.from_manifest(d, files["sheet"], cols=CAST_SHEET_COLS)
        shutil.copyfile(d / f"{c.id}-idle.png", files["idle"])
        files["key"].write_text(keys[c.id])
        done.append(c.id)
    print(f"cast rendered: {', '.join(done) or 'none'} -> {out}")
    if failed:
        raise failed
    return 0


def cmd_render_stills(args) -> int:
    pdir = part_dir(args)
    if not (pdir / "story.json").exists():
        raise UserError(f"{pdir / 'story.json'} not found: run --stage shots first")
    story = StoryModel.model_validate_json((pdir / "story.json").read_bytes())
    _, series = load_existing_series(args)
    waiting = render_stage.unapproved_cast(story, series)
    if waiting:
        raise UserError(f"cast not approved: {', '.join(waiting)}. Check the cast sheet (cast-sheet {args.slug}), "
                        f"then approve-cast {args.slug} <id>.")
    run_engine("--part", pdir, "--stills")
    out = sheet.from_manifest(pdir / "frames" / "stills", pdir / "stills-sheet.png", cols=STILLS_SHEET_COLS)
    print(f"stills sheet: {out}")
    return 0


def cmd_approve(args) -> int:
    pdir = part_dir(args)
    part = load_part(pdir / "part.json")
    a = getattr(part.approvals, args.what)
    if a.approved_at:
        print(f"{args.part} {args.what} already approved at {a.approved_at:%Y-%m-%d %H:%M} UTC (kept)")
        return 0
    a.approved_at = utcnow()
    save_part(pdir / "part.json", part)
    print(f"{args.part} {args.what} approved")
    if args.what == "final":
        cleanup(pdir)
    return 0


# Only there to make final.mp4: once it is approved they are dead weight (frames alone are 1-2 GB a part).
# Kept: story.md, voice.mp3, voice-tight.wav, script-for-tts.txt, phrases.json, story.json, part.json, final.mp4,
# qa.json, thumbs/, upload.md, stills-sheet.png. Changing an approved video afterwards means rendering it again.
DISPOSABLE = ["frames", "audio", "preview.mp4", "test-render.mp4", "captions.ass", "end-card.png"]


def cleanup(pdir: Path) -> int | None:
    """Delete a part's DISPOSABLE assets once its final is approved and finished. Returns bytes freed, or None when
    refused (no approval, no finished final.mp4, or a render running; the reason is printed)."""
    part = load_part(pdir / "part.json")
    why = ("final not approved yet" if not part.approvals.final.approved_at
           else "no finished final.mp4" if part.stages.finish.status != "done" or not (pdir / "final.mp4").is_file()
           else "a render is running on it" if render_stage.lock_owner(pdir) else None)
    if why:
        print(f"cleanup skipped: {why}; nothing deleted")
        return None
    freed, gone = 0, []
    for name in DISPOSABLE:
        f = pdir / name
        if f.is_dir():
            freed += sum(x.stat().st_size for x in f.rglob("*") if x.is_file())
            shutil.rmtree(f)
        elif f.is_file():
            freed += f.stat().st_size
            f.unlink()
        else:
            continue
        gone.append(name)
    print(f"cleanup: deleted {', '.join(gone) or 'nothing (already clean)'} ({freed / 1e6:.1f} MB freed); "
          f"final.mp4, voice, story and thumbnails kept")
    return freed


def cmd_cleanup(args) -> int:
    return 1 if cleanup(part_dir(args)) is None else 0


def cmd_approve_cast(args) -> int:
    f, series = load_existing_series(args)
    c = next((c for c in series.cast if c.id == args.cast_id), None)
    if c is None:
        raise UserError(f"cast id {args.cast_id!r} not in {args.slug} (cast: {', '.join(x.id for x in series.cast) or '-'})")
    if c.approved_at:
        print(f"{c.id} already approved at {c.approved_at:%Y-%m-%d %H:%M} UTC (kept)")
        return 0
    if not cast_render_current(f.parent, c):
        raise UserError(f"{c.id} has no render of its current look: run cast-sheet {args.slug} {c.id}, check it, "
                        f"then approve")
    c.approved_at = utcnow()
    save_series(f, series)
    print(f"{c.id} approved")
    return 0


def cmd_set_captions(args) -> int:
    f, series = load_existing_series(args)
    series.style.captions = args.state == "on"
    save_series(f, series)
    print(f"{args.slug} captions: {args.state} (re-run finish to apply)")
    return 0


def cmd_pick_thumbnail(args) -> int:
    pdir = part_dir(args)
    choice = f"thumbs/thumb-{args.n}.png"
    if not (pdir / choice).exists():
        raise UserError(f"{pdir / choice} not found: run {args.slug} {args.part} --stage thumbnails first")
    part = load_part(pdir / "part.json")
    part.thumbnail_choice = choice
    save_part(pdir / "part.json", part)
    print(f"{args.part} thumbnail: {choice}")
    return 0


def cmd_mark_posted(args) -> int:
    pdir = part_dir(args)
    if not re.match(r"^https?://\S+$", args.url):
        raise UserError(f"invalid url {args.url!r}: expected http(s)://...")
    if args.date:
        try:
            when = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise UserError(f"invalid date {args.date!r}: expected YYYY-MM-DD")
    else:
        when = utcnow()
    part = load_part(pdir / "part.json")
    old = getattr(part.posted, args.platform)
    if old and not args.force:
        raise UserError(f"{args.part} already marked posted on {args.platform} ({old.url}, {_date(old.posted_at)}); "
                        f"use --force to replace it")
    setattr(part.posted, args.platform, Post(url=args.url, posted_at=when))
    save_part(pdir / "part.json", part)
    print(f"{args.part} posted on {args.platform}: {args.url} ({_date(when)})")
    return 0


def cmd_clean_frames(args) -> int:
    if args.posted:
        return clean_posted(args)
    if not (args.slug and args.part):
        raise UserError("clean-frames needs <slug> <part>, or --posted [<slug>]")
    if args.yes:
        raise UserError("--yes goes with --posted (one part is cleaned without asking)")
    pdir = part_dir(args)
    frames = pdir / "frames"
    if not (pdir / "final.mp4").exists() or load_part(pdir / "part.json").stages.finish.status != "done":
        raise UserError(f"{args.part} has no finished final.mp4 yet (run {args.slug} {args.part} --stage finish); "
                        f"frames kept")
    if render_stage.lock_owner(pdir):
        raise UserError("a render is running on this part; frames kept")
    if not frames.exists():
        print("no frames/ to clean")
        return 0
    size = sum(f.stat().st_size for f in frames.rglob("*") if f.is_file())
    shutil.rmtree(frames)
    print(f"deleted {frames} ({size / 1e6:.1f} MB freed)")
    return 0


def clean_posted(args) -> int:
    """frames/ of every part approved final AND posted on both platforms (one series, or the whole library).
    Dry run unless --yes."""
    if args.part:
        raise UserError("--posted cleans every posted part: give at most a <slug>")
    root = library_root(args)
    if args.slug:
        dirs = [load_existing_series(args)[0].parent]
    else:
        dirs = sorted(d for d in root.iterdir() if (d / "series.json").is_file()) if root.is_dir() else []
    total = count = 0
    for d in dirs:
        for pid in load_series(d / "series.json").parts:
            pdir, frames = d / pid, d / pid / "frames"
            if not (pdir / "part.json").exists() or not frames.exists():
                continue
            p = load_part(pdir / "part.json")
            if not (p.approvals.final.approved_at and p.posted.youtube and p.posted.instagram
                    and (pdir / "final.mp4").exists()):
                continue
            if render_stage.lock_owner(pdir):
                print(f"skipped {d.name} {pid}: a render is running")
                continue
            size = sum(f.stat().st_size for f in frames.rglob("*") if f.is_file())
            print(f"{'deleted' if args.yes else 'would delete'} {frames} ({size / 1e6:.1f} MB)")
            if args.yes:
                shutil.rmtree(frames)
            total, count = total + size, count + 1
    if args.yes:
        print(f"{total / 1e6:.1f} MB freed ({count} part(s))")
    else:
        print(f"dry run: {total / 1e6:.1f} MB would be freed ({count} part(s))" + "; add --yes to delete" * bool(count))
    return 0


def build_parser() -> Parser:
    common = Parser(add_help=False)
    common.add_argument("--library", help="library root (default: $SCRIBBLE_LIBRARY or ./library)")
    p = Parser(prog="python -m pipeline.scribble.cli")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("new-series", parents=[common], help="create library/<slug>/series.json")
    c.add_argument("slug")
    c.add_argument("--title", required=True)
    c.set_defaults(func=cmd_new_series)

    c = sub.add_parser("new-part", parents=[common], help="add the next part to a series")
    c.add_argument("slug")
    c.add_argument("--title")
    c.set_defaults(func=cmd_new_part)

    c = sub.add_parser("delete-series", parents=[common],
                       help="delete a series: its whole folder, every part included (dry run unless --yes)")
    c.add_argument("slug")
    c.add_argument("--yes", action="store_true", help="really delete")
    c.set_defaults(func=cmd_delete_series)

    c = sub.add_parser("delete-part", parents=[common],
                       help="delete a part: its whole folder and its series.json entry (dry run unless --yes)")
    c.add_argument("slug")
    c.add_argument("part")
    c.add_argument("--yes", action="store_true", help="really delete")
    c.set_defaults(func=cmd_delete_part)

    c = sub.add_parser("cast-add", parents=[common], help="add a character to a series cast")
    c.add_argument("slug")
    c.add_argument("id")
    c.add_argument("--name", required=True)
    c.add_argument("--color", required=True, help="outfit colour #rrggbb")
    c.add_argument("--eyes", choices=["dots", "half_closed"], default="dots")
    c.add_argument("--body", default="human", help="creature id (built in or library/creatures.json); human: the stickman")
    c.add_argument("--headless", choices=["yes", "no"], default="no", help="creatures with a stump: no head")
    c.set_defaults(func=cmd_cast_add)

    c = sub.add_parser("cast-edit", parents=[common], help="change a cast member (a new look clears its approval)")
    c.add_argument("slug")
    c.add_argument("id")
    c.add_argument("--name")
    c.add_argument("--top", choices=["plain", "suit", "tank", "shirt", "dress"])
    c.add_argument("--top-color", "--color", dest="top_color", help="top colour #rrggbb")
    c.add_argument("--accent", help="suit tie / dress hat ribbon colour #rrggbb, or none")
    c.add_argument("--number", help="chest number, 1-3 digits, or none")
    c.add_argument("--headwear", choices=["none", "flat_cap", "postman_cap", "bowler", "straw_hat", "wide_hat"])
    c.add_argument("--headwear-color", help="#rrggbb")
    c.add_argument("--legwear", choices=["none", "shorts", "ragged_shorts", "trousers"])
    c.add_argument("--legwear-color", help="#rrggbb")
    c.add_argument("--props", help='held props "kind:hand,kind:hand" (max 2, one per hand; built-in or from '
                                    'library/props.json), e.g. "clipboard:right,stopwatch:left", or none')
    c.add_argument("--default-expression", choices=list(get_args(Expression)))
    c.add_argument("--eyes", choices=["dots", "half_closed"])
    c.add_argument("--body", help="creature id (built in or library/creatures.json); human: the stickman")
    c.add_argument("--headless", choices=["yes", "no"], help="creatures with a stump: no head")
    c.set_defaults(func=cmd_cast_edit)

    c = sub.add_parser("set-voice", parents=[common], help="set the series voice name")
    c.add_argument("slug")
    c.add_argument("--name", required=True)
    c.set_defaults(func=cmd_set_voice)

    c = sub.add_parser("set-style", parents=[common], help="set the series style preset (refused once locked)")
    c.add_argument("slug")
    c.add_argument("--preset", required=True)
    c.set_defaults(func=cmd_set_style)

    c = sub.add_parser("status", parents=[common], help="show series and part status")
    c.add_argument("slug")
    c.set_defaults(func=cmd_status)

    c = sub.add_parser("run", parents=[common], help="run one pipeline stage for a part")
    c.add_argument("slug")
    c.add_argument("part")
    c.add_argument("--stage", required=True, choices=list(STAGES))
    c.add_argument("--force", action="store_true", help="re-run even if up to date")
    c.set_defaults(func=cmd_run)

    c = sub.add_parser("check-story", parents=[common],
                       help="check story.md (directives, cast, sets, actions, props, approvals, changed words) "
                            "without voice or timing; exit 0 ready, 1 problems")
    c.add_argument("slug")
    c.add_argument("part")
    c.set_defaults(func=cmd_check_story)

    c = sub.add_parser("render", parents=[common], help="full render in parallel chunks (resumable) -> preview.mp4")
    c.add_argument("slug")
    c.add_argument("part")
    c.add_argument("--workers", type=int, default=render_stage.WORKERS, help="parallel browser processes")
    c.add_argument("--force", action="store_true", help="delete all frames and render again")
    c.add_argument("--swiftshader", action="store_true", help="software WebGL instead of the GPU")
    c.set_defaults(func=cmd_render)

    c = sub.add_parser("test-render", parents=[common], help="5 s test clip with voice -> test-render.mp4")
    c.add_argument("slug")
    c.add_argument("part")
    c.add_argument("--at", type=float, default=0.0, help="start time in seconds (clamped to the part)")
    c.add_argument("--swiftshader", action="store_true", help="software WebGL instead of the GPU")
    c.set_defaults(func=cmd_test_render)

    c = sub.add_parser("cast-sheet", parents=[common],
                       help="render cast members (default: all) -> <series>/cast/<id>.png, <id>-idle.png")
    c.add_argument("slug")
    c.add_argument("ids", nargs="*", help="only these cast ids")
    c.set_defaults(func=cmd_cast_sheet)

    c = sub.add_parser("render-stills", parents=[common], help="render one still per shot -> part-NN/stills-sheet.png")
    c.add_argument("slug")
    c.add_argument("part")
    c.set_defaults(func=cmd_render_stills)

    c = sub.add_parser("approve", parents=[common], help="approve a part's stills, test render or final")
    c.add_argument("slug")
    c.add_argument("part")
    c.add_argument("what", choices=["stills", "test_render", "final"])
    c.set_defaults(func=cmd_approve)

    c = sub.add_parser("cleanup", parents=[common],
                       help="delete what only made final.mp4 (frames, audio stems, preview, test render, captions.ass) "
                            "of a part whose final is approved; approving the final does this automatically")
    c.add_argument("slug")
    c.add_argument("part")
    c.set_defaults(func=cmd_cleanup)

    c = sub.add_parser("approve-cast", parents=[common], help="approve a cast member after checking the cast sheet")
    c.add_argument("slug")
    c.add_argument("cast_id")
    c.set_defaults(func=cmd_approve_cast)

    c = sub.add_parser("set-captions", parents=[common], help="burned-in captions on or off for a series")
    c.add_argument("slug")
    c.add_argument("state", choices=["on", "off"])
    c.set_defaults(func=cmd_set_captions)

    c = sub.add_parser("pick-thumbnail", parents=[common], help="choose thumbnail candidate 1, 2 or 3")
    c.add_argument("slug")
    c.add_argument("part")
    c.add_argument("n", type=int, choices=[1, 2, 3])
    c.set_defaults(func=cmd_pick_thumbnail)

    c = sub.add_parser("mark-posted", parents=[common], help="record a posted link")
    c.add_argument("slug")
    c.add_argument("part")
    c.add_argument("platform", choices=["youtube", "instagram"])
    c.add_argument("--url", required=True)
    c.add_argument("--date", help="YYYY-MM-DD (default: today, UTC)")
    c.add_argument("--force", action="store_true", help="replace an existing entry")
    c.set_defaults(func=cmd_mark_posted)

    c = sub.add_parser("clean-frames", parents=[common],
                       help="delete frames/ once final.mp4 is finished; --posted: of every posted part")
    c.add_argument("slug", nargs="?")
    c.add_argument("part", nargs="?")
    c.add_argument("--posted", action="store_true", help="every part approved final and posted on YouTube and "
                                                         "Instagram (of <slug>, else the whole library); dry run")
    c.add_argument("--yes", action="store_true", help="with --posted: really delete")
    c.set_defaults(func=cmd_clean_frames)
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):  # a redirected Windows console is cp1252: never crash on a message
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (UserError, ValidationError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
