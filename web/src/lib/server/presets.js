// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Material presets.
 *
 * The point of the ladder calibration pattern is to turn "what force for this
 * vinyl?" into a number you looked up once. This is where that number lives so
 * it stops being a sticky note on the side of the machine.
 *
 * Defaults below are starting points, not gospel: 110gf comes from the Fab Lab
 * Barcelona GX-24 documentation. Re-run `cutter pattern ladder` on your actual
 * material and correct them.
 */

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { env } from '$env/dynamic/private';

const FILE = env.PRESETS_FILE || join(process.cwd(), '..', 'config', 'presets.json');

export const DEFAULTS = [
  { id: 'cast', name: 'Cast vinyl', force: 90, speed: 20, note: 'Thin, conformable' },
  { id: 'calendered', name: 'Calendered vinyl', force: 110, speed: 20, note: 'Standard sign vinyl' },
  { id: 'htv', name: 'Heat transfer', force: 80, speed: 15, note: 'Cut mirrored' },
  { id: 'reflective', name: 'Reflective', force: 150, speed: 10, note: 'Thick; slow down' },
  { id: 'mask', name: 'Paint mask', force: 60, speed: 25, note: 'Light touch' }
];

export async function load() {
  try {
    const raw = await readFile(FILE, 'utf8');
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) && parsed.length ? parsed : DEFAULTS;
  } catch {
    // No file yet, or an unreadable one: fall back rather than break the page.
    return DEFAULTS;
  }
}

export async function save(presets) {
  if (!existsSync(dirname(FILE))) await mkdir(dirname(FILE), { recursive: true });
  await writeFile(FILE, JSON.stringify(presets, null, 2));
  return presets;
}
