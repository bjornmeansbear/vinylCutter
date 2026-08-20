# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build HPGL / Roland CAMM-GL III documents for the GX-24.

Command confidence levels
-------------------------
Two classes of command appear here, and the distinction matters if something
misbehaves on the machine:

STANDARD HPGL -- these are the ISO/ANSI HPGL commands the GX-24 implements as
part of CAMM-GL III. They are safe:

    IN;                 initialise, reset to defaults
    SP<n>;              select pen (always 1 on a cutter -- there is one blade)
    PU<x>,<y>;          pen up, move to absolute coordinate
    PD<x>,<y>,...;      pen down, cut through the listed absolute coordinates
    VS<n>;              velocity select, cm/s

ROLAND EXTENSION -- taken from field use (fab modules, Inkcut, community
drivers) rather than from Roland's own programmer's manual, which was not
available to verify against. They are believed correct but treat them as
unproven on your specific firmware (GX-24 ships v2.30):

    !FS<n>;             blade force, grams
    !PG;                page eject / feed and cut off

Everything Roland-specific is gated behind `roland_ext`. Pass
`roland_ext=False` to emit pure HPGL and set force/speed on the front panel
instead -- that is the fallback if the extensions turn out to misbehave.

Blade offset is deliberately NOT compensated here. The GX-24 corrects for the
swivel blade in firmware via its OFFSET menu setting. Applying offset in
software as well double-corrects and rounds off every corner.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .units import GX24_MAX_WIDTH_MM, mm_to_units

#: Coordinates emitted per PD command before starting a new one. The GX-24's
#: input buffer is small and long command lines are a known way to overrun it,
#: so paths are split across several PD commands rather than emitted as one
#: enormous line. Splitting is semantically free: consecutive PDs continue the
#: same cut because the pen stays down.
MAX_COORDS_PER_PD = 20

#: Roland documents blade force on the GX-24 as 20-250 gf.
FORCE_RANGE_GF = (20, 250)

#: Cutting speed in cm/s. The GX-24 panel exposes 1-50.
SPEED_RANGE_CMS = (1, 50)

Point = tuple[float, float]


class HpglError(ValueError):
    """Raised when a job cannot be expressed as valid HPGL for this machine."""


@dataclass
class HpglDocument:
    """Accumulates paths and renders them as an HPGL command stream.

    Coordinates are supplied in millimetres relative to the job origin, with
    +x across the media and +y along the feed direction. They are converted to
    plotter units at render time.
    """

    force_gf: int | None = None
    speed_cms: int | None = None
    roland_ext: bool = True
    #: Emit !PG; at the end to feed the material clear and cut it off.
    page_eject: bool = False
    #: Reject geometry wider than the GX-24 can physically reach.
    check_width: bool = True

    paths: list[tuple[list[Point], int | None]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.force_gf is not None:
            _check_range("force", self.force_gf, FORCE_RANGE_GF, "gf")
        if self.speed_cms is not None:
            _check_range("speed", self.speed_cms, SPEED_RANGE_CMS, "cm/s")

    def add_path(self, points: list[Point], force_gf: int | None = None) -> None:
        """Add one continuous cut path, in millimetres.

        `force_gf` overrides the document force for this path only, which is
        how the force-ladder calibration pattern steps pressure across a single
        job. It requires the Roland extensions.

        A path of fewer than two points cuts nothing and is dropped rather than
        emitted, since a lone PU/PD pair just stabs the vinyl.
        """
        if len(points) < 2:
            return
        if force_gf is not None:
            _check_range("force", force_gf, FORCE_RANGE_GF, "gf")
        if self.check_width:
            for x, _y in points:
                if not 0 <= x <= GX24_MAX_WIDTH_MM:
                    raise HpglError(
                        f"x={x:.1f}mm is outside the GX-24 carriage travel "
                        f"(0-{GX24_MAX_WIDTH_MM}mm). Scale or reposition the job."
                    )
        self.paths.append((list(points), force_gf))

    def add_paths(self, paths: list[list[Point]]) -> None:
        for p in paths:
            self.add_path(p)

    @property
    def bounds_mm(self) -> tuple[float, float, float, float]:
        """(min_x, min_y, max_x, max_y) over all paths, in mm."""
        if not self.paths:
            return (0.0, 0.0, 0.0, 0.0)
        pts = [pt for path, _ in self.paths for pt in path]
        xs = [x for x, _ in pts]
        ys = [y for _, y in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def render(self) -> str:
        """Render the full command stream, one command per line.

        Newlines are cosmetic -- HPGL is delimited by semicolons -- but they
        make the output diffable and readable, which is worth the few bytes
        when you are debugging what the machine actually received.
        """
        out: list[str] = ["IN;", "SP1;"]

        if self.speed_cms is not None:
            out.append(f"VS{self.speed_cms};")
        if self.force_gf is not None:
            if self.roland_ext:
                out.append(f"!FS{self.force_gf};")
            else:
                out.append(f"(* force {self.force_gf}gf -- set on front panel *)")

        current_force = self.force_gf
        for path, path_force in self.paths:
            if (
                path_force is not None
                and path_force != current_force
                and self.roland_ext
            ):
                out.append(f"!FS{path_force};")
                current_force = path_force
            out.extend(_render_path(path))

        # Park at the origin so the blade is clear of the work and the next job
        # starts from a known position.
        out.append("PU0,0;")
        if self.page_eject and self.roland_ext:
            out.append("!PG;")

        return "\n".join(out) + "\n"

    def __str__(self) -> str:
        return self.render()


def _render_path(path: list[Point]) -> list[str]:
    """Render one path as a PU move followed by chunked PD cuts."""
    head, *rest = path
    out = [f"PU{mm_to_units(head[0])},{mm_to_units(head[1])};"]

    for i in range(0, len(rest), MAX_COORDS_PER_PD):
        chunk = rest[i : i + MAX_COORDS_PER_PD]
        coords = ",".join(
            f"{mm_to_units(x)},{mm_to_units(y)}" for x, y in chunk
        )
        out.append(f"PD{coords};")

    return out


def _check_range(name: str, value: int, bounds: tuple[int, int], unit: str) -> None:
    lo, hi = bounds
    if not lo <= value <= hi:
        raise HpglError(
            f"{name} {value}{unit} is outside the GX-24 range {lo}-{hi}{unit}"
        )
