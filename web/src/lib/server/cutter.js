// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Thin wrapper around the `cutter` CLI.
 *
 * The server deliberately shells out rather than reimplementing geometry in
 * JS. The Python package is the single source of truth for what the machine
 * receives -- a second implementation would be a second thing to keep correct,
 * and the failure mode (a job that is subtly the wrong size) is expensive in
 * material and invisible until it is cut.
 */

import { spawn } from 'node:child_process';
import { env } from '$env/dynamic/private';

/** Path to the cutter CLI. Override with CUTTER_BIN on the Pi. */
const BIN = env.CUTTER_BIN || 'cutter';

const CONVERT_TIMEOUT_MS = 30_000;
/** Real cuts take minutes; a large job on slow settings can take far longer. */
const CUT_TIMEOUT_MS = 30 * 60_000;

export class CutterError extends Error {
  constructor(message, { stderr = '', code = null } = {}) {
    super(message);
    this.name = 'CutterError';
    this.stderr = stderr;
    this.code = code;
  }
}

function run(args, { timeout = CONVERT_TIMEOUT_MS } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(BIN, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    let settled = false;

    const timer = setTimeout(() => {
      settled = true;
      child.kill('SIGTERM');
      reject(new CutterError(`\`cutter ${args[0]}\` timed out`, { stderr }));
    }, timeout);

    child.stdout.on('data', (d) => (stdout += d));
    child.stderr.on('data', (d) => (stderr += d));

    child.on('error', (err) => {
      clearTimeout(timer);
      if (settled) return;
      settled = true;
      reject(
        err.code === 'ENOENT'
          ? new CutterError(
              `Could not run \`${BIN}\`. Install the package (pip install -e .) ` +
                `or set CUTTER_BIN to its path.`
            )
          : new CutterError(err.message, { stderr })
      );
    });

    child.on('close', (code) => {
      clearTimeout(timer);
      if (settled) return;
      settled = true;
      if (code === 0) resolve({ stdout, stderr });
      else
        reject(
          new CutterError(firstErrorLine(stderr) || `cutter exited ${code}`, {
            stderr,
            code
          })
        );
    });
  });
}

/** The CLI prints `error: <message>`; surface that rather than a whole trace. */
function firstErrorLine(stderr) {
  const line = stderr.split('\n').find((l) => l.startsWith('error: '));
  return line ? line.slice(7) : '';
}

/**
 * Parse the job report the CLI writes to stderr, e.g.
 *   logo.svg: 6 paths, 85.0 x 50.7 mm
 *     cut 0.37 m, travel 0.21 m (down 19% from sorting)
 */
function parseReport(stderr) {
  const shape = stderr.match(/:\s*(\d+) paths?,\s*([\d.]+) x ([\d.]+) mm/);
  const lengths = stderr.match(/cut ([\d.]+) m, travel ([\d.]+) m/);
  const saved = stderr.match(/down (\d+)% from sorting/);
  if (!shape) return null;
  return {
    paths: Number(shape[1]),
    widthMm: Number(shape[2]),
    heightMm: Number(shape[3]),
    cutMetres: lengths ? Number(lengths[1]) : null,
    travelMetres: lengths ? Number(lengths[2]) : null,
    travelSavedPct: saved ? Number(saved[1]) : 0
  };
}

function machineArgs({ force, speed, rolandExt = true, pageEject = false }) {
  const args = [];
  if (force != null) args.push('--force', String(force));
  if (speed != null) args.push('--speed', String(speed));
  if (!rolandExt) args.push('--no-roland-ext');
  if (pageEject) args.push('--page-eject');
  return args;
}

/** What the machine can see. Never throws -- a missing CLI is a UI state. */
export async function info() {
  try {
    const { stdout } = await run(['info']);
    const devices = stdout
      .split('\n')
      .filter((l) => l.trim().startsWith('/dev/'))
      .map((l) => l.trim());
    const note = stdout.match(/^\s{2}(macOS has no.*|Check power.*)$/m);
    return {
      available: true,
      connected: devices.length > 0,
      devices,
      note: note ? note[1] : null
    };
  } catch (err) {
    return { available: false, connected: false, devices: [], note: err.message };
  }
}

/** Convert an SVG file to HPGL. Returns { hpgl, report }. */
export async function convert(svgPath, opts = {}) {
  const args = ['convert', svgPath, ...machineArgs(opts)];
  if (opts.marginMm != null) args.push('--margin', String(opts.marginMm));
  if (opts.scale != null && opts.scale !== 1) args.push('--scale', String(opts.scale));
  if (opts.noSort) args.push('--no-sort');

  const { stdout, stderr } = await run(args);
  return { hpgl: stdout, report: parseReport(stderr) };
}

/** Render HPGL back to SVG. This round-trips what the machine will receive. */
export async function preview(hpglPath) {
  const { stdout } = await run(['preview', hpglPath]);
  return stdout;
}

/** Stream an HPGL file to the cutter. */
export async function send(hpglPath, { device = null, dryRun = false } = {}) {
  const args = ['send', hpglPath];
  if (device) args.push('--device', device);
  if (dryRun) args.push('--dry-run');
  const { stderr } = await run(args, { timeout: CUT_TIMEOUT_MS });
  return { log: stderr };
}
