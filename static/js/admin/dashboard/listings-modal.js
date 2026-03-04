/**
 * Admin Dashboard — Listing Detail / Pricing Modal
 *
 * Opens a detailed pricing breakdown for any listing row in the Listings tab.
 * All data comes from window.LISTING_DETAILS (emitted by _listings_tab.html),
 * so no additional network requests are made.
 */

(function () {
  'use strict';

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function fmt(n) {
    if (n == null) return '—';
    return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtPremium(n) {
    if (n == null) return '—';
    const abs = Math.abs(n);
    const formatted = Number(abs).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return (n >= 0 ? '+' : '−') + '$' + formatted;
  }

  function row(label, value, opts) {
    opts = opts || {};
    const valueStyle = opts.highlight
      ? 'font-weight:700;color:' + (opts.color || '#1a1a2e') + ';font-size:' + (opts.size || '15px')
      : 'font-weight:500;color:#1a1a2e;font-size:14px';
    const labelStyle = 'font-size:13px;color:#6b7280;min-width:160px;flex-shrink:0';
    return '<div class="user-info-row" style="display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid #f3f4f6;">'
      + '<span style="' + labelStyle + '">' + label + '</span>'
      + '<span style="' + valueStyle + '">' + value + '</span>'
      + '</div>';
  }

  function sectionHeader(icon, label) {
    return '<h4 style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;'
      + 'color:#6b7280;margin:20px 0 8px;display:flex;align-items:center;gap:6px;">'
      + '<i class="' + icon + '" style="font-size:11px;"></i>' + label + '</h4>';
  }

  // ── Modal open/close ─────────────────────────────────────────────────────────

  window.openListingDetailModal = function (listingId) {
    var data = (window.LISTING_DETAILS || {})[listingId];
    if (!data) {
      console.warn('Listing detail not found for id', listingId);
      return;
    }

    document.getElementById('listingDetailTitle').textContent =
      '#' + data.id + ' — ' + (data.title || 'Listing');

    var html = '';

    // ── Product Info ──────────────────────────────────────────────────────────
    html += sectionHeader('fa-solid fa-box', 'Product');

    var specParts = [];
    if (data.product_line) specParts.push(data.product_line);
    else if (data.coin_series) specParts.push(data.coin_series);
    if (data.product_type && !specParts.length) specParts.push(data.product_type);
    var specLabel = specParts.join(' · ') || data.product_type || '—';

    html += row('Metal', data.metal || '—');
    html += row('Weight', data.weight || '—');
    if (data.purity) html += row('Purity', data.purity);
    if (data.finish) html += row('Finish', data.finish);
    if (data.year)   html += row('Year', data.year);
    if (data.mint)   html += row('Mint', data.mint);
    if (data.grade)  html += row('Grade', data.grade);
    html += row('Type / Line', specLabel);
    html += row('Seller', '@' + (data.seller || '—'));
    html += row('Quantity Available', String(data.quantity));
    var statusColor = data.status === 'approved' ? '#059669' : '#d97706';
    html += row('Status',
      '<span style="background:' + (data.status === 'approved' ? '#d1fae5' : '#fef3c7') + ';'
      + 'color:' + statusColor + ';padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;">'
      + data.status + '</span>');

    // ── Pricing ───────────────────────────────────────────────────────────────
    html += sectionHeader('fa-solid fa-dollar-sign', 'Pricing');

    var modeLabel = data.pricing_mode === 'premium_to_spot' ? 'Spot + Premium' : 'Static (Fixed)';
    var modeBg    = data.pricing_mode === 'premium_to_spot' ? '#fef3c7' : '#eff6ff';
    var modeColor = data.pricing_mode === 'premium_to_spot' ? '#92400e' : '#1d4ed8';
    html += row('Pricing Mode',
      '<span style="background:' + modeBg + ';color:' + modeColor + ';'
      + 'padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;">'
      + modeLabel + '</span>');

    if (data.pricing_mode === 'premium_to_spot') {
      // Show breakdown: spot → + premium → subtotal → vs floor → effective
      var metalLabel = data.pricing_metal
        ? data.pricing_metal.charAt(0).toUpperCase() + data.pricing_metal.slice(1)
        : (data.metal || '—');
      html += row('Pricing Metal', metalLabel);

      if (data.spot_snapshot_price != null) {
        html += row('Current Spot', fmt(data.spot_snapshot_price),
          { highlight: false });
      } else {
        html += row('Current Spot',
          '<span style="color:#9ca3af;font-size:13px;">No snapshot available</span>');
      }

      html += row('Spot Premium', fmtPremium(data.spot_premium));
      html += row('Floor Price', fmt(data.floor_price),
        { highlight: false });

      // Divider + effective
      html += '<div style="border-top:2px solid #e5e7eb;margin:12px 0 4px;"></div>';

      if (data.effective_price != null) {
        var spot   = data.spot_snapshot_price || 0;
        var prem   = data.spot_premium || 0;
        var floor  = data.floor_price || 0;
        var subtotal = spot + prem;
        var isFloorActive = floor > subtotal;

        var calcNote = isFloorActive
          ? 'Floor applied — spot+premium (' + fmt(subtotal) + ') was below floor'
          : 'Spot + Premium = ' + fmt(subtotal);

        html += row('Effective Price', fmt(data.effective_price),
          { highlight: true, color: '#059669', size: '17px' });
        html += '<p style="font-size:12px;color:#6b7280;margin:4px 0 0;text-align:right;">'
          + calcNote + '</p>';
      } else {
        html += row('Effective Price',
          '<span style="color:#9ca3af;">— (no spot snapshot)</span>');
      }

    } else {
      // Static listing
      html += row('Static Price', fmt(data.price_per_coin),
        { highlight: true, color: '#1a1a2e', size: '17px' });
      html += row('Effective Price', fmt(data.price_per_coin),
        { highlight: true, color: '#059669', size: '15px' });
    }

    // ── Links ─────────────────────────────────────────────────────────────────
    html += sectionHeader('fa-solid fa-link', 'Links');
    html += '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:4px;">'
      + '<a href="/bucket/' + data.bucket_id + '" target="_blank" '
      + 'style="display:inline-flex;align-items:center;gap:6px;padding:8px 16px;'
      + 'background:#1a1a2e;color:#fff;border-radius:8px;font-size:13px;font-weight:500;text-decoration:none;">'
      + '<i class="fa-solid fa-arrow-up-right-from-square"></i> View Bucket #' + data.bucket_id + '</a>'
      + '</div>';

    document.getElementById('listingDetailContent').innerHTML = html;
    document.getElementById('listingDetailModal').style.display = 'flex';
  };

  window.closeListingDetailModal = function () {
    document.getElementById('listingDetailModal').style.display = 'none';
  };

})();
