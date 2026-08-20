<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script>
  /**
   * One job: what it will cut, how big, and the control that starts the blade.
   *
   * The cut button is deliberately two-step. This runs on a phone in a pocket
   * next to a machine with an exposed blade, and a single tap is too little
   * friction for an action that cannot be undone.
   */
  let { job, canCut, busy, oncut } = $props();

  let armed = $state(false);
  let armTimer;

  function arm() {
    armed = true;
    clearTimeout(armTimer);
    // Disarm on its own so a forgotten tap does not stay live indefinitely.
    armTimer = setTimeout(() => (armed = false), 5000);
  }

  function confirm() {
    clearTimeout(armTimer);
    armed = false;
    oncut(job);
  }

  const statusLabel = {
    ready: 'ready',
    cutting: 'cutting',
    done: 'cut',
    error: 'error'
  };
</script>

<article class="panel stack">
  <div class="head">
    <h3>{job.name}</h3>
    <span
      class="badge"
      class:badge-accent={job.status === 'cutting'}
      class:badge-quiet={job.status !== 'cutting'}
    >
      {statusLabel[job.status] ?? job.status}
    </span>
  </div>

  {#if job.status === 'error'}
    <p class="error">{job.error}</p>
  {/if}

  {#if job.report}
    <img
      class="preview"
      src="/api/jobs/{job.id}/preview"
      alt="Cut path preview for {job.name}: {job.report.paths} paths across
           {job.report.widthMm} by {job.report.heightMm} millimetres."
    />

    <dl class="report">
      <div><dt>Size</dt><dd>{job.report.widthMm} &times; {job.report.heightMm} mm</dd></div>
      <div><dt>Paths</dt><dd>{job.report.paths}</dd></div>
      <div><dt>Cut</dt><dd>{job.report.cutMetres} m</dd></div>
      <div>
        <dt>Travel</dt>
        <dd>
          {job.report.travelMetres} m
          {#if job.report.travelSavedPct > 1}
            <span class="muted">(&minus;{job.report.travelSavedPct}%)</span>
          {/if}
        </dd>
      </div>
      {#if job.settings.force != null}
        <div><dt>Force</dt><dd>{job.settings.force} gf</dd></div>
      {/if}
      {#if job.settings.speed != null}
        <div><dt>Speed</dt><dd>{job.settings.speed} cm/s</dd></div>
      {/if}
    </dl>
  {/if}

  {#if job.report}
    <div class="row">
      {#if armed}
        <button class="button-accent" onclick={confirm}>
          Confirm &mdash; start cutting
        </button>
        <button onclick={() => (armed = false)}>Cancel</button>
      {:else}
        <button
          class="button-accent"
          disabled={!canCut || busy || job.status === 'cutting'}
          onclick={arm}
        >
          {job.status === 'done' ? 'Cut again' : 'Cut'}
        </button>
        {#if !canCut}
          <span class="muted">No cutter connected.</span>
        {:else if busy}
          <span class="muted">The cutter is busy.</span>
        {/if}
      {/if}
    </div>
  {/if}
</article>

<style>
  .head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: var(--space-2);
  }

  .preview {
    display: block;
    width: 100%;
    height: auto;
    border: var(--rule);
    background: var(--color-bg);
  }

  .report {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: var(--space-2);
    margin: 0;
  }

  .report dt {
    font-size: var(--text-xs);
    line-height: var(--leading-xs);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-weight: 700;
    color: var(--color-muted);
  }

  .report dd {
    margin: 0;
    font-family: var(--font-mono);
    font-size: var(--text-sm);
  }

  .error {
    margin: 0;
    padding: var(--space-2);
    border: var(--rule);
    border-left: 4px solid var(--color-accent);
    font-size: var(--text-sm);
    line-height: var(--leading-sm);
  }

  @media (min-width: 40rem) {
    .report { grid-template-columns: repeat(4, 1fr); }
  }
</style>
