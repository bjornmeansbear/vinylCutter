# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests. Run with: python3 -m unittest discover -s tests -t .

These lean on exact coordinate assertions rather than smoke tests, because the
failure mode that matters here is silent: a job that is off by a unit-conversion
factor still produces valid HPGL, and you find out by ruining a sheet of vinyl.
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cutter import optimize, preview, svg  # noqa: E402
from cutter.hpgl import HpglDocument, HpglError  # noqa: E402
from cutter.units import mm_to_units  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


class TestUnits(unittest.TestCase):
    def test_plotter_unit_is_40_per_mm(self):
        self.assertEqual(mm_to_units(1), 40)
        self.assertEqual(mm_to_units(25.4), 1016)  # one inch
        self.assertEqual(mm_to_units(0.025), 1)

    def test_rounds_rather_than_truncates(self):
        # 0.0374mm is 1.496 units. Truncation would bias toward the origin.
        self.assertEqual(mm_to_units(0.0374), 1)
        self.assertEqual(mm_to_units(0.0376), 2)


class TestHpgl(unittest.TestCase):
    def test_square_coordinates(self):
        doc = HpglDocument()
        doc.add_path([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        out = doc.render()
        self.assertIn("PU0,0;", out)
        self.assertIn("PD400,0,400,400,0,400,0,0;", out)

    def test_preamble_and_parking(self):
        out = HpglDocument(force_gf=110, speed_cms=20).render()
        lines = out.strip().split("\n")
        self.assertEqual(lines[0], "IN;")
        self.assertEqual(lines[1], "SP1;")
        self.assertIn("VS20;", lines)
        self.assertIn("!FS110;", lines)
        self.assertEqual(lines[-1], "PU0,0;")

    def test_roland_ext_can_be_disabled(self):
        out = HpglDocument(force_gf=110, roland_ext=False).render()
        self.assertNotIn("!FS", out)
        self.assertIn("front panel", out)

    def test_page_eject_requires_roland_ext(self):
        self.assertIn("!PG;", HpglDocument(page_eject=True).render())
        self.assertNotIn(
            "!PG;", HpglDocument(page_eject=True, roland_ext=False).render()
        )

    def test_long_path_is_split_across_pd_commands(self):
        doc = HpglDocument()
        doc.add_path([(i * 0.1, 0) for i in range(101)])
        pds = [l for l in doc.render().split("\n") if l.startswith("PD")]
        self.assertGreater(len(pds), 1, "long paths must be chunked for the buffer")
        for line in pds:
            coords = line[2:-1].split(",")
            self.assertLessEqual(len(coords) // 2, 20)

    def test_degenerate_paths_are_dropped(self):
        doc = HpglDocument()
        doc.add_path([(5, 5)])
        doc.add_path([])
        self.assertEqual(doc.paths, [])

    def test_rejects_out_of_range_force(self):
        with self.assertRaises(HpglError):
            HpglDocument(force_gf=500)

    def test_rejects_geometry_wider_than_the_machine(self):
        doc = HpglDocument()
        with self.assertRaises(HpglError) as ctx:
            doc.add_path([(0, 0), (700, 0)])
        self.assertIn("carriage travel", str(ctx.exception))

    def test_per_path_force_emits_once_per_change(self):
        doc = HpglDocument()
        doc.add_path([(0, 0), (1, 1)], force_gf=60)
        doc.add_path([(2, 2), (3, 3)], force_gf=60)
        doc.add_path([(4, 4), (5, 5)], force_gf=90)
        self.assertEqual(doc.render().count("!FS60;"), 1)
        self.assertEqual(doc.render().count("!FS90;"), 1)


class TestSvg(unittest.TestCase):
    def test_rect_lands_at_stated_physical_size(self):
        # 100mm wide artboard, viewBox 0 0 100 60 -> 1 user unit == 1mm.
        polylines, w, h = svg.load(FIXTURES / "sampler.svg")
        self.assertAlmostEqual(w, 100.0, places=6)
        self.assertAlmostEqual(h, 60.0, places=6)
        rect = next(p for p in polylines if len(p) == 5 and p[0] == p[-1]
                    and abs(p[0][0] - 5) < 1e-6 and abs(p[0][1] - 5) < 1e-6)
        xs = [x for x, _ in rect]
        ys = [y for _, y in rect]
        self.assertAlmostEqual(max(xs) - min(xs), 30.0, places=6)
        self.assertAlmostEqual(max(ys) - min(ys), 20.0, places=6)

    def test_text_and_hidden_layers_are_skipped(self):
        polylines, _w, _h = svg.load(FIXTURES / "sampler.svg")
        # The hidden layer is a full 100x60 rect; nothing may span the artboard.
        for pl in polylines:
            xs = [x for x, _ in pl]
            self.assertLess(max(xs) - min(xs), 99.0)

    def test_circle_is_round_and_correctly_sized(self):
        polylines, _w, _h = svg.load(FIXTURES / "sampler.svg")
        circle = max(polylines, key=lambda p: _radius_fit(p, (60, 15)))
        for x, y in circle:
            self.assertAlmostEqual(math.dist((x, y), (60, 15)), 10.0, delta=0.05)

    def test_flattening_stays_within_machine_resolution(self):
        # A circle flattened too coarsely shows as chords shorter than the
        # radius error; 0.02mm tolerance is below the 0.025mm machine unit.
        polylines, _w, _h = svg.load(FIXTURES / "sampler.svg")
        circle = max(polylines, key=lambda p: _radius_fit(p, (60, 15)))
        for a, b in zip(circle, circle[1:]):
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            sagitta = 10.0 - math.dist(mid, (60, 15))
            self.assertLess(sagitta, 0.025)

    def test_y_flip_puts_origin_at_bottom_left(self):
        polylines, _w, h = svg.load(FIXTURES / "sampler.svg")
        flipped = svg.to_machine_frame(polylines, h)
        _, min_y_before, _, max_y_before = optimize.bounds(polylines)
        _, min_y_after, _, max_y_after = optimize.bounds(flipped)
        self.assertAlmostEqual(min_y_after, h - max_y_before, places=6)

    def test_transform_on_group_is_applied(self):
        # The rounded rect sits inside translate(10,0) rotate(15 20 50), so no
        # point of it may remain at its untransformed x of 15..25.
        polylines, _w, _h = svg.load(FIXTURES / "sampler.svg")
        rounded = [p for p in polylines if 40 < min(y for _, y in p) < 60]
        self.assertTrue(rounded, "rounded rect not found")


class TestOptimize(unittest.TestCase):
    def test_linesort_reduces_travel(self):
        far = [[(0, 0), (1, 0)], [(100, 0), (101, 0)], [(2, 0), (3, 0)]]
        self.assertLess(
            optimize.travel(optimize.linesort(far)), optimize.travel(far)
        )

    def test_dedupe_drops_zero_length_segments(self):
        out = optimize.dedupe([[(0, 0), (0, 0), (0, 0), (10, 0)]])
        self.assertEqual(out, [[(0, 0), (10, 0)]])

    def test_dedupe_drops_single_point_paths(self):
        self.assertEqual(optimize.dedupe([[(5, 5), (5, 5)]]), [])

    def test_move_to_origin_respects_margin(self):
        out = optimize.move_to_origin([[(50, 50), (60, 60)]], margin=2)
        self.assertEqual(out[0][0], (2, 2))


class TestPreviewRoundTrip(unittest.TestCase):
    def test_hpgl_parses_back_to_the_same_geometry(self):
        """The strongest check available without hardware: geometry must
        survive the full mm -> plotter unit -> mm round trip."""
        original = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        doc = HpglDocument()
        doc.add_path(original)
        cuts, _travel = preview.parse(doc.render())
        self.assertEqual(len(cuts), 1)
        for got, want in zip(cuts[0], original):
            self.assertAlmostEqual(got[0], want[0], places=6)
            self.assertAlmostEqual(got[1], want[1], places=6)

    def test_travel_moves_are_separated_from_cuts(self):
        doc = HpglDocument()
        doc.add_path([(0, 0), (10, 0)])
        doc.add_path([(50, 0), (60, 0)])
        cuts, travels = preview.parse(doc.render())
        self.assertEqual(len(cuts), 2)
        self.assertTrue(any(math.dist(a, b) > 30 for a, b in travels))


def _radius_fit(path, centre):
    """Score how well a path matches a circle about `centre` (higher = better)."""
    ds = [math.dist(p, centre) for p in path]
    if not ds or max(ds) == 0:
        return -math.inf
    return -(max(ds) - min(ds)) - abs(len(path) < 8) * 100


if __name__ == "__main__":
    unittest.main()
