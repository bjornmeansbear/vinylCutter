<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script>
  /** @type {{ device: { available: boolean, connected: boolean, devices: string[], note: string|null } }} */
  let { device } = $props();

  let state = $derived(
    !device.available ? 'missing' : device.connected ? 'ready' : 'offline'
  );
</script>

<div class="status" data-state={state}>
  <span class="badge" class:badge-accent={state === 'ready'} class:badge-quiet={state !== 'ready'}>
    {state === 'ready' ? 'connected' : state === 'offline' ? 'no cutter' : 'no cutter cli'}
  </span>

  {#if state === 'ready'}
    <span class="mono">{device.devices[0]}</span>
  {:else}
    <span class="muted">{device.note ?? 'Cutter not found.'}</span>
  {/if}
</div>

<style>
  .status {
    display: flex;
    gap: var(--space-2);
    align-items: baseline;
    flex-wrap: wrap;
    border: var(--rule);
    border-left: 4px solid var(--color-muted);
    padding: var(--space-2);
    margin-bottom: var(--space-4);
  }

  /* Accent marks the one state where the machine can actually cut. */
  .status[data-state='ready'] { border-left-color: var(--color-accent); }
</style>
