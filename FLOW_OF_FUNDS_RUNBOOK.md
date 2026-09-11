# Flow-of-Funds Operations Runbook

`FLOW_OF_FUNDS_IMPLEMENTATION_SPEC.md` is authoritative. Conflicting legacy behavior must be changed or disabled.

## Safe operating state

Checkout fails closed until the Authorized Metex Administrator approves `tracking_upload_deadline_days` and `ups_coverage_and_claim_policy` in `flow_policy_config`. ACH shipment authorization additionally requires an approved `ach_approval_policy`. Grading and automatic component refunds remain disabled until their policy rows are approved. These are deliberate production gates.

The web process runs recovery every five minutes and provider reconciliation daily. Run `python -m scripts.reconcile_flow_of_funds` after database recovery and as an independent deployment health check. Any nonzero exit, `RETRY` webhook, `OPEN` reconciliation case, unbalanced journal, expired operation, payment-binding mismatch, active dispute, ACH return, grading failure, shipment failure, or account restriction requires review before releasing the affected seller funds.

## Recovery rules

- A browser close, 3DS redirect, timeout, or lost response never creates a second payment. The PaymentIntent metadata identifies the checkout and immutable snapshot. Replay the signed webhook or reload `/order-success`.
- Webhooks are retained before processing and replay by provider event ID. A processing error returns HTTP 500 so Stripe retries.
- `payment_intent.processing` retains inventory and cannot authorize shipment. ACH authorization requires evidence and an admin audit event.
- Failed bid payment retains its reservation for one day. Other definitive pre-funding failures release inventory exactly once. Unknown/pending payments are never released by the ordinary reservation timeout.
- Refunds are created from fill quantities and original component slices. Never enter an arbitrary cross-order refund amount. A provider call uses the persisted financial-operation idempotency key.
- A connected-account transfer is `TRANSFERRED_TO_CONNECTED_ACCOUNT`. Only provider payout events may record `BANK_PAYOUT_PAID`.
- Post-transfer recovery requires an approved reason-specific seller liability mapping. Apply provider reversal, available balance, future offsets, negative balance, repayment, then suspension; log each attempt.

## Restore procedure

Restore the database, leave checkout and payouts paused, run schema creation, ingest missing provider webhooks, run reconciliation, resolve every open variance, and only then re-enable approved scopes. Do not resend outbox rows already marked sent.
