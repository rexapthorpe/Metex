# Metex Payments — Staging Test Checklist

Use Stripe test mode keys and test card numbers throughout.
Mark each scenario PASS / FAIL / BLOCKED in the result column.

---

## Scenario 1 — Normal Checkout with New Card

**Steps**
1. Log in as a buyer with no saved cards.
2. Add one or more listings to cart. Proceed to checkout.
3. Confirm shipping address at Step 1.
4. At Step 2 (Payment), verify the Stripe Payment Element renders (no saved-card picker shown).
5. Enter Stripe test card `4242 4242 4242 4242`, any future expiry, any CVC.
6. Advance to Step 3 (Review) and click Place Order.
7. Confirm redirect to `/order-success`.

**Expected Result**
- Order created in DB with `payment_status = 'paid'`.
- `stripe_payment_intent_id` stored on the order.
- Seller sees order in Sold tab with payout state "Waiting for shipment".
- Admin ledger shows order with Payment Method = "Card".
- Webhook `payment_intent.succeeded` fires and is idempotent if replayed.

**Result** `[ ] PASS  [ ] FAIL  [ ] BLOCKED`
**Notes**

---

## Scenario 2 — Normal Checkout with Saved Card

**Steps**
1. Log in as a buyer who has previously completed a checkout (saved card should exist).
2. Navigate to `/account` → Payment Methods. Confirm at least one saved card is listed.
3. Add items to cart. Proceed to checkout.
4. At Step 2, verify the saved card picker renders and the saved card is pre-selected.
5. Do NOT select "Use a new card". Click Continue.
6. At Step 3, click Place Order.
7. Confirm redirect to `/order-success`.

**Expected Result**
- Order completes without mounting the Stripe Payment Element.
- Stripe `confirmPayment` is called with `payment_method: <pm_id>` and `redirect: 'if_required'`.
- `payment_status = 'paid'` on the order.
- If card requires 3DS: Stripe handles redirect automatically and buyer returns to `/order-success`.
- If saved card is declined: error message appears in step 3 with a "Change payment method" link that returns to step 2.

**Result** `[ ] PASS  [ ] FAIL  [ ] BLOCKED`
**Notes**

---

## Scenario 3 — ACH Checkout and Clearance

**Steps**
1. Log in as a buyer. Add items to cart. Proceed to checkout.
2. At Step 2, select the "Bank account (ACH)" option in the Stripe Payment Element.
3. Use Stripe test bank account credentials to authorize the transfer.
4. Complete checkout. Confirm redirect to `/order-success`.
5. In DB: verify `orders.payment_method_type = 'us_bank_account'` and `requires_payment_clearance = 1`.
6. Check seller's Sold tab → payout bar should show **"Waiting for ACH clearance"** (blue).
7. Check admin Ledger → order detail. Verify:
   - Payment Method header shows **"ACH / Bank Transfer"** (not "card").
   - Yellow ACH clearance banner is visible with "Mark ACH Cleared" button.
8. Click "Mark ACH Cleared" as admin.
9. Verify seller payout state transitions to "Waiting for shipment" or the delay window state.

**Expected Result**
- `payment_method_type` is set by webhook (not hardcoded).
- Seller never sees "Processing" or "Card" for an ACH order.
- Admin can clear ACH and unblock the payout pipeline.
- Admin ledger list shows "ACH / Bank" in the Payment Method column.

**Result** `[ ] PASS  [ ] FAIL  [ ] BLOCKED`
**Notes**

---

## Scenario 4 — Bid Placement and Seller Acceptance Payment

**Steps**
1. Log in as a buyer. Navigate to a listing's bucket page.
2. Attempt to place a bid without a saved card. Confirm the UI shows a "Payment Method Required" message and blocks bid submission.
3. Add a saved card (via `/account` → Payment Methods → Add Card).
4. Place a bid with a fixed price below the current ask.
5. Log in as the seller. Navigate to the matching bucket. Find the bid in the bid list.
6. Click Accept on the bid. Confirm the acceptance modal flow.
7. Confirm the acceptance POST succeeds and an order is created.
8. Verify: `bid.bid_payment_status = 'charged'`, `bid.status = 'Filled'`, order exists.
9. Verify: buyer receives a bid-accepted notification.

**Expected Result**
- Bid can only be placed with a saved card on file.
- Seller acceptance charges the buyer's saved card via Stripe PaymentIntent.
- Stripe idempotency key (`bid-accept-<bid_id>-<order_id>`) prevents double-charge.
- Order appears in buyer's orders and seller's Sold tab.

**Result** `[ ] PASS  [ ] FAIL  [ ] BLOCKED`
**Notes**

---

## Scenario 5 — Failed Bid Payment and Strike Enforcement

**Steps**
1. Log in as a buyer. Save Stripe test card `4000 0000 0000 0002` (always declines).
2. Place a bid. Log in as seller and accept the bid.
3. Verify acceptance fails with a payment declined message in the modal.
4. Verify: `bid.status = 'Payment Failed'`, `bid.active = 0`, `bid.bid_payment_status = 'failed'`.
5. Verify: buyer's account tab (Bids) shows the bid with a red "Payment Failed" badge.
6. Verify: buyer receives a bid payment failed in-app notification.
7. Verify: seller sees a styled "Payment Failed" modal (not a browser `alert()`), with a "Back to Bids" button.
8. Check buyer's `bid_payment_strikes` incremented by 1.
9. Repeat for a total of 3 card-decline failures on the same buyer account.
10. Attempt a fourth bid. Confirm the UI shows "Bid Placement Restricted" and blocks submission.

**Expected Result**
- Each card decline: bid permanently closed, seller notified, buyer notified, strike incremented.
- Network errors or non-card errors do NOT increment strikes.
- At 3 strikes: bid placement is blocked with a clear message.
- Failed bids cannot be re-accepted by the seller (guard in `accept_bid.py`).

**Result** `[ ] PASS  [ ] FAIL  [ ] BLOCKED`
**Notes**

---

## Scenario 6 — Seller Tracking Upload and Payout Delay Timing

**Steps**
1. Complete a checkout as a buyer (card payment). Wait for order to appear in seller Sold tab.
2. Verify initial payout state: "Waiting for shipment".
3. As seller: click Add Tracking, enter a tracking number and carrier.
4. Verify payout state changes to "Payout available in 2 days" (card = 2-day delay).
5. In DB: verify `seller_order_tracking.updated_at` is set to now.
6. In admin ledger: verify the Delay / Eligible At column shows correct eligible timestamp.
7. Advance system time past the 2-day window (or update `updated_at` directly in test DB to 3 days ago).
8. Run "Evaluate Readiness" in admin for the payout. Verify payout transitions to `PAYOUT_READY`.
9. Verify seller payout state now shows "Ready for payout".

**Expected Result**
- Delay is enforced based on `seller_order_tracking.updated_at`, not order date.
- Card orders: 2-day window. ACH orders: 5-day window.
- Readiness correctly transitions from NOT_READY → READY after window passes.
- Admin checklist shows all conditions green once window passes.

**Result** `[ ] PASS  [ ] FAIL  [ ] BLOCKED`
**Notes**

---

## Scenario 7 — Manual Payout Release (Admin)

**Steps**
1. Ensure a payout exists in `PAYOUT_READY` state (all conditions met: tracking uploaded, delay passed, Stripe connected, no refund).
2. Navigate to admin ledger → order detail.
3. Verify the Readiness Checklist column shows all green checkmarks.
4. Click "Release Payout". Verify the two-step confirmation strip appears (no browser `confirm()` dialog).
5. Click "Confirm Release".
6. Verify: Stripe transfer created, `payout_status = 'PAID_OUT'`, `provider_transfer_id` populated.
7. Verify: seller Sold tab shows payout state "Paid".
8. Now create a second payout that is blocked (e.g., tracking not uploaded). Verify "Release Payout" button does NOT appear — only a "Blocked: ..." message.

**Expected Result**
- Release button only appears when `get_payout_block_reason()` returns None (all conditions met).
- Two-step confirmation prevents accidental release.
- Backend independently re-validates before creating transfer.
- Manual payout respects `manual_payouts_enabled` system setting.

**Result** `[ ] PASS  [ ] FAIL  [ ] BLOCKED`
**Notes**

---

## Scenario 8 — Refund Before Payout / After Payout (Recovery)

### Part A — Refund before payout released

**Steps**
1. Complete a checkout. Verify order has `payment_status = 'paid'`.
2. Ensure payout is still in `PAYOUT_NOT_READY` or `PAYOUT_READY` (not yet PAID_OUT).
3. Admin: navigate to ledger order detail → Buyer Refund section. Click "Refund Buyer".
4. Enter a reason. Confirm.
5. Verify: Stripe refund created, `orders.refund_status = 'refunded'`.
6. Verify: payout transitions to `PAYOUT_CANCELLED`, `payout_recovery_status = 'not_needed'`.
7. Verify: seller's payout state shows "Payout cancelled".

**Expected Result**
- Refund and payout cancellation happen atomically.
- Seller never receives money for a refunded order.

### Part B — Refund after payout released

**Steps**
1. Complete a checkout. Release the payout to `PAID_OUT` (Stripe transfer created).
2. Admin: issue a refund for the same order.
3. Verify: `payout_recovery_status = 'pending'`, yellow "Payout Recovery Required" banner appears.
4. In admin Recovery cell: click "Attempt Recovery".
5. Verify one of three outcomes:
   - **Recovered**: `payout_recovery_status = 'recovered'`, `provider_reversal_id` stored.
   - **Manual Review**: seller had insufficient funds; admin sees purple "Manual Review" state.
   - **Failed**: red "Recovery Failed" state; retry button available.

**Expected Result**
- Recovery attempt uses `stripe.Transfer.create_reversal()`.
- All three outcome states are correctly stored and displayed.
- Manual review state surfaces a clear message that admin must follow up with seller.

**Result** `[ ] PASS  [ ] FAIL  [ ] BLOCKED`
**Notes**

---

## Pre-Test Environment Checklist

| Item | Status |
|------|--------|
| `STRIPE_PUBLISHABLE_KEY` set (test mode) | `[ ]` |
| `STRIPE_SECRET_KEY` set (test mode) | `[ ]` |
| `STRIPE_WEBHOOK_SECRET` set (test mode) | `[ ]` |
| Stripe webhook endpoint registered for `/webhook` | `[ ]` |
| At least one seller with `stripe_account_id` and `stripe_payouts_enabled=1` | `[ ]` |
| `manual_payouts_enabled` system setting = true | `[ ]` |
| `auto_payouts_enabled` system setting = true (for auto-run tests) | `[ ]` |
| `checkout_enabled` system setting = true | `[ ]` |

## Stripe Test Cards Reference

| Card Number | Behavior |
|-------------|----------|
| `4242 4242 4242 4242` | Always succeeds |
| `4000 0000 0000 0002` | Always declines (card_declined) |
| `4000 0025 0000 3155` | Requires 3DS authentication |
| `4000 0000 0000 9995` | Insufficient funds decline |
| Use Stripe test bank account | ACH / us_bank_account |
