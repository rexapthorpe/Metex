/* landing.js — Metex landing page: spot prices + trades ticker */
(function () {
  'use strict';

  /* ── Spot Price Loader ───────────────────────────────── */
  function fmt(n) {
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function loadSpot() {
    fetch('/api/spot-prices')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success || !data.prices) return;
        var p = data.prices;

        // Panel header chips
        var goldChip = document.getElementById('lp-spot-gold');
        var silvChip = document.getElementById('lp-spot-silver');

        if (goldChip && p.gold) {
          goldChip.textContent = 'XAU ' + fmt(p.gold);
          goldChip.classList.add('loaded');
        }
        if (silvChip && p.silver) {
          silvChip.textContent = 'XAG ' + fmt(p.silver);
          silvChip.classList.add('loaded');
        }
      })
      .catch(function () { /* spot is supplementary — fail silently */ });
  }

  /* ── Trades Ticker ───────────────────────────────────── */
  function initTicker() {
    var dataEl = document.getElementById('lp-trades-data');
    var wrapEl = document.getElementById('lp-ticker-wrap');
    var trackEl = document.getElementById('lp-ticker-track');

    if (!dataEl || !wrapEl || !trackEl) return;

    var trades;
    try {
      trades = JSON.parse(dataEl.textContent || '[]');
    } catch (e) {
      trades = [];
    }

    if (!trades || trades.length === 0) {
      wrapEl.style.display = 'none';
      return;
    }

    /* Build ticker items */
    var items = trades.map(function (t) {
      var price = parseFloat(t.price);
      var priceStr = '$' + price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

      var changeHtml = '';
      if (t.change_pct != null) {
        var pct = parseFloat(t.change_pct);
        var sign = pct >= 0 ? '+' : '';
        var color = pct >= 0 ? '#16a34a' : '#dc2626';
        changeHtml =
          '<span style="color:#374151">·</span>' +
          '<span class="lp-ticker-item-change" style="color:' + color + ';font-weight:600">' +
            sign + pct.toFixed(2) + '%' +
          '</span>';
      }

      return (
        '<span class="lp-ticker-item">' +
          '<span class="lp-ticker-item-name">' + escHtml(t.name) + '</span>' +
          '<span style="color:#374151">·</span>' +
          '<span class="lp-ticker-item-price">' + priceStr + '</span>' +
          changeHtml +
        '</span>'
      );
    });

    /* Repeat items until one copy is wider than the viewport so the
       -50% loop never shows empty space or jumps visibly. */
    var viewW = window.innerWidth || 1200;
    var estItemW = 220; /* conservative px estimate per item + separator */
    var reps = Math.max(1, Math.ceil((viewW + 400) / Math.max(1, items.length * estItemW)));
    var copy = [];
    for (var i = 0; i < reps; i++) copy = copy.concat(items);

    /* Two identical copies — animation scrolls -50% for seamless loop */
    var sep = '<span class="lp-ticker-sep">▸</span>';
    var copyHtml = copy.join(sep) + sep;
    trackEl.innerHTML = copyHtml + copyHtml;

    wrapEl.style.display = 'flex';

    /* Measure after browser has laid out the new content, then set speed */
    requestAnimationFrame(function () {
      var halfW = trackEl.scrollWidth / 2;
      var speed = 80; /* px per second */
      trackEl.style.animationDuration = Math.max(10, halfW / speed).toFixed(1) + 's';
    });
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* ── Transparent Header Over Dark Hero ──────────────── */
  function initTransparentHeader() {
    var band   = document.querySelector('.lp-dark-band');
    var header = document.querySelector('.header-bar');
    if (!band || !header) return;

    function update() {
      /* Stay transparent while the dark band's bottom edge is still
         well below the top of the viewport (>80px away). Switch to
         white as the user scrolls past the dark content. */
      var bandBottom = band.getBoundingClientRect().bottom;
      if (bandBottom > 80) {
        header.classList.add('header--over-hero');
      } else {
        header.classList.remove('header--over-hero');
      }
    }

    window.addEventListener('scroll', update, { passive: true });
    update(); /* set correct state immediately on page load */
  }

  /* ── Boot ────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    loadSpot();
    initTicker();
    initTransparentHeader();
  });

  /* Refresh spot prices every 5 minutes */
  setInterval(loadSpot, 300000);

}());
