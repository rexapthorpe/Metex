# Metex manual staging sign-off

Updated 2026-09-30. The older March scenario instructions have been consolidated into the [staging scenario matrix](STAGING_PAYMENT_TEST_CHECKLIST.md). Use that matrix for procedures and expectations; do not maintain duplicate ACH, payout or refund rules here.

## Run record

- Date / operator:
- Commit / working changes:
- Environment / database / provider mode:
- Evidence location (exclude secrets and unnecessary personal data):

Record PASS, FAIL or BLOCKED and evidence for each scenario:

| Scenarios | Result | Evidence / unresolved issue |
|---|---|---|
| S1–S3: card, saved card, 3DS | | |
| S4–S6: ACH and bid fills | | |
| S7–S9: prices, payment binding, webhooks | | |
| S10–S12: insurance, fulfillment, payouts | | |
| S13–S14: refunds and recovery | | |
| S15–S16: security and crash recovery | | |
| S17–S18: reconciliation, PostgreSQL, restore | | |
| S19–S20: browser/mobile, tax and scope | | |

## Approval

- [ ] Every required scenario has linked evidence; all failures/blockers dispositioned.
- [ ] External provider, insurance, legal/tax and operational gates in [readiness](LAUNCH_READINESS_STATUS.md) are verified with dates.
- [ ] [Production rollout](PRODUCTION_ROLLOUT_CHECKLIST.md) is complete for the intended release scope.
- Authorized administrator / date / approved scope:

An empty record does not approve launch. Write resulting evidence and remaining blockers into readiness rather than creating another status summary.
