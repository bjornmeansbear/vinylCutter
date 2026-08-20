# History

A running log of what we decided, why, and what still needs proving. Newest
work at the bottom.

---

## 2026-08-19 — Starting point

Roland GX-24 (CAMM-1 servo, firmware v2.30). The Adobe plugin has stopped being
maintained; looking for open-source options and a Raspberry Pi that jobs can be
sent to.

### What Roland actually still offers

From the [GX-24 support page](https://www.rolanddga.com/support/products/cutting/camm-1-gx-24-24-vinyl-cutter):

- Drivers: **Windows only**, newest Win10 v1.50 (alongside Win95/98/ME)
- CutStudio Illustrator plugin: stops at **CC 2020**
- CorelDRAW plugin: 2017
- **No macOS driver listed at all**

So on a current Mac with current Illustrator there is no vendor-supported path.
Not a gap that closes with waiting.

This matters less than it looks. The GX-24 enumerates as a **USB printer-class
device** and accepts **CAMM-GL III**, which is HPGL. The Windows driver is
transport plus a CutStudio bridge. Generating the right bytes is the real work;
moving them is trivial on any OS with a USB stack.

### Open-source landscape

| Tool | What it is | Verdict |
|---|---|---|
| [Inkcut](https://github.com/inkcut/inkcut) | Standalone Qt app + optional Inkscape extension. GX-24 listed as working, connection type "Printer". v2.1.8 Jun 2026, actively maintained | **Best off-the-shelf option.** Use it to validate hardware |
| [vpype](https://github.com/abey79/vpype) | CLI plotter vector toolkit, best SVG→HPGL pipeline available | Wanted it as our converter — see the Shapely problem below |
| [mods CE](https://modsproject.org/) | Maintained successor to fab modules. Has GX/GS-24 programs, now takes SVG as well as PNG | Fab-lab lingua franca; thinner cut-path controls than Inkcut |
| Inkscape built-in | `File → Save As → .hpgl` | Crude, but a zero-install sanity check |
| SignCut | Commonly recommended | Proprietary/subscription — out of scope |

**Inkcut is not Inkscape-only.** That was the initial assumption and it's wrong.
It's a standalone app with a real CLI (`inkcut open drawing.svg`, and `-` for
stdin — confirmed in `inkcut/job/manifest.enaml`). The Inkscape extension is a
convenience shim that shells the selection over. What it's really doing for you
is path prep: it calls `inkscape --actions="select-all;object-unlink-clones;object-to-path"`
before handoff. That's the entire value of the integration, and you can do it by
hand from any app.

Inkcut has **no headless mode** — the maintainer has said it's feasible (built on
Twisted) but nobody built it. `inkcut open` still raises the GUI. That's the gap
this project fills.

### Prior art on this exact machine

- **[Fab Academy 2015, week 2](https://vkbg.github.io/week2.html)** (ours) — GX-24
  as a CUPS 1.7.2 queue named `vinyl`, driven by fab modules: PNG in → `make.path`
  → `make.camm`. Note the input format: **PNG**. Raster. That's the part to
  replace, not the transport.
- **[Fab Academy 2016, Barcelona](https://archive.fabacademy.org/2016/fablabbcn2016/students/27/exercise07a.html)**
  — GX-24 on a Raspberry Pi, CUPS, generic text-only driver, `/dev/usb/lp0`,
  **force = 110gf** on vinyl. Useful starting force.

Two independent documentations confirm the Pi handles this machine fine over USB.
Transport was never the problem.

---

## 2026-08-19 — Decision: no CUPS

Researched the printing stack ([OpenPrinting](https://openprinting.github.io/cups/),
[CUPS](https://www.cups.org/), [IPP Everywhere](https://www.pwg.org/ipp/everywhere.html),
[Apple AirPrint](https://support.apple.com/en-us/102895)) and concluded the CUPS
route is a receding shore.

From [OpenPrinting's drivers page](https://openprinting.github.io/cups/drivers.html):

> Support for raw queues was deprecated with CUPS 2.2 in 2018 and printer drivers
> starting with CUPS 2.3 in 2019.

Raw queues are exactly what both Fab Academy tutorials build. CUPS 3.x goes
further — no PPDs, no classic drivers, `libcups3` drops PPD support entirely. The
replacement is IPP Everywhere plus PAPPL printer applications.

**And IPP Everywhere has no slot for a cutter.** It standardises document
formats: PWG Raster, JPEG, PDF, Apple Raster. It is a *raster imaging* standard.
A cutter needs vector paths plus per-path force, speed, and blade-offset
semantics. There is no cut-path vocabulary in it. You cannot write an honest
PAPPL printer application for a GX-24 — you'd be smuggling HPGL through as an
unrecognised binary format, which *is* a raw queue, which is the deprecated thing.

Current stable is CUPS 2.4.19 (Apr 2026), which is what Raspberry Pi OS ships, so
the old tutorials still work *today*. But there's a published demolition date.

**Decision:** drop CUPS from the design. It was only providing a job queue,
network sharing, and permissions — all of which the planned web server provides
better, alongside a preview and cut-specific controls CUPS cannot model.

The durable interface is the USB printer-class endpoint itself: `/dev/usb/lp0`,
via the `usblp` kernel module. Not a workaround around a deprecated stack — the
actual machine interface, with no framework and no deprecation timeline. It's why
Inkcut's "Printer" device type works on the GX-24 at all.

Bonus: the Mac becomes an HTTP client rather than a print client, so whatever
Apple does to macOS printing stops mattering.

---

## 2026-08-19 — Decision: no vpype either (stdlib SVG flattener instead)

vpype was the intended SVG→HPGL converter. It doesn't install here:

```
OSError: Could not find library geos_c or load any of its variants
ERROR: Failed to build 'Shapely' when getting requirements to build wheel
```

vpype depends on Shapely, which needs a compiled GEOS and has no wheel for
Python 3.14 (this machine's Python). It would install fine on the Pi via
piwheels, but making the machine layer depend on it means **the tool cannot be
installed on the machine you are holding** — and pins the whole project to
whichever Python version currently has Shapely wheels.

**Decision:** hand-roll the SVG flattener in stdlib (`src/cutter/svg.py`). Zero
dependencies, installs anywhere Python does, testable immediately. vpype stays
worth adding later as an *optional* optimisation pass, not a requirement.

Handles: `path` (all commands including arcs and smooth curves), `rect` (incl.
rounded), `circle`, `ellipse`, `line`, `polyline`, `polygon`, all transform
types, viewBox scaling, unit suffixes, and `display:none` skipping. Curves
flatten to a 0.02mm tolerance — deliberately just below the machine's 0.025mm
addressable unit, since finer detail is unrepresentable.

Deliberately not handled: fills, strokes, text, clip paths, masks. A cutter
follows path geometry and nothing else.

---

## 2026-08-19 — Built the machine layer

`src/cutter/` — 8 modules, no dependencies, 23 tests passing.

Design notes worth remembering:

- **1 plotter unit = 0.025mm exactly** (40 units/mm, 1016/inch). Standard HPGL,
  not Roland-specific. `mm_to_units` rounds rather than truncates — truncation
  biases every coordinate toward the origin and accumulates into visible drift.
- **PD commands are chunked** to 20 coordinate pairs. Consecutive PDs continue
  the same cut (the pen stays down), so splitting is semantically free, and long
  command lines are a known way to overrun the GX-24's small input buffer.
- **Writes are chunked and paced** (1KB, 50ms). Open-loop by choice: USB printer
  class is bidirectional in principle and the GX-24 answers HPGL status queries,
  but readback is firmware-dependent, so writing slower than the machine consumes
  is the conservative default. The symptom this prevents is a cut that starts
  correctly then jumps to the origin partway through.
- **Blade offset is not compensated in software.** The GX-24 does it in firmware
  via the panel OFFSET setting. Doing both double-corrects and rounds every corner.
- **Path ordering matters more than it looks.** Every pen-up move drags media
  back and forth under the pinch rollers, and that's what makes long jobs drift
  out of registration. Greedy nearest-neighbour with optional path reversal;
  measured ~19% travel reduction on the test sampler, typically more on real art.
- **`preview.py` round-trips the HPGL, not the source SVG.** That's the point —
  it shows what the machine will do, so it catches unit errors and axis flips
  that a source-side preview would hide.

### Command confidence — READ BEFORE TRUSTING

Roland's CAMM-GL programmer's manual could not be verified in-session (the PDF
Roland hosts is a 6-page excerpt and wouldn't render). So commands are split
into two confidence levels, and everything uncertain is gated behind
`roland_ext` with a `--no-roland-ext` escape hatch.

**Standard HPGL — safe:**
`IN;` `SP<n>;` `PU<x>,<y>;` `PD<x>,<y>,...;` `VS<n>;`

**Roland extension — from field use (fab modules, Inkcut, community drivers),
NOT confirmed against Roland docs:**
`!FS<n>;` (blade force, grams) · `!PG;` (page eject / feed and cut off)

If `!FS` turns out to be ignored, the ladder pattern will cut every square
identically — that's the tell. Fall back to `--no-roland-ext` and set force and
speed on the front panel.

### Not yet done

- **Nothing has touched a physical GX-24.** All 23 tests are geometric and
  hardware-free. The registration pattern is the first thing to run.
- Confirm Roland's USB vendor ID is `0x0b3c` with `lsusb` on the Pi and narrow
  `config/99-roland-gx24.rules` if needed.
- Confirm `!FS` and `!PG` behaviour on firmware v2.30.
- Find the real force/speed for the vinyl actually in the shop (start near
  110gf, per the 2016 BCN documentation).
- SvelteKit server. `POST /jobs` taking SVG is the whole API surface.

---

## 2026-08-20 — Built the web server

SvelteKit + `adapter-node` in `web/`. Builds and runs; every endpoint exercised
over HTTP against the real CLI.

**It shells out to the `cutter` CLI rather than reimplementing geometry in JS.**
A second implementation would be a second thing to keep correct, and the failure
mode — a job that is subtly the wrong size — is expensive in material and
invisible until it is cut.

Design decisions worth remembering:

- **Uploading converts but never cuts.** There is always a preview between
  choosing a file and moving a blade. Cutting is a separate call.
- **The cut button is two-step**, with a 5s auto-disarm. This runs on a phone in
  a pocket next to a machine with an exposed blade; one tap is too little
  friction for something that cannot be undone.
- **Cuts are serialised through one promise chain.** There is exactly one blade.
  Two jobs at once is not a degraded experience, it is a crash and a ruined
  sheet. The API returns `409` when busy rather than letting the client try.
- **A failed cut cannot wedge the queue** — errors are captured onto the job,
  not propagated into the chain.
- **Jobs persist to disk** so they survive a restart, which matters on a Pi that
  may lose power. A job found in state `cutting` at startup is marked errored,
  because it definitively did not finish and saying so beats a spinner forever.
- **Material presets** turn the ladder calibration into a number you look up
  once instead of a sticky note on the machine. Defaults are starting points.

### Design system

Built against `~/Code/color-system-and-guidelines` (kit.css + RULES.md). Warm
`--gray-0` ground, `--brown-8` line work, pink accent, structure from solid
rules and whitespace — no shadow, no gradient, no radius except at badge scale.
State shows by inverting foreground/background, never elevation. Mobile-first
with the 40rem breakpoint. Baseline grid on the 6px rhythm.

Contrast computed rather than eyeballed, per the standing rule about muted
tokens:

| pair | ratio | |
|---|---|---|
| `--brown-8` on `--gray-0` | 16.94:1 | AAA |
| `--gray-6` muted on `--gray-0` | 7.27:1 | AAA |
| `--pink-6` on `--gray-0` | 7.39:1 | AAA |
| `--pink-5` on `--gray-0` | 4.87:1 | AA, tight |
| `--gray-0` on `--pink-5` | 4.87:1 | AA, tight |

Pink-5 clears AA but with little headroom, so **small accent text uses pink-6**;
pink-5 is kept for fills and rules where the pairing that matters is
bg-on-pink. Also: 44px minimum touch targets, `:focus-visible` accent outline
never suppressed, labels bound to every control, `aria-pressed` on preset
toggles, and preview images carrying real alt text ("Cut path preview for
sampler.svg: 6 paths across 85 by 50.7 millimetres").

### Verified over HTTP

- `POST /api/jobs` with the sampler → 6 paths, 85.0 × 50.7mm, matches the CLI
- `GET /api/jobs/:id/preview` → SVG rendered from the HPGL
- `POST /api/jobs/:id/cut` with no device → **409** with the macOS explanation
- `POST` with `{"dryRun":true}` → **202**, job runs ready → cutting → done
- Jobs persist to `jobs/` and reload

### Gotcha for next time

`sveltekit()` for `vite.config.js` comes from `@sveltejs/kit/vite`, **not**
`@sveltejs/vite-plugin-svelte` — the latter has no such export and fails at
config load.

---

## 2026-08-20 — License: AGPL-3.0-or-later

Chose the **GNU Affero GPL v3 or later**, not GPL-3.0 and not a permissive
license.

The deciding factor is that this project ships a web server. Plain GPL only
triggers on *distribution* — someone could take this, improve it, run it as a
hosted cutting service, and never share a line back, because they never handed
anyone a copy. **AGPL section 13 closes that gap**: run a modified version that
people interact with over a network, and those people are entitled to the source.

Permissive (MIT/Apache) was considered and rejected on purpose. This exists
because a vendor stopped maintaining something people depend on. A permissive
license would let exactly that happen again to this code; copyleft is the part
that prevents enclosure.

Also the right neighbourhood: [Inkcut](https://github.com/inkcut/inkcut) is
GPL-3.0 and the Fab Lab lineage this grew from is libre throughout.

Known tradeoff, accepted: some organisations ban AGPL internally (Google, among
others). For a personal fab tool that is not a cost worth optimising against.

Implementation:
- `LICENSE` — full AGPL-3.0 text
- `SPDX-License-Identifier: AGPL-3.0-or-later` on all 26 source files
- `pyproject.toml` uses the PEP 639 SPDX expression (needs setuptools>=77)
- **The web app footer links to its own source.** That is not decoration — it is
  how the running service satisfies section 13. A fork must repoint it.

---

## 2026-08-20 — Published

Pushed to `git@github.com:bjornmeansbear/vinylCutter.git`.

---

## Ideas and future additions

Not committed to, just parked with enough context to pick up later.

**Other machines.** See `docs/other-machines.md` for the full map. Short version:
another HPGL cutter (Summa, Graphtec in HPGL mode, generic imports) is nearly
free — mostly a device profile, and `hpgl.py` already gates the Roland `!`
commands behind `roland_ext` for exactly this. A Silhouette Cameo would need a
`gpgl.py` emitter plus a libusb transport, since Silhouette uses a
vendor-specific USB interface rather than the printer class `usblp` gives us. An
AxiDraw would need a motion planner as well as an emitter — use
[saxi](https://github.com/nornagon/saxi) or axicli instead.

**Cut features worth having**, roughly in order of usefulness — all present in
Inkcut, none here yet: weedlines, copies and tiling, mirroring (needed for heat
transfer vinyl), registration marks for print-and-cut.

**vpype as an optional pass.** Rejected as a dependency (Shapely/GEOS, see
above), but if it is installed it would be a better line optimiser than the
greedy nearest-neighbour in `optimize.py`. Detect and use, never require.

**Bidirectional device I/O.** USB printer class is bidirectional and the GX-24
answers HPGL status queries. Real flow control would beat the current open-loop
chunk-and-pause, but readback is firmware-dependent, so this needs the machine in
front of you to develop against.

**systemd unit** so the web server starts on boot, plus mDNS so it is reachable
at a name rather than an IP.

---

## Reference links

**This machine**
- [Roland GX-24 support & downloads](https://www.rolanddga.com/support/products/cutting/camm-1-gx-24-24-vinyl-cutter)
- [Roland download centre — GX-24](https://downloadcenter.rolanddg.com/GX-24)
- [CAMM-GL II programmer's manual (excerpt)](https://downloadcenter.rolanddg.com/contents/manuals/CAMM-GL2_PRO_EN_R1.pdf)

**Software**
- [Inkcut](https://github.com/inkcut/inkcut) · [supported devices](https://github.com/inkcut/inkcut/blob/master/docs/supported-devices.md) · [install docs](https://github.com/inkcut/inkcut/blob/master/docs/installing.md) · [homepage](https://codelv.com/projects/inkcut/)
- [vpype](https://github.com/abey79/vpype) · [HPGL device config cookbook](https://vpype.readthedocs.io/en/latest/cookbook.html)
- [mods CE](https://modsproject.org/)

**Printing stack (why we're not using it)**
- [OpenPrinting — Printer Applications and Printer Drivers](https://openprinting.github.io/cups/drivers.html)
- [OpenPrinting CUPS source](https://github.com/openprinting/cups) · [openprinting.github.io](https://openprinting.github.io/)
- [PWG IPP Everywhere](https://www.pwg.org/ipp/everywhere.html)
- [Debian Wiki — CUPS New Architecture](https://wiki.debian.org/CUPSNewArchitecture)
- [Apple — About AirPrint](https://support.apple.com/en-us/102895)

**Prior art**
- [Our Fab Academy 2015 week 2](https://vkbg.github.io/week2.html)
- [Fab Academy 2016 BCN — GX-24 on a Raspberry Pi](https://archive.fabacademy.org/2016/fablabbcn2016/students/27/exercise07a.html)
- [Waag/Fablab Amsterdam — using the Roland vinyl cutter](https://fablab.waag.org/Vinyl%20Cutter/How%20to%20use%20the%20Roland%20vinyl%20cutter/)

**Other machines** (full notes in `docs/other-machines.md`)
- [inkscape-silhouette](https://github.com/fablabnbg/inkscape-silhouette) · [GPGL command notes](https://github.com/fablabnbg/inkscape-silhouette/blob/main/Commands.md)
- [robocut](https://github.com/Timmmm/robocut)
- [EBB command set](https://evil-mad.github.io/EggBot/ebb.html) · [Schmalz EBB hardware docs](http://www.schmalzhaus.com/EBB/EBBCommands.html)
- [saxi](https://github.com/nornagon/saxi) · [axicli/pyaxidraw](https://axidraw.com/doc/cli_api/)
- [vpype-gcode](https://github.com/plottertools/vpype-gcode)
