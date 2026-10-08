# Flow-of-Funds Operations Runbook

Reviewed against local code on 2026-09-30. The [repository specification](FLOW_OF_FUNDS_IMPLEMENTATION_SPEC.md), including its launch amendment, is authoritative. Read [approved policies](docs/APPROVED_LAUNCH_POLICIES.md) and [launch readiness](docs/LAUNCH_READINESS_STATUS.md) for decisions and dated external evidence.

## Gates and operating state

September 14 policy defaults approve the three-day tracking deadline, 900-second reservation/quote limit, ACH-success rule and reason-specific refund/recovery rules. These are no longer unresolved business decisions. Actual `ups_coverage_and_claim_policy` approval and qualifying per-shipment insurance evidence remain required. Do not approve coverage without a real applicable contract and evidence.

The optional grading service is disabled for launch. Legacy grading columns/commands are historical compatibility, not permission to sell that service.

ACH `processing` shows `SOLD_PENDING_ACH` and retains inventory without an execution, payable, revenue or shipment authorization. The same verified payment reaching `succeeded` is promoted to funded execution; shipment still needs approved payment and active insurance. Authorization starts the tracking clock. Seller release requires delivery and the canonical 24-hour delivery hold plus the other applicable account, dispute, refund and transfer gates. Do not use the old tracking-based card/ACH delay tables.

## Recovery and incident response

1. Pause new checkout and automatic/manual payouts through the existing administrator controls (`checkout_enabled`, `auto_payouts_enabled`, `manual_payouts_enabled`; inspect maintenance-mode coverage). Verify bids, matching and background entry points are also stopped where required; do not assume a UI toggle covers every path.
2. Keep signed provider webhook ingestion available. Disabling webhooks loses recovery visibility; switching a provider dashboard to test mode is not a production shutdown control.
3. Preserve checkout, payment, operation, webhook and provider IDs. Reconcile authoritative provider evidence before retrying a financial action. Never issue a fresh payment to repair an unknown outcome.
4. Review `RETRY` webhooks, `OPEN` reconciliation cases, journal imbalance, binding mismatch, expired operations, ACH returns, active holds and account restrictions before releasing affected funds.
5. Refund submission is pending until provider success. Use original fill/unit component allocations and persisted idempotency keys. Resolve failure rather than recording success manually.
6. Connected-account transfer is distinct from bank payout. Recover post-transfer losses by approved reason-specific liability and record each recovery attempt; unknown liability requires human review.

`services/flow_worker.py` schedules its first tick after 15 seconds, then every 300 seconds in each participating web process. It retries webhooks, expires eligible reservations, processes tracking forfeiture/refunds, dispatches the outbox and checks internal journals. It retrieves bound PaymentIntents on its first tick and daily thereafter. Timers are process-local; a sleeping/restarting web service is not a reliable independent scheduler. Verify worker health and schedule independently as required.

## Reconciliation command: has side effects

From the repository, `python -m scripts.reconcile_flow_of_funds` checks journals and retrieves provider PaymentIntents, but also expires reservations, marks forfeitures, processes refunds and dispatches notifications. It is **not a read-only diagnostic**. Verify environment, database, credentials and authorization for those operations before running it.

A zero exit does not prove every refund, transfer, payout or external record has reconciled: current command coverage is internal balance plus bound PaymentIntents. Use the [staging matrix](docs/STAGING_PAYMENT_TEST_CHECKLIST.md) and provider records to establish broader evidence.

## Restore and resumption

1. Keep new checkout/payouts paused; preserve pending provider events and operation identities.
2. Restore database and required uploads/evidence into an isolated recovery target first. Retain a backup and validate schema compatibility before `python -m scripts.create_schema`, which mutates the selected target.
3. Review missing provider objects/events, replay durable retry events and reconcile money, inventory and seller obligations. Do not resend outbox rows already marked sent.
4. Exercise the relevant failure/restore scenarios and retain results. The procedure here is not proof of a completed restore drill.
5. Resume only after discrepancies are resolved, provider/insurance gates are satisfied and the authorized administrator approves the applicable scope. Follow the [rollout checklist](docs/PRODUCTION_ROLLOUT_CHECKLIST.md).

## September 30 operational changes (not production-certified)

Use `/admin/operations` for new-operation controls and manual carrier evidence. Insurance must be applicable and recorded before shipment authorization; carrier acceptance and destination evidence are mandatory. Admin review release clears only `ADMIN_REVIEW` holds, never dispute/shipping/ACH holds. Refund submission and pending allocation do not mean money has been returned. Failed refunds release exact unit allocations; unknown submissions retain them and reuse the original key. Partial ACH refunds are blocked until provider support is resolved.

`python -m scripts.run_flow_worker` runs the dedicated recovery loop. Provision its provider/configuration access and verify the `flow_worker_lease.last_success` heartbeat before disabling `EMBEDDED_FLOW_WORKER`. The cycle includes compensation, tax reporting, notification delivery and daily UTC releases. Automatic release requires both automatic and manual release switches; defaults are off. Daily attempts retain operation keys on failure and create review records. Unknown transfer retries after a hold/refund changes entitlement are blocked and need provider reconciliation. No worker deployment or production controls were changed in this run.

Tax configuration requires `TAX_CONFIGURATION_APPROVED=true` plus adviser-reviewed product-code and seller-origin mappings. Email delivery requires `EMAIL_DELIVERY_ENABLED=true` and verified credentials; it defaults off. SMTP ambiguity cannot promise exactly-once mail, even with a stable Message-ID. Upload storage uses `UPLOADS_ROOT/public` and `UPLOADS_ROOT/private/reports`; run the checksum-copy tool against an isolated restore first and retain original files.
