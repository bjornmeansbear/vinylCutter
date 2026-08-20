# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit conversion for Roland CAMM-GL III / HPGL coordinates.

The GX-24 addresses its work area in HPGL plotter units. One plotter unit is
0.025 mm exactly, i.e. 40 units/mm (1016 units/inch). This is the standard HPGL
resolution and is not Roland-specific.
"""

#: One HPGL plotter unit in millimetres.
UNIT_MM = 0.025

#: Plotter units per millimetre.
UNITS_PER_MM = 40

#: Plotter units per inch.
UNITS_PER_INCH = 1016

#: Maximum usable cut width of a GX-24 in mm. The machine accepts 24" media but
#: the carriage cannot reach the full width; Roland specifies 584 mm of travel.
GX24_MAX_WIDTH_MM = 584


def mm_to_units(mm: float) -> int:
    """Convert millimetres to plotter units, rounded to the nearest unit.

    Rounding here rather than truncating matters: truncation biases every
    coordinate toward the origin, which accumulates into visible drift on
    paths with many segments.
    """
    return round(mm * UNITS_PER_MM)


def units_to_mm(units: int) -> float:
    """Convert plotter units back to millimetres."""
    return units * UNIT_MM


def inch_to_mm(inch: float) -> float:
    return inch * 25.4
