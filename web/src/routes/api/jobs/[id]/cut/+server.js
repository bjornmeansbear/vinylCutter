// SPDX-License-Identifier: AGPL-3.0-or-later
import { json, error } from '@sveltejs/kit';
import * as cutter from '$lib/server/cutter.js';
import * as store from '$lib/server/store.js';

/** Send a converted job to the machine. Queued: one blade, one job at a time. */
export async function POST({ params, request }) {
  await store.load();
  const job = store.get(params.id);
  if (!job) error(404, 'No such job.');
  if (job.status === 'cutting') error(409, 'That job is already cutting.');

  const body = await request.json().catch(() => ({}));
  const dryRun = body.dryRun === true;

  if (!dryRun) {
    const device = await cutter.info();
    if (!device.connected) {
      error(409, device.note || 'No cutter connected.');
    }
    if (store.isCutting()) {
      error(409, 'The cutter is busy with another job.');
    }
  }

  // Deliberately not awaited: a real cut takes minutes and the client should
  // get an immediate acknowledgement, then poll. The queue guarantees ordering.
  store.enqueueCut(job, () => cutter.send(store.hpglPath(job.id), { dryRun }));

  return json({ job: store.get(job.id) }, { status: 202 });
}
