# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render an HPGL job back to SVG so you can look at it before cutting.

This is a deliberate round trip: it parses the HPGL that will actually go down
the wire, not the source artwork. That is the whole point -- it catches unit
errors, axis flips, and paths that fell out during conversion, because it shows
you what the *machine* will do rather than what you drew.

Pen-up travel is drawn too, faintly. Long straight hops across the preview are
the visual signature of a job that will spend its time driving around instead
of cutting.
"""

from __future__ import annotations

import re

from .units import UNIT_MM

_COMMAND = re.compile(r"(!?[A-Za-z]{2})([^;]*);")

Point = tuple[float, float]


def parse(hpgl: str) -> tuple[list[list[Point]], list[tuple[Point, Point]]]:
    """Parse HPGL into (cut_paths, travel_moves), in millimetres."""
    cuts: list[list[Point]] = []
    travels: list[tuple[Point, Point]] = []
    pos: Point = (0.0, 0.0)
    current: list[Point] = []

    for cmd, args in _COMMAND.findall(hpgl):
        cmd = cmd.upper()
        nums = [int(n) for n in re.findall(r"-?\d+", args)]
        pts = [
            (nums[i] * UNIT_MM, nums[i + 1] * UNIT_MM)
            for i in range(0, len(nums) - 1, 2)
        ]

        if cmd == "PU":
            if len(current) >= 2:
                cuts.append(current)
            current = []
            for pt in pts:
                travels.append((pos, pt))
                pos = pt
        elif cmd == "PD":
            if not current:
                current = [pos]
            for pt in pts:
                current.append(pt)
                pos = pt

    if len(current) >= 2:
        cuts.append(current)
    return cuts, travels


def to_svg(hpgl: str, *, show_travel: bool = True) -> str:
    """Render an HPGL stream as an SVG string, in the cutter's y-up frame."""
    cuts, travels = parse(hpgl)
    pts = [p for path in cuts for p in path]
    if not pts:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"/>'

    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad = 5.0
    w = (max_x - min_x) + 2 * pad
    h = (max_y - min_y) + 2 * pad

    def place(p: Point) -> str:
        # Flip y back for display: SVG is y-down, the machine frame is y-up.
        return f"{p[0] - min_x + pad:.3f},{max_y - p[1] + pad:.3f}"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}mm" '
        f'height="{h:.2f}mm" viewBox="0 0 {w:.3f} {h:.3f}">',
        f'<rect width="{w:.3f}" height="{h:.3f}" fill="#faf7f0"/>',
    ]

    if show_travel and travels:
        d = " ".join(f"M{place(a)} L{place(b)}" for a, b in travels)
        parts.append(
            f'<path d="{d}" fill="none" stroke="#c9b8a8" stroke-width="0.15" '
            f'stroke-dasharray="0.8 0.8"/>'
        )

    for path in cuts:
        d = "M" + " L".join(place(p) for p in path)
        parts.append(
            f'<path d="{d}" fill="none" stroke="#2b1d14" stroke-width="0.3" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
        )

    parts.append("</svg>")
    return "\n".join(parts)
