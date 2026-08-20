// SPDX-License-Identifier: AGPL-3.0-or-later
import { json, error } from '@sveltejs/kit';
import { writeFile } from 'node:fs/promises';
import * as cutter from '$lib/server/cutter.js';
import * as store from '$lib/server/store.js';

export async function GET() {
  await store.load();
  return json({ jobs: store.list(), cutting: store.isCutting() });
}

/**
 * Upload an SVG and convert it. This does NOT cut -- conversion and cutting are
 * separate steps on purpose, so there is always a preview between choosing a
 * file and moving a blade.
 */
export async function POST({ request }) {
  await store.load();

  const form = await request.formData();
  const file = form.get('svg');
  if (!file || typeof file === 'string') error(400, 'No SVG uploaded.');
  if (file.size > store.MAX_UPLOAD_BYTES) {
    error(413, `That file is ${(file.size / 1e6).toFixed(1)}MB; the limit is 8MB.`);
  }

  const settings = {
    force: numberOr(form.get('force'), null),
    speed: numberOr(form.get('speed'), null),
    marginMm: numberOr(form.get('margin'), 0),
    scale: numberOr(form.get('scale'), 1),
    rolandExt: form.get('rolandExt') !== 'false',
    preset: form.get('preset') || null
  };

  const job = await store.create({
    name: file.name || 'untitled.svg',
    report: null,
    settings
  });

  await writeFile(store.svgPath(job.id), Buffer.from(await file.arrayBuffer()));

  try {
    const { hpgl, report } = await cutter.convert(store.svgPath(job.id), settings);
    await writeFile(store.hpglPath(job.id), hpgl);
    const preview = await cutter.preview(store.hpglPath(job.id));
    await writeFile(store.previewPath(job.id), preview);
    job.report = report;
    job.status = 'ready';
  } catch (err) {
    job.status = 'error';
    job.error = err.message;
  }

  return json({ job }, { status: job.status === 'error' ? 422 : 201 });
}

function numberOr(value, fallback) {
  if (value == null || value === '') return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}
