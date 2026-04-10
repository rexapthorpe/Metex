/**
 * Bucket Images Tab — admin/dashboard/bucket-images-tab.js
 *
 * Manages the Bucket Image Catalog admin UI:
 *  - Lists standard buckets with cover-image stats
 *  - Create / edit standard bucket entries
 *  - Ingest images from URL or direct upload
 *  - Review candidates: approve / activate / reject / delete
 *  - View full asset provenance in a detail modal
 */

/* ─────────────────────────────────────────── state ── */
let _biBuckets      = [];    // flat list from API
let _biActiveBid    = null;  // currently open bucket id in detail modal
let _biSelectedIds  = new Set(); // asset IDs selected for bulk ops

/* ─────────────────────────────────────────── init ─── */
document.addEventListener('DOMContentLoaded', function () {
  // Load when the tab is first activated (lazy)
  // biLoadBuckets() will be called by switchTab via the auto-load hook below
});

/** Called by the tab framework (tabs.js) when this tab becomes active. */
function biOnTabActivate() {
  biLoadBuckets();
}

/* ─────────────────────────────────────────── list ─── */
function biLoadBuckets() {
  const metal     = document.getElementById('biFilterMetal').value;
  const queueSel  = document.getElementById('biFilterQueue');
  const queueVal  = queueSel ? queueSel.value : '';
  let url = '/admin/api/bucket-images/buckets?active_only=false';
  if (metal) url += `&metal=${encodeURIComponent(metal)}`;
  // Map dropdown value → query param(s)
  if (queueVal === 'missing_cover')   url += '&missing_cover=true';
  if (queueVal === 'no_candidates')   url += '&no_candidates=true';
  if (queueVal === 'pending_only')    url += '&pending_only=true';
  if (queueVal === 'low_confidence')  url += '&low_confidence=true';
  if (queueVal === 'retailer_only')   url += '&retailer_only=true';
  if (queueVal === 'missing_license') url += '&missing_license=true';

  document.getElementById('biBucketList').innerHTML =
    '<div class="dispute-loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading…</div>';
  document.getElementById('biBucketEmpty').style.display = 'none';

  fetch(url)
    .then(r => r.json())
    .then(data => {
      if (!data.success) { biShowError(data.error); return; }
      _biBuckets = data.buckets || [];
      biRenderBucketList(_biBuckets);
      biUpdateStats(_biBuckets);
    })
    .catch(err => biShowError(String(err)));
}

function biUpdateStats(buckets) {
  const total   = buckets.length;
  const covered = buckets.filter(b => (b.active_count || 0) > 0).length;
  const missing = total - covered;
  document.getElementById('biStatsBuckets').textContent  = total;
  document.getElementById('biStatsCovered').textContent  = covered;
  document.getElementById('biStatsMissing').textContent  = missing;
}

function biRenderBucketList(buckets) {
  const wrap = document.getElementById('biBucketList');
  const empty = document.getElementById('biBucketEmpty');

  if (!buckets.length) {
    wrap.innerHTML = '';
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';

  const rows = buckets.map(b => {
    const hasCover   = (b.active_count || 0) > 0;
    const hasPending = (b.pending_count || 0) > 0;
    const conf       = b.active_confidence != null ? parseFloat(b.active_confidence) : null;
    const confStr    = conf != null ? ` (${Math.round(conf * 100)}%)` : '';
    const confColor  = conf != null ? (conf < 0.6 ? '#f59e0b' : '#22a559') : '';

    let coverBadge;
    if (hasCover) {
      coverBadge = `<span style="color:${confColor};font-size:11px;"><i class="fa-solid fa-circle-check"></i> Active${confStr}</span>`;
    } else if (hasPending) {
      coverBadge = `<span style="color:#6366f1;font-size:11px;"><i class="fa-solid fa-clock"></i> ${b.pending_count} pending</span>`;
    } else {
      coverBadge = '<span style="color:#f59e0b;font-size:11px;"><i class="fa-solid fa-circle-exclamation"></i> No cover</span>';
    }

    const assets = b.total_assets || 0;
    const licenseWarn = hasCover && !b.active_license_type
      ? ' <span title="No license on active image" style="color:#f59e0b;font-size:10px;"><i class="fa-solid fa-triangle-exclamation"></i></span>'
      : '';

    return `<tr>
      <td><strong>${esc(b.title)}</strong><br><code style="font-size:11px;color:#888;">${esc(b.slug)}</code></td>
      <td>${esc(b.metal)}</td>
      <td>${esc(b.form || '')}</td>
      <td>${esc(b.weight || '')}</td>
      <td>${esc(b.mint || '')}</td>
      <td>${assets} asset${assets !== 1 ? 's' : ''}<br>${coverBadge}${licenseWarn}</td>
      <td>
        <button class="admin-action-btn" style="padding:4px 10px;font-size:12px;"
                onclick="biOpenBucketDetail(${b.id})">
          <i class="fa-solid fa-images"></i> Manage Images
        </button>
      </td>
    </tr>`;
  }).join('');

  wrap.innerHTML = `
    <table class="admin-table" style="width:100%;border-collapse:collapse;">
      <thead>
        <tr>
          <th>Title / Slug</th><th>Metal</th><th>Form</th>
          <th>Weight</th><th>Mint</th><th>Images</th><th>Actions</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

/* ─────────────────────────────────────── create bucket ── */
function biOpenCreateBucketModal() {
  ['biNewSlug','biNewTitle','biNewMint','biNewDenomination','biNewFamily',
   'biNewSeries','biNewYear','biNewPurity','biNewWeight','biNewWeightOz',
   'biNewCategoryBucketId'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  document.getElementById('biNewMetal').value = '';
  document.getElementById('biNewForm').value  = 'coin';
  document.getElementById('biNewYearPolicy').value = 'fixed';
  document.getElementById('biCreateBucketModal').style.display = 'flex';
}
function biCloseCreateBucketModal() {
  document.getElementById('biCreateBucketModal').style.display = 'none';
}

function biCreateBucket() {
  const payload = {
    slug:               document.getElementById('biNewSlug').value.trim(),
    title:              document.getElementById('biNewTitle').value.trim(),
    metal:              document.getElementById('biNewMetal').value,
    form:               document.getElementById('biNewForm').value,
    weight:             document.getElementById('biNewWeight').value.trim() || null,
    weight_oz:          parseFloat(document.getElementById('biNewWeightOz').value) || null,
    denomination:       document.getElementById('biNewDenomination').value.trim() || null,
    mint:               document.getElementById('biNewMint').value.trim() || null,
    product_family:     document.getElementById('biNewFamily').value.trim() || null,
    product_series:     document.getElementById('biNewSeries').value.trim() || null,
    year_policy:        document.getElementById('biNewYearPolicy').value,
    year:               document.getElementById('biNewYear').value.trim() || null,
    purity:             document.getElementById('biNewPurity').value.trim() || null,
    category_bucket_id: parseInt(document.getElementById('biNewCategoryBucketId').value) || null,
  };

  if (!payload.slug || !payload.title || !payload.metal) {
    alert('Slug, Title, and Metal are required.');
    return;
  }

  fetch('/admin/api/bucket-images/buckets', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
    body:    JSON.stringify(payload),
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) { alert('Error: ' + data.error); return; }
      biCloseCreateBucketModal();
      biLoadBuckets();
    })
    .catch(err => alert('Error: ' + err));
}

/* ─────────────────────────────────── bucket detail modal ── */
function biOpenBucketDetail(bucketId) {
  _biActiveBid   = bucketId;
  _biSelectedIds = new Set();
  _biUpdateBulkUI();
  document.getElementById('biBucketDetailModal').style.display = 'flex';
  biRefreshBucketDetail();
}
function biCloseBucketDetailModal() {
  document.getElementById('biBucketDetailModal').style.display = 'none';
  _biActiveBid    = null;
  _biSelectedIds  = new Set();
  biLoadBuckets(); // refresh stats
}

/* ─────────────────────────── auto-activate best candidate ── */
function biAutoActivateBest() {
  if (!_biActiveBid) return;
  if (!confirm('Activate the highest-confidence candidate for this bucket? ' +
               'Any existing active image will be demoted to approved.')) return;

  fetch(`/admin/api/bucket-images/buckets/${_biActiveBid}/auto-activate`, {
    method:  'POST',
    headers: { 'X-CSRFToken': getCsrfToken() },
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) { alert('Error: ' + data.error); return; }
      const conf = Math.round((data.asset.confidence_score || 0) * 100);
      alert(`Activated!\nSource: ${data.asset.source_name}\nConfidence: ${conf}%`);
      biRefreshBucketDetail();
    })
    .catch(err => alert('Error: ' + err));
}

/* ─────────────────────────── bulk selection + reject ── */
function biToggleAssetSelection(assetId, checked) {
  if (checked) {
    _biSelectedIds.add(assetId);
  } else {
    _biSelectedIds.delete(assetId);
  }
  _biUpdateBulkUI();
}

function biToggleSelectAll() {
  // Collect all selectable asset ids from the grid checkboxes
  const checkboxes = document.querySelectorAll('#biCandidatesGrid .bi-asset-checkbox');
  const allChecked = checkboxes.length > 0 &&
                     Array.from(checkboxes).every(cb => cb.checked);
  checkboxes.forEach(cb => {
    cb.checked = !allChecked;
    const id = parseInt(cb.dataset.assetId, 10);
    if (!allChecked) _biSelectedIds.add(id);
    else             _biSelectedIds.delete(id);
  });
  _biUpdateBulkUI();
}

function _biUpdateBulkUI() {
  const count = _biSelectedIds.size;
  const btn   = document.getElementById('biBulkRejectBtn');
  const cntEl = document.getElementById('biBulkCount');
  if (btn)   btn.style.display   = count > 0 ? '' : 'none';
  if (cntEl) cntEl.textContent   = count;
}

function biBulkRejectSelected() {
  if (_biSelectedIds.size === 0) return;
  if (!confirm(`Reject ${_biSelectedIds.size} selected candidate(s)? This cannot be undone.`)) return;

  fetch('/admin/api/bucket-images/assets/bulk-reject', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
    body:    JSON.stringify({ asset_ids: Array.from(_biSelectedIds) }),
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) { alert('Error: ' + data.error); return; }
      _biSelectedIds = new Set();
      _biUpdateBulkUI();
      biRefreshBucketDetail();
    })
    .catch(err => alert('Error: ' + err));
}

/* ─────────────────────────── coverage report ── */
function biLoadCoverageReport() {
  const bar  = document.getElementById('biCoverageBar');
  const body = document.getElementById('biCoverageContent');
  if (!bar || !body) return;
  bar.style.display = '';
  body.innerHTML    = '<i class="fa-solid fa-spinner fa-spin"></i> Loading…';

  fetch('/admin/api/bucket-images/coverage')
    .then(r => r.json())
    .then(data => {
      if (!data.success) { body.innerHTML = 'Error: ' + esc(data.error); return; }
      const r = data.report;
      const metalRows = Object.entries(r.by_metal || {}).map(([metal, s]) =>
        `<tr>
          <td style="padding:2px 12px 2px 0;">${esc(metal)}</td>
          <td style="padding:2px 8px;">${s.with_active} / ${s.total}</td>
          <td style="padding:2px 0;color:${s.coverage_pct >= 80 ? '#22a559' : s.coverage_pct >= 40 ? '#f59e0b' : '#ef4444'};">
            ${s.coverage_pct}%
          </td>
        </tr>`
      ).join('');

      const srcRows = Object.entries(r.by_source || {}).map(([src, cnt]) =>
        `<tr>
          <td style="padding:2px 12px 2px 0;">${esc(src)}</td>
          <td style="padding:2px 0;">${cnt} active image${cnt !== 1 ? 's' : ''}</td>
        </tr>`
      ).join('');

      const pct = r.coverage_pct;
      const pctColor = pct >= 80 ? '#22a559' : pct >= 40 ? '#f59e0b' : '#ef4444';

      body.innerHTML = `
        <div style="display:flex;gap:24px;flex-wrap:wrap;">
          <div>
            <div style="margin-bottom:6px;">
              <strong style="font-size:22px;color:${pctColor};">${pct}%</strong>
              <span style="color:#888;font-size:12px;"> covered</span>
            </div>
            <table style="font-size:12px;border-collapse:collapse;">
              <tr><td style="color:#888;padding-right:12px;">Total buckets</td><td><strong>${r.total}</strong></td></tr>
              <tr><td style="color:#888;padding-right:12px;">With active cover</td><td style="color:#22a559;"><strong>${r.with_active}</strong></td></tr>
              <tr><td style="color:#888;padding-right:12px;">Pending only</td><td style="color:#f59e0b;"><strong>${r.pending_only}</strong></td></tr>
              <tr><td style="color:#888;padding-right:12px;">No candidates</td><td style="color:#ef4444;"><strong>${r.no_candidates}</strong></td></tr>
            </table>
          </div>
          <div>
            <div style="font-size:11px;font-weight:600;color:#666;text-transform:uppercase;margin-bottom:4px;">By Metal</div>
            <table style="font-size:12px;border-collapse:collapse;">${metalRows}</table>
          </div>
          ${srcRows ? `<div>
            <div style="font-size:11px;font-weight:600;color:#666;text-transform:uppercase;margin-bottom:4px;">Active Images By Source</div>
            <table style="font-size:12px;border-collapse:collapse;">${srcRows}</table>
          </div>` : ''}
        </div>`;
    })
    .catch(err => { body.innerHTML = 'Error: ' + esc(String(err)); });
}

function biRefreshBucketDetail() {
  if (!_biActiveBid) return;
  fetch(`/admin/api/bucket-images/buckets/${_biActiveBid}`)
    .then(r => r.json())
    .then(data => {
      if (!data.success) { alert('Error loading bucket: ' + data.error); return; }
      biRenderBucketDetail(data.bucket);
    })
    .catch(err => alert('Error: ' + err));
}

function biRenderBucketDetail(bucket) {
  // Title
  document.getElementById('biBucketDetailTitle').innerHTML =
    `<i class="fa-solid fa-images"></i> ${esc(bucket.title)}`;

  // Metadata row
  const meta = [
    ['Metal', bucket.metal],
    ['Form',  bucket.form],
    ['Weight', bucket.weight || '—'],
    ['Mint', bucket.mint || '—'],
    ['Year Policy', bucket.year_policy],
    ['Year', bucket.year || '—'],
    ['Family', bucket.product_family || '—'],
    ['Slug', bucket.slug],
  ];
  document.getElementById('biBucketMeta').innerHTML = meta.map(([k,v]) =>
    `<div><span style="font-size:11px;color:#888;display:block;">${esc(k)}</span><strong>${esc(v)}</strong></div>`
  ).join('');

  // Active cover
  const active = (bucket.assets || []).find(a => a.status === 'active');
  const coverImg = document.getElementById('biActiveCoverImg');
  const coverPh  = document.getElementById('biActiveCoverPlaceholder');
  if (active && active.thumb_path) {
    coverImg.src = `/static/${active.thumb_path}`;
    coverImg.style.display = '';
    coverPh.style.display  = 'none';
  } else {
    coverImg.style.display = 'none';
    coverPh.style.display  = '';
  }

  // Candidates grid
  const assets = (bucket.assets || []).sort((a,b) => {
    const order = {active:0, approved:1, pending:2, rejected:3};
    return (order[a.status]||9) - (order[b.status]||9);
  });
  const grid  = document.getElementById('biCandidatesGrid');
  const empty = document.getElementById('biCandidatesEmpty');

  if (!assets.length) {
    grid.innerHTML = '';
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';

  grid.innerHTML = assets.map(a => biRenderAssetCard(a)).join('');
}

function biRenderAssetCard(a) {
  const statusColors = { active:'#22a559', approved:'#3b82f6', pending:'#f59e0b', rejected:'#ef4444' };
  const color  = statusColors[a.status] || '#888';
  const imgSrc = a.thumb_path ? `/static/${a.thumb_path}` : '';
  const imgTag = imgSrc
    ? `<img src="${imgSrc}" alt="" style="width:100%;height:120px;object-fit:contain;background:#f5f5f5;">`
    : `<div style="width:100%;height:120px;background:#f0f0f0;display:flex;align-items:center;justify-content:center;color:#bbb;"><i class="fa-solid fa-image fa-2x"></i></div>`;
  const conf  = Math.round((a.confidence_score || 0) * 100);
  const warns = (() => { try { return JSON.parse(a.match_warnings||'[]'); } catch { return []; } })();

  // Selectable (for bulk ops) when not active
  const selectable = a.status !== 'active';
  const checkbox   = selectable
    ? `<input type="checkbox" class="bi-asset-checkbox" data-asset-id="${a.id}"
              style="position:absolute;top:6px;right:6px;z-index:5;cursor:pointer;"
              onclick="event.stopPropagation();biToggleAssetSelection(${a.id}, this.checked)">`
    : '';

  return `<div style="position:relative;border:2px solid ${color};border-radius:8px;overflow:hidden;font-size:12px;cursor:pointer;"
               onclick="biOpenAssetDetail(${a.id})">
    ${checkbox}
    ${imgTag}
    <div style="padding:8px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
        <span style="background:${color};color:#fff;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:600;">${a.status.toUpperCase()}</span>
        <span style="color:#888;">${conf}% match</span>
      </div>
      <div style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(a.source_name)}</div>
      <div style="color:#888;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(a.source_type)}</div>
      ${warns.length ? `<div style="color:#f59e0b;margin-top:3px;">${warns.map(w=>`⚠ ${w}`).join(' ')}</div>` : ''}
    </div>
  </div>`;
}

/* ─────────────────────────────────── ingest from URL ── */
function biIngestFromUrl() {
  if (!_biActiveBid) return;
  const url        = document.getElementById('biIngestUrl').value.trim();
  const sourceName = document.getElementById('biIngestSourceName').value.trim();
  const sourceType = document.getElementById('biIngestSourceType').value;
  const rawTitle   = document.getElementById('biIngestRawTitle').value.trim();
  const licenseType= document.getElementById('biIngestLicenseType').value.trim();

  if (!url)        { alert('Image URL is required.'); return; }
  if (!sourceName) { alert('Source name is required.'); return; }

  const payload = {
    url, source_name: sourceName, source_type: sourceType,
    raw_source_title: rawTitle, license_type: licenseType || null,
  };

  fetch(`/admin/api/bucket-images/buckets/${_biActiveBid}/ingest-url`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
    body:    JSON.stringify(payload),
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) { alert('Ingest error: ' + data.error); return; }
      if (data.duplicate) {
        alert('This image already exists in the catalog (duplicate checksum).');
      } else {
        alert(`Image ingested!\nStatus: ${data.status}\nConfidence: ${Math.round((data.confidence_score||0)*100)}%`);
        // Clear fields
        ['biIngestUrl','biIngestSourceName','biIngestRawTitle','biIngestLicenseType'].forEach(id => {
          const el = document.getElementById(id); if (el) el.value = '';
        });
      }
      biRefreshBucketDetail();
    })
    .catch(err => alert('Error: ' + err));
}

/* ─────────────────────────────────── upload file ── */
function biUploadImage() {
  if (!_biActiveBid) return;
  const fileInput  = document.getElementById('biUploadFile');
  const sourceName = (document.getElementById('biUploadSourceName').value.trim()) || 'Admin Upload';

  if (!fileInput.files || !fileInput.files[0]) {
    alert('Please select an image file.');
    return;
  }

  const fd = new FormData();
  fd.append('image',       fileInput.files[0]);
  fd.append('source_name', sourceName);
  fd.append('source_type', 'internal_upload');

  fetch(`/admin/api/bucket-images/buckets/${_biActiveBid}/upload`, {
    method:  'POST',
    headers: { 'X-CSRFToken': getCsrfToken() },
    body:    fd,
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) { alert('Upload error: ' + data.error); return; }
      if (data.duplicate) {
        alert('This image already exists in the catalog.');
      } else {
        alert(`Image uploaded!\nStatus: ${data.status}`);
        fileInput.value = '';
      }
      biRefreshBucketDetail();
    })
    .catch(err => alert('Error: ' + err));
}

/* ─────────────────────────────────── asset detail modal ── */
function biOpenAssetDetail(assetId) {
  fetch(`/admin/api/bucket-images/buckets/${_biActiveBid}`)
    .then(r => r.json())
    .then(data => {
      if (!data.success) return;
      const asset = (data.bucket.assets||[]).find(a => a.id === assetId);
      if (!asset) return;
      biShowAssetDetail(asset);
    });
}
function biCloseAssetDetailModal() {
  document.getElementById('biAssetDetailModal').style.display = 'none';
}

function biShowAssetDetail(a) {
  const warns = (() => { try { return JSON.parse(a.match_warnings||'[]'); } catch { return []; } })();
  const imgSrc = a.web_path ? `/static/${a.web_path}` : '';

  document.getElementById('biAssetDetailBody').innerHTML = `
    <div style="display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap;">
      <div>
        ${imgSrc ? `<img src="${imgSrc}" alt="" style="max-width:220px;max-height:220px;object-fit:contain;border:1px solid #eee;border-radius:6px;">` : '<div style="width:180px;height:180px;background:#f0f0f0;display:flex;align-items:center;justify-content:center;color:#bbb;border-radius:6px;"><i class="fa-solid fa-image fa-3x"></i></div>'}
      </div>
      <div style="flex:1;min-width:220px;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          ${biDetailRow('Status',      `<strong style="color:${statusColor(a.status)}">${a.status.toUpperCase()}</strong>`)}
          ${biDetailRow('Source',      esc(a.source_name))}
          ${biDetailRow('Source Type', esc(a.source_type))}
          ${biDetailRow('Priority',    a.source_priority)}
          ${biDetailRow('Confidence',  Math.round((a.confidence_score||0)*100) + '%')}
          ${warns.length ? biDetailRow('Warnings', warns.map(w=>`<span style="color:#f59e0b">⚠ ${esc(w)}</span>`).join(' ')) : ''}
          ${biDetailRow('Dimensions',  (a.width && a.height) ? `${a.width} × ${a.height}` : '—')}
          ${biDetailRow('File Size',   a.file_size ? Math.round(a.file_size/1024) + ' KB' : '—')}
          ${biDetailRow('MIME Type',   a.mime_type || '—')}
          ${biDetailRow('Checksum',    `<code style="font-size:11px;">${(a.checksum||'').slice(0,16)}…</code>`)}
          ${biDetailRow('License',     esc(a.license_type || '—'))}
          ${biDetailRow('Rights Note', esc(a.rights_note || '—'))}
          ${biDetailRow('Attribution', esc(a.attribution_text || '—'))}
          ${a.source_page_url ? biDetailRow('Source Page', `<a href="${esc(a.source_page_url)}" target="_blank" rel="noopener">${esc(a.source_page_url).slice(0,60)}…</a>`) : ''}
          ${a.original_image_url ? biDetailRow('Original URL', `<a href="${esc(a.original_image_url)}" target="_blank" rel="noopener">link</a>`) : ''}
          ${biDetailRow('Raw Title',   esc(a.raw_source_title || '—'))}
          ${biDetailRow('Ingested',    esc(a.created_at || '—'))}
          ${biDetailRow('Reviewed',    esc(a.reviewed_at || 'Not reviewed'))}
        </table>
      </div>
    </div>`;

  // Action buttons based on current status
  const footer = document.getElementById('biAssetDetailFooter');
  footer.innerHTML = '';

  if (a.status !== 'rejected') {
    const rejectBtn = document.createElement('button');
    rejectBtn.className = 'admin-action-btn admin-action-btn--danger';
    rejectBtn.innerHTML = '<i class="fa-solid fa-ban"></i> Reject';
    rejectBtn.onclick = () => biLifecycleAction(a.id, 'reject');
    footer.appendChild(rejectBtn);
  }
  if (a.status === 'pending') {
    const approveBtn = document.createElement('button');
    approveBtn.className = 'admin-action-btn';
    approveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Approve';
    approveBtn.onclick = () => biLifecycleAction(a.id, 'approve');
    footer.appendChild(approveBtn);
  }
  if (a.status === 'approved' || a.status === 'pending') {
    const activateBtn = document.createElement('button');
    activateBtn.className = 'admin-action-btn admin-action-btn--primary';
    activateBtn.innerHTML = '<i class="fa-solid fa-star"></i> Set as Active Cover';
    activateBtn.onclick = () => biLifecycleAction(a.id, 'activate');
    footer.appendChild(activateBtn);
  }
  if (a.status !== 'active') {
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'admin-action-btn admin-action-btn--danger';
    deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i> Delete';
    deleteBtn.onclick = () => biDeleteAsset(a.id);
    footer.appendChild(deleteBtn);
  }

  document.getElementById('biAssetDetailModal').style.display = 'flex';
}

function biDetailRow(label, value) {
  return `<tr>
    <td style="padding:4px 12px 4px 0;color:#888;white-space:nowrap;vertical-align:top;">${esc(label)}</td>
    <td style="padding:4px 0;">${value}</td>
  </tr>`;
}

function statusColor(s) {
  return {active:'#22a559',approved:'#3b82f6',pending:'#f59e0b',rejected:'#ef4444'}[s] || '#888';
}

/* ─────────────────────────────────── lifecycle actions ── */
function biLifecycleAction(assetId, action) {
  fetch(`/admin/api/bucket-images/assets/${assetId}/${action}`, {
    method:  'POST',
    headers: { 'X-CSRFToken': getCsrfToken() },
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) { alert('Error: ' + data.error); return; }
      biCloseAssetDetailModal();
      biRefreshBucketDetail();
    })
    .catch(err => alert('Error: ' + err));
}

function biDeleteAsset(assetId) {
  if (!confirm('Permanently delete this image asset and its files? This cannot be undone.')) return;
  fetch(`/admin/api/bucket-images/assets/${assetId}`, {
    method:  'DELETE',
    headers: { 'X-CSRFToken': getCsrfToken() },
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) { alert('Error: ' + data.error); return; }
      biCloseAssetDetailModal();
      biRefreshBucketDetail();
    })
    .catch(err => alert('Error: ' + err));
}

/* ─────────────────────────────────────────── utils ── */
function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) return meta.content;
  // Fallback: look in cookie
  const m = document.cookie.match(/csrf_token=([^;]+)/);
  return m ? m[1] : '';
}

function biShowError(msg) {
  document.getElementById('biBucketList').innerHTML =
    `<div style="color:#ef4444;padding:16px;">Error: ${esc(msg)}</div>`;
}

/* ─────────────────────────────────────────── tab hook ── */
// Hook into the tabs.js switchTab function so we auto-load on first visit
(function patchSwitchTab() {
  const original = window.switchTab;
  if (typeof original !== 'function') return;
  window.switchTab = function(tabName) {
    original(tabName);
    if (tabName === 'bucket-images') biOnTabActivate();
  };
})();
