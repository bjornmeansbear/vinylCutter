// SPDX-License-Identifier: AGPL-3.0-or-later
import { json } from '@sveltejs/kit';
import * as cutter from '$lib/server/cutter.js';

export async function GET() {
  return json(await cutter.info());
}
