"""scribblefactory CLI. Run: python -m pipeline.scribble.cli <command> [--library DIR]

Exit codes: 0 ok, 1 user error, 2 not implemented.
"""

import argparse
import os
import re
import sys
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from .io import load_part, load_series, save_part, save_series
from .schemas import PartModel, SeriesModel, Slug, Stages, Style, Voice, utcnow


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
    # ponytail: voice_name/style preset are placeholders until a command sets them.
    series = SeriesModel(slug=args.slug, title=args.title, created_at=utcnow(),
                         voice=Voice(voice_name=""), style=Style(preset="default"))
    d.mkdir(parents=True, exist_ok=True)  # an interrupted earlier run may have left the folder
    save_series(d / "series.json", series)
    print(f"created {d / 'series.json'}")
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


def _date(dt) -> str:
    return dt.strftime("%Y-%m-%d") if dt else "-"


def cmd_status(args) -> int:
    d = series_dir(args)
    if not (d / "series.json").exists():
        raise UserError(f"series {args.slug!r} not found at {d}")
    s = load_series(d / "series.json")
    print(f"{s.title} ({s.slug})  status: {s.status}  parts: {len(s.parts)}")
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


def cmd_render(args) -> int:
    print("render not implemented yet (Step 5)")
    return 2


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

    c = sub.add_parser("status", parents=[common], help="show series and part status")
    c.add_argument("slug")
    c.set_defaults(func=cmd_status)

    c = sub.add_parser("render", parents=[common], help="render a part (not implemented yet)")
    c.add_argument("slug")
    c.add_argument("part")
    c.set_defaults(func=cmd_render)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (UserError, ValidationError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
