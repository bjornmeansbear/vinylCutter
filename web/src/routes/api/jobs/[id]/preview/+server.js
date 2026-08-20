// SPDX-License-Identifier: AGPL-3.0-or-later
import { error } from '@sveltejs/kit';
import { readFile } from 'node:fs/promises';
import * as store from '$lib/server/store.js';

/** The preview is rendered from the HPGL, so it shows what the machine will do. */
export async function GET({ params }) {
  await store.load();
  if (!store.get(params.id)) error(404, 'No such job.');
  try {
    const svg = await readFile(store.previewPath(params.id), 'utf8');
    return new Response(svg, {
      headers: {
        'content-type': 'image/svg+xml',
        'cache-control': 'no-cache'
      }
    });
  } catch {
    error(404, 'No preview for that job.');
  }
}
