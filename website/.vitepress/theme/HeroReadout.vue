<template>
  <div class="readout" role="img" aria-label="An example readout: the cost is shown before the run; some cases are held back and never seen by the writer; the result is Proven or Not proven.">
    <div class="ro-head"><span class="ro-dot" /><span>Run readout</span><span class="ro-tag">example</span></div>
    <svg class="ro-trace" viewBox="0 0 300 56" preserveAspectRatio="none" aria-hidden="true" focusable="false">
      <path class="ro-line" d="M0 36 H60 L72 36 L82 14 L96 50 L108 36 H170 L182 36 L190 22 L202 42 L212 36 H300" />
    </svg>
    <dl aria-hidden="true">
      <div><dt>Cost</dt><dd>Shown before the run</dd></div>
      <div><dt>Cases</dt><dd>Some held back, never seen by the writer</dd></div>
      <div class="ro-end">
        <dt>Result</dt>
        <dd><span class="pill ok">Proven</span><span class="ro-or">or</span><span class="pill warn">Not proven</span></dd>
      </div>
    </dl>
  </div>
</template>
