// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Job storage and the cut queue.
 *
 * The queue exists for one reason: there is exactly one blade. Two jobs cutting
 * at once is not a degraded experience, it is a crash and a ruined sheet. So
 * cuts are serialised through a single promise chain, and the UI is told when
 * the machine is busy rather than being allowed to try.
 *
 * Jobs live on disk under JOBS_DIR so they survive a restart of the server --
 * which matters on a Pi that may lose power mid-session.
 */

import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { env } from '$env/dynamic/private';

const JOBS_DIR = env.JOBS_DIR || join(process.cwd(), '..', 'jobs');

/** Upper bound on an uploaded SVG. Real cut files are tens of KB. */
export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;

/** @type {Map<string, Job>} */
const jobs = new Map();
let loaded = false;

/** Serialises every cut. Never reassign to anything that can reject. */
let cutChain = Promise.resolve();
let cutting = null;

export function jobsDir() {
  return JOBS_DIR;
}

async function ensureDir() {
  if (!existsSync(JOBS_DIR)) await mkdir(JOBS_DIR, { recursive: true });
}

function metaPath(id) {
  return join(JOBS_DIR, `${id}.json`);
}

export function svgPath(id) {
  return join(JOBS_DIR, `${id}.svg`);
}

export function hpglPath(id) {
  return join(JOBS_DIR, `${id}.hpgl`);
}

export function previewPath(id) {
  return join(JOBS_DIR, `${id}.preview.svg`);
}

async function persist(job) {
  await ensureDir();
  await writeFile(metaPath(job.id), JSON.stringify(job, null, 2));
}

/** Load previously-created jobs once per process. */
export async function load() {
  if (loaded) return;
  loaded = true;
  await ensureDir();
  const files = await readdir(JOBS_DIR).catch(() => []);
  for (const f of files) {
    if (!f.endsWith('.json')) continue;
    try {
      const job = JSON.parse(await readFile(join(JOBS_DIR, f), 'utf8'));
      // A job left "cutting" means the process died mid-cut. It did not
      // finish, and saying so is more useful than showing a spinner forever.
      if (job.status === 'cutting') {
        job.status = 'error';
        job.error = 'Server restarted while this job was cutting.';
      }
      jobs.set(job.id, job);
    } catch {
      // A corrupt job file should not take down the whole list.
    }
  }
}

export async function create({ name, report, settings }) {
  const job = {
    id: randomUUID(),
    name,
    report,
    settings,
    status: 'ready',
    error: null,
    createdAt: new Date().toISOString(),
    cutAt: null
  };
  jobs.set(job.id, job);
  await persist(job);
  return job;
}

export function get(id) {
  return jobs.get(id) ?? null;
}

export function list() {
  return [...jobs.values()].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export function isCutting() {
  return cutting;
}

async function update(job, patch) {
  Object.assign(job, patch);
  await persist(job);
  return job;
}

/**
 * Queue a cut. Resolves when this job's turn is done.
 *
 * `runner` receives no arguments and does the actual send. Errors are captured
 * onto the job rather than propagated into the chain, so one failed cut cannot
 * wedge the queue for every job after it.
 */
export function enqueueCut(job, runner) {
  const turn = cutChain.then(async () => {
    cutting = job.id;
    await update(job, { status: 'cutting', error: null });
    try {
      await runner();
      await update(job, { status: 'done', cutAt: new Date().toISOString() });
    } catch (err) {
      await update(job, { status: 'error', error: err.message });
    } finally {
      cutting = null;
    }
    return job;
  });
  cutChain = turn.then(
    () => undefined,
    () => undefined
  );
  return turn;
}
