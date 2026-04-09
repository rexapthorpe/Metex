/**
 * Column Info Popup — Admin Dashboard
 * =====================================
 * Lightweight click-to-open tooltip panels for column header "ⓘ" icons.
 * Used in: User Risk tab, Refunds tab.
 *
 * Public API
 * ----------
 *   colInfoIcon(key)          → HTML string: the <button> icon to embed in a <th>
 *   showColInfo(el, key)      → opens the popup for the given content key
 *   closeColInfo()            → closes any open popup
 *
 * To add a new column: add an entry to COL_INFO below.
 */

// ── Content definitions ───────────────────────────────────────────────────────

const COL_INFO = {

  // ── User Risk tab ───────────────────────────────────────────────────────────

  risk_score: `
    <h5><i class="fa-solid fa-arrow-up-right-dots" style="color:#dc2626;margin-right:5px;"></i>Risk Score</h5>
    <p>A number from <strong>0 to 100</strong> reflecting this user's overall risk level based on their dispute and refund history. Higher is riskier. The score is recomputed live from the database each time.</p>
    <hr class="col-info-divider">
    <p style="font-weight:600;margin-bottom:4px;">Formula</p>
    <div class="col-info-formula">score =
  (disputes opened as buyer)       × 4
+ (buyer disputes won/refunded)    × 10
+ (buyer disputes denied)          × 1
+ (disputes opened as seller)      × 3
+ (disputes upheld against seller) × 12
+ (refunds received — count)       × 8
+ min(refunds received — amount
      × 0.02, 20)

Capped at 100.</div>
    <hr class="col-info-divider">
    <p style="font-weight:600;margin-bottom:4px;">Auto-flag rules (180-day window)</p>
    <ul>
      <li>≥ 3 disputes opened as buyer → <strong>Watch</strong></li>
      <li>≥ 2 disputes upheld against seller → <strong>Watch</strong></li>
      <li>≥ $500 in refunds received → <strong>Watch</strong></li>
    </ul>
    <p style="color:#9ca3af;font-size:11px;margin-top:4px;">Auto-flag only reaches "Watch". Higher flags (Restricted, Suspended) are set manually.</p>`,

  risk_flag: `
    <h5><i class="fa-solid fa-flag" style="color:#ef4444;margin-right:5px;"></i>Manual Risk Flag</h5>
    <p>An admin-set status applied to users who require closer attention or restrictions. Does not change automatically above "Watch".</p>
    <hr class="col-info-divider">
    <div class="col-info-flag-row"><span class="risk-flag-badge risk-flag-none">None</span> Normal account. No restrictions.</div>
    <div class="col-info-flag-row"><span class="risk-flag-badge risk-flag-watch">Watch</span> Elevated concern — monitor closely. Can be set automatically by the risk system.</div>
    <div class="col-info-flag-row"><span class="risk-flag-badge risk-flag-restricted">Restricted</span> Admin-imposed limit (e.g. selling suspended). Set manually only.</div>
    <div class="col-info-flag-row"><span class="risk-flag-badge risk-flag-suspended">Suspended</span> Account fully suspended pending review. Set manually only.</div>`,

  risk_buyer_disputes: `
    <h5>Buyer Disputes</h5>
    <p>Total number of disputes this user has opened <strong>as a buyer</strong> — i.e. complaints about orders they purchased.</p>
    <p>Disputes count regardless of their outcome or current status.</p>
    <p style="color:#9ca3af;font-size:11px;">See the detail view for a breakdown: won vs. denied.</p>`,

  risk_seller_disputes: `
    <h5>Seller Disputes</h5>
    <p>Total number of disputes opened <strong>against this user as a seller</strong> — i.e. buyers complaining about their orders.</p>
    <p>Disputes upheld against the seller (buyer received a refund) carry the highest score weight (×12).</p>
    <p style="color:#9ca3af;font-size:11px;">See the detail view for a breakdown: upheld vs. other outcomes.</p>`,

  risk_refunds: `
    <h5>Refunds Issued</h5>
    <p>Refunds the user has <strong>received as a buyer</strong> — both the count and total USD amount.</p>
    <p>All current refunds are full-order refunds issued by an admin when resolving a dispute in the buyer's favor.</p>
    <p>Both the count (×8) and the amount (up to 20 points) contribute to the risk score.</p>`,

  risk_role: `
    <h5>Role</h5>
    <p>Derived from this user's order history — whether they have completed purchases, sales, or both.</p>
    <ul>
      <li><strong>Buyer</strong> — has at least one completed purchase</li>
      <li><strong>Seller</strong> — has at least one completed sale</li>
      <li><strong>Buyer + Seller</strong> — active on both sides</li>
      <li><strong>—</strong> — no completed orders yet</li>
    </ul>`,

  risk_joined: `
    <h5>Joined</h5>
    <p>The date this user's account was created. Accounts are displayed in the timezone of the server.</p>
    <p>Open the detail view to also see the user's last login time and IP address.</p>`,

  // ── Refunds tab ─────────────────────────────────────────────────────────────

  refund_id: `
    <h5>Refund ID</h5>
    <p>Internal auto-assigned identifier for this refund record. Unique across all refunds on the platform.</p>
    <p>Use this ID if you need to reference a specific refund in support conversations or audit logs.</p>`,

  refund_dispute: `
    <h5>Dispute</h5>
    <p>The dispute that this refund was issued for. Clicking the ID will take you to the Disputes tab.</p>
    <p>All current refunds are tied to a dispute — there is no standalone manual refund flow.</p>`,

  refund_order: `
    <h5>Order</h5>
    <p>The order that was refunded. This is the original purchase that the buyer disputed.</p>
    <p>Open the detail view to see the order's total value and status alongside the refund amount.</p>`,

  refund_buyer: `
    <h5>Buyer</h5>
    <p>The username of the buyer who <strong>received</strong> this refund. This is the user who opened the dispute.</p>`,

  refund_seller: `
    <h5>Seller</h5>
    <p>The username of the seller whose sale was refunded. This is the user against whom the dispute was resolved.</p>`,

  refund_amount: `
    <h5>Amount</h5>
    <p>The refund amount in <strong>USD ($)</strong>.</p>
    <p>Currently all refunds are <strong>full-order refunds</strong> — the entire order total is returned to the buyer via Stripe. Partial refunds are not yet supported.</p>
    <p>The amount is charged back to the seller's payout and returned to the buyer's original payment method.</p>`,

  refund_provider_id: `
    <h5>Provider Refund ID</h5>
    <p>The refund reference ID assigned by <strong>Stripe</strong> (e.g. <code>re_3Pxyz...</code>). This uniquely identifies the refund transaction within Stripe's system.</p>
    <p>Use this ID to look up the refund in the Stripe Dashboard if you need to verify processing status or resolve a payment dispute.</p>
    <p>If blank, the refund was recorded internally but Stripe was unavailable at the time — verify manually in the Stripe Dashboard.</p>`,

  refund_issued_by: `
    <h5>Issued By</h5>
    <p>The admin username who resolved the dispute and triggered this refund. Refunds are only created when an admin marks a dispute as "Resolved — Refund" in the Disputes tab.</p>
    <p>This field provides an audit trail for accountability.</p>`,

  refund_issued_at: `
    <h5>Issued At</h5>
    <p>The timestamp when this refund record was created — i.e. when the admin resolved the dispute. All times are server-local.</p>
    <p>Note: Stripe processes refunds asynchronously. The actual return of funds to the buyer's card may take 5–10 business days after this timestamp.</p>`,
};

// ── Popup engine ──────────────────────────────────────────────────────────────

let _colInfoEl = null;

/**
 * Open the info popup for the given content key, anchored near `triggerEl`.
 * Called via the onclick of colInfoIcon() buttons.
 */
function showColInfo(triggerEl, key) {
  closeColInfo();  // close any existing popup first

  const content = COL_INFO[key];
  if (!content) return;

  const popup = document.createElement('div');
  popup.className = 'col-info-popup';
  popup.setAttribute('role', 'tooltip');
  popup.style.top  = '-9999px';  // off-screen while we measure
  popup.style.left = '-9999px';
  popup.innerHTML  = `<button class="col-info-close" onclick="closeColInfo()" aria-label="Close">&times;</button>${content}`;
  document.body.appendChild(popup);
  _colInfoEl = popup;

  // Position: below and left-aligned to the trigger icon, clamped to viewport.
  const rect = triggerEl.getBoundingClientRect();
  const vw   = window.innerWidth;
  const vh   = window.innerHeight;

  // Read rendered dimensions
  const pw = popup.offsetWidth;
  const ph = popup.offsetHeight;

  let top  = rect.bottom + 6;
  let left = rect.left;

  // Clamp right edge
  if (left + pw > vw - 12) left = Math.max(8, vw - pw - 12);
  // Clamp bottom: if it would go off-screen, flip above
  if (top + ph > vh - 12) top = Math.max(8, rect.top - ph - 6);

  popup.style.top  = top  + 'px';
  popup.style.left = left + 'px';

  // Dismiss on outside click (deferred so current click doesn't immediately close it)
  setTimeout(() => {
    document.addEventListener('click', _colInfoOutsideClick, true);
    document.addEventListener('keydown', _colInfoEscape, true);
  }, 0);
}

function closeColInfo() {
  if (_colInfoEl) {
    _colInfoEl.remove();
    _colInfoEl = null;
  }
  document.removeEventListener('click', _colInfoOutsideClick, true);
  document.removeEventListener('keydown', _colInfoEscape,      true);
}

function _colInfoOutsideClick(e) {
  if (_colInfoEl && !_colInfoEl.contains(e.target)) {
    closeColInfo();
  }
}

function _colInfoEscape(e) {
  if (e.key === 'Escape') closeColInfo();
}

/**
 * Returns an HTML string for the info icon button to embed in a <th>.
 * @param {string} key - Key in COL_INFO
 */
function colInfoIcon(key) {
  // stopPropagation prevents the outside-click handler from firing on the same event
  return `<button class="col-info-btn" type="button" aria-label="Column info"
    onclick="event.stopPropagation(); showColInfo(this, '${key}')">
    <i class="fa-solid fa-circle-info"></i>
  </button>`;
}
