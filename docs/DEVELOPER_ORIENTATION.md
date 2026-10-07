# Metex Developer Orientation

Reviewed against local checkout `d152b52` and existing working changes on 2026-09-30. This is a navigation guide, not production certification. Start with [agent instructions](../AGENTS.md) and [launch readiness](LAUNCH_READINESS_STATUS.md).

## Product and authority

Metex is a Flask/Jinja marketplace for precious-metal coins and bullion, with listings grouped into specification buckets, bids, carts, Stripe card/ACH checkout, seller fulfillment and Connect payouts. Launch is US/USD; the optional third-party grading service is removed. Item grade/certification attributes remain distinct from that removed service.

The [repository financial specification](../FLOW_OF_FUNDS_IMPLEMENTATION_SPEC.md), including its launch amendment, owns financial requirements. [Approved launch policies](APPROVED_LAUNCH_POLICIES.md) records business decisions. Older copies outside this repository and historical reports must not override them.

## Repository map

| Location | Responsibility |
|---|---|
| `app.py`, `core/__init__.py` | Entry point, app factory, configuration, blueprint registration, session validation, workers and error handling |
| `core/blueprints/` | Most domain routes: auth, account, buy, sell, bids, cart, checkout, admin, Stripe Connect, disputes, messages, ratings, notifications and API |
| `routes/` | Compatibility exports **and some active modules**; follow registration/imports before editing |
| `services/flow_of_funds.py` | Canonical schema/policy registry, checkout snapshots/reservations, provider binding, executions, journal, refunds, holds, recovery, shipment and payable commands |
| `services/flow_worker.py`, `scripts/run_flow_worker.py` | Leased recovery cycle, embedded fallback and dedicated worker entry point |
| `services/` | Active pricing, spot feeds/scheduling, risk, notifications, email, orders, disputes and supporting services |
| `core/services/ledger/`, `core/services/analytics/` | Modular legacy ledger/display functionality and analytics; do not assume legacy ledger rows are canonical financial authority |
| `database.py` | PostgreSQL adapter when `DATABASE_URL` is set; SQLite fallback at `data/database.db` |
| `scripts/create_schema.py`, `migrations/` | Schema bootstrap and historical/versioned schema changes; verify fresh and upgrade behavior separately |
| `utils/`, `auth_utils.py` | Security, auth, CSRF, rate limits, uploads, category and cart helpers |
| `templates/`, `static/` | Jinja pages/partials, CSS and browser JavaScript |
| `tests/` | Financial, route, security, pricing and browser regression tests |
| `render.yaml`, `.github/workflows/flow-of-funds-ci.yml` | Deployment recipe and automated safety checks |
| `bucket_image_acquisition/` | Catalog/image acquisition subsystem with its own README and manifests |
| `CLAUDE/`, `Claude Code Reports/` | Historical implementation reports; no current-state authority |

## Follow a transaction

1. Browser checkout lives in `templates/checkout_page.html` and `static/js/checkout_page.js`; server checkout is `core/blueprints/checkout/routes.py`.
2. `prepare_checkout` freezes cents, identities, component allocations and inventory reservations. Provider payment is bound to that checkout; method changes use `revise_payment_rail`.
3. Provider verification and `finalize_payment` enforce binding and create funded executions, fills, payables, journal entries and legacy-facing order projections. `record_ach_processing` creates only `SOLD_PENDING_ACH` visibility and keeps inventory held.
4. `core/blueprints/stripe_connect/routes.py` verifies webhook signatures and calls durable `record_webhook` / `process_webhook`. Recovery retries stored events independently of browser return.
5. Insurance evidence and `authorize_shipment` gate fulfillment; tracking ownership, carrier acceptance and delivery evidence affect eligibility. Pending ACH does not authorize shipment.
6. Refunds allocate original components per fill/unit, remain pending until provider confirmation and hold affected funds. Transfers to connected accounts and bank payout events are separate states.
7. `flow_worker.py` and the reconciliation script recover/reconcile work. Consult the [runbook](../FLOW_OF_FUNDS_RUNBOOK.md) before operating them.

## Find the right implementation

| Task | Start here |
|---|---|
| Route is live or duplicated | `core/__init__.py::_register_blueprints`, then the imported blueprint's `__init__.py` |
| Checkout / tax / payment setup | `core/blueprints/checkout/routes.py`, `static/js/checkout_page.js` |
| Payment event / Connect onboarding | `core/blueprints/stripe_connect/routes.py` |
| Bids / automatic matches | `core/blueprints/bids/`, `routes/auto_fill_bid.py`, `services/flow_of_funds.py::execute_bid_fill` |
| Sell / tracking | `core/blueprints/sell/`, canonical shipment commands |
| Admin refund / reconciliation | `core/blueprints/admin/refunds.py`, `reconciliation.py`, canonical financial commands |
| Ban/freeze session behavior | `core/__init__.py::_register_session_validation`, auth/account/admin modules |
| Smart Pricing / seller-managed premium | `services/smart_pricing_service.py`, sell/listings creation and edit routes, `static/js/smart_pricing.js`; due reviews run in the existing flow worker. Central structured item/year classification with audited reasons, strict completed-sales→safe year→capped adjacent-grade corroboration→identified family→active-asks evidence, deterministic confidence, seller seed hold/transition, exact set metal valuation, bounded age/demand target and 24/48/72-hour V1 parameters are centralized in the service. `/sell/smart-pricing-preview` refreshes the existing normal spot cache when needed, bridges fresh observations preserving UTC timestamps into canonical snapshots, and issues seller/product/price-bound 900-second confirmation tokens; valid previews populate the seller summary automatically, while create/edit validate them atomically at final listing confirmation; new listing creation timestamps support age, with conservative enable-time fallback for legacy rows. Schema/history are in the service; current premium remains `listings.spot_premium`. |
| Spot price / quote freshness | `services/checkout_spot_service.py`, `spot_snapshot_service.py`, `spot_scheduler.py`, canonical snapshot validation |
| Database shape | `scripts/create_schema.py`, `services/flow_of_funds.py::ensure_flow_schema`, relevant migrations |

## Development and verification

Use the existing environment or install `requirements.txt` in an isolated environment. Local `python app.py` starts a debug server on port 5002 and may start background work; use test credentials and an isolated database. Required Stripe configuration is enforced outside `FLASK_TESTING`. Never apply test bypasses to production.

`python -m scripts.create_schema` changes the selected database. Render runs it before `gunicorn "core:create_app()"`. Verify the target before running it. The surrounding workspace's `metex-preview/` uses an isolated read-only preview; it cannot prove payment readiness.

Run task-relevant tests with `python -m pytest`; the CI workflow names the financial/security acceptance subset. Run `node --test tests/test_checkout_payment_setup.cjs` for the existing local payment-setup regression and `node --check static/js/checkout_page.js` for syntax. Do not copy historical test counts as a current baseline. PostgreSQL concurrency, browser/Stripe lifecycles and restore drills need separate evidence in the [staging matrix](STAGING_PAYMENT_TEST_CHECKLIST.md).

## Placement and maintenance

Add route behavior to the owning domain blueprint and import new modules so they register. Extend the active service owning a capability: both `services/` and `core/services/` contain implementations. Preserve public imports/URLs and keep compatibility wrappers thin where they already are wrappers. Prefer focused modules; do not undertake an unrelated mass relocation to satisfy old line-count targets.

Patch actual connection/provider boundaries in tests; use `database.get_db_connection()` through a module-level wrapper when late binding is needed. Keep money and transaction correctness centralized rather than adding a second checkout/refund path.

Update this map when ownership or registration changes. Record decisions in approved policies, operating instructions in the runbook, scenarios in the staging matrix, and evidence/blockers in readiness. January refactor/security inventories and old ledger documentation are historical references.

## September 30 implementation additions

`flow_safety.py` serializes canonical financial mutations in caller-owned transactions. `payout_service.py` dispatches provider transfers with stable operation identity and daily controls. `recovery_service.py` owns evidence-reviewed reversals and future-proceeds offsets; its remaining operational verification is recorded in readiness. `compensation_service.py` refunds late successful payments without selling already-released inventory. `tax_service.py` calculates per listing and records sale/reversal tasks. `delivery_service.py` fans durable financial events into in-app and email queues. `admin_flow_service.py` preserves canonical review holds and delivery; `flow_projection_service.py` projects confirmed refunds without counting pending allocations as returned money. The admin operations page is `/admin/operations`. Upload migration is `python -m scripts.migrate_upload_storage --destination PATH` (dry run); `--apply` copies with checksum verification and never deletes source files.

Shared single-choice dropdown presentation lives in `static/js/standard_dropdowns.js` and `static/css/standard_dropdowns.css`, loaded by base.html. The native select remains the form value; menus synchronize input/change/reset and dynamic options, support keyboard navigation and disabled state, and use top-layer popovers to avoid modal clipping. Bid pricing retains its equivalent existing disclosure control. Multiple-selection listboxes remain native.
