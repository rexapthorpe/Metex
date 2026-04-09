/* landing.js — Metex landing page: spot prices + hero search */
(function () {
  'use strict';

  /* ── Spot Price Loader ───────────────────────────────── */
  function fmt(n) {
    return '$' + n.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }) + '/oz';
  }

  function loadSpot() {
    fetch('/api/spot-prices')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success || !data.prices) return;
        var p = data.prices;

        var metals = ['gold', 'silver', 'platinum'];
        metals.forEach(function (m) {
          if (!p[m]) return;
          var priceEl  = document.getElementById('lp-spot-' + m);
          if (priceEl) priceEl.textContent = fmt(p[m]);
        });
      })
      .catch(function () { /* spot is supplementary — fail silently */ });
  }

  /* ── Boot ────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    loadSpot();
  });

  /* Refresh spot prices every 5 minutes */
  setInterval(loadSpot, 300000);

}());
