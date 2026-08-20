<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# Other machines, other languages

Notes and links for driving cutters and plotters that aren't the GX-24 — partly
reference, partly a map of what it would take to support them here.

Verified August 2026; repo activity figures were current then.

---

## The three protocol families

Understanding which family a machine belongs to tells you immediately how much
work supporting it is.

| Family | Machines | What the host sends |
|---|---|---|
| **HPGL / CAMM-GL** | Roland, Summa, Graphtec CE-series (HPGL mode), Mutoh, most generic imports (USCutter, Vinyl Express) | Coordinates. `PU`/`PD` move and cut |
| **GPGL** | Silhouette (Cameo, Portrait, Curio), Graphtec CraftRobo, Graphtec CE-series (GP-GL mode) | Coordinates. `M`/`D` move and draw |
| **Motor control** | AxiDraw, EggBot, WaterColorBot | Step counts and durations. No paths at all |

The first two are drawing languages and are close cousins — different syntax,
same idea. The third is a different category of thing.

---

## Silhouette Cameo — GPGL

**GPGL** (Graphtec Plotter Graphics Language). Silhouette is made by Graphtec.
Same conceptual model as HPGL, unrelated syntax:

```
M 2400,0        move with the tool up      (HPGL: PU2400,0;)
D 2400,1200     draw with the tool down    (HPGL: PD2400,1200;)
```

Never publicly documented for these machines — the protocol was reverse
engineered, originally by Tim Hutt. The closest thing to a spec is
[Commands.md in inkscape-silhouette](https://github.com/fablabnbg/inkscape-silhouette/blob/main/Commands.md),
which documents observed behaviour per model.

### The Silhouette Studio problem

Free Silhouette Studio **cannot import SVG at all** — that is gated behind
Designer Edition. This is the usual reason people go looking for alternatives,
and all three options below sidestep Studio completely.

### Options

**[inkscape-silhouette](https://github.com/fablabnbg/inkscape-silhouette)** (fablabnbg)
— the one to start with. 660 stars, last pushed August 2026, actively developed.
Python, talks GPGL over USB directly via pyusb. Supports Cameo 1/2/3/4/4 Plus/4
Pro/5, Portrait, and Curio. Runs as an Inkscape extension, but Inkscape is only
the host shell — the extension does the work.

**[robocut](https://github.com/Timmmm/robocut)** (Timmmm) — standalone Qt app,
reads SVG directly, no Inkscape needed. 100 stars, last pushed May 2026. Older
device coverage than inkscape-silhouette. Worth it if you want to stay out of
Inkscape entirely. Note: [nosliwneb/robocut](https://github.com/nosliwneb/robocut)
is a Cameo/Portrait fork but has been dead since 2013 — use Timmmm's.

**[Inkcut](https://github.com/inkcut/inkcut)** — speaks GPGL as well as HPGL, so
it can drive a Cameo *and* a Roland from one tool. Weaker Silhouette-specific
device support than inkscape-silhouette, but one tool for both machines has
obvious appeal if you run both.

### From Illustrator

There is no Illustrator plugin for any of these. The workflow is the same as this
project's: **export SVG from Illustrator**, then open it in robocut, or in
Inkscape with the extension installed. Outline text and expand strokes first —
same rules as `README.md` § Preparing artwork.

---

## AxiDraw — EBB, and a different problem

AxiDraw does **not** use a drawing language. It speaks
[EBB](https://evil-mad.github.io/EggBot/ebb.html) (EiBotBoard), a plain-ASCII
protocol over USB CDC serial that is pure motor control:

```
SM,1000,320,-240     run both steppers this many steps over 1000 ms
SP,1                 pen servo up
```

No coordinates, no paths, no concept of a shape. **The host does all the motion
planning** — segmenting curves, acceleration ramps, timing every move. The GX-24
has a servo controller inside doing that job; the AxiDraw pushes it onto your
computer.

That is why supporting an AxiDraw here would be much more than a new emitter — it
needs a motion planner too. Probably not worth building when good drivers exist:

- [axicli / pyaxidraw](https://axidraw.com/doc/cli_api/) — official, Python
- [saxi](https://github.com/nornagon/saxi) — third-party, TypeScript, does its own
  planning; well regarded
- [snoyer/axidraw-control](https://github.com/snoyer/axidraw-control) — minimal
  direct-EBB control, useful for understanding the protocol
- [EBB command reference](http://www.schmalzhaus.com/EBB/EBBCommands.html) —
  Brian Schmalz's original hardware docs

---

## What it would take to support these here

The layers in `src/cutter/` split cleanly along the protocol boundary:

```
svg.py + optimize.py     machine-agnostic  -- SVG to optimised polylines in mm
hpgl.py + device.py      Roland-specific
```

- **A Cameo** would need one new emitter (`gpgl.py`) behind the same pipeline,
  plus a USB transport — Silhouette uses a vendor-specific interface via
  libusb/pyusb rather than the printer-class node `usblp` gives us, so
  `device.py` would need a sibling. Moderate work, well-trodden.
- **Another HPGL cutter** (Summa, Graphtec in HPGL mode, a generic import) is
  nearly free — mostly a device profile: max width, force and speed ranges, and
  which vendor extensions it honours. `hpgl.py` already gates the Roland `!`
  commands behind `roland_ext` for exactly this reason.
- **An AxiDraw** would need an emitter *and* a motion planner. Use `saxi` or
  `axicli` instead.

---

## Preprocessing, any machine

- [vpype](https://github.com/abey79/vpype) — the best SVG preprocessing toolkit
  for plotter work: line sorting, merging, dedup, layer handling, HPGL export.
  Not used in this project because it depends on Shapely, which needs a compiled
  GEOS and lags new Python releases — see `history.md`. Still the right tool if
  you are working outside this repo.
- [vpype-gcode](https://github.com/plottertools/vpype-gcode) — adds G-code and
  arbitrary text-format output, useful for CNC-ish machines.

---

## Fab-lab lineage

- [mods CE](https://modsproject.org/) — maintained successor to fab modules.
  Browser-based, covers many machines including Roland cutters and mills.
- [Fab Academy machine documentation](https://archive.fabacademy.org/) — decades
  of per-machine writeups, frequently the only real documentation for older gear.
