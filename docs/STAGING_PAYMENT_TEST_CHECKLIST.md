# Metex staging payment scenario matrix

Reconciled with the repository launch amendment and current code on 2026-09-30. This is the single scenario source; [manual sign-off](FINAL_MANUAL_STAGING_CHECKLIST.md) records results, and [production rollout](PRODUCTION_ROLLOUT_CHECKLIST.md) covers deployment. The [repository specification](../FLOW_OF_FUNDS_IMPLEMENTATION_SPEC.md) and [approved policies](APPROVED_LAUNCH_POLICIES.md) govern expected behavior.

## Prerequisites and evidence

Use isolated staging, separate buyer/seller accounts, provider test credentials, production-equivalent PostgreSQL, a clean/upgrade-tested schema and controlled inventory. Record commit plus working changes, environment, date, operator, checkout/payment/event/fill IDs and exact cents. Retain screenshots, provider outcomes, journal/reservation checks and PASS/FAIL/BLOCKED per scenario. Blank checkboxes are not passing results.

Do not fabricate UPS approval to pass a test. Use explicit test fixtures/adapters in isolation and record real insurance/provider gates as BLOCKED until evidence exists. Mocks and SQLite unit tests do not substitute for the provider/browser/concurrency drills.

## Scenarios

| ID | Exercise | Required evidence / expected outcome |
|---|---|---|
| S1 | New card; double submit and refresh | One bound payment and funded execution; exact amount/customer/currency; balanced journal and inventory; 5% seller fee and total-base 2.99% gross-up |
| S2 | Saved card; policy/tax/network setup failure then retry | Review blocked without client secret and payment ID; useful error; retry works; failed setup creates no funded execution |
| S3 | 3DS success/failure, browser loss, late webhook | Recover same checkout/payment; no duplicate funding; unfinished authorization respects expiry; late events cannot reopen terminal states |
| S4 | ACH processing, success, failure and later return | Processing projects `SOLD_PENDING_ACH` only; inventory held, no payable/revenue/shipping deadline; verified success funds the same payment; return holds funds and triggers reason-specific review |
| S5 | Bid acceptance; failed/off-session authentication or mandate | Independent canonical payment per execution; correction window retained; no unpaid funded order; success/retry is idempotent |
| S6 | Partial and multi-seller fills; simultaneous accepts | Remaining quantity and stock correct; independent payments/fills; no overselling or self-trade |
| S7 | Spot price changes at confirmation; method switch; quote expiry | Cent-level change requires renewed consent; rail revision consistent; reservations/quotes limited to 900 seconds; unknown pending payments not blindly released |
| S8 | Foreign, wrong-amount/currency, reused and missing payment | Rejected on every order-creation entry point; no unauthorized order or stock mutation |
| S9 | Duplicate/early/late webhook, processing error and replay | Signature required; durable record; retryable error/replay; financial operation occurs once |
| S10 | Insurance, ship authorization and tracking | Actual qualifying coverage gate; approved payment and active insurance required; three-day clock begins only at authorization; UPS acceptance/ownership/destination and uniqueness verified; signature threshold $500 |
| S11 | Tracking deadline expiry, delivery and payout holds | Forfeiture/refund operates without page visits; delivery plus 24-hour canonical hold; disputes/refunds/restrictions block release; payout above $10,000 reviewed |
| S12 | Seller transfer and bank payout success/failure | Stable transfer identity; correct net and gates; connected transfer and bank payout represented separately |
| S13 | Partial multi-seller refund before transfer | Original unit components allocated once; unaffected fills remain correct; allocated surcharge follows cancellation reason; pending/failed/succeeded truthfully represented |
| S14 | Refund/dispute/chargeback after transfer; ACH return | Exact affected recovery amount, holds, reviewed liability and recovery attempts; no blanket reversal of unrelated seller proceeds |
| S15 | Ban/freeze/password change; unauthorized account mutations | Old session revoked and applicable financial boundaries restricted; foreign tracking/payment/order access rejected |
| S16 | Crash/timeout after provider success; restart worker | Same operation recovered without second charge/refund/transfer; inventory and journal conserved; outbox not resent |
| S17 | Internal and provider reconciliation | Compare charges, refunds, transfers and bank payouts to journal/components; unknown objects and discrepancies retained for review; do not infer full coverage from command exit |
| S18 | PostgreSQL concurrency, clean/upgrade schema and backup restoration | Isolated drill, versioned schema evidence, lock/uniqueness checks, restored uploads/evidence and reconciled pending operations |
| S19 | Mobile/browser checkout and fulfillment views | New/saved card and ACH, errors/retry, 3DS return, totals, pending/refund/payout labels, keyboard and narrow-screen usability |
| S20 | Tax, grading removal and launch boundaries | Address/tax failure fails closed; tax records/reversals verified; optional grading absent and forged fields disabled; grade attributes preserved |

## Automation references

CI scope is defined in `.github/workflows/flow-of-funds-ci.yml`. Relevant tests include `test_flow_of_funds_acceptance.py`, `test_delivery_payout.py`, `test_refund_workflow.py`, `test_staging_blockers.py` and security suites. The existing local `test_checkout_payment_setup.cjs` covers S2 failures/retries. Record actual commands and results; do not claim CI includes the untracked browser test.

For release, execute the specification's full penny-value matrix after the required provider/business gates and explicit authorization for real transactions. No provider or live test was run by this documentation refresh.

September 30 regression additions: `test_launch_safety.py`, `test_storage_migration.py` and the separate localhost PostgreSQL `test_postgres_launch_concurrency.py` job. Include ambiguous payment creation/cancellation, late compensation, failed refund unit reuse, partial ACH rejection, dispute terminal replay, account-mapped payouts, pending tracking acceptance, admin hold isolation, immutable repeated checkout/rail revision, transfer timeout/changed entitlement, reviewed reversal/offset caps and notification replay in provider acceptance. These tests use disposable data and do not certify provider or live acceptance.
