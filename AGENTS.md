# Metex agent instructions

## Read these first

1. [Launch readiness](docs/LAUNCH_READINESS_STATUS.md): current implementation, open work, local changes and dated external findings.
2. [Developer orientation](docs/DEVELOPER_ORIENTATION.md): architecture and where to change code.
3. For money, checkout, bids, fulfillment or payouts, read the relevant sections of the [repository financial specification](FLOW_OF_FUNDS_IMPLEMENTATION_SPEC.md), [approved policies](docs/APPROVED_LAUNCH_POLICIES.md), and [operations runbook](FLOW_OF_FUNDS_RUNBOOK.md).

The repository specification, including its launch amendment, is authoritative for financial requirements. Approved policies supply business decisions; readiness records evidence and unfinished work. Neither code nor historical reports overrides requirements. Report discrepancies instead of silently treating them as approved changes.

## Working rules

- Inspect Git status and preserve pre-existing changes. Inspect actual blueprint registration before choosing a route file.
- Follow the navigation and placement rules in developer orientation. `services/` contains active business logic; `routes/` includes both wrappers and active legacy modules.
- Use integer cents and stable operation identities for canonical money flows. Keep financial entry points on the canonical engine.
- Read only task-relevant historical reports. They are evidence of past work, not current instructions or proof of present behavior.
- Run checks appropriate to the change; record results and limitations. SQLite and mocks do not certify PostgreSQL concurrency or real provider behavior.
- Do not move, delete or deduplicate historical reports without a separately scoped cleanup. All 21 reports unique to `Claude Code Reports/` must be preserved.

## Keep context current

When behavior, architecture, decisions, blockers or operational procedures change, update the existing document that owns that information in the same task. Update readiness with date, code revision, verification evidence, remaining uncertainty and meaningful uncommitted work. Preserve dates on external findings until rechecked. Keep completed-in-code distinct from provider-tested and production-approved.

Maintain one architecture guide, one staging scenario matrix and one rollout checklist. Link to them instead of copying them into new summaries. Do not create another project-brain system. Historical documents retain their original content with a supersession notice.

## Verification documents

- [Staging scenario matrix](docs/STAGING_PAYMENT_TEST_CHECKLIST.md)
- [Manual staging sign-off](docs/FINAL_MANUAL_STAGING_CHECKLIST.md)
- [Production rollout](docs/PRODUCTION_ROLLOUT_CHECKLIST.md)
