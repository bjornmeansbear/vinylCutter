// SPDX-License-Identifier: AGPL-3.0-or-later
import { json } from '@sveltejs/kit';
import * as presets from '$lib/server/presets.js';

export async function GET() {
  return json({ presets: await presets.load() });
}

export async function POST({ request }) {
  const body = await request.json();
  return json({ presets: await presets.save(body.presets) });
}
