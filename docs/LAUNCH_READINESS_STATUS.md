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
- ACH `processing` projects a sold/pending order without creating a payable or revenue; the same PaymentIntent is promoted only after `succeeded`.
- Refund submissions remain pending until Stripe confirms success; refund webhooks are durable and idempotent.
- Approved launch policy values are versioned in the canonical policy registry. The only remaining fulfillment policy gate is actual UPS coverage evidence.
- Production admin login created and verified; Buy, Sell, Cart, Account, and Admin Dashboard load without a server error.

## Deliberate production gates

The business-policy questions previously blocking implementation are resolved
and encoded. Shipment authorization remains blocked until Metex has actual UPS
coverage and claim-handling evidence for the relevant contents and value.

## Current launch-blocker layout

| Area | Status | Remaining work | Owner |
|---|---|---|---|
| Canonical checkout/payment binding | DONE IN CODE | Production payment tests after Stripe activation | Codex + Authorized Metex Administrator |
| Atomic inventory/order/ledger | DONE IN CODE | PostgreSQL concurrency and crash drill in staging | Codex |
| Card, 3DS, webhook recovery | DONE IN CODE | Live card/3DS test and live webhook secret | Codex after Stripe activation |
| ACH processing/approval/return | DONE IN CODE; TEST CONFIG READY | Live ACH capability and return test | Authorized Metex Administrator identity onboarding, then Codex |
| Refunds/cancellations/disputes | DONE IN CANONICAL ENGINE | End-to-end Stripe test events; remove remaining legacy-only paths after data check | Codex |
| Chargebacks/recovery | DONE IN CODE | Test-mode dispute and post-transfer recovery drill | Codex |
| Payout gates/transfers | DONE IN CODE | Stripe Connect platform activation, seller onboarding, live transfer/payout drill | Authorized Metex Administrator + Codex |
| Tracking/forfeiture | DONE IN CODE | Carrier validation adapter credentials and scheduled worker verification | Codex after provider setup |
| UPS insurance | BLOCKED EXTERNALLY | Buy coverage suitable for bullion; confirm limits, exclusions, signature, claim evidence, and API/manual workflow | Authorized Metex Administrator / insurer |
| Stripe Tax | PARTIAL EXTERNAL | Stripe Tax test state is pending; supply business address/registrations and obtain tax-adviser review | Authorized Metex Administrator / tax adviser |
| Legal and compliance | BLOCKED EXTERNALLY | Review terms, privacy, marketplace disclosures, returns, card surcharge legality, seller verification, AML/sanctions obligations | Counsel/compliance professional |
| Render web service | DEPLOYED ON FREE PLAN | Upgrade compute for predictable availability and production support | Authorized Metex Administrator |
| Render database | TEMPORARY FREE DATABASE | Upgrade before October 11, 2026; configure backups and perform a restore drill | Authorized Metex Administrator + Codex |
| Render database network | NEEDS HARDENING | Replace public `0.0.0.0/0` PostgreSQL access with required sources only | Authorized Metex Administrator approval, then Codex |
| Monitoring/incident response | PARTIAL | Error tracking, uptime alert, payment/worker alerts, named responder and runbook | Codex + Authorized Metex Administrator |
| Email/support | PARTIAL | Production email provider credentials, sender verification, support ownership | Authorized Metex Administrator |
| Final release | BLOCKED | Complete penny-value matrix, reconcile every provider object to ledger, then explicitly enable public transactions | Authorized Metex Administrator + Codex |

## External launch work

- Stripe is currently test-only. The test webhook is enabled for all 14 required payment, refund, dispute, and payout events; cards and ACH are available in the test payment-method configuration. The Stripe account itself is not activated (`details_submitted=false`, charges and payouts disabled), so no live keys or live payment capability exist yet.
- Purchase/configure UPS insurance.
- Obtain tax, marketplace, return-policy, privacy, and terms review.
- Upgrade the Render free database before its expiration and configure tested backups and restore drills.
- Configure production email/support ownership, monitoring alerts, and incident response.

## Launch order

1. Complete Stripe business/identity onboarding and activate Connect, live card, live ACH, and Stripe Tax.
2. Purchase/configure UPS bullion coverage and approve its evidence mapping.
3. Upgrade the Render web service and database, restrict database ingress, and verify backup restoration.
4. Complete tax, marketplace, surcharge, returns, privacy, terms, seller-verification, and compliance review.
5. Configure production monitoring, email, support, and incident ownership.
6. Run the specification's live penny-value matrix with separate buyer and seller accounts, including 3DS, ACH processing/success/return, partial multi-seller refund, dispute, transfer, payout, and recovery.
7. Reconcile every provider record to the Metex ledger and enable public transactions only after the Authorized Metex Administrator signs off.
