<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script>
  import '../app.css';
  let { children } = $props();
</script>

<div class="shell">
  <header>
    <h1>Vinyl Cutter</h1>
    <p class="muted">Roland CAMM-1 GX-24</p>
  </header>

  {@render children()}

  <footer class="muted">
    <p>
      SVG in, HPGL out, straight to the device node. No print queue involved.
    </p>
    <!-- AGPL section 13: anyone interacting with this over a network is
         entitled to its source. This link is how that obligation is met. -->
    <p>
      Free software under the
      <a href="https://www.gnu.org/licenses/agpl-3.0.html">AGPL-3.0</a> &mdash;
      <a href="https://github.com/bjornmeansbear/vinylCutter">source</a>
    </p>
  </footer>
</div>

<style>
  .shell {
    max-width: 46rem;
    margin: 0 auto;
    padding: var(--space-4) var(--space-3) var(--space-6);
  }

  header {
    border-bottom: var(--rule-thick);
    padding-bottom: var(--space-2);
    margin-bottom: var(--space-4);
  }

  header p { margin: 0; }

  footer {
    margin-top: var(--space-6);
    padding-top: var(--space-2);
    border-top: var(--rule);
  }

  footer p { margin: 0; }
  footer p + p { margin-top: var(--space-1); }

  footer a { color: var(--color-accent-strong); }

  @media (min-width: 40rem) {
    .shell { padding-inline: var(--space-4); }
  }
</style>
