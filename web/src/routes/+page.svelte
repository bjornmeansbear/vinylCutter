<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script>
  import DeviceStatus from '$lib/components/DeviceStatus.svelte';
  import JobCard from '$lib/components/JobCard.svelte';

  let { data } = $props();

  let device = $state(data.device);
  let jobs = $state(data.jobs);
  let cutting = $state(data.cutting);
  let presets = $state(data.presets);

  let selectedPreset = $state(presets[1]?.id ?? presets[0]?.id ?? '');
  let force = $state(presets[1]?.force ?? 110);
  let speed = $state(presets[1]?.speed ?? 20);
  let margin = $state(5);
  let rolandExt = $state(true);

  let uploading = $state(false);
  let uploadError = $state('');
  let fileInput;

  let canCut = $derived(device.connected && !cutting);

  function choosePreset(preset) {
    selectedPreset = preset.id;
    force = preset.force;
    speed = preset.speed;
  }

  async function upload(file) {
    if (!file) return;
    uploading = true;
    uploadError = '';

    const body = new FormData();
    body.set('svg', file);
    body.set('force', String(force));
    body.set('speed', String(speed));
    body.set('margin', String(margin));
    body.set('rolandExt', String(rolandExt));
    if (selectedPreset) body.set('preset', selectedPreset);

    try {
      const res = await fetch('/api/jobs', { method: 'POST', body });
      const payload = await res.json();
      if (payload.job) {
        jobs = [payload.job, ...jobs];
        if (payload.job.status === 'error') uploadError = payload.job.error;
      } else {
        uploadError = payload.message ?? 'Upload failed.';
      }
    } catch (err) {
      uploadError = err.message;
    } finally {
      uploading = false;
      if (fileInput) fileInput.value = '';
    }
  }

  async function cut(job) {
    const res = await fetch(`/api/jobs/${job.id}/cut`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: '{}'
    });
    if (!res.ok) {
      const payload = await res.json().catch(() => ({}));
      uploadError = payload.message ?? 'Could not start the cut.';
      return;
    }
    poll();
  }

  /** Poll while a cut is running. Cuts take minutes; 2s is responsive enough. */
  let polling = false;
  async function poll() {
    if (polling) return;
    polling = true;
    try {
      while (true) {
        const res = await fetch('/api/jobs');
        const payload = await res.json();
        jobs = payload.jobs;
        cutting = payload.cutting;
        if (!cutting) break;
        await new Promise((r) => setTimeout(r, 2000));
      }
      device = await (await fetch('/api/device')).json();
    } finally {
      polling = false;
    }
  }

  let dragging = $state(false);
</script>

<DeviceStatus {device} />

<section class="stack">
  <div>
    <h2>New job</h2>
    <p class="muted">
      Outline text and expand strokes before exporting. Fills are ignored &mdash;
      only path geometry is cut.
    </p>
  </div>

  <div
    class="drop"
    class:dragging
    role="button"
    tabindex="0"
    ondragover={(e) => { e.preventDefault(); dragging = true; }}
    ondragleave={() => (dragging = false)}
    ondrop={(e) => { e.preventDefault(); dragging = false; upload(e.dataTransfer?.files?.[0]); }}
    onclick={() => fileInput.click()}
    onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } }}
  >
    {#if uploading}
      <strong>Converting&hellip;</strong>
    {:else}
      <strong>Drop an SVG here</strong>
      <span class="muted">or tap to choose a file</span>
    {/if}
  </div>

  <input
    bind:this={fileInput}
    class="visually-hidden"
    type="file"
    accept=".svg,image/svg+xml"
    onchange={(e) => upload(e.currentTarget.files?.[0])}
  />

  {#if uploadError}
    <p class="error" role="alert">{uploadError}</p>
  {/if}

  <fieldset class="panel stack">
    <legend class="label">Material</legend>

    <div class="row" role="group" aria-label="Material presets">
      {#each presets as preset (preset.id)}
        <button
          type="button"
          aria-pressed={selectedPreset === preset.id}
          onclick={() => choosePreset(preset)}
        >
          {preset.name}
        </button>
      {/each}
    </div>

    <div class="fields">
      <div>
        <label class="label" for="force">Force &mdash; {force} gf</label>
        <input id="force" type="range" min="20" max="250" step="5" bind:value={force} />
      </div>
      <div>
        <label class="label" for="speed">Speed &mdash; {speed} cm/s</label>
        <input id="speed" type="range" min="1" max="50" step="1" bind:value={speed} />
      </div>
      <div>
        <label class="label" for="margin">Margin from origin (mm)</label>
        <input id="margin" type="number" min="0" max="100" step="1" bind:value={margin} />
      </div>
    </div>

    <label class="check">
      <input type="checkbox" bind:checked={rolandExt} />
      <span>
        Send force and speed to the machine
        <span class="muted">
          &mdash; uncheck if your firmware ignores them and set both on the front panel
        </span>
      </span>
    </label>
  </fieldset>
</section>

<section class="stack jobs">
  <h2>Jobs</h2>
  {#if jobs.length === 0}
    <p class="muted">Nothing yet.</p>
  {:else}
    {#each jobs as job (job.id)}
      <JobCard {job} {canCut} busy={!!cutting} oncut={cut} />
    {/each}
  {/if}
</section>

<style>
  section + section { margin-top: var(--space-5); }

  .drop {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    align-items: center;
    justify-content: center;
    min-height: 8rem;
    padding: var(--space-4);
    border: 2px dashed var(--color-border);
    text-align: center;
    cursor: pointer;
  }

  .drop.dragging {
    border-style: solid;
    border-color: var(--color-accent);
    background: var(--color-accent-subtle);
  }

  fieldset { border: var(--rule); }
  legend { padding-inline: var(--space-1); }

  .fields { display: grid; gap: var(--space-3); }

  .check {
    display: flex;
    gap: var(--space-2);
    align-items: flex-start;
    font-size: var(--text-sm);
    line-height: var(--leading-sm);
  }

  .check input { margin-top: 0.25rem; accent-color: var(--color-accent); }

  .error {
    padding: var(--space-2);
    border: var(--rule);
    border-left: 4px solid var(--color-accent);
    font-size: var(--text-sm);
    line-height: var(--leading-sm);
  }

  .jobs > :global(article + article) { margin-top: var(--space-3); }

  @media (min-width: 40rem) {
    .fields { grid-template-columns: repeat(3, 1fr); }
  }
</style>
