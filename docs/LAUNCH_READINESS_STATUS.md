# Metex Launch Readiness Status

Code and local verification updated: 2026-09-30. Baseline: `d152b52`. Changes remain local and uncommitted; deployed code, live account capabilities and production configuration are not verified.

`FLOW_OF_FUNDS_IMPLEMENTATION_SPEC.md` is authoritative. This status file records implementation progress and the remaining launch decisions; it does not override the specification.

## Smart Pricing V1 — 2026-10-01 (local, uncommitted)

Implemented optional Smart Pricing inside the existing sell pricing area: automatic selection of a valid signed quote with final listing confirmation, three discrete strategies, dynamic descriptions, prescribed prices and estimated proceeds without seller dollar-entry fields, reduced-motion-aware transitions, existing-listing edit restoration and return to the original manual controls. Creation and editing persist settings atomically with the authoritative legacy `listings.spot_premium`; seller dashboard controls/history use an owner-only CSRF-protected route at `/listings/<id>/smart-pricing`. Smart mode remains `premium_to_spot`, so existing spot/display/checkout calculations remain in use. Returning to manual spot keeps the managed premium; returning to fixed requires a positive explicit fixed price. Pending purchases lock out price edits. Checkout verifies the current managed ask under the canonical mutex before inventory reservation and rejects stale quotes rather than accepting an older seller premium.

Schema: additive `smart_pricing_settings` (strategy, authorization minimum in cents, revision, review/estimate/timestamps) and `smart_pricing_history` (old/new cents, strategy, fair estimate, reason JSON, version, unique listing/revision); no duplicate current-premium column. Both fresh and upgraded deployments use the existing schema bootstrap. New checkout snapshots freeze product identity and fresh spot metal value for later sale normalization; older sales lacking trustworthy frozen evidence are excluded.

Deterministic logic in `services/smart_pricing_service.py`, version `premium-v1-classified-preview`: accumulate exact completed sales, safe year-relaxed sales, adjacent-grade sales, then standardized-family sales; stop at the first defensible distribution. Only if completed evidence is inadequate, add active asks in the same exact/year/grade/family sequence. Completed sales must be approved, buyer-delivered, non-refunded/unheld, within 90 days, with frozen sale-time metal value; own-seller evidence is excluded. Base sales weights are 8/6/2/3; asking weights 2/1.5/.5/.75. Historical recency is 30/(30+age days); active asks count one best-tier/lowest ask per competing seller. No external comparable source is queried.

Exact identifiers include metal, product type/line/family, mint, normalized weight, purity, denomination, dates, grade, grading service, finish, series, designation, packaging and collector identity. Year relaxation uses centralized structured classification, never a calendar cutoff. Ordinary BU/business-strike/uncirculated/mint-state coin/bar/round metadata with a known bullion family (or identified bar/round product line) may relax year; proof/special-strike/numbered/limited/variant/key-date/mintage/unique/set and unknown classes cannot. Recent transactions retain existing recency weighting regardless of product year. Adjacent certified MS68–MS70 with the same nonempty grading service are corroboration only: base weight 2 for sales/.5 for asks, match quality .3; they cannot create an estimate alone, aggregate grade weight is capped at half surviving exact-grade evidence, premiums more than 50% from its weighted median are excluded, and confidence is capped at .6. Raw/proof/major-grade/designation/mint/content differences never expand. Family expansion permits only empty/Loose/Capsule packaging differences within the same identified branded bullion family; bars/rounds require a product-line identity. Rare, proof, limited/numbered, variant, isolated and set inventory never expands to generic bullion. Central item/year classifiers retain classification and reason codes in activation/review history. Seller title/description/condition prose can record POSSIBLE_SPECIAL_ITEM_UNCONFIRMED only; it never independently changes classification, warnings or year eligibility. Standardized-item condition prose is also excluded from comparable signatures; structured condition identifiers still match exactly. Unknown products receive a warning and remain exact-only. Sets require exact sorted component identities, quantities, numbering and listing title; metal value sums actual component metal cents multiplied by quantity, never unrelated item premiums.

Evidence rules: zero/one observation is insufficient. Reject IQR/six-MAD outliers; require two retained observations, effective weighted sample size at least 1.8, score at least .15. Two observations also require premium difference divided by max(abs(median), $1) at most .5. Score = min(1,effective_count/3) × weighted mean(match quality × source quality × recency) × dispersion penalty × outlier penalty. Match qualities exact/year/grade/family are 1/.8/.3/.45; source quality sales/asks is 1/.65; penalties .85 for excessive dispersion and .9 when outliers are rejected. High ≥.75, Medium ≥.45, otherwise Low; insufficient data produces no estimate. Several recent consistent exact sales can be High; two consistent exact sales Medium; two exact asks Low; count alone never certifies evidence.

Activation uses the authenticated `/sell/smart-pricing-preview` endpoint, which can refresh the existing spot cache before calculating a quote. Rare/set/one-of-a-kind inventory first requires an accuracy warning acknowledgment. Preview shows strategy, fair premium/range when defensible, exact initial dollar premium, fresh metal value and prominent initial total, plus proceeds after the canonical 5% seller fee and before shipping costs. Insufficient comparable data explains the limitation and directs the seller to Fixed Price or Premium to Spot; new activation never substitutes a seller seed or a spot-only price. Legacy seeded settings retain their protected hold/transition behavior. Strategy/minimum/product/set changes invalidate confirmation. A seller/product/price-bound signed preview expires after 900 seconds; create/edit recalculate and validate it under the existing financial mutex, rolling back changed inputs, spots or targets. Warning acknowledgment and initial pricing are retained in history even when the premium is unchanged. Activation from dashboard cannot bypass the preview. Seeded premiums hold indefinitely without defensible evidence; once evidence exists, existing cadence and bounded steps apply.
Fast/Balanced/Big share this distribution and target P25/P50/P75 with review/cooldown intervals 24/48/72 hours. Age grace periods are 2/7/21 days; saturating age pressure is `-IQR × cap × elapsed/(elapsed+ramp)` with caps 50%/25%/10% and ramps 14/30/60 days. New listings now retain `listings.created_at`; upgrades add a nullable timestamp without inventing historical dates. For older listings without that evidence, Smart enable time is a conservative age lower bound, identified in review JSON. Existing enable time survives strategy/minimum edits. No reliable view/save/conversion series exists; `demand_adjustment` is an explicit neutral extension point with recorded reason. Adjusted targets are bounded from P25 minus half IQR to P75, then the seller minimum overrides that market range as an absolute boundary. Subsequent movement is 25%/15%/8% of the greater absolute current/fair premium, confidence-scaled and bounded to $1–$50; changes below $1 hold. New unpublished listings establish their strategy target before publication, while later market rises/falls converge via bounded steps. Audit JSON retains observations/weights, rejected count, percentiles, confidence/effective count, base target, age/demand adjustments, guarded target, step, minimum, strategy configuration and version. All calculations use cents/Decimal; existing `listings.spot_premium` remains authoritative. No ML or provider dependency was added.

Execution: existing leased flow worker checks up to 100 due listings per cycle (default five minutes). Every adjustment, review and history insertion commits together under `flow_mutex`, shared with canonical checkout/inventory operations. Duplicate jobs re-read current settings/cooldown under lock; failures roll back completely. Manual, sold/inactive, reserved-inventory and banned/frozen-seller listings cannot be automatically repriced. `SMART_REPRICING_ENABLED=false` pauses repricing without stopping financial recovery. No browser repricing timer, LLM or new provider dependency.

Safety assumptions: existing weight denotes contained metal using existing troy-ounce/gram/kg/lb conversion conventions; no new purity multiplier. Minimums are nonnegative and clamp the initial target/seed. Fresh spot snapshots (at most 15 minutes old) for every contained metal are required for activation; stale/unavailable feeds or insufficient comps hold the authorized premium during reviews. Single-item and set dynamic display use the same half-up metal-cent calculation as the preview. Checkout fetches component metals and actual category weight for fresh confirmation; canonical reservations reject stale prices. No real financial transactions or customer communications were performed.

Verification (2026-10-01 final amendment): 464 targeted financial/security/route/spot/cart regression tests passed, including 95 Smart Pricing tests. Coverage includes hierarchy/strict exclusions, 0/1/2/3+ confidence, outliers, no external sources, seed hold/transition, signed/expired/stale previews, warning acknowledgment, actual create/edit price equality, mixed-metal sets, fractional-weight rounding, duplicate jobs, mutex reservation and rollback/retry. Eight isolated local PostgreSQL concurrency/financial tests and twelve JavaScript tests passed. Browser checks cover desktop/mobile warning/manual/blocked-stale-spot states; local stored spots are stale, so live numerical preview activation is correctly blocked rather than fabricated. Exact-price flows were verified with isolated test fixtures. Python compilation, JavaScript syntax, all Jinja template parsing and diff whitespace checks passed. Desktop (1280×900) and mobile (390×844) warning layout, manual cancellation, acknowledgment and unavailable-spot activation blocking were inspected on the refreshed isolated local site.

Targeted correction verification (2026-10-01): 135 Smart Pricing tests cover classification/reasons, common 2021↔2025 years, structured collector exclusions, marketing-only diagnostics, grade-only rejection and capped corroboration, explicit certification, friendly stale/missing spots, same-page recovery, malformed-price rejection and changed/expired preview renewal. Fifteen JavaScript tests and eight isolated PostgreSQL tests passed. Full regression run: 1,032 passed, 143 failed, 9 errors, 8 skipped. All remaining failure/error test identities reproduced in an isolated pre-correction baseline; no new failures, and two bid-price failures eliminated. Legacy failures include tests importing retired ACH helpers and expecting removed bid/payment source paths. They remain unresolved and the full repository suite is not certified green. The targeted financial/security/route/spot/cart checkpoint passed 500 tests before the final four added guard/invalid-record cases; all 135 Smart Pricing tests passed afterward. Compilation, JavaScript syntax, Jinja parsing and whitespace checks passed. Desktop (1280×900) and mobile (390×844) outage/retry/manual escape layout was inspected and screenshots saved.

Spot UX now presents “Current metal pricing is temporarily unavailable” with Try Again and Use Manual Pricing. Unsafe confirmation and old prices are cleared. Retry uses the existing normal-pricing provider/cache refresh path when no fresh cache or snapshot exists, then copies only genuinely fresh cache observations with their original UTC timestamps into authoritative snapshots. It never performs financial rematching. Once fresh data arrives, the same page regenerates a signed exact preview and requires consent. Publication of a changed/expired quote rolls back and returns a typed Price updated response; the UI refreshes the preview and requires consent again. Unexpected preview/server errors are logged internally and never rendered as raw details. Local preview remains isolated with email/financial workers disabled and stale actual spot data; live-feed recovery is proven with fixtures, not fabricated browser values.

Production still requires deployment/migration approval, a running existing worker and healthy spot feed, and staging validation with representative real catalog/comparable inventory. Production operation and live-money behavior are not certified by local tests. No additional Smart Pricing credential is required.

## Account/landing refinements — 2026-10-01 (local, uncommitted)

Footer layering follow-up: the shared footer now has a positioned stacking layer above the fixed landing curves, keeping its existing opaque background and normal scrolling. Stylesheet whitespace checks passed and the local preview stylesheet was updated. Browser verification remains blocked by the unavailable admin-policy security check.

Landing curves now occupy a persistent viewport background instead of being clipped at the hero rectangle. Account empty states for ratings/messages lose their surrounding list border only when empty; reports reuse Orders styling. Cart gains the matching icon, a divided header, subtitle and header Browse action. Sold items gain a Sell action; Orders/Sold/Listings gain subtitles. Portfolio header padding is aligned to other tabs and empty allocation replaces the unused chart area with a centered matching empty state. Main-wrapper overflow is corrected so existing desktop sticky navigation columns can follow document scrolling; mobile drawer behavior is retained.

Verification: 44 route smoke tests passed, portfolio JavaScript syntax and whitespace checks passed, and maintained templates compile. Visual verification of this follow-up is blocked by the browser's unavailable admin-policy check; no bypass attempted. No account data or financial behavior changed.

## Authentication UI — 2026-10-01 (local, uncommitted)

Replaced the mismatched 980px/768px two-pane behavior with an all-width Login/Create Account toggle. Server-rendered hidden/inert state exposes only one form before JavaScript; overlapping layout cells preserve the taller form's height. The shell retains alignment without an extra visual box/spacer; a lighter unclipped card shadow replaces the broad fade. Solid blue curves reposition between modes. Authentication navigation slides outgoing main content left and incoming content from the right; form toggles run sequential slides, respect reduced motion and keep inactive inputs inert. Back/forward cache restoration clears outgoing animations. Existing submission routes remain intact.

Verification: 47 route/initial-visibility tests passed, both JavaScript files passed syntax checks, and whitespace checks passed. Browser switching checked at 1280, 897, 685, 390 and 320px: one visible pane, identical card height between modes, no horizontal overflow. Marketplace Sign Up navigation and selected toggle colors verified. No accounts were created, credentials submitted, or production configuration changed.

## Landing redesign — 2026-10-01 (local, uncommitted)

The `/buy` landing page now uses concise physical-bullion messaging, Browse/Sell actions, existing metal filter URLs and the existing real catalog directly below the hero. The blue METEX identity is retained; promotional feature/trust panels, gold treatment and unused spot/trade presentation were removed from this page. Standard, individual and set listing links/prices/images remain data-driven. Empty inventory and filtered empty results are explicit. Shared navigation gains Browse and an accessible search label; other workflows are unchanged.

Visual follow-up: removed the hero metal directory at Rex's request, added solid blue curved background shapes with decorative accessibility semantics, and emphasized “Market prices. Set by buyers and sellers.” Existing metal filters remain beside catalog results. Desktop and mobile previews inspected; 49 route/filter checks passed.

Follow-up: metal filtering now normalizes case/whitespace and restricts both category selection and listing price aggregation. The catalog has visible selected-metal controls and metal-specific empty-state feedback. Regression fixtures cover all four metals across standard, individual and set groups; 49 targeted route/filter tests passed.

Verification: 44 route smoke tests passed; all Jinja templates compiled; all three catalog variants rendered using isolated test-only fixtures; whitespace check passed. An isolated empty database preview ran on localhost:5058. Desktop (1440×900) and mobile (390×844) were visually inspected; mobile header overlap was corrected, metal filtering worked and no mobile horizontal overflow was detected. Screenshots retained as task artifacts. This browser check supersedes the earlier browser-availability blocker for this landing page only. Populated production inventory and authenticated financial UI were not visually tested in this task. No dependencies, provider configuration or production data changed.

## Implementation and verification — 2026-09-30 (local, uncommitted)

Baseline `d152b52`; changes have not been deployed. Older completion statements below describe the September 14 implementation and are superseded where this section identifies incomplete verification.

Implemented: Connect account reuse through protected POST and transfer-capability refresh; connected account/payout webhook routing; exact refund unit allocation and reason-specific surcharge; failure release/retry; won/lost dispute holds and balanced cash-loss journals; ACH return/admin restrictions; evidence-backed carrier confirmation and delivery; canonical admin holds; insurance/signature/high-value/US gates; default-off checkout/release/shipping controls; reviewed recovery reversals and future-proceeds offsets; daily canonical release dispatch; immutable checkout/revision snapshot identity; provider-aware inventory expiration and late-payment compensation; adviser-gated per-listing tax calculations, transaction/reversal queue; durable financial notification/email queue; production shared rate-limit requirement; persistent public/private uploads and checksum-copy tool; dedicated worker entry point; locked category creation preserving finish/grade; pinned dependencies; factual landing-page claims.

Local verification: 387 launch, financial, security, route, delivery, scheduler, storage and reconciliation tests passed after the final changes. Four PostgreSQL 16 concurrent inventory/payment/refund/transfer/category tests passed against a disposable local database. Fresh PostgreSQL schema creation and additive schema rerun succeeded; a custom-format backup restored a simulated funded order and confirmed partial refund with a $95 residual seller entitlement and balanced journals. Three checkout JavaScript regressions passed. Python compilation, admin JavaScript syntax, dependency consistency and whitespace checks passed. Provider calls and SMTP were mocked; no real transactions or customer emails were made.

Full repository suite: 889 passed, 143 failed, four PostgreSQL-only tests skipped without DATABASE_URL, nine setup errors. An isolated baseline had 147 failures and the same nine errors. Four payment-method mock fixtures were corrected to model the current Stripe SDK. Tests for retired unsafe money commands were replaced with explicit retirement and canonical regression coverage. Remaining failures include legacy payment/tax/matching expectations and historical fixtures; they are not suppressed or represented as passing. The full suite is not green and broader certification remains incomplete.

Additional fixes found during execution: terminal internal disputes release only their own canonical holds; pending dispute refunds stay under review and retry the original operation; confirmation replay closes the matching dispute without releasing other holds. Dispute/payment-failure notices use the durable queue and scope affected sellers. Unverified recovery bookkeeping is retired in favor of evidence-backed reversal/offset commands. Production session validation fails closed on database errors. Insurance amounts reject fractional, boolean, missing and nonfinite cents before any ledger write.

Visual desktop/mobile/accessibility QA is blocked: the browser's admin-enforced security policy could not be verified. No alternative browser-control method was used. Backend route tests do not establish visual acceptance. Shared production Redis, email delivery, monitoring alerts, dedicated worker scheduling, provider reconciliation, production data cleanup/migration and production backup restoration require account access/configuration or supervised acceptance. Legacy data removal awaits a production record mapping; unsafe legacy money entry points already fail closed.

External findings were not refreshed during implementation: September 29 Stripe email pauses bank payouts pending marketplace/payment-facilitation review. Dashboard capabilities and live webhook configuration remain unverified. September 14 Render expiry/plan claims require current account verification. Actual bullion insurance, reviewed tax registrations/product codes/seller origins, legal review, production email/monitoring credentials, paid durable hosting/backup restoration, production data migration and supervised provider/real-money acceptance remain external gates. Partial ACH refunds fail closed; this supported-path decision must be resolved with Stripe before offering them.

## Historical September 14 snapshot — superseded by the dated section above

The following implementation/account statements and launch tables are retained as historical context. They are not September 30 production verification.

### Completed in code

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

## Local working changes and documentation refresh — 2026-09-30

Pre-existing, uncommitted `static/js/checkout_page.js` changes improve payment-setup failure messages, retain setup errors, require both client secret and payment ID before review (including saved cards), and allow retries after failed setup. The untracked `tests/test_checkout_payment_setup.cjs` exercises policy rejection, tax failure and network retry. These are local changes, not evidence of deployment or CI inclusion. They were preserved by the documentation refresh.

Architecture/runbook and staging/rollout documents now use the amended repository specification and September 14 policies. Historical reports remain in place, including all 21 reports unique to `Claude Code Reports/`; the duplicate archives have not been cleaned up. No application relocation or provider operations were performed.

Start with [AGENTS.md](../AGENTS.md), [architecture](DEVELOPER_ORIENTATION.md), [runbook](../FLOW_OF_FUNDS_RUNBOOK.md), [staging matrix](STAGING_PAYMENT_TEST_CHECKLIST.md), [sign-off](FINAL_MANUAL_STAGING_CHECKLIST.md) and [rollout](PRODUCTION_ROLLOUT_CHECKLIST.md). Maintain these existing documents in the same task as relevant changes; retain dates and verification limits.

Documentation-refresh verification: all relative links in the maintained entry-point, architecture, runbook, status and checklist documents resolve. All 359 tracked historical documents labeled in the repository retain their original contents below the notice. Report folders still contain 163 and 184 Markdown files, with 163 identical pairs and 21 unique reports preserved. The existing local checkout regression ran with `node --test tests/test_checkout_payment_setup.cjs`: 3 passed, 0 failed. This does not establish full-suite, browser, PostgreSQL, provider or production readiness.

Smart Pricing simplification verification (2026-10-01): 145 Smart Pricing tests and 514 targeted financial/security/route/storage/spot/cart tests passed; 16 JavaScript tests and eight PostgreSQL tests passed. Full suite: 1,042 passed, 143 failed, nine errors, eight skipped; the same legacy failures remain. Normal spot-cache freshness now uses UTC and rejects future timestamps; the API accurately marks stale fallback values and the sell preview does not advertise them as current. No prices or comparable inventory were fabricated.

Login decoration/footer boundary (2026-10-01, local uncommitted): moved the auth-only 60px footer gap into the decorated login region and removed the auth footer margin. Shapes now continue to the opaque footer without a blank clipping strip; other pages retain existing footer spacing. Three auth visibility tests and whitespace checks passed. Browser measurements confirmed zero gap at desktop and 390px mobile, with no mobile horizontal overflow; screenshot saved.

Pricing interface refinement (2026-10-07, local after b8cb4f5): new listings open in unconfirmed Smart Pricing, inside one clipped pricing viewport with sliding manual/Smart contents, touch swipe controls, reduced-motion support and an animated rounded three-strategy selector. Existing manual edits retain their mode. Strategy explanations are one line. Incomplete standard item specifications request completion before classification/provider calls, avoiding misleading rarity warnings for a blank item; complete unknown/collector/set identities still require server acknowledgment. The isolated preview has no primary metal-feed credential, so refresh depends on the existing fallback; actual browser refresh recovered to insufficient comparable data for the checked standard item, without fabricating a quote. 145 Smart Pricing backend tests passed; UI/checkout tests, syntax/template and whitespace checks passed. Desktop and 390px mobile layouts were inspected, manual transitions verified, zero horizontal overflow measured, and screenshots saved. Production pricing still requires a dependable configured spot feed and defensible comparable inventory.

Smart Pricing demo (2026-10-07, isolated local preview only): user-authorized simulated data in bucket 88886: nine active 1 oz PAMP Suisse gold-bar listings, eight distinct simulated competing sellers and eight approved/delivered synthetic sale snapshots over eight days, with frozen historical metal basis and $50–$85 premiums. Eight simulated bucket chart points are present. The testuser-owned listing 99997 can be explored at `/sell?edit_listing_id=99997`. Local preview shows a persistent simulation banner; no provider payment, refund, shipment, payout or email was performed. Current spot remains feed-derived. All three strategies produced signed non-seeded sales_exact previews; repeat-safe seeding, accounting arithmetic, one-bucket counts and unchanged repository database were verified. `scripts/seed_smart_pricing_demo.py` rejects databases outside marked temporary preview roots. These records are test fixtures, not verified financial accounting or production transaction history.

Compact Smart Pricing amendment (2026-10-07, local uncommitted): valid signed previews now automatically populate the premium and listing summary; the extra Use step is removed from the visible flow at Rex’s request. Final publish/update confirmation remains mandatory, and changed/expired quotes still roll back on the server, close confirmation and regenerate for renewed review. Missing, malformed, insufficient and pending quotes remain unselected and block submission. Display centers on the initial total with metal value beneath, one dollar-total market range/midpoint line, transparent but subdued proceeds/5% fee disclosure, compact manual/refresh links, and keyboard-accessible animated info expansion. Duplicate strategy/premium/confidence labels are hidden from the visible quote. Backend pricing and freshness rules are unchanged. 145 backend and 20 UI/checkout tests passed, including automatic signed selection, stale-response rejection, immediate invalidation, insufficient evidence, retry and manual restoration; template parsing, syntax and whitespace checks passed.

### 2026-10-07 — pricing visual polish (local, uncommitted; baseline b8cb4f5)
Moved the shimmering blue Smart Pricing link to the manual header; removed its helper copy, matched rounded arrow strokes to link text, added decorative strategy icons and highlighted the market-value estimate. Reduced-motion preferences disable shimmer. Bucket main overflow now allows card shadows to fade into side gutters while body overflow still prevents horizontal page scrolling. Verified both pricing modes and bucket shadows in the isolated local preview; 17 Smart Pricing UI tests pass. No pricing calculation or financial flow changes.

### 2026-10-07 — bucket and bid form polish (local, uncommitted; baseline b8cb4f5)
Removed shadow clipping from bucket columns and thumbnail row while retaining rounded gallery image clipping. Bid pricing uses a rounded, keyboard-accessible disclosure menu synchronized with its original select; amount inputs fill their row. Removed the ACH callout checkmark. Continue now disables on Payment when no saved method/selection exists and re-enables on earlier steps or selection; subdued blur marks the disabled state. Local browser verification covered pricing menu, amount entry, navigation through Delivery to the disabled Payment step and bucket shadows, without submitting a bid. Two payment-navigation regression tests and JavaScript syntax/diff checks pass. Provider and production behavior were not changed or certified.

### 2026-10-07 — standard dropdowns and empty cart (local, uncommitted; baseline b8cb4f5)
Shared rounded option menus enhance single-choice native selects, including dynamically loaded forms, preserving native form values and input/change events. Disabled and reset states, keyboard arrows/Escape and outside clicks are supported; top-layer menus avoid modal clipping. Bid pricing keeps its matching disclosure. Empty-cart content now occupies the full page width. Local browser checks confirmed exact horizontal centers at 1280px and 390px viewport widths, dynamic bid address menus, NY selection updating the original select, and unclipped menus. JavaScript syntax and diff checks pass. No bid was submitted.

### 2026-10-07 — saved website version
Current visual refinements, shared dropdowns, empty-cart alignment and isolated simulation seeder are being saved together from baseline b8cb4f5. Info control now has equal fixed 28px bounds overriding phone button sizing; verified 28×28 at 390px viewport. Verification: 145 Smart Pricing backend tests and 22 UI/payment-navigation tests pass, plus syntax/diff checks. Simulation inventory and auto-login remain only in the temporary preview, not production data or application authentication. GitHub main update is the requested source version; hosted deployment completion is not yet verified.

### 2026-10-07 — rigorous Smart Pricing stress verification
Baseline: c030f42. Added regression tests in tests/test_smart_pricing.py; no production algorithm changes were required by this run.

| Check | Result |
| --- | --- |
| Smart Pricing backend, including expanded stress scenarios | 214 passed |
| Interface, stale-response handling and payment navigation | 22 passed |
| Canonical financial acceptance and launch safety | 84 passed |
| Related cart, checkout spot, scheduler, quantity and direct-buy suites | 84 passed, 9 failed |
| PostgreSQL concurrency | 8 skipped: no test PostgreSQL connection configured |

Stress coverage: 600 spot movement/rounding calculations across Gold, Silver, Platinum and Palladium, three strategies and five weights (1 oz, half oz, tenth oz, 1 g, 10 oz); 72 time-controlled scheduled worker cycles spanning rising/falling comparable premiums, spot reversals, stale-price holds and recovery; 24 authenticated preview quotes through spot reversals, preserving integer-cent amounts and canonical seller-fee identities, rejecting each old price-bound token and accepting the refreshed quote. Concurrent evaluation with 2/4/8/16 threads produces exactly one adjustment and the remaining calls hold under cooldown. Worker checks enforce seller minimum, bounded movement toward target, replay safety and complete persisted audit history (dashboard intentionally shows only 20 events). Existing tests also exercise held inventory, suspended sellers, settings changes, insufficient/contaminated comparisons, expiry/tampering and history-write failure rollback.

The nine related-suite failures are in unchanged legacy checkout-route fixtures/assertions: missing users.session_version causes authentication to fail; routes also require current checkout identity instead of the prior direct-finalization contract. They do not constitute a clean checkout certification and remain unresolved. The canonical current financial acceptance suite passes. Initial new-test failures were corrected test assumptions (weight spelling 'gram' versus supported 'g', and treating the dashboard's 20-row history cap as the full audit table); no production failure was hidden by relaxing the algorithm assertions.

Limits: SQLite fixtures and simulated time/data do not prove PostgreSQL concurrency, live feed uptime, hosted scheduler configuration or actual sale-speed/price optimization. This run placed no real orders/bids and used no live payments. Overall 404 passing tests, 9 legacy failures and 8 PostgreSQL skips across the executed groups.

### 2026-10-07 — live feed and historical-outcome audit
Read-only live probe: Yahoo fallback returned all four metals in 3/3 rounds (1.26s, 0.65s, 0.62s). Primary METALPRICE_API_KEY is absent in the local process, so primary provider access was not tested. End-to-end live refresh/cache/Smart Pricing quote/signature validation passed for Fast, Balanced and Big using an isolated copied database and simulated comparable evidence. No orders, bids, payments or original database writes were performed.

Important unresolved live-feed provenance issue: Yahoo metadata identifies FUTURE instruments in USD; provider quote timestamps were 604–667 seconds old during the audit. fetch_spot_prices_from_yahoo returns price values without their provider timestamps. save_spot_prices_to_cache stamps CURRENT_TIMESTAMP and source='metalpriceapi' even for Yahoo fallback, so successful fresh fetches can make delayed underlying quotes appear newly priced and incorrectly sourced. This audit proves momentary availability and integration, not long-run uptime or true spot accuracy. Provider age/source must be preserved and checked before certifying freshness.

Outcome data: local canonical executions/snapshots/fills/shipments/history counts were all zero. Isolated preview contains 8 approved delivered executions with frozen basis, all smart-demo simulations. No real eligible sale sample is available locally for retrospective sale-price/speed evaluation; live real-market strategy effectiveness remains untested. No production DB or hosted provider configuration was accessed.

### 2026-10-07 — marketplace hero simplification
Baseline: 24764f9. Centered the /buy hero copy and CTA row across desktop and phone widths; removed the eyebrow, explanatory paragraph and metal filter row. Added “No dealer-set prices” beneath the market message and replaced CTA arrows with decorative search and dollar icons. Existing browse/sell destinations remain intact. Local browser verification at 1280px and 390px confirmed centered content, visible icons and no filter row; diff checks pass. Saved to the GitHub review branch; main merge and hosted deployment remain pending approval.

### 2026-10-07 — equal hero button widths
Baseline: 1f52af7. Browse Bullion and Sell Bullion now share responsive widths: 190px on desktop and 179px at a 390px phone viewport. Local browser measurement and visual checks confirmed equality and side-by-side phone layout; diff check passes. Saved on the existing GitHub review branch.

### 2026-10-07 — uppercase hero and balanced framing
Baseline: 7b4b7bf. Hero headline displays in uppercase with adjusted sizing. Equal-width actions now use centered labels/icons, restrained blue, consistent 50px height and refined borders. Matching decorative curves frame the left side, with smaller phone shapes. Browser verification at desktop and 390px confirmed visible uppercase text, equal 179px phone buttons and no horizontal overflow. Diff check passes; saved to the review branch.

### 2026-10-07 — catalog hover lift
Baseline: 9cdb3c2. Mouse hover lifts the complete product link (image and details) by 6px with a 220ms transform transition. Limited to fine-pointer hover devices; reduced-motion preference removes movement. Browser inspection confirmed the loaded transform transition and desktop hover capability; diff check passes.

### 2026-10-07 — product-first marketplace introduction
Baseline: 3d9fc20. Updated hero to “Buy and sell bullion. Set your price.” with plain supporting copy, smaller pale background curves and a three-step buying row. Native disclosure explains checking product/payment/shipping terms, tracking purchases and contacting support, without unsupported escrow or verification claims. Shared template macros preserve custom listing titles, avoid repeated mint/line prefixes, add product type where absent, omit missing year values and show purity where supplied. Prices are more prominent. Browser checks confirmed cleaned PAMP Suisse Bar titles, mobile disclosure expansion and no overflow at 390px; diff check passes. Saved to existing review branch.

### 2026-10-07 — prominent selling action
Baseline: 993d109. Sell Bullion now uses solid blue with white text/icon and a darker hover state, matching Browse visual weight. Verified in local browser; diff check passes.

### 2026-10-07 — light blue selling action
Baseline: fc576de. Sell Bullion uses a light blue fill and dark blue label/icon with a slightly deeper hover fill. Local browser visual verification and diff check pass.

### 2026-10-07 — numbered buying timeline
Baseline: 32e75af. Expanded buying guide uses a semantic ordered list, numbered circular markers, a vertical connector and separate headings. Existing disclosure and explanatory copy remain. Browser verified expanded content and visual timeline; diff check passes.

### 2026-10-07 — smooth buying guide expansion
Baseline: 14ff248. Native buying disclosure opens with a 280ms height animation, moving following content down smoothly. Cancels previous animation on toggles; reduced-motion preferences skip animation. Browser expansion check showed complete content and no page errors; JavaScript syntax and diff checks pass.

### 2026-10-07 — animated guide closure
Baseline: 1cf9813. Buying guide animates both directions, preserving content until closing finishes and reversing from its current height on quick toggles. Reduced-motion skips animation. Local browser opening/closing showed no errors; lifecycle check confirmed closure waits for animation completion. Syntax and diff checks pass.

### 2026-10-07 — homepage discovery, return visits and quote provenance
Baseline: f38c6eb. Shortened the hero, clarified asking-price/bid behavior, moved the animated buying guide below inventory and removed repeated section headings. Added accessible catalog search, multi-term field matching, gold-bar/silver-coin shortcuts and existing new-listing sort. Cards show purity when present and distinguish active offers from historical recorded prices. Recent primary spot references can show per-item premium context; unavailable, stale, unknown and futures references are omitted. Buying explanation now states the approved three-day seller-fault reporting window and no buyer-remorse returns without advertising unverified escrow/insurance guarantees.

Browser-local saved products/searches persist across reloads. Saved view, removable entries, target prices, return-visit price-drop/availability/target notices and storage-failure handling are implemented. Preferences are not account-synced and no email/push/background notification service is claimed. Browser verification covered saving/removing, target match, persistence, saved-only view, gold-bar multi-term results, saving/clearing searches and 390px no-overflow layout. Test preferences were cleared after verification.

Corrected audited Yahoo provenance flaw: actual provider timestamps survive cache writes and scheduled snapshot ingestion; Yahoo values are labeled futures, not MetalpriceAPI. Primary timestamps are also retained and validated. Untimestamped numeric input is marked unknown/epoch, not made fresh. UTC-aware deduplication and price-age calculation are supported. Five provenance regression tests plus 46 scheduler/chart tests pass; 214 Smart Pricing tests pass (265 total). Scheduler fixture quotes now explicitly supply UTC provider provenance; their timestamp parser supports offsets. A missing cache table in chart-route fixtures exposed and fixed a read-only display edge case. JavaScript syntax and diff checks pass.

Remaining limits: no live primary credential/uptime certification, no real sale-outcome proof, no PostgreSQL concurrency certification, no new account-synced watchlist or email/push delivery, and no measured retention lift. Final product images and inventory quality depend on actual catalog content. Existing checkout/provider/insurance/deployment gates remain. Saved locally and to the review branch; production merge/deployment is not performed.

### 2026-10-07 — remove duplicate catalog discovery row
Baseline: db501c3. Removed the entire requested discovery row: catalog search/label/button, browsing shortcuts, saved-products toggle, saved-search controls and panel. Shared navigation search remains; catalog listings now follow the hero directly. Per-product saving, target prices and return-visit notices remain, with their status below the catalog. Removed unused row styles and script dependencies to avoid null-element failures. Jinja template parsing, JavaScript syntax and diff checks pass. No financial behavior changes; production deployment remains outside this review-branch update.

### 2026-10-08 — round marketplace photo corners
Baseline: a79de49. Homepage product image containers use an 18px corner radius instead of 6px, with overflow clipping retained for actual photos and placeholders across screen sizes. Diff check passes; local preview stylesheet updated.

### 2026-10-08 — simplify listing price typography
Baseline: cca4ef3. Removed “From” from active homepage listing prices across all card types and changed price weight from 650 to 400. Historical prices retain their “Last recorded” label. Template parsing and diff checks pass.

### 2026-10-08 — restore consistent price font weight
Baseline: af837e9. Restored the previous 650 weight for all homepage listing prices at user request; the removal of “From” remains. Diff check passes; local preview stylesheet updated.

### 2026-10-08 — grouped checkout currency display
Baseline: f2e613f. Dynamic checkout tax, processing fee, summary total and Place Order total use en-US USD currency formatting with comma grouping and two decimals, matching server-rendered amounts. Calculations are unchanged.

### 2026-10-08 — center compressed account empty states
Baseline: 2c3540e. Shared account empty states use border-box sizing, full parent width, centered text/items and narrow-screen padding. Cart columns stretch when the layout stacks below 900px, removing the shrink-to-content column that shifted the empty panel left. Covers standard tab, filter-empty and ratings states. Diff check passes.

### 2026-10-08 — align password recovery with login design
Baseline: fee44ac. Forgot/reset pages reuse login’s pale curved background, white card, shared form spacing, type and buttons. Removed old animated dark blobs, duplicate M badge, extra header spacer and inline card sizing. Kept recovery fields, IDs and submission logic unchanged. Template parsing and diff checks pass.

### 2026-10-08 — remove homepage buying guide
Baseline: c589edb. Removed the entire homepage buying guide, three-step row and expanded timeline at user request, and stopped loading its unused animation script on this page. Template parsing and diff checks pass.
