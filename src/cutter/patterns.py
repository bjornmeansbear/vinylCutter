# SPDX-License-Identifier: AGPL-3.0-or-later
"""Calibration and test patterns.

These exist so you can prove out the machine before trusting it with real
artwork. Run them in this order:

1. `registration` -- confirms the job lands where you expect, at the right
   scale, with the axes the right way round. Measure the arms with a ruler.
2. `ladder` -- finds the blade force for your material. Weed the result; the
   lowest force whose square lifts cleanly without scoring the backing wins.
3. `nested` -- confirms corner quality and that the OFFSET setting is right.
"""

from __future__ import annotations

from .hpgl import HpglDocument, Point


def _rect(x: float, y: float, w: float, h: float) -> list[Point]:
    """A closed rectangle, starting and ending at the same corner."""
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]


def registration(doc: HpglDocument, *, arm_x: float = 60, arm_y: float = 30) -> None:
    """An L with deliberately unequal arms, plus a 10mm tick on each.

    Unequal arms are the point: a square tells you nothing if x and y are
    swapped, but a 60x30 L is unambiguous. Measure both arms. If they read
    60mm and 30mm you have correct scale and orientation; if they read 30 and
    60 your axes are transposed; if they read something like 1.5mm and 0.75mm
    your unit conversion is off by the 40 units/mm factor.
    """
    doc.add_path([(0, 0), (arm_x, 0)])
    doc.add_path([(0, 0), (0, arm_y)])
    # Ticks at 10mm from the corner, pointing inward, to check for backlash.
    doc.add_path([(10, 0), (10, 3)])
    doc.add_path([(0, 10), (3, 10)])


def ladder(
    doc: HpglDocument,
    *,
    forces: list[int] | None = None,
    size: float = 15,
    gap: float = 5,
) -> None:
    """A row of squares, each cut at a different blade force.

    Requires the Roland !FS extension. If your firmware ignores mid-job force
    changes every square will cut identically -- that is itself a useful
    result, and means you calibrate by running single squares instead.
    """
    forces = forces or [40, 60, 80, 100, 120, 140, 160]
    for i, f in enumerate(forces):
        x = i * (size + gap)
        doc.add_path(_rect(x, 0, size, size), force_gf=f)


def nested(doc: HpglDocument, *, outer: float = 40, inner: float = 20) -> None:
    """A square inside a square -- the weeding and corner-quality test.

    Cut this and weed the ring between the two squares. Sharp inside corners
    mean the OFFSET panel setting matches your blade. Rounded corners mean
    OFFSET is too low; overshooting corners with little tails mean it is too
    high.
    """
    pad = (outer - inner) / 2
    doc.add_path(_rect(0, 0, outer, outer))
    doc.add_path(_rect(pad, pad, inner, inner))


def square(doc: HpglDocument, *, size: float = 20) -> None:
    """The smallest useful thing: one closed square. Hello, world."""
    doc.add_path(_rect(0, 0, size, size))


#: name -> (builder, one-line description) for the CLI.
PATTERNS = {
    "square": (square, "a single 20mm square -- smallest possible test cut"),
    "registration": (registration, "60x30mm L -- verifies scale, origin and axis order"),
    "ladder": (ladder, "row of squares at stepped blade force -- material calibration"),
    "nested": (nested, "square in a square -- corner quality and weeding test"),
}


def build(name: str, doc: HpglDocument, **kwargs) -> HpglDocument:
    """Populate `doc` with the named pattern and return it."""
    if name not in PATTERNS:
        raise KeyError(
            f"unknown pattern {name!r}; try one of: {', '.join(sorted(PATTERNS))}"
        )
    builder, _desc = PATTERNS[name]
    builder(doc, **kwargs)
    return doc
