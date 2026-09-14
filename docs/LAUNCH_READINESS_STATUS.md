# Metex Launch Readiness Status

Last updated: 2026-09-14

`FLOW_OF_FUNDS_IMPLEMENTATION_SPEC.md` is authoritative. This status file records implementation progress and the remaining launch decisions; it does not override the specification.

## Completed in code

- Durable immutable checkout identity, snapshot hashing, payment binding, and one-payment/one-execution enforcement.
- Atomic inventory reservation, execution, order projection, seller fills, payables, and balanced ledger posting.
- Card gross-up surcharge, ACH zero buyer surcharge, seller 5% fee, captured spread, taxes, grading liabilities, and expense classification.
- Card 3DS recovery, signed durable webhooks, duplicate suppression, retry replay, failed-payment recovery, ACH holds/approval/return states, and the bid correction window.
- Per-fill cancellations, component refunds, disputes, processor chargebacks, payout holds, and post-payout recovery obligations.
- Tracking ownership and validation, configurable tracking forfeiture, per-leg insurance records, grading custody legs, payout gates, and bank-payout state separation.
- Safe automatic bid matching through the canonical engine, including independent payments for partial and multi-seller fills.
- Internal/provider reconciliation, audit events, notification outbox, worker retries, atomic spot-scheduler lease, and retired unsafe legacy refund paths.
- Durable session revocation for bans, freezes, and password changes.
- GitHub Actions checks for financial acceptance, security, routes, JavaScript syntax, Python compilation, spot scheduling, and reconciliation.
- Third-party grading removed from the launch product at both the UI and server boundaries.
- Spot-linked prices revalidated immediately before payment confirmation; changed prices require renewed consent.

## Deliberate production gates

Transactions remain blocked for the affected scope until an Authorized Metex Administrator records and approves these policies:

- Tracking upload deadline.
- UPS coverage and claim handling for seller-to-buyer shipments.
- ACH approval evidence and return handling.
- Card-surcharge refund treatment by cancellation/fault reason.
- Return rules and restocking conditions.
- Chargeback liability allocation by reason.

## External launch work

- Confirm Stripe Connect, Tax, ACH, webhook, refund, transfer, dispute, and live-mode account approval.
- Purchase/configure UPS insurance.
- Obtain tax, marketplace, return-policy, privacy, and terms review.
- Upgrade the Render free database before its expiration and configure tested backups and restore drills.
- Configure production email/support ownership, monitoring alerts, and incident response.

## Launch order

1. Approve the policy gates in the admin dashboard with reviewed values.
2. Complete Stripe, UPS, tax, and legal setup.
3. Upgrade the Render database and verify backup restoration.
4. Run a live-mode penny-value transaction matrix with separate buyer and seller accounts.
5. Reconcile the provider records to the Metex ledger, verify seller payout states, then enable public transactions.
