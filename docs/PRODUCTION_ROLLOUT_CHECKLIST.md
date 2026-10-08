# Metex production rollout checklist

Updated 2026-09-30 against local code. Governing requirements: [repository specification](../FLOW_OF_FUNDS_IMPLEMENTATION_SPEC.md) and [approved policies](APPROVED_LAUNCH_POLICIES.md). This checklist owns deployment steps; payment scenarios live in the [staging matrix](STAGING_PAYMENT_TEST_CHECKLIST.md).

## Before deployment

- [ ] Record revision, local changes, owner, release scope and rollback revision.
- [ ] Review [readiness](LAUNCH_READINESS_STATUS.md); recheck September 14 external findings. The documented free Render database expiration is October 11, 2026; verify current plan/expiration and upgrade if still applicable.
- [ ] Confirm processor activation, Connect/card/ACH capabilities, seller onboarding and approved precious-metals business representation.
- [ ] Obtain applicable UPS coverage/evidence and tax/legal review; configure approved policies without bypassing gates.
- [ ] Verify production compute, database ingress, backups/isolated restore, upload/evidence durability, email/support and alert ownership.
- [ ] Review `render.yaml`, `config.py`, `.env.example` and actual runtime settings together. Set `DATABASE_URL`, `SECRET_KEY`, `SITE_URL`, Stripe keys/webhook secret, applicable spot/email credentials, proxy/secure cookie/HSTS settings. `FLASK_TESTING` must be absent in production. Never place secrets in docs.
- [ ] Validate clean and upgrade schema on staging; schema startup mutates the selected database.
- [ ] Keep public checkout and payouts paused until evidence and administrator approval permit release.

## Deploy and verify

- [ ] Run appropriate CI and retain results; confirm deployed revision and database target.
- [ ] Verify `/healthz`, authentication/session restrictions and Buy/Sell/Cart/Account/Admin views.
- [ ] Verify signed `POST /stripe/webhook` ingestion and durable replay. Required current event families include payment success/processing/failure/cancel, dispute lifecycle, refund created/updated/failed and payout created/updated/paid/failed. Confirm actual provider event configuration against handler code and the specification; a success-only endpoint is insufficient.
- [ ] Verify recovery worker, scheduling, notification outbox and reconciliation alerting. A web-process timer on sleeping compute is not an independent reliable job.
- [ ] Complete [staging scenarios and sign-off](FINAL_MANUAL_STAGING_CHECKLIST.md), then authorized live penny-value tests with separate buyer/seller accounts.
- [ ] Reconcile every relevant provider charge/refund/transfer/bank payout to journal and allocations. A PaymentIntent-only check is insufficient.
- [ ] Record authorized administrator, date and enabled transaction scope in readiness.

## Incident or rollback

- [ ] Pause new checkout and automatic/manual payouts with application controls; verify coverage of bids/matching/background paths.
- [ ] Keep signed webhook ingestion available and preserve durable event/operation identities. Provider dashboard test-mode selection is not a shutdown control.
- [ ] Follow the [runbook](../FLOW_OF_FUNDS_RUNBOOK.md); retain provider evidence and reconcile unknown outcomes before retries.
- [ ] Validate schema compatibility before rolling back application code. Restore into isolation and rehearse recovery before changing the production target.
- [ ] Resume only after reconciliation and explicit approval for the affected scope.

## First-day operations

- [ ] Watch request failures, worker freshness, webhook retries, journal imbalance, reconciliation cases, failed refunds, inventory discrepancies and notification failures.
- [ ] Review ACH returns, disputes, tracking/coverage exceptions, transfer/payout failures and account restrictions.
- [ ] Confirm daily release review, high-value manual review and named human exception response within one business day.
- [ ] Date operational evidence and update readiness when gates change. Do not declare production readiness from page loads or unit tests alone.
