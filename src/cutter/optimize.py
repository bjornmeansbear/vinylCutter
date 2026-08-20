# SPDX-License-Identifier: AGPL-3.0-or-later
"""Path ordering and cleanup.

Ordering matters more on a cutter than it looks. An unoptimised job spends most
of its time driving the head between shapes with the blade up, and every one of
those moves drags the media back and forth under the pinch rollers. Less travel
means less cumulative tracking error, which is the thing that makes long jobs
drift out of registration.
"""

from __future__ import annotations

import math

Point = tuple[float, float]
Polyline = list[Point]


def dedupe(polylines: list[Polyline], tol: float = 0.01) -> list[Polyline]:
    """Drop consecutive duplicate points and paths too small to cut.

    Illustrator exports frequently contain zero-length segments and stray
    single-point paths; each one is a needless blade drop into the vinyl.
    """
    out: list[Polyline] = []
    for pl in polylines:
        cleaned: Polyline = []
        for pt in pl:
            if not cleaned or math.dist(cleaned[-1], pt) > tol:
                cleaned.append(pt)
        if len(cleaned) >= 2 and _length(cleaned) > tol:
            out.append(cleaned)
    return out


def linesort(polylines: list[Polyline], *, flip: bool = True) -> list[Polyline]:
    """Greedily reorder paths to minimise pen-up travel.

    Nearest-neighbour rather than anything cleverer: it is O(n^2) but n is the
    number of *paths*, not points, so it stays instant for real artwork, and it
    typically removes 60-80% of travel versus document order. With `flip`, each
    path may also be reversed if its far end is nearer, which helps a lot on
    open paths like lettering strokes.
    """
    if len(polylines) < 2:
        return list(polylines)

    remaining = list(polylines)
    current = remaining.pop(0)
    ordered = [current]
    pos = current[-1]

    while remaining:
        best_i = 0
        best_d = math.inf
        best_reversed = False
        for i, pl in enumerate(remaining):
            d_start = math.dist(pos, pl[0])
            if d_start < best_d:
                best_i, best_d, best_reversed = i, d_start, False
            if flip:
                d_end = math.dist(pos, pl[-1])
                if d_end < best_d:
                    best_i, best_d, best_reversed = i, d_end, True
        nxt = remaining.pop(best_i)
        if best_reversed:
            nxt = nxt[::-1]
        ordered.append(nxt)
        pos = nxt[-1]

    return ordered


def travel(polylines: list[Polyline]) -> float:
    """Total pen-up distance in the given order, in mm."""
    if not polylines:
        return 0.0
    total = math.dist((0.0, 0.0), polylines[0][0])
    for a, b in zip(polylines, polylines[1:]):
        total += math.dist(a[-1], b[0])
    return total


def cut_length(polylines: list[Polyline]) -> float:
    """Total pen-down distance, in mm."""
    return sum(_length(pl) for pl in polylines)


def bounds(polylines: list[Polyline]) -> tuple[float, float, float, float]:
    pts = [p for pl in polylines for p in pl]
    if not pts:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def move_to_origin(polylines: list[Polyline], margin: float = 0.0) -> list[Polyline]:
    """Translate so the artwork's lower-left corner sits at (margin, margin).

    The GX-24 cuts relative to wherever you set the origin on the panel, so
    artwork that carries an arbitrary offset from its artboard wastes material
    and can push the job outside the carriage travel.
    """
    min_x, min_y, _, _ = bounds(polylines)
    dx, dy = margin - min_x, margin - min_y
    return [[(x + dx, y + dy) for x, y in pl] for pl in polylines]


def scale(polylines: list[Polyline], factor: float) -> list[Polyline]:
    return [[(x * factor, y * factor) for x, y in pl] for pl in polylines]


def _length(pl: Polyline) -> float:
    return sum(math.dist(a, b) for a, b in zip(pl, pl[1:]))
