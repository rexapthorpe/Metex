# Final Manual Staging Checklist — Metex Payments

> Last updated: 2026-03-26
> Run all scenarios on staging (test Stripe keys) before production cutover.
> Use Stripe test cards: https://stripe.com/docs/testing#cards

---

## Scenario Index

| # | Scenario | Risk Level |
|---|---|---|
| S1 | Standard card checkout (new card) | Medium |
| S2 | Saved card checkout | High |
| S3 | 3DS checkout | High |
| S4 | ACH checkout | High |
| S5 | Bid acceptance — success | Critical |
| S6 | Bid acceptance — payment failure | Critical |
| S7 | Partial-fill bid acceptance | Critical |
| S8 | Strike threshold blocking | High |
| S9 | Tracking upload + payout countdown | High |
| S10 | Manual payout release | High |
| S11 | Refund before payout | High |
| S12 | Refund after payout + recovery | Critical |

---

## S1 — Standard Card Checkout (New Card)

**Risk:** Webhook not received → order never marked paid; buyer charged but order stuck.

**Setup:**
- One active listing with quantity ≥ 1.
- Buyer account with no saved cards.
- Seller account with completed Stripe Express onboarding.

**Steps:**
1. Log in as buyer.
2. Add listing to cart.
3. Go to `/checkout`. Enter `4242 4242 4242 4242`, exp `12/34`, CVC `123`.
4. Submit. Browser redirects to `/order-success`.
5. Wait up to 10 seconds for webhook delivery (check app logs).

**Expected Buyer:** Redirect to `/order-success`. Notification: order confirmed.

**Expected Seller:** Order appears in Sold tab with status `paid` or `awaiting_shipment`.

**Expected Admin:** Ledger tab shows new order with `payment_status = paid`, `stripe_payment_intent_id` set, `paid_at` set.

**Expected Stripe:** Dashboard → Payments: charge `succeeded`. Dashboard → Webhooks: `payment_intent.succeeded` event → 200 response.

**Pass:** [ ] / **Fail:** [ ]

**Notes:**
_______________________________________________

---

## S2 — Saved Card Checkout

**Risk:** IDOR — buyer uses another user's saved PM. PM ownership check must fire.

**Setup:**
- Buyer has a saved card (run S1 first and save the card, or add via `/account`).
- One active listing in cart.

**Steps:**
1. Log in as buyer.
2. Add listing to cart. Go to `/checkout`.
3. Select the saved card from the dropdown (not entering new card details).
4. Submit. Confirm redirect to `/order-success`.

**Expected Buyer:** Order confirmed without re-entering card details.

**Expected Seller:** Same as S1.

**Expected Admin:** Same as S1. `payment_method_type = 'card'`, `requires_payment_clearance = 0`.

**Expected Stripe:** Charge against the saved `pm_...` PaymentMethod ID. `payment_intent.succeeded` webhook → 200.

**Pass:** [ ] / **Fail:** [ ]

**Negative test — IDOR:**
1. Log in as Buyer A.
2. Directly POST to `/account/api/payment-methods/<pm_id_of_buyer_B>/detach`.
3. Expected: 403 (if Stripe customer ID is present on both users) or 404 (no customer → PM not found).

**IDOR Pass:** [ ] / **Fail:** [ ]

**Notes:**
_______________________________________________

---

## S3 — 3DS Checkout (SCA Authentication)

**Risk:** 3DS challenge is shown; if app doesn't handle redirect, buyer is charged but order is stuck.

**Setup:**
- Buyer account with no saved cards.
- One active listing in cart.
- Use Stripe test card that requires authentication: `4000 0027 6000 3184`

**Steps:**
1. Log in as buyer. Add listing to cart. Go to `/checkout`.
2. Enter 3DS test card `4000 0027 6000 3184`, exp `12/34`, CVC `123`.
3. Submit. Stripe shows a 3DS authentication challenge modal/page.
4. Click "Complete authentication" in the test modal.
5. Browser should redirect to `/order-success`.

**Expected Buyer:** 3DS challenge shown → after authentication → redirect to `/order-success`.

**Expected Seller:** Same as S1 — order visible once webhook fires.

**Expected Admin:** Order marked paid after webhook. `payment_method_type = 'card'`.

**Expected Stripe:** PI status goes `requires_action` → `succeeded` after authentication. Webhook fires `payment_intent.succeeded`.

**Pass:** [ ] / **Fail:** [ ]

**Negative test — 3DS declined:**
1. Repeat with card `4000 0000 0000 9979` (3DS required, authentication will fail).
2. Click "Fail authentication" in the test modal.
3. Expected: buyer sees an error page or is redirected back to checkout with an error message. Order should NOT be marked paid. No charge in Stripe.

**3DS declined Pass:** [ ] / **Fail:** [ ]

**Notes:**
_______________________________________________

---

## S4 — ACH Checkout

**Risk:** ACH sets `requires_payment_clearance = 1`. If this flag is wrong, payout goes out before ACH clears.

**Setup:**
- Buyer account with no saved cards.
- One active listing in cart.
- Stripe test bank: routing `110000000`, account `000123456789`

**Steps:**
1. Log in as buyer. Add listing to cart. Go to `/checkout`.
2. Select ACH/bank transfer as payment method.
3. Enter Stripe test bank details.
4. Submit. Confirm page redirects (ACH confirmation may not be instant).
5. In Stripe Dashboard (test mode), manually confirm the ACH payment to trigger `payment_intent.succeeded`.

**Expected Buyer:** Order visible in account with status indicating bank processing.

**Expected Seller:** Order appears but payout is NOT released (ACH clearance required).

**Expected Admin:** Ledger shows `payment_method_type = 'us_bank_account'`, `requires_payment_clearance = 1`. Payout block reason: "ACH payment — awaiting bank clearance". Payout state: NOT eligible for auto-release.

**Expected Stripe:** PI type `us_bank_account`. Webhook fires `payment_intent.succeeded`.

**Pass:** [ ] / **Fail:** [ ]

**Notes:**
_______________________________________________

---

## S5 — Bid Acceptance — Success

**Risk:** Charge fails silently; payout fires before charge confirmed; seller receives funds for uncharged bid.

**Setup:**
- Buyer A has a placed bid with `bid_payment_method_id` set (requires Stripe saved card).
- Seller A has Stripe Express onboarding complete.
- Buyer A's saved card is `4242 4242 4242 4242` (always succeeds).

**Steps:**
1. Log in as Seller A.
2. Navigate to the bucket → bid management.
3. Select Buyer A's bid → click Accept → confirm.

**Expected Buyer:** Payment charged off-session. Notification: "Your bid was accepted and payment processed."

**Expected Seller:** Bid marked `status = 'Filled'`. Order created. Payout pending.

**Expected Admin:** `orders` row with `stripe_payment_intent_id` set. `bid_payment_status = 'charged'` on the bid. Order in Ledger.

**Expected Stripe:** PI created with `off_session=True`, `metadata.source = 'bid_acceptance'`. `succeeded` immediately (no 3DS for test card).

**Pass:** [ ] / **Fail:** [ ]

**Notes:**
_______________________________________________

---

## S6 — Bid Acceptance — Payment Failure

**Risk:** Failed charge left as `'charged'` permanently blocking future acceptance; or strikes not recorded; or buyer not notified.

**Setup:**
- Buyer A has a placed bid with `bid_payment_method_id` set.
- Buyer A's saved card is Stripe test decline card: `4000 0000 0000 0002` (always declines).

**Steps:**
1. Log in as Seller A.
2. Accept Buyer A's bid.

**Expected Buyer:** Payment declined. `bid_payment_status = 'failed'`. `bid_payment_strikes` incremented by 1. Notification: bid payment failed.

**Expected Seller:** Flash message: payment failed, bid was not filled.

**Expected Admin:** Bid record shows `bid_payment_status = 'failed'`, `bid_payment_failure_code` set (e.g., `card_declined`), `bid_payment_failure_message` set.

**Expected Stripe:** PI created, `status = 'requires_payment_method'` or `CardError` raised. No charge.

**Pass:** [ ] / **Fail:** [ ]

**Strike accumulation test:**
- Repeat this scenario 3 times with the same buyer (3 separate bids, all fail).
- After 3rd failure: buyer's `bid_payment_strikes = 3`.
- Attempt to place a new bid as that buyer. Expected: blocked with "Too many payment failures" message.

**Strike block Pass:** [ ] / **Fail:** [ ]

**Notes:**
_______________________________________________

---

## S7 — Partial-Fill Bid Acceptance

**Risk:** After partial fill, `bid_payment_status` left as `'charged'` blocks a second seller from accepting remaining quantity. (Bug was present; fixed in this codebase.)

**Setup:**
- Buyer places bid for **quantity = 3**.
- Seller A has only **quantity = 1** available.
- Seller B has **quantity = 2** available.
- Both sellers have Stripe Express onboarding complete.

**Steps:**
1. Log in as Seller A. Accept 1 unit of the bid.
2. Verify acceptance succeeds. Charge fires for 1 unit.
3. Check DB: `bids.remaining_quantity = 2`, `bids.status = 'Partially Filled'`, `bids.bid_payment_status = 'pending'`, `bids.bid_payment_intent_id = NULL`.
4. Log in as Seller B. Accept the remaining 2 units.
5. Verify second acceptance succeeds. Charge fires for 2 units.
6. Check DB: `bids.status = 'Filled'`, `bids.remaining_quantity = 0`.

**Expected Buyer:** Charged twice (once per acceptance). Both charges succeed.

**Expected Seller A:** Order created for 1 unit. Payout pending.

**Expected Seller B:** Order created for 2 units. Payout pending.

**Expected Admin:** Two orders in Ledger, each linked to the same bid. Correct platform fee snapshots on each.

**Expected Stripe:** Two separate PIs. `metadata.bid_id` same on both. `metadata.source = 'bid_acceptance'`.

**Pass:** [ ] / **Fail:** [ ]

**Notes:**
_______________________________________________

---

## S8 — Strike Threshold Blocking

**Risk:** Buyer with 3 strikes places a new bid; strike check bypassed at bid submission.

**Setup:**
- Buyer with `bid_payment_strikes = 3` in DB (set directly or via repeated failures in S6).

**Steps:**
1. Log in as strike-threshold buyer.
2. Navigate to a bucket. Click "Place Bid."
3. Fill in bid form. Submit.

**Expected Buyer:** Error: blocked from placing bid. No bid row created in DB.

**Expected Seller:** No new bid appears on their bucket.

**Expected Admin:** No bid row for this attempt in the DB.

**Expected Stripe:** No Stripe calls made.

**Pass:** [ ] / **Fail:** [ ]

**Notes:**
_______________________________________________

---

## S9 — Tracking Upload + Payout Countdown

**Risk:** Payout releases before tracking is uploaded; or countdown calculates from wrong timestamp.

**Setup:**
- A paid order (from S1 or S5) in `status = 'paid'` or `awaiting_shipment`.
- Seller account with Stripe Express complete.

**Steps:**
1. Log in as Seller. Navigate to Sold tab.
2. Upload a tracking number for the order.
3. Record the exact timestamp of upload.
4. Check DB: `orders.tracking_uploaded_at` is set. `payout_status = 'not_ready_for_payout'`.
5. Verify payout is NOT released immediately.
6. (In staging, manually advance the date or set `tracking_uploaded_at` to 3 days ago in DB.)
7. Check payout eligibility: `is_order_payout_eligible(order)` should return True for card after 2 days.

**Expected Seller:** Payout status transitions correctly once delay window passes.

**Expected Admin:** Can see `tracking_uploaded_at` and payout countdown in Ledger. Payout status moves from `not_ready_for_payout` → `PAYOUT_READY` after delay.

**Expected Stripe:** No transfer yet.

**Pass:** [ ] / **Fail:** [ ]

**Notes:**
_______________________________________________

---

## S10 — Manual Payout Release

**Risk:** Transfer sent to wrong connected account; or double-transfer to same seller; or transfer ignores platform fee.

**Setup:**
- A card-paid order past the 2-day delay window (tracking uploaded, delay elapsed).
- Payout status = `PAYOUT_READY` or `PAYOUT_SCHEDULED`.
- Seller with valid Stripe Express account.

**Steps:**
1. Log in as Admin. Navigate to Admin Dashboard → Ledger tab.
2. Find the eligible order. Click "Release Payout."
3. Confirm payout release.

**Expected Buyer:** No change.

**Expected Seller:** Stripe transfer appears in their connected account. Amount = gross_amount minus platform fee (based on fee_value snapshotted at order creation).

**Expected Admin:** `payout_status = 'PAID_OUT'`. Event logged. Cannot release again (double-payout blocked).

**Expected Stripe:** `stripe.Transfer.create` with `destination = seller.stripe_account_id`. Amount in cents. Transfer ID recorded in DB.

**Pass:** [ ] / **Fail:** [ ]

**Double-payout test:**
1. After payout is `PAID_OUT`, attempt to release again via admin action.
2. Expected: `EscrowControlError` raised. No second transfer in Stripe. Admin sees error message.

**Double-payout block Pass:** [ ] / **Fail:** [ ]

**Notes:**
_______________________________________________

---

## S11 — Refund Before Payout

**Risk:** Refund is processed but payout still goes out; or refund changes order to wrong terminal state.

**Setup:**
- A paid order (card) where payout has NOT been released (`payout_status = 'not_ready_for_payout'`).
- Order in `PAID_IN_ESCROW` or `AWAITING_SHIPMENT` status.

**Steps:**
1. Log in as Admin. Navigate to Admin Dashboard → Ledger.
2. Find the order. Click "Refund" → select "Full refund" → enter reason → confirm.
3. Verify order status transitions to `REFUNDED`.

**Expected Buyer:** Stripe refund issued. Balance credit on card within 5–10 business days. Notification sent.

**Expected Seller:** Payout cancelled (`payout_status = 'PAYOUT_CANCELLED'`). No transfer.

**Expected Admin:** Order status = `REFUNDED`. `refund_status` set. Event logged with admin ID and reason. Cannot refund again (terminal state).

**Expected Stripe:** `stripe.Refund.create` against the original PI. Refund visible in Dashboard → Payments.

**Pass:** [ ] / **Fail:** [ ]

**Notes:**
_______________________________________________

---

## S12 — Refund After Payout + Recovery

**Risk:** Refund attempted on an already-paid-out order. `PAID_OUT` must block standard refund path. Admin must handle manually via recovery workflow.

**Setup:**
- A paid order where payout HAS been released (`payout_status = 'PAID_OUT'`).
- Order in `COMPLETED` or `SHIPPED` status.

**Steps:**
1. Log in as Admin. Navigate to Admin Dashboard → Ledger.
2. Find the order with `payout_status = 'PAID_OUT'`.
3. Attempt standard "Full refund" action.
4. Expected: Error — "Cannot refund: Payout for seller X is PAID_OUT."
5. Admin must initiate a recovery path: reverse the transfer manually in Stripe Dashboard (`stripe.Transfer.reverse`) then process the refund separately.

**Expected Buyer:** Standard refund path blocked with clear error. Manual recovery required via admin.

**Expected Seller:** No automatic action. Admin initiates transfer reversal in Stripe Dashboard directly.

**Expected Admin:** Attempt fails with descriptive error. `requires_payout_recovery` flag should be set on the order to signal this condition. Admin resolves via Stripe Dashboard manually.

**Expected Stripe:** No automatic reversal from the app. Admin manually reverses the transfer in Stripe Dashboard.

**Pass:** [ ] / **Fail:** [ ]

**Special care note:** This scenario has NO automated recovery path in the current codebase. The `process_refund()` function raises `EscrowControlError` when a payout is `PAID_OUT`. The admin must handle via Stripe Dashboard + manual DB update. Consider adding a formal recovery flow before scaling to high volume.

**Notes:**
_______________________________________________

---

## Pre-Launch Sign-Off

| Area | Tested by | Date | Result |
|---|---|---|---|
| S1 — Standard card checkout | | | |
| S2 — Saved card checkout + IDOR | | | |
| S3 — 3DS success + 3DS declined | | | |
| S4 — ACH checkout | | | |
| S5 — Bid acceptance success | | | |
| S6 — Bid acceptance failure + strikes | | | |
| S7 — Partial-fill bid acceptance | | | |
| S8 — Strike threshold blocking | | | |
| S9 — Tracking upload + countdown | | | |
| S10 — Manual payout + double-payout block | | | |
| S11 — Refund before payout | | | |
| S12 — Refund after payout (recovery path) | | | |

**Ready for production cutover:** [ ] Yes / [ ] No

**Signed off by:** _____________________________ **Date:** ___________
