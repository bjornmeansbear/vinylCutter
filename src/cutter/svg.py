# SPDX-License-Identifier: AGPL-3.0-or-later
"""Flatten an SVG into polylines, in millimetres.

Why this is hand-rolled rather than delegated to vpype: vpype depends on
Shapely, which needs a compiled GEOS and lags new Python releases -- it will not
install on Python 3.14 without a source build. Making the machine layer depend
on that would mean the tool cannot be installed on the machine you are holding.
Everything here is stdlib, so it runs anywhere Python does. vpype remains
worth adding later as an *optional* optimisation pass.

What this handles: path, polyline, polygon, line, rect, circle, ellipse, all
transform types, viewBox scaling, and unit suffixes. Curves and arcs are
flattened to polylines at a tolerance tied to the machine's own resolution --
there is no point emitting detail finer than 0.025mm because the GX-24 cannot
address it.

What this deliberately does NOT handle: fills, strokes, text, clip paths, and
masks. A cutter follows path geometry and nothing else. Text must be converted
to outlines and strokes expanded before export -- see README.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

Point = tuple[float, float]
Matrix = tuple[float, float, float, float, float, float]  # a b c d e f

SVG_NS = "http://www.w3.org/2000/svg"

IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

#: Flattening tolerance in user units before scaling. Refined per-document once
#: the mm scale is known; see _tolerance_for.
DEFAULT_TOLERANCE_MM = 0.02

#: CSS absolute unit lengths in millimetres. SVG's user unit is the CSS px.
UNIT_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "in": 25.4,
    "pt": 25.4 / 72,
    "pc": 25.4 / 6,
    "px": 25.4 / 96,
    "": 25.4 / 96,
}

_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_LENGTH = re.compile(r"^\s*([-+]?[\d.eE+-]+)\s*([a-z%]*)\s*$", re.I)
_CMD = re.compile(r"([MmZzLlHhVvCcSsQqTtAa])")
_TRANSFORM = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")


class SvgError(ValueError):
    """Raised when an SVG cannot be interpreted as cuttable geometry."""


# --------------------------------------------------------------------------
# matrix helpers
# --------------------------------------------------------------------------

def mat_mul(m: Matrix, n: Matrix) -> Matrix:
    """Compose two 2x3 affine matrices (apply n, then m)."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def mat_apply(m: Matrix, pt: Point) -> Point:
    a, b, c, d, e, f = m
    x, y = pt
    return (a * x + c * y + e, b * x + d * y + f)


def parse_transform(text: str | None) -> Matrix:
    """Parse an SVG transform attribute into a single matrix."""
    if not text:
        return IDENTITY
    m = IDENTITY
    for name, args in _TRANSFORM.findall(text):
        v = [float(x) for x in _NUM.findall(args)]
        if name == "matrix" and len(v) == 6:
            t = (v[0], v[1], v[2], v[3], v[4], v[5])
        elif name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            sx = v[0]
            sy = v[1] if len(v) > 1 else sx
            t = (sx, 0, 0, sy, 0, 0)
        elif name == "rotate":
            ang = math.radians(v[0])
            cos, sin = math.cos(ang), math.sin(ang)
            t = (cos, sin, -sin, cos, 0, 0)
            if len(v) >= 3:
                cx, cy = v[1], v[2]
                t = mat_mul((1, 0, 0, 1, cx, cy), mat_mul(t, (1, 0, 0, 1, -cx, -cy)))
        elif name == "skewX":
            t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewY":
            t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            continue
        m = mat_mul(m, t)
    return m


def parse_length(text: str | None, default: float | None = None) -> float | None:
    """Parse an SVG length into millimetres. Percentages are not resolvable."""
    if text is None:
        return default
    match = _LENGTH.match(text)
    if not match:
        return default
    value, unit = match.group(1), match.group(2).lower()
    if unit == "%":
        return default
    if unit not in UNIT_MM:
        return default
    return float(value) * UNIT_MM[unit]


# --------------------------------------------------------------------------
# curve flattening
# --------------------------------------------------------------------------

def _cubic_steps(p0: Point, p1: Point, p2: Point, p3: Point, tol: float) -> int:
    """Pick a subdivision count for a cubic bezier.

    Uses the control polygon length as a cheap upper bound on arc length, then
    solves for the step count whose flat-chord error stays under `tol`. Cheap
    and conservative, which is the right trade here -- overshooting by a few
    segments costs bytes, undershooting costs visible faceting in the vinyl.
    """
    poly = (
        math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
    )
    if poly <= 0:
        return 1
    # Chord error of an n-segment approximation scales as (L/n)^2 / 8R; using
    # the polygon length as a proxy for both gives this bound.
    n = int(math.ceil(math.sqrt(poly / max(tol, 1e-9))))
    return max(1, min(n, 512))


def _cubic(p0: Point, p1: Point, p2: Point, p3: Point, tol: float) -> list[Point]:
    n = _cubic_steps(p0, p1, p2, p3, tol)
    pts = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        x = u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0]
        y = u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
        pts.append((x, y))
    return pts


def _quadratic(p0: Point, p1: Point, p2: Point, tol: float) -> list[Point]:
    """Elevate the quadratic to a cubic and reuse the cubic flattener."""
    c1 = (p0[0] + 2 / 3 * (p1[0] - p0[0]), p0[1] + 2 / 3 * (p1[1] - p0[1]))
    c2 = (p2[0] + 2 / 3 * (p1[0] - p2[0]), p2[1] + 2 / 3 * (p1[1] - p2[1]))
    return _cubic(p0, c1, c2, p2, tol)


def _arc(
    p0: Point,
    rx: float,
    ry: float,
    rotation: float,
    large_arc: bool,
    sweep: bool,
    p1: Point,
    tol: float,
) -> list[Point]:
    """Flatten an SVG elliptical arc using the endpoint->centre parameterisation
    from the SVG spec, appendix F.6."""
    if p0 == p1:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [p1]

    phi = math.radians(rotation % 360)
    cos_p, sin_p = math.cos(phi), math.sin(phi)

    dx2 = (p0[0] - p1[0]) / 2
    dy2 = (p0[1] - p1[1]) / 2
    x1p = cos_p * dx2 + sin_p * dy2
    y1p = -sin_p * dx2 + cos_p * dy2

    # Scale radii up if they are too small to span the endpoints (spec F.6.6).
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        scale = math.sqrt(lam)
        rx *= scale
        ry *= scale

    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    factor = math.sqrt(max(num / den, 0)) if den else 0.0
    if large_arc == sweep:
        factor = -factor

    cxp = factor * rx * y1p / ry
    cyp = -factor * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (p0[0] + p1[0]) / 2
    cy = sin_p * cxp + cos_p * cyp + (p0[1] + p1[1]) / 2

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        norm = math.hypot(ux, uy) * math.hypot(vx, vy)
        if norm == 0:
            return 0.0
        a = math.acos(max(-1.0, min(1.0, dot / norm)))
        return -a if ux * vy - uy * vx < 0 else a

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle(
        (x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry
    )
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    r_max = max(rx, ry)
    steps = max(2, int(math.ceil(abs(delta) / (2 * math.acos(max(-1.0, min(1.0, 1 - tol / max(r_max, 1e-9))))))))
    steps = min(steps, 512)

    pts = []
    for i in range(1, steps + 1):
        t = theta1 + delta * i / steps
        x = cos_p * rx * math.cos(t) - sin_p * ry * math.sin(t) + cx
        y = sin_p * rx * math.cos(t) + cos_p * ry * math.sin(t) + cy
        pts.append((x, y))
    return pts


# --------------------------------------------------------------------------
# path data
# --------------------------------------------------------------------------

def parse_path_data(d: str, tol: float) -> list[list[Point]]:
    """Flatten an SVG path `d` attribute into a list of subpaths."""
    tokens = [t for t in _CMD.split(d) if t.strip()]
    subpaths: list[list[Point]] = []
    current: list[Point] = []
    pos: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)
    prev_cubic: Point | None = None
    prev_quad: Point | None = None
    cmd = ""

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if _CMD.fullmatch(token):
            cmd = token
            i += 1
            args = _NUM.findall(tokens[i]) if i < len(tokens) and not _CMD.fullmatch(tokens[i]) else []
            nums = [float(a) for a in args]
            if args:
                i += 1
        else:
            nums = [float(a) for a in _NUM.findall(token)]
            i += 1

        rel = cmd.islower()
        c = cmd.upper()

        def take(n: int, k: int) -> tuple[float, ...]:
            return tuple(nums[k : k + n])

        if c == "Z":
            if current:
                if current[0] != current[-1]:
                    current.append(current[0])
                subpaths.append(current)
                current = []
            pos = start
            prev_cubic = prev_quad = None
            continue

        if c == "M":
            k = 0
            first = True
            while k + 2 <= len(nums):
                x, y = take(2, k)
                pt = (pos[0] + x, pos[1] + y) if rel else (x, y)
                if first:
                    if current:
                        subpaths.append(current)
                    current = [pt]
                    start = pt
                    first = False
                else:
                    current.append(pt)
                pos = pt
                k += 2
            prev_cubic = prev_quad = None
            continue

        if not current:
            # A drawing command without a preceding moveto: start where we are.
            current = [pos]
            start = pos

        k = 0
        while k < len(nums):
            if c == "L":
                x, y = take(2, k); k += 2
                pt = (pos[0] + x, pos[1] + y) if rel else (x, y)
                current.append(pt); pos = pt
                prev_cubic = prev_quad = None
            elif c == "H":
                (x,) = take(1, k); k += 1
                pt = (pos[0] + x, pos[1]) if rel else (x, pos[1])
                current.append(pt); pos = pt
                prev_cubic = prev_quad = None
            elif c == "V":
                (y,) = take(1, k); k += 1
                pt = (pos[0], pos[1] + y) if rel else (pos[0], y)
                current.append(pt); pos = pt
                prev_cubic = prev_quad = None
            elif c == "C":
                x1, y1, x2, y2, x, y = take(6, k); k += 6
                if rel:
                    c1 = (pos[0] + x1, pos[1] + y1)
                    c2 = (pos[0] + x2, pos[1] + y2)
                    end = (pos[0] + x, pos[1] + y)
                else:
                    c1, c2, end = (x1, y1), (x2, y2), (x, y)
                current.extend(_cubic(pos, c1, c2, end, tol))
                prev_cubic, prev_quad = c2, None
                pos = end
            elif c == "S":
                x2, y2, x, y = take(4, k); k += 4
                if rel:
                    c2 = (pos[0] + x2, pos[1] + y2)
                    end = (pos[0] + x, pos[1] + y)
                else:
                    c2, end = (x2, y2), (x, y)
                c1 = (
                    (2 * pos[0] - prev_cubic[0], 2 * pos[1] - prev_cubic[1])
                    if prev_cubic
                    else pos
                )
                current.extend(_cubic(pos, c1, c2, end, tol))
                prev_cubic, prev_quad = c2, None
                pos = end
            elif c == "Q":
                x1, y1, x, y = take(4, k); k += 4
                if rel:
                    c1 = (pos[0] + x1, pos[1] + y1)
                    end = (pos[0] + x, pos[1] + y)
                else:
                    c1, end = (x1, y1), (x, y)
                current.extend(_quadratic(pos, c1, end, tol))
                prev_quad, prev_cubic = c1, None
                pos = end
            elif c == "T":
                x, y = take(2, k); k += 2
                end = (pos[0] + x, pos[1] + y) if rel else (x, y)
                c1 = (
                    (2 * pos[0] - prev_quad[0], 2 * pos[1] - prev_quad[1])
                    if prev_quad
                    else pos
                )
                current.extend(_quadratic(pos, c1, end, tol))
                prev_quad, prev_cubic = c1, None
                pos = end
            elif c == "A":
                rx, ry, rot, laf, sf, x, y = take(7, k); k += 7
                end = (pos[0] + x, pos[1] + y) if rel else (x, y)
                current.extend(_arc(pos, rx, ry, rot, bool(laf), bool(sf), end, tol))
                prev_cubic = prev_quad = None
                pos = end
            else:
                break

    if current:
        subpaths.append(current)
    return [sp for sp in subpaths if len(sp) >= 2]


# --------------------------------------------------------------------------
# shapes and document walking
# --------------------------------------------------------------------------

def _floats(el: ET.Element, *names: str) -> list[float]:
    return [float(el.get(n, 0) or 0) for n in names]


def _shape_to_subpaths(el: ET.Element, tag: str, tol: float) -> list[list[Point]]:
    """Convert a non-path shape element into subpaths, in user units."""
    if tag == "rect":
        x, y, w, h, rx, ry = _floats(el, "x", "y", "width", "height", "rx", "ry")
        if w <= 0 or h <= 0:
            return []
        if rx or ry:
            # Rounded rect: fall through to a path so the corner arcs get the
            # same flattening treatment as everything else.
            rx = rx or ry
            ry = ry or rx
            rx, ry = min(rx, w / 2), min(ry, h / 2)
            d = (
                f"M{x+rx},{y} H{x+w-rx} A{rx},{ry} 0 0 1 {x+w},{y+ry} "
                f"V{y+h-ry} A{rx},{ry} 0 0 1 {x+w-rx},{y+h} "
                f"H{x+rx} A{rx},{ry} 0 0 1 {x},{y+h-ry} "
                f"V{y+ry} A{rx},{ry} 0 0 1 {x+rx},{y} Z"
            )
            return parse_path_data(d, tol)
        return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]

    if tag == "line":
        x1, y1, x2, y2 = _floats(el, "x1", "y1", "x2", "y2")
        return [[(x1, y1), (x2, y2)]]

    if tag in ("polyline", "polygon"):
        nums = [float(n) for n in _NUM.findall(el.get("points", ""))]
        pts = list(zip(nums[::2], nums[1::2]))
        if len(pts) < 2:
            return []
        if tag == "polygon" and pts[0] != pts[-1]:
            pts.append(pts[0])
        return [pts]

    if tag in ("circle", "ellipse"):
        if tag == "circle":
            cx, cy, r = _floats(el, "cx", "cy", "r")
            rx = ry = r
        else:
            cx, cy, rx, ry = _floats(el, "cx", "cy", "rx", "ry")
        if rx <= 0 or ry <= 0:
            return []
        d = (
            f"M{cx-rx},{cy} A{rx},{ry} 0 1 0 {cx+rx},{cy} "
            f"A{rx},{ry} 0 1 0 {cx-rx},{cy} Z"
        )
        return parse_path_data(d, tol)

    return []


def _is_hidden(el: ET.Element) -> bool:
    """Skip hidden layers.

    Illustrator exports hidden layers as display:none rather than omitting
    them, so without this check a file that looks like one logo cuts three
    rejected drafts stacked on top of each other.
    """
    if el.get("display") == "none":
        return True
    style = el.get("style", "")
    return "display:none" in style.replace(" ", "")


def _walk(
    el: ET.Element, ctm: Matrix, tol: float, out: list[list[Point]]
) -> None:
    if _is_hidden(el):
        return

    ctm = mat_mul(ctm, parse_transform(el.get("transform")))
    tag = el.tag.split("}")[-1]

    if tag == "path":
        d = el.get("d", "")
        if d.strip():
            for sp in parse_path_data(d, tol):
                out.append([mat_apply(ctm, p) for p in sp])
    elif tag in ("rect", "line", "polyline", "polygon", "circle", "ellipse"):
        for sp in _shape_to_subpaths(el, tag, tol):
            out.append([mat_apply(ctm, p) for p in sp])
    elif tag in ("defs", "clipPath", "mask", "symbol", "marker", "text"):
        # Not cuttable geometry. `text` in particular must be outlined before
        # export; silently skipping is better than cutting a fallback glyph.
        return

    for child in el:
        _walk(child, ctm, tol, out)


def _tolerance_for(scale: float) -> float:
    """Flattening tolerance in user units, given user-units-to-mm `scale`."""
    return DEFAULT_TOLERANCE_MM / scale if scale else DEFAULT_TOLERANCE_MM


def load(source: str | Path) -> tuple[list[list[Point]], float, float]:
    """Read an SVG and return (polylines_in_mm, width_mm, height_mm).

    Coordinates come back in SVG orientation: origin top-left, +y downward.
    Converting to the cutter's bottom-left, +y-up frame is the caller's job --
    see `to_machine_frame`.
    """
    source = Path(source)
    try:
        tree = ET.parse(source)
    except ET.ParseError as exc:
        raise SvgError(f"{source.name} is not valid XML: {exc}") from exc

    root = tree.getroot()
    if root.tag.split("}")[-1] != "svg":
        raise SvgError(f"{source.name} has root <{root.tag}>, expected <svg>")

    viewbox = root.get("viewBox")
    vb = [float(n) for n in _NUM.findall(viewbox)] if viewbox else None

    width_mm = parse_length(root.get("width"))
    height_mm = parse_length(root.get("height"))

    # Establish user-units-to-mm. Prefer the ratio of physical size to viewBox,
    # which is what makes an Illustrator artboard come out at its stated size.
    if vb and len(vb) == 4 and vb[2] and vb[3] and width_mm and height_mm:
        scale = width_mm / vb[2]
        base: Matrix = (1, 0, 0, 1, -vb[0], -vb[1])
    elif vb and len(vb) == 4 and vb[2] and vb[3]:
        # No physical size: treat user units as CSS px.
        scale = UNIT_MM["px"]
        width_mm, height_mm = vb[2] * scale, vb[3] * scale
        base = (1, 0, 0, 1, -vb[0], -vb[1])
    else:
        scale = UNIT_MM["px"]
        width_mm = width_mm or 0.0
        height_mm = height_mm or 0.0
        base = IDENTITY

    tol = _tolerance_for(scale)
    raw: list[list[Point]] = []
    _walk(root, base, tol, raw)

    polylines = [[(x * scale, y * scale) for x, y in sp] for sp in raw]
    return polylines, width_mm or 0.0, height_mm or 0.0


def to_machine_frame(
    polylines: list[list[Point]], height_mm: float
) -> list[list[Point]]:
    """Flip from SVG's y-down frame to the cutter's y-up frame."""
    return [[(x, height_mm - y) for x, y in sp] for sp in polylines]
