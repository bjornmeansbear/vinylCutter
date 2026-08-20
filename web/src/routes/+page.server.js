// SPDX-License-Identifier: AGPL-3.0-or-later
import * as cutter from '$lib/server/cutter.js';
import * as presets from '$lib/server/presets.js';
import * as store from '$lib/server/store.js';

export async function load() {
  await store.load();
  return {
    device: await cutter.info(),
    presets: await presets.load(),
    jobs: store.list(),
    cutting: store.isCutting()
  };
}
