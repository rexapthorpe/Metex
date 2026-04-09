/**
 * Admin Feedback Tab
 * ==================
 * Analytics page for user feedback submissions.
 * Handles stats cards, donut + bar charts, filter pills, paginated table,
 * and detail modal.
 */

// ── State ─────────────────────────────────────────────────────────────────────
var _fbPage     = 1;
var _fbTypeFilter = '';
var _fbDonutChart = null;
var _fbBarChart   = null;

// ── Type helpers ──────────────────────────────────────────────────────────────
var _FB_TYPE_META = {
  issue:       { label: 'Issue / Bug',   badge: 'fb-badge-issue',       icon: 'fa-bug',      color: '#ef4444' },
  improvement: { label: 'Improvement',   badge: 'fb-badge-improvement', icon: 'fa-lightbulb',color: '#3b82f6' },
  praise:      { label: 'Praise',        badge: 'fb-badge-praise',      icon: 'fa-thumbs-up',color: '#22c55e' },
  other:       { label: 'Other',         badge: 'fb-badge-other',       icon: 'fa-ellipsis', color: '#8b5cf6' },
};

function _fbTypeMeta(type) {
  return _FB_TYPE_META[type] || { label: 'Uncategorized', badge: 'fb-badge-unset', icon: 'fa-circle-question', color: '#9ca3af' };
}

function _fmtDateTimeFb(s) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch (_) { return s; }
}

function _fmtDateFb(s) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  } catch (_) { return s; }
}

// ── Stats ─────────────────────────────────────────────────────────────────────

function loadFeedbackStats() {
  fetch('/admin/api/feedback/stats')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.success) return;

      var total = data.total || 0;
      function pct(n) { return total > 0 ? ' (' + Math.round((n / total) * 100) + '%)' : ''; }

      _setText('fbStatTotal',           total);
      _setText('fbStatIssue',           data.by_type.issue);
      _setText('fbStatIssuePct',        pct(data.by_type.issue));
      _setText('fbStatImprovement',     data.by_type.improvement);
      _setText('fbStatImprovementPct',  pct(data.by_type.improvement));
      _setText('fbStatPraise',          data.by_type.praise);
      _setText('fbStatPraisePct',       pct(data.by_type.praise));
      _setText('fbStatOther',           data.by_type.other);
      _setText('fbStatOtherPct',        pct(data.by_type.other));
      _setText('fbStat30d',             data.last_30d);

      // Trend vs previous 30d
      var trendEl = document.getElementById('fbStat30dTrend');
      if (trendEl) {
        var cur = data.last_30d || 0;
        var prev = data.prev_30d || 0;
        if (prev === 0 && cur === 0) {
          trendEl.textContent = 'No recent activity';
          trendEl.className = 'fb-stat-trend flat';
        } else if (prev === 0) {
          trendEl.textContent = '\u2191 New activity';
          trendEl.className = 'fb-stat-trend up';
        } else {
          var diff = cur - prev;
          var pctChg = Math.round(Math.abs(diff / prev) * 100);
          if (diff > 0) {
            trendEl.textContent = '\u2191 ' + pctChg + '% vs prev 30d';
            trendEl.className = 'fb-stat-trend up';
          } else if (diff < 0) {
            trendEl.textContent = '\u2193 ' + pctChg + '% vs prev 30d';
            trendEl.className = 'fb-stat-trend down';
          } else {
            trendEl.textContent = 'Same as prev 30d';
            trendEl.className = 'fb-stat-trend flat';
          }
        }
      }

      // Charts
      _renderDonutChart(data.by_type, total);
      _renderBarChart(data.trend_data || []);
    })
    .catch(function() {});
}

function _setText(id, val) {
  var el = document.getElementById(id);
  if (el) el.textContent = (val !== null && val !== undefined) ? val : '—';
}

// ── Donut Chart ───────────────────────────────────────────────────────────────

function _renderDonutChart(byType, total) {
  var canvas = document.getElementById('fbDonutChart');
  if (!canvas || typeof Chart === 'undefined') return;

  var counts = [
    byType.issue || 0,
    byType.improvement || 0,
    byType.praise || 0,
    byType.other || 0,
    byType.unset || 0,
  ];
  var colors = ['#ef4444', '#3b82f6', '#22c55e', '#8b5cf6', '#9ca3af'];
  var labels = ['Issue', 'Improvement', 'Praise', 'Other', 'Uncategorized'];

  if (_fbDonutChart) { _fbDonutChart.destroy(); _fbDonutChart = null; }

  _fbDonutChart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: counts,
        backgroundColor: colors,
        borderWidth: 2,
        borderColor: '#fff',
        hoverOffset: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              var n = ctx.raw || 0;
              var pct = total > 0 ? Math.round((n / total) * 100) : 0;
              return ctx.label + ': ' + n + ' (' + pct + '%)';
            }
          }
        }
      }
    }
  });

  // Legend
  var legendEl = document.getElementById('fbDonutLegend');
  if (!legendEl) return;
  legendEl.innerHTML = labels.map(function(lbl, i) {
    if (!counts[i]) return '';
    var pct = total > 0 ? Math.round((counts[i] / total) * 100) : 0;
    return '<div class="feedback-donut-legend-item">' +
      '<div class="feedback-donut-legend-swatch" style="background:' + colors[i] + '"></div>' +
      '<span>' + lbl + '</span>' +
      '<span class="feedback-donut-legend-count">' + counts[i] + ' <span style="color:#9ca3af;font-weight:400">(' + pct + '%)</span></span>' +
      '</div>';
  }).join('');
}

// ── Bar Chart ─────────────────────────────────────────────────────────────────

function _renderBarChart(trendData) {
  var canvas = document.getElementById('fbBarChart');
  if (!canvas || typeof Chart === 'undefined') return;

  // Fill in missing days in last 30
  var filled = _fillDays(trendData, 30);

  if (_fbBarChart) { _fbBarChart.destroy(); _fbBarChart = null; }

  _fbBarChart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: filled.map(function(d) {
        var dt = new Date(d.date + 'T00:00:00');
        return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      }),
      datasets: [{
        label: 'Submissions',
        data: filled.map(function(d) { return d.count; }),
        backgroundColor: 'rgba(245,158,11,0.7)',
        borderColor: '#f59e0b',
        borderWidth: 1,
        borderRadius: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: function(items) {
              var idx = items[0].dataIndex;
              return new Date(filled[idx].date + 'T00:00:00').toLocaleDateString('en-US', {
                weekday: 'short', month: 'short', day: 'numeric'
              });
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            font: { size: 10 },
            maxRotation: 45,
            autoSkip: true,
            maxTicksLimit: 10,
          }
        },
        y: {
          beginAtZero: true,
          ticks: { stepSize: 1, font: { size: 11 } },
          grid: { color: '#f3f4f6' }
        }
      }
    }
  });
}

function _fillDays(trendData, days) {
  var map = {};
  (trendData || []).forEach(function(d) { map[d.date] = d.count; });
  var result = [];
  for (var i = days - 1; i >= 0; i--) {
    var dt = new Date();
    dt.setDate(dt.getDate() - i);
    var key = dt.toISOString().slice(0, 10);
    result.push({ date: key, count: map[key] || 0 });
  }
  return result;
}

// ── List ──────────────────────────────────────────────────────────────────────

function loadFeedbackList(page) {
  _fbPage = page || _fbPage || 1;

  var params = new URLSearchParams();
  if (_fbTypeFilter) params.set('type', _fbTypeFilter);
  var from = document.getElementById('fbFilterFrom');
  var to   = document.getElementById('fbFilterTo');
  var user = document.getElementById('fbFilterUser');
  if (from && from.value) params.set('date_from', from.value);
  if (to   && to.value)   params.set('date_to',   to.value);
  if (user && user.value) params.set('user', user.value.trim());
  params.set('page', _fbPage);
  params.set('per_page', 50);

  var listEl = document.getElementById('fbList');
  if (listEl) listEl.innerHTML = '<div class="feedback-empty"><i class="fa-solid fa-spinner fa-spin fa-lg"></i><br><br>Loading…</div>';

  fetch('/admin/api/feedback?' + params.toString())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.success) {
        if (listEl) listEl.innerHTML = '<div class="feedback-empty"><i class="fa-solid fa-circle-exclamation"></i><br>' + escapeHtml(data.error || 'Error loading feedback') + '</div>';
        return;
      }
      _renderFeedbackTable(data.feedback || []);
      _renderPagination(data.page, data.pages, data.total);
    })
    .catch(function(err) {
      if (listEl) listEl.innerHTML = '<div class="feedback-empty"><i class="fa-solid fa-circle-exclamation"></i><br>Network error: ' + escapeHtml(String(err)) + '</div>';
    });
}

function _renderFeedbackTable(items) {
  var listEl = document.getElementById('fbList');
  if (!listEl) return;

  if (!items.length) {
    listEl.innerHTML = '<div class="feedback-empty"><i class="fa-regular fa-comment"></i><br>No feedback found matching your filters.</div>';
    return;
  }

  var rows = items.map(function(fb) {
    var meta = _fbTypeMeta(fb.feedback_type);
    var badge = '<span class="feedback-type-badge ' + meta.badge + '">' +
      '<i class="fa-solid ' + meta.icon + '"></i> ' + meta.label + '</span>';
    var preview = (fb.content || '').replace(/[\r\n]+/g, ' ').slice(0, 100);
    if ((fb.content || '').length > 100) preview += '…';
    return '<tr>' +
      '<td style="color:#9ca3af;font-size:12px;">#' + fb.id + '</td>' +
      '<td style="font-weight:500;">' + escapeHtml(fb.username) + '</td>' +
      '<td>' + badge + '</td>' +
      '<td class="feedback-content-preview" title="' + escapeHtml(fb.content || '') + '">' + escapeHtml(preview) + '</td>' +
      '<td style="white-space:nowrap;font-size:12px;color:#6b7280;">' + _fmtDateTimeFb(fb.created_at) + '</td>' +
      '<td><button class="action-icon" onclick="viewFeedbackDetail(' + fb.id + ')" title="View full feedback"><i class="fa-solid fa-eye"></i></button></td>' +
      '</tr>';
  }).join('');

  listEl.innerHTML = '<table>' +
    '<thead><tr>' +
    '<th>#</th><th>User</th><th>Type</th><th>Content</th><th>Submitted</th><th></th>' +
    '</tr></thead>' +
    '<tbody>' + rows + '</tbody>' +
    '</table>';
}

function _renderPagination(page, pages, total) {
  var pag  = document.getElementById('fbPagination');
  var prev = document.getElementById('fbPagePrev');
  var next = document.getElementById('fbPageNext');
  var info = document.getElementById('fbPageInfo');

  if (!pag) return;
  pag.style.display = pages > 1 ? 'flex' : 'none';
  if (prev) prev.disabled = (page <= 1);
  if (next) next.disabled = (page >= pages);
  if (info) info.textContent = 'Page ' + page + ' of ' + pages + ' (' + total + ' total)';
  _fbPage = page;
}

// ── Type filter pills ─────────────────────────────────────────────────────────

function _initFbTypePills() {
  var container = document.getElementById('fbTypePills');
  if (!container) return;
  container.querySelectorAll('.fb-filter-pill').forEach(function(pill) {
    pill.addEventListener('click', function() {
      container.querySelectorAll('.fb-filter-pill').forEach(function(p) { p.classList.remove('active'); });
      pill.classList.add('active');
      _fbTypeFilter = pill.dataset.type || '';
      loadFeedbackList(1);
    });
  });
}

function resetFeedbackFilters() {
  _fbTypeFilter = '';
  var from = document.getElementById('fbFilterFrom');
  var to   = document.getElementById('fbFilterTo');
  var user = document.getElementById('fbFilterUser');
  if (from) from.value = '';
  if (to)   to.value   = '';
  if (user) user.value = '';
  var container = document.getElementById('fbTypePills');
  if (container) {
    container.querySelectorAll('.fb-filter-pill').forEach(function(p) { p.classList.remove('active'); });
    var allPill = container.querySelector('[data-type=""]');
    if (allPill) allPill.classList.add('active');
  }
  loadFeedbackList(1);
}

// ── Detail Modal ──────────────────────────────────────────────────────────────

function viewFeedbackDetail(id) {
  var modal = document.getElementById('feedbackDetailModal');
  var body  = document.getElementById('fbDetailBody');
  var title = document.getElementById('fbDetailTitle');
  if (!modal) return;
  if (title) title.innerHTML = '<i class="fa-solid fa-comment-dots"></i> Feedback #' + id;
  if (body)  body.innerHTML  = '<div class="modal-loading"><i class="fa-solid fa-spinner fa-spin fa-lg"></i></div>';
  modal.style.display = 'flex';

  fetch('/admin/api/feedback/' + id)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.success) {
        if (body) body.innerHTML = '<p style="color:#ef4444">' + escapeHtml(data.error || 'Error') + '</p>';
        return;
      }
      if (body) body.innerHTML = _renderFbDetail(data.item);
    })
    .catch(function(err) {
      if (body) body.innerHTML = '<p style="color:#ef4444">Network error: ' + escapeHtml(String(err)) + '</p>';
    });
}

function _renderFbDetail(item) {
  var meta = _fbTypeMeta(item.feedback_type);
  var badge = '<span class="feedback-type-badge ' + meta.badge + '">' +
    '<i class="fa-solid ' + meta.icon + '"></i> ' + meta.label + '</span>';

  return '<div class="user-detail-section">' +
    '<h4>Submission Details</h4>' +
    '<div class="user-info-row"><span class="user-info-label">Feedback #</span><span class="user-info-value">' + item.id + '</span></div>' +
    '<div class="user-info-row"><span class="user-info-label">User</span><span class="user-info-value">' + escapeHtml(item.username) + '</span></div>' +
    '<div class="user-info-row"><span class="user-info-label">Email</span><span class="user-info-value">' + escapeHtml(item.email) + '</span></div>' +
    '<div class="user-info-row"><span class="user-info-label">Type</span><span class="user-info-value">' + badge + '</span></div>' +
    '<div class="user-info-row"><span class="user-info-label">Submitted</span><span class="user-info-value">' + _fmtDateTimeFb(item.created_at) + '</span></div>' +
    '</div>' +
    '<div class="user-detail-section" style="margin-top:16px;">' +
    '<h4>Message</h4>' +
    '<div class="feedback-detail-content">' + escapeHtml(item.content) + '</div>' +
    '</div>';
}

function closeFeedbackDetailModal() {
  var modal = document.getElementById('feedbackDetailModal');
  if (modal) modal.style.display = 'none';
}

// ── Tab activation ────────────────────────────────────────────────────────────

var _fbPillsInited = false;

(function() {
  var _origSwitch = window.switchTab;
  window.switchTab = function(tab) {
    if (_origSwitch) _origSwitch(tab);
    if (tab === 'feedback') {
      if (!_fbPillsInited) {
        _fbPillsInited = true;
        _initFbTypePills();
      }
      // Always reload — so data is fresh every time you visit the tab
      _fbPage = 1;
      loadFeedbackStats();
      loadFeedbackList(1);
    }
  };
})();
