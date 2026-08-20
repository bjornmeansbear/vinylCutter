# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command line interface.

    cutter info                     what the tool can see from here
    cutter pattern registration     generate a calibration pattern
    cutter convert art.svg          SVG -> HPGL, with a job report
    cutter preview job.hpgl         render the job back to SVG to check it
    cutter send job.hpgl            stream HPGL to the machine
    cutter cut art.svg              convert and send in one step

Every command that can touch the machine takes --dry-run, and --dry-run is the
default on any platform without a device node, so nothing moves by accident.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, optimize
from .device import DeviceError, Sender, find_devices, platform_note
from .hpgl import FORCE_RANGE_GF, SPEED_RANGE_CMS, HpglDocument, HpglError
from .patterns import PATTERNS, build
from .preview import to_svg
from .svg import SvgError, load, to_machine_frame
from .units import GX24_MAX_WIDTH_MM


def _machine_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--force", type=int, metavar="GF",
                   help=f"blade force in grams ({FORCE_RANGE_GF[0]}-{FORCE_RANGE_GF[1]})")
    p.add_argument("--speed", type=int, metavar="CMS",
                   help=f"cutting speed in cm/s ({SPEED_RANGE_CMS[0]}-{SPEED_RANGE_CMS[1]})")
    p.add_argument("--no-roland-ext", action="store_true",
                   help="emit pure HPGL only; set force and speed on the front panel")
    p.add_argument("--page-eject", action="store_true",
                   help="feed and cut off the material when the job finishes (!PG)")


def _send_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--device", help="device node (default: first /dev/usb/lp*)")
    p.add_argument("--dry-run", action="store_true", help="print HPGL instead of cutting")
    p.add_argument("--chunk", type=int, default=1024, help="bytes per write (default 1024)")
    p.add_argument("--delay", type=float, default=0.05,
                   help="seconds between writes (default 0.05)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cutter", description="Drive a Roland GX-24 vinyl cutter directly."
    )
    parser.add_argument("--version", action="version", version=f"cutter {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="show detected devices and environment")

    p_pattern = sub.add_parser("pattern", help="generate a calibration pattern")
    p_pattern.add_argument("name", choices=sorted(PATTERNS))
    p_pattern.add_argument("-o", "--output", type=Path, help="write HPGL here")
    _machine_args(p_pattern)
    _send_args(p_pattern)
    p_pattern.add_argument("--send", action="store_true", help="send it to the cutter")

    p_convert = sub.add_parser("convert", help="convert an SVG to HPGL")
    p_convert.add_argument("svg", type=Path)
    p_convert.add_argument("-o", "--output", type=Path)
    _machine_args(p_convert)
    _convert_args(p_convert)

    p_preview = sub.add_parser("preview", help="render an HPGL job back to SVG")
    p_preview.add_argument("hpgl", type=Path)
    p_preview.add_argument("-o", "--output", type=Path, help="write SVG here")
    p_preview.add_argument("--no-travel", action="store_true",
                           help="hide pen-up travel lines")

    p_send = sub.add_parser("send", help="stream an HPGL file to the cutter")
    p_send.add_argument("hpgl", type=Path)
    _send_args(p_send)

    p_cut = sub.add_parser("cut", help="convert an SVG and send it")
    p_cut.add_argument("svg", type=Path)
    _machine_args(p_cut)
    _convert_args(p_cut)
    _send_args(p_cut)

    return parser


def _convert_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--margin", type=float, default=0.0,
                   help="mm of clearance from the origin (default 0)")
    p.add_argument("--scale", type=float, default=1.0, help="scale factor (default 1.0)")
    p.add_argument("--no-sort", action="store_true", help="keep document path order")
    p.add_argument("--no-flip-y", action="store_true",
                   help="do not flip SVG's y-down axis to the cutter's y-up")
    p.add_argument("--keep-origin", action="store_true",
                   help="do not move artwork to the origin")


# --------------------------------------------------------------------------

def cmd_info(args: argparse.Namespace) -> int:
    print(f"cutter {__version__}")
    print(f"python {sys.version.split()[0]}  {sys.platform}")
    devices = find_devices()
    if devices:
        print("\ndevices:")
        for d in devices:
            print(f"  {d}")
    else:
        print("\ndevices: none found")
        note = platform_note()
        if note:
            print(f"  {note}")
        else:
            print("  Check power and USB, then: dmesg | tail")
    print(f"\nmax cut width: {GX24_MAX_WIDTH_MM}mm")
    print(f"patterns: {', '.join(sorted(PATTERNS))}")
    return 0


def _doc_from_args(args: argparse.Namespace) -> HpglDocument:
    return HpglDocument(
        force_gf=args.force,
        speed_cms=args.speed,
        roland_ext=not args.no_roland_ext,
        page_eject=args.page_eject,
    )


def _emit(hpgl: str, args: argparse.Namespace, *, send: bool) -> int:
    output = getattr(args, "output", None)
    if output:
        output.write_text(hpgl)
        print(f"wrote {output} ({len(hpgl)} bytes)", file=sys.stderr)
    if not send:
        if not output:
            sys.stdout.write(hpgl)
        return 0
    return _send(hpgl, args)


def _send(hpgl: str, args: argparse.Namespace) -> int:
    dry = args.dry_run or (not find_devices() and not args.device)
    if dry and not args.dry_run:
        print("No device found -- showing HPGL instead of cutting.", file=sys.stderr)

    def progress(sent: int, total: int) -> None:
        pct = 100 * sent / total
        print(f"\r  sending {sent}/{total} bytes ({pct:.0f}%)", end="", file=sys.stderr)

    sender = Sender(
        device=args.device,
        chunk_bytes=args.chunk,
        chunk_delay=args.delay,
        dry_run=dry,
        progress=None if dry else progress,
    )
    n = sender.send(hpgl)
    if not dry:
        print(f"\n  done, {n} bytes to {sender.device}", file=sys.stderr)
    return 0


def cmd_pattern(args: argparse.Namespace) -> int:
    doc = _doc_from_args(args)
    build(args.name, doc)
    return _emit(doc.render(), args, send=args.send)


def _load_job(args: argparse.Namespace) -> HpglDocument:
    polylines, _w, height = load(args.svg)
    if not polylines:
        raise SvgError(
            f"{args.svg.name} contains no cuttable paths. Text must be converted "
            "to outlines and strokes expanded before export."
        )

    if not args.no_flip_y:
        polylines = to_machine_frame(polylines, height)
    if args.scale != 1.0:
        polylines = optimize.scale(polylines, args.scale)

    polylines = optimize.dedupe(polylines)
    before = optimize.travel(polylines)
    if not args.no_sort:
        polylines = optimize.linesort(polylines)
    after = optimize.travel(polylines)

    if not args.keep_origin:
        polylines = optimize.move_to_origin(polylines, args.margin)

    min_x, min_y, max_x, max_y = optimize.bounds(polylines)
    saved = (1 - after / before) * 100 if before else 0.0
    print(
        f"{args.svg.name}: {len(polylines)} paths, "
        f"{max_x - min_x:.1f} x {max_y - min_y:.1f} mm\n"
        f"  cut {optimize.cut_length(polylines) / 1000:.2f} m, "
        f"travel {after / 1000:.2f} m"
        + (f" (down {saved:.0f}% from sorting)" if saved > 1 else ""),
        file=sys.stderr,
    )

    doc = _doc_from_args(args)
    doc.add_paths(polylines)
    return doc


def cmd_convert(args: argparse.Namespace) -> int:
    return _emit(_load_job(args).render(), args, send=False)


def cmd_cut(args: argparse.Namespace) -> int:
    return _send(_load_job(args).render(), args)


def cmd_preview(args: argparse.Namespace) -> int:
    svg = to_svg(args.hpgl.read_text(), show_travel=not args.no_travel)
    if args.output:
        args.output.write_text(svg)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(svg)
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    return _send(args.hpgl.read_text(), args)


COMMANDS = {
    "info": cmd_info,
    "pattern": cmd_pattern,
    "convert": cmd_convert,
    "preview": cmd_preview,
    "send": cmd_send,
    "cut": cmd_cut,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (HpglError, SvgError, DeviceError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc.filename}: no such file", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted -- the machine may be mid-job", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
