# vinylCutter

Drive a Roland CAMM-1 GX-24 directly over USB. SVG in, HPGL out, bytes to the
device node — no driver, no vendor software.

Roland's own support for this machine has stopped: the drivers are Windows-only,
the CutStudio Illustrator plugin ends at CC 2020, and there is no macOS driver at
all. None of that matters, because the driver was only ever moving bytes. The
GX-24 enumerates as a USB printer-class device and speaks CAMM-GL III, which is
HPGL. That interface has no maintainer and no deprecation timeline — it just
works, and will keep working.

## What is HPGL?

**HPGL** is Hewlett-Packard Graphics Language, written in the 1970s to drive pen
plotters. It is a plain-text command language, and it is about as simple as a
graphics format gets — the whole working vocabulary is four commands:

```hpgl
IN;              initialise
SP1;             select pen 1
PU2400,0;        pen UP, move to (2400, 0)
PD2400,1200;     pen DOWN, cut to (2400, 1200)
```

That's it. Move with the tool up, move with the tool down. No fills, no strokes,
no layers, no colour — just a head travelling in straight lines between
coordinates, and a single bit saying whether it's touching the material.

It survived into vinyl cutters because a cutter and a pen plotter are the same
machine. Both move a tool head around a 2D area and raise or lower it. Swap the
pen for a blade and the file format doesn't need to change. So a language
designed for 1977 plotters drives a 2007 cutter without modification, and the
"pen" in `PU`/`PD` is really your blade.

**Coordinates are in plotter units**, where one unit is 0.025mm exactly — 40 per
millimetre, 1016 per inch. That resolution is the machine's actual addressable
precision, which is why this project flattens curves to a 0.02mm tolerance and no
finer: below one unit, extra detail cannot be represented.

**Curves don't exist.** HPGL has arc commands, but the reliable subset is
straight lines, so every bezier in your artwork gets flattened into a chain of
short segments before it goes down the wire. At 0.02mm each, your eye reads them
as a curve.

**CAMM-GL III** is Roland's dialect — standard HPGL plus a few extensions of
their own, written with a leading `!`:

```hpgl
!FS110;          blade force, 110 grams
!PG;             feed the material out and cut it off
```

Those extensions are the only Roland-specific thing in the whole pipeline, and
they're the only part not confirmed against vendor documentation — see
[Status](#status) and `history.md`.

### Other terms used here

| | |
|---|---|
| **Plotter unit** | 0.025mm. The machine's smallest addressable step |
| **Force** | Blade pressure in grams. Too low won't cut through; too high scores the backing |
| **Blade offset** | The blade tip sits *behind* its axis of rotation, so it swivels to follow direction changes. The machine compensates in firmware via its OFFSET setting — do not also do it in software |
| **Weeding** | Peeling away the vinyl you don't want after cutting, leaving the design on the backing |
| **Kiss cut** | Cutting through the vinyl but not the backing paper. What you want, essentially always |
| **usblp** | The Linux kernel module that exposes a USB printer-class device as `/dev/usb/lp0`. This project's entire transport layer |

## Status

The machine layer is complete and tested (23 tests, no hardware required).
**Nothing here has been run against a physical GX-24 yet** — see
[Calibration](#calibration) for the order to prove it out in, and `history.md`
for which commands are standard HPGL versus Roland extensions taken from field
use.

## Install

```bash
git clone <this repo> && cd vinylCutter
pip install -e .
```

No dependencies. Python 3.10+.

### On the Raspberry Pi

**Choosing a board.** Anything from a Pi 3 up runs everything. A **Pi Zero /
Zero W is CLI-only** — see the constraints below before committing to one.

| | Zero / Zero W | Zero 2 W and up |
|---|---|---|
| Architecture | ARMv6, single core, 512MB | arm64, quad core |
| OS image | Raspberry Pi OS Lite **32-bit** | Lite 64-bit |
| `cutter` CLI | works | works |
| Web server | no — official Node dropped ARMv6 at v11 (2019) | works |

#### Pi Zero W: one USB port, and the cutter needs it

The Zero has exactly **one data-capable USB port**, and a port cannot be a USB
host and a USB gadget at once. So:

- The USB port goes to the **cutter**, via a micro-USB-male to USB-A-female OTG
  adapter. You need that adapter; it is not optional.
- Network access therefore has to come from **built-in WiFi**, which is fine —
  WiFi does not use the USB port.
- `scripts/enable-usb-gadget.sh` is still useful for first-boot access and
  troubleshooting, but only while the cutter is unplugged. It is not how you run
  the machine day to day.

#### Split the work across two machines

`convert` and `send` are separate commands on purpose, so they can run in
different places. On a 512MB single-core board, put the CPU work on your laptop
and let the Pi be a reliable pipe:

```bash
# on your laptop -- SVG parsing, flattening, path ordering
cutter convert logo.svg --force 110 --speed 20 -o logo.hpgl
cutter preview logo.hpgl -o check.svg      # eyeball it before it exists in vinyl

# hand it over
scp logo.hpgl pi@raspberrypi.local:~/

# on the Pi -- chunked writes to the device node, almost no work at all
cutter send logo.hpgl
```

This is a better fit for a Zero W than running everything on it, and it costs
nothing: the HPGL is identical either way.

#### Bootstrap

Use the bootstrap script — it handles the venv (required: Pi OS marks the system
Python externally-managed), the udev rule, the `lp` group, and the `usblp`
kernel module:

```bash
./scripts/setup-pi.sh
```

Then plug the cutter in and check what the Pi can see:

```bash
./scripts/diagnose.sh
```

`diagnose.sh` is read-only and needs no sudo. It reports USB enumeration, the
`usblp` module state, device nodes, permissions, and recent kernel messages —
which between them explain essentially every "why isn't it showing up" case.

## Use

```bash
cutter info                                  # what can this machine see?
cutter pattern registration --force 110      # generate a calibration cut
cutter convert art.svg -o job.hpgl           # SVG -> HPGL, with a job report
cutter preview job.hpgl -o check.svg         # render the job back, to eyeball it
cutter send job.hpgl                         # stream it to the cutter
cutter cut art.svg --force 110 --speed 20    # convert and send in one step
```

`--dry-run` prints HPGL instead of cutting, and is the automatic default
anywhere there is no device node — so on your Mac nothing can move by accident.

### Preparing artwork

The cutter follows path geometry and nothing else. Before exporting SVG from
Illustrator (or anywhere):

- **Convert text to outlines.** Type is skipped silently, not cut.
- **Expand strokes.** A 2pt stroke is a centerline to a cutter, not a shape.
- **Expand compound shapes and release clipping masks.** Appearance-based
  geometry does not survive.
- Fills mean nothing. Only the paths matter.

Hidden layers are skipped — Illustrator exports them as `display:none` rather
than omitting them, so without that check a file that looks like one logo cuts
three rejected drafts stacked on top of each other.

## Calibration

Run these in order on scrap before trusting the machine with real material.

1. **`cutter pattern registration`** — a 60×30mm L. Measure both arms with a
   ruler. 60 and 30 means correct scale and orientation. 30 and 60 means your
   axes are transposed. Something like 1.5 and 0.75 means the 40 units/mm
   conversion is wrong.
2. **`cutter pattern ladder`** — squares at stepped blade force. Weed it; the
   lowest force that lifts cleanly without scoring the backing is your setting.
   If every square cuts identically, your firmware ignores mid-job `!FS` — fall
   back to `--no-roland-ext` and the front panel.
3. **`cutter pattern nested`** — a square in a square. Sharp inside corners mean
   the panel OFFSET setting matches your blade.

Blade offset is deliberately **not** compensated in software. The GX-24 does it
in firmware. Doing it in both places double-corrects and rounds off every corner.

> Before debugging any of this in software, put a loupe on the blade. A chipped
> tip is invisible to the naked eye and produces failures indistinguishable from
> a bad job file.

## Layout

```
src/cutter/
  units.py      mm <-> plotter units (1 unit = 0.025mm, exactly)
  svg.py        SVG -> polylines: paths, shapes, transforms, curve flattening
  optimize.py   path ordering, dedup, origin normalisation
  hpgl.py       polylines -> HPGL / CAMM-GL III
  patterns.py   calibration patterns
  preview.py    HPGL -> SVG, to check a job before cutting
  device.py     chunked writes to /dev/usb/lp0
  cli.py        the `cutter` command
config/         udev rule
tests/          run with: python3 -m unittest discover -s tests -t .
```

## Other machines

Notes on Silhouette/Cameo (GPGL), AxiDraw (EBB), and other HPGL cutters — plus
what it would take to support them here — are in
[docs/other-machines.md](docs/other-machines.md).

## Why no CUPS

CUPS raw queues — the mechanism every Fab Lab GX-24 tutorial uses — have been
deprecated since CUPS 2.2 in 2018. CUPS 3.x removes PPDs and classic drivers
entirely; `libcups3` has no PPD support. The replacement is IPP Everywhere plus
PAPPL printer applications, and IPP Everywhere standardises *raster document
formats*. There is no cut-path vocabulary in it and there never will be, because
a cutter is not a printer.

CUPS was only providing a queue, network sharing, and permissions. The planned
web server provides all three, plus a preview and force/speed controls that CUPS
could never model. So it is not in the path at all.

See `history.md` for the full reasoning and sources.

## Web server

A SvelteKit app for the Pi — drop an SVG from a phone at the machine, check the
preview, cut.

```bash
cd web
npm install
npm run dev          # http://<pi>:5173, bound to all interfaces
npm run build && node build   # production
```

It shells out to the `cutter` CLI rather than reimplementing any geometry, so
there is one source of truth for what the machine receives. Configure with
`web/.env`:

```
CUTTER_BIN=cutter        # or ../bin/cutter to run from source
JOBS_DIR=../jobs
PRESETS_FILE=../config/presets.json
```

`bin/cutter` is a dev shim that runs the CLI from source without installing.

### API

| | |
|---|---|
| `GET /api/device` | what the server can see |
| `GET /api/jobs` · `POST /api/jobs` | list; upload an SVG and convert it |
| `GET /api/jobs/:id/preview` | the job rendered back from its HPGL |
| `POST /api/jobs/:id/cut` | queue a cut (`{"dryRun":true}` to rehearse) |
| `GET /api/presets` · `POST /api/presets` | material presets |

Uploading converts but never cuts — there is always a preview between choosing
a file and moving a blade. Cutting is a separate, two-step action, and the API
refuses with `409` when no cutter is connected or one is already running. Cuts
are serialised through a single queue because there is exactly one blade.

### Material presets

Force and speed per material, so the ladder calibration only has to happen once.
Defaults ship in `src/lib/server/presets.js`; edits are saved to
`config/presets.json`. **Correct them against your own vinyl** — the defaults are
starting points, with 110gf taken from the Fab Lab Barcelona documentation.

## License

**GNU Affero General Public License v3.0 or later** ([AGPL-3.0-or-later](LICENSE)).

Copyright (C) 2026 Kristian Bjornard

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along
with this program. If not, see <https://www.gnu.org/licenses/>.

### Why AGPL and not GPL

Because this project ships a web server. Plain GPL only triggers on
*distribution* — someone could take this, improve it, run it as a hosted cutting
service, and never share a line back, because they never handed anyone a copy.
AGPL section 13 closes that: if you run a modified version where people interact
with it over a network, those people are entitled to your source.

Use it, run it, cut with it, sell what you cut. Modify it and pass it on — or run
it as a service — and those changes stay free too. That is the whole deal, and
it is deliberate: this exists because a vendor stopped maintaining something
people depend on, and the license is the part that makes sure this one cannot be
enclosed the same way.

The web app links to its own source in the footer, which is how it satisfies
section 13 in practice. **If you fork it, change that link to point at your
fork** — otherwise you are pointing your users at the wrong source.

Same family as the tools this builds on: [Inkcut](https://github.com/inkcut/inkcut)
is GPL-3.0, and the Fab Lab lineage this grew out of is libre throughout.
