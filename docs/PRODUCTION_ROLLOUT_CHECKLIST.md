# Production Rollout Checklist — Metex Payments

> Last updated: 2026-03-26
> Complete every item before going live. Items are ordered by blast-radius (highest risk first).

---

## 1. Required Environment Variables

Set all of the following in your deployment environment (Render, Railway, etc.) before starting the app. The app hard-fails on startup if the Stripe keys are missing (`config.py` raises `EnvironmentError`).

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | YES | Flask session signing key. Must be random, ≥32 chars, kept secret. |
| `DATABASE_URL` | YES | PostgreSQL connection URL (`postgres://...`). Used by `database.py`. |
| `STRIPE_SECRET_KEY` | YES | Starts with `sk_live_...` in production. `sk_test_...` only in staging. |
| `STRIPE_PUBLISHABLE_KEY` | YES | Starts with `pk_live_...` in production. |
| `STRIPE_WEBHOOK_SECRET` | YES | `whsec_...` from Stripe Dashboard → Webhooks. Without this the webhook returns 500 and no orders will be marked paid. |
| `EMAIL_ADDRESS` | YES | Gmail address for transactional mail. |
| `EMAIL_PASSWORD` | YES | Gmail App Password (not your Google login password). |
| `GOOGLE_CLIENT_ID` | YES (if OAuth active) | From Google Cloud Console. |
| `GOOGLE_CLIENT_SECRET` | YES (if OAuth active) | From Google Cloud Console. |
| `METALPRICE_API_KEY` | YES | From metalpriceapi.com. App functions without it but spot prices will be stale. |
| `PRICE_LOCK_DURATION_SECONDS` | Optional | Default `10`. Increase to `30` for production if desired. |
| `SPOT_PRICE_CACHE_TTL_MINUTES` | Optional | Default `5`. Controls staleness tolerance. |
| `FLASK_TESTING` | MUST BE ABSENT | If set to `1`/`true`, Stripe key checks are bypassed. Never set in prod. |

**Verify:**
- [ ] `echo $STRIPE_SECRET_KEY` starts with `sk_live_`
- [ ] `echo $STRIPE_PUBLISHABLE_KEY` starts with `pk_live_`
- [ ] `echo $STRIPE_WEBHOOK_SECRET` starts with `whsec_`
- [ ] `echo $FLASK_TESTING` is empty or unset
- [ ] `echo $SECRET_KEY` is not the default fallback `'your-very-random-fallback-key-here'`

---

## 2. Stripe Live/Test Mode Checks

- [ ] Dashboard → Developers → toggle to **Live mode** (not test mode).
- [ ] Confirm `sk_live_` and `pk_live_` keys are from the **same** Stripe account.
- [ ] Confirm no `sk_test_` or `pk_test_` keys appear anywhere in the deployed environment.
- [ ] Stripe Dashboard → Payments → confirm the account currency is **USD**.
- [ ] Stripe Dashboard → Settings → Account details → confirm business name and country are correct.
- [ ] If using Radar fraud rules, confirm they are configured for live mode (test rules do not carry over).

---

## 3. Webhook Endpoint Verification

**App webhook route:** `POST /stripe/webhook` (CSRF-exempt, signature-verified)

**Stripe Dashboard setup:**
1. Navigate to: Developers → Webhooks → Add endpoint
2. URL: `https://yourdomain.com/stripe/webhook`
3. Events to listen for (minimum required):
   - `payment_intent.succeeded` — source of truth for order payment finalization
   - `account.updated` — optional, for real-time Connect account status sync
4. Copy the **Signing secret** (`whsec_...`) → set as `STRIPE_WEBHOOK_SECRET` env var

**Verify:**
- [ ] Webhook endpoint registered in Stripe Dashboard (live mode).
- [ ] `STRIPE_WEBHOOK_SECRET` is set and matches the Dashboard signing secret.
- [ ] Send a test event from Stripe Dashboard → your endpoint returns `{"received": true}` with 200.
- [ ] Check app logs: `[Stripe webhook] verified event type=payment_intent.succeeded` should appear.
- [ ] Webhook is NOT listening on a `stripe listen` local CLI forward (that is for dev only).

---

## 4. Connected Account Sanity Checks

Sellers must complete Stripe Express onboarding before they can accept bids or receive payouts.

**Verify for each test seller account:**
- [ ] Stripe Dashboard → Connect → Accounts: account exists with `type: express`.
- [ ] `charges_enabled: true` on the connected account.
- [ ] `payouts_enabled: true` on the connected account.
- [ ] `details_submitted: true` on the connected account.
- [ ] DB: `users.stripe_account_id` matches the account ID in Stripe Dashboard.
- [ ] DB: `users.stripe_charges_enabled = 1` and `users.stripe_payouts_enabled = 1`.

**Onboarding flow routes:**
- `GET /stripe/create-account` → creates Express account, saves `stripe_account_id`
- `GET /stripe/create-account-link` → generates AccountLink, redirects to Stripe
- `GET /stripe/return` → syncs `charges_enabled`, `payouts_enabled`, `onboarding_complete` from Stripe API
- `GET /stripe/refresh` → regenerates expired onboarding link

**Verify:**
- [ ] `return_url` in `AccountLink.create` resolves to `https://yourdomain.com/stripe/return` (not localhost).
- [ ] `refresh_url` in `AccountLink.create` resolves to `https://yourdomain.com/stripe/refresh`.

---

## 5. Payout Permission Checks

Payout eligibility rules (enforced by `services/payout_eligibility.py` and `core/services/ledger/escrow_control.py`):

| Condition | Payout Eligible? |
|---|---|
| `payment_status != 'paid'` | No |
| `payout_status != 'not_ready_for_payout'` (already processed or on hold) | No |
| `requires_payment_clearance = 1` (ACH) | No — requires explicit admin release |
| `payment_method_type = 'us_bank_account'` | No — ACH risk window |
| Card, fully paid, tracking uploaded, delay window elapsed | Yes |

**Payout delay windows** (from `ledger_constants.py`):
- Card: **2 days** after tracking upload (`PAYOUT_DELAY_DAYS_CARD = 2`)
- ACH: **5 days** after tracking upload + explicit admin release (`PAYOUT_DELAY_DAYS_ACH = 5`)

**Double-payout guard:** `PAID_OUT` is a terminal state with no valid transitions — `release_stripe_transfer` will raise `EscrowControlError` if called on a `PAID_OUT` payout.

**Verify:**
- [ ] Admin dashboard shows correct payout state machine (not_ready → ready → scheduled → in_progress → PAID_OUT).
- [ ] ACH orders show "ACH payment — awaiting bank clearance" block reason in admin dashboard.
- [ ] Admin can manually release ACH payout after clearance window.
- [ ] Double-payout is blocked: attempting to release a `PAID_OUT` payout returns an error (do not skip this test).
- [ ] Platform fee is snapshotted at order creation (changing bucket fee does not retroactively alter existing orders).

---

## 6. Rollback Plan

If a critical bug is discovered post-launch:

### Immediate (< 5 minutes)
1. **Disable new payments:** Stripe Dashboard → Developers → toggle to test mode or disable the webhook endpoint. This stops new `payment_intent.succeeded` events from processing.
2. **Put the app in maintenance mode:** Add a maintenance page at the load balancer or set `FLASK_ENV=maintenance` if supported.
3. **Do NOT delete any data.** All order state is recoverable from Stripe events.

### Short-term (< 1 hour)
4. **Roll back the deployment** to the last known-good release via your hosting platform (Render → manual deploy, Railway → redeploy previous commit).
5. **Verify rolled-back app starts without errors** by hitting `/` and checking logs.
6. **Re-enable webhook endpoint** after rollback is confirmed healthy.

### Recovery for orphaned PaymentIntents
If orders were created but not marked paid during downtime:
- The webhook has a fallback: it looks up the order by `stripe_payment_intent_id` if `metadata.order_id` is missing.
- Stripe retries webhook delivery for up to 3 days — no manual intervention needed for most cases.
- For edge cases: Stripe Dashboard → Event → resend the `payment_intent.succeeded` event.

### Recovery for stuck payouts
- Admin dashboard → Ledger tab → find affected orders.
- Use `hold_order()` / `release_payout()` admin actions — these are designed for manual intervention.
- Do NOT directly edit payout state in the DB — it will bypass event logging.

---

## 7. Post-Launch Monitoring Checklist

### First 15 minutes
- [ ] Place a real test order with a live card (small amount, e.g. $1 if possible, or use a low-value listing).
- [ ] Confirm `payment_intent.succeeded` webhook received: check app logs for `[Stripe webhook] order marked paid`.
- [ ] Confirm order appears in DB with `status='paid'`, `paid_at` set, `stripe_payment_intent_id` set.
- [ ] Confirm Stripe Dashboard → Payments shows the charge succeeded.
- [ ] Confirm Stripe Dashboard → Connect → Transfers shows the platform fee split.

### First hour
- [ ] Monitor Stripe Dashboard → Webhooks → recent events. All `payment_intent.succeeded` events should return 200.
- [ ] Monitor app logs for any `[Stripe webhook] signature verification failed` — if present, `STRIPE_WEBHOOK_SECRET` is wrong.
- [ ] Monitor app logs for `[Stripe webhook] order not found` — if present, orders are not being created before PI confirmation.
- [ ] Check error rate on `/checkout` and `/stripe/webhook` routes.

### First day
- [ ] Verify at least one seller completes Stripe Express onboarding end-to-end.
- [ ] Verify the admin dashboard shows new orders in the Ledger tab.
- [ ] Verify bid acceptance charges succeed for at least one test bid.
- [ ] Monitor for `bid_payment_status = 'failed'` in the bids table — track strike accumulation.
- [ ] Spot price scheduler: confirm `spot_price_snapshots` table is being populated every ~10 minutes.

---

## 8. First-Day Operational Checks

- [ ] Confirm SMTP email delivery is working: place an order, verify buyer receives confirmation.
- [ ] Confirm admin can view the Ledger and Transactions tabs without errors.
- [ ] Confirm `GET /admin/dashboard` returns 200 for admin users.
- [ ] Confirm non-admin users are redirected from admin routes (403 or redirect to login).
- [ ] Confirm CSRF is active: a direct POST to a protected form without a token returns 400.
- [ ] Confirm rate limiting is acceptable for your expected traffic (Flask-Limiter is NOT installed; consider adding if needed).
- [ ] Confirm `FLASK_TESTING` is absent from all production environment variables.
- [ ] Confirm no `.env` file with test/staging credentials is deployed to the server.
- [ ] Review Stripe Dashboard → Radar → first real charges for any false-positive fraud blocks.

---

## 9. Known Launch Considerations

| Area | Status | Notes |
|---|---|---|
| 3DS (SCA) for saved cards / bid acceptance | Partial risk | Off-session bid charges (`off_session=True`) may return `requires_action` if card has SCA. The charge is declined and a payment failure notification is sent. Buyer must re-authenticate and update their saved card. No user-facing recovery flow exists yet. |
| ACH clearance manual release | Requires admin action | No automated ACH clearance timer exists. Admin must manually release ACH payouts after 5 days. |
| Partial bid fill | Fixed | `bid_payment_status` resets to `'pending'` after partial fill, allowing future sellers to accept remaining quantity. |
| Platform fee changes | Safe | Fee snapshots are immutable. Changing a bucket's fee never retroactively alters existing orders. |
| `stripe listen` in production | NEVER | The dev CLI forward must not be used in production. All webhooks must go through the registered Dashboard endpoint. |
