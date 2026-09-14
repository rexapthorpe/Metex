# Metex Flow of Funds Implementation Specification

## Launch policy amendment — third-party grading removed

Third-party grading is not part of the launch product. New carts, bids,
checkouts, execution snapshots, charges, shipments, notifications, admin
actions, and customer pages MUST NOT offer, request, price, or create a grading
service or grading custody leg. Server endpoints MUST force grading to the
disabled state even when an old or forged client submits legacy grading fields.
Legacy grading columns may remain temporarily for schema compatibility and
historical reads, but they are deprecated and MUST NOT drive new behavior.

This amendment supersedes every grading-add-on requirement later in this
document for launch. Those passages remain only as the specification for a
future, separately approved reintroduction. No grading vendor, fee,
incurrence rule, form, address, refund allocation, shipment leg, or payout
gate is required for launch.

Approved launch policy also requires a fresh server-side price comparison
immediately before confirmation of every spot-linked purchase or bid fill. If
the cent-denominated price changed, the operation MUST stop and present the
new price for renewed buyer or seller consent. A quote or reservation may live
for at most 900 seconds, but that time limit does not authorize execution at a
price that has changed.

For launch ACH payments, Stripe `payment_intent.processing` creates only a
customer/seller-facing `SOLD_PENDING_ACH` projection and continues the durable
inventory hold. It MUST NOT create an execution, seller payable, fee/spread
revenue, ledger journal, shipment authorization, or tracking deadline. The
same bound PaymentIntent reaching `succeeded` promotes that projection to the
funded execution. Only then may insurance and shipment authorization proceed,
and only shipment authorization starts the three-calendar-day tracking clock.
A later ACH return is a separate payment-risk event that immediately holds the
affected funds and enters reason-specific recovery review.

Version: 1.0 · Date: 2026-09-11 · Status: authoritative implementation target; unresolved production configuration gates are explicitly identified below.

## 1. Scope, authority, and completion standard

This specification governs all Metex Buy Now purchases, bid matching and acceptance, payment attempts, inventory reservations, orders, seller fills, grading, shipping, insurance, refunds, internal disputes, processor chargebacks, ACH returns, transfers, bank payouts, and recovery. It applies equally to browser, API, webhook, worker, support, seller, and admin entry points.

**If existing code, tests, database defaults, UI text, or legacy documentation conflict with this specification, change them. Do not preserve legacy transaction behavior merely because it exists or a test expects it.** A passing legacy test is not evidence of compliance.

Precedence, highest first:

1. The approved business rules consolidated in this specification from the latest explicit instructions and corrections in the “Project Status Summary” conversation.
2. Explicitly approved, versioned policy configuration within the bounds this specification permits. Configuration cannot silently change the 5% seller fee, zero ACH buyer surcharge, full positive spread capture, or other approved invariants.
3. The deterministic engineering requirements and explicitly labeled implementation defaults below.
4. The September 10, 2026 Metex launch audit as evidence of defects and required validation, not as a competing business policy.
5. Existing code, historical drafts, comments, and tests.

The latest corrections supersede earlier merchandise-only card-fee calculations, optional pre-approval ACH shipping, immediate bid reservation release on failure, grading of selected units within one identical line, grader-receipt payout, and unspecified non-graded delivery holds. They also supersede any suggestion that incurred grading fees become refundable if a vendor later credits Metex.

Normative terms: **MUST/MUST NOT** are requirements; **DEFAULT** is a deterministic engineering choice, not newly approved commercial policy; **ADMIN/POLICY CONFIGURATION REQUIRED** means the architecture must support the choice and an Authorized Metex Administrator must supply the identified decision/evidence. Missing mandatory configuration must block the affected operation with a visible reason, never silently substitute a business rule. Purely technical work and sandbox tests must continue using named fixtures.

This is a repo-ready implementation contract, not certification that code is implemented, deployed, or approved by a payment, tax, insurance, or grading provider. Provider-specific API versions, event mappings, supported capabilities, and commercial conditions must be verified during implementation. No live money movement is authorized by this document alone.

### 1.1 Source baseline and audit limits

Sources: the explicit approved rules accompanying this file request; available “Project Status Summary” history, including its later corrections; and `audit-2026-09-10/Metex-launch-audit.md` (also supplied as the conversation's audit attachment). Audit baseline commit: `8118e4d13305fc5b37d5ff808d53807825f9b0be`. Paths in §17 are audit-era navigation hints; implementing agents must confirm actual route registration and current code before editing.

The audit reproduced acceptance of an incorrectly bound payment, reuse of a payment to create two orders, and unauthorized tracking mutation. Its focused 78-test pass was overlapping coverage, not launch approval. Full production-equivalent PostgreSQL, browser, provider integration, and fault testing remained outstanding. Do not copy obsolete example economics from earlier drafts.

### 1.2 Non-negotiable invariants

- One successful buyer payment funds at most one execution and its single order aggregate. One checkout version has at most one accepted successful payment. Duplicate successful external charges become excess-payment compensation cases, never extra orders.
- One seller fill has exactly one canonical seller payable after verified payment success, with independently allocated quantities. Before success there is no finalized seller payable, fee revenue, or spread revenue.
- Seller fee is 5% of seller execution value; seller contractual net is 95%, rounded as §3 specifies. Buyer never pays an additional 5% marketplace fee.
- Metex captures all positive buyer-minus-seller spread for each fill; spread is never negative. Reject an execution whose buyer value is below seller value; do not silently fund a deficit.
- ACH buyer surcharge is zero. Actual ACH cost and required UPS insurance are Metex expenses; neither reduces seller contractual net.
- All card surcharge calculations include merchandise, tax, grading, and approved other buyer charges in their base. Gross-up is the default approved formula for a percentage assessed on the final charge.
- Taxes are separate liabilities. Grading is separate from seller revenue and seller fee calculations.
- Money, inventory, holds, refunds, and fulfillment must remain attributable to the affected seller and units. No seller's shortfall may be funded by another seller's payable.
- No shipment authorization before verified payment and, for ACH, the configured approval condition. No payout while an applicable hold exists.
- Connected-account transfer is not final bank payout. Recovery is not an ordinary refund. Processor chargeback is not an internal buyer dispute.
- No browser session, email, dashboard label, provider timeout, or admin button alone proves money moved.

## 2. Glossary and transaction boundaries

| Term | Canonical meaning |
|---|---|
| Buyer execution unit price `b` | Frozen merchandise price agreed by the buyer, excluding tax, grading, and surcharge. For an executed bid this is its agreed execution price, not a mutable current quote. |
| Seller execution unit price `s` | Frozen merchandise price agreed by the seller before the 5% deduction. Never confuse this with net payable. |
| Distinct line | Product/specification group purchased on the same terms with one all-or-none grading election. Normalize equivalent duplicate cart entries before election; seller splits do not permit bypassing this rule. |
| Seller fill | One seller's allocation of a line at one pair of execution prices and grading terms. Multiple prices/products require separate fills. |
| Execution | One frozen commercial event, funded by one accepted successful payment, containing one or more seller fills for one buyer. |
| Order | Customer-facing aggregate for an execution; its display status is derived from independent child records. An unpaid checkout is not a paid order. |
| Parent bid | Buyer's continuing quantity/price mandate; may produce many separate executions over time. Placing a bid does not charge money or recognize revenue. |
| Reservation | Durable exclusive claim on listing quantity and, for bids, bid quantity before payment commitment. |
| Payment approval | Verified provider success plus configured rail-specific risk/approval conditions. An ACH initiation, estimated settlement date, or pending debit is not approval. |
| Seller payable | Metex's recorded net obligation to one seller fill, held until release gates pass. |
| Release approval | Internal permission to submit an exact seller transfer amount, subject to rechecking all gates. |
| Transfer | Movement to the seller's connected provider account. |
| Bank payout | Provider-confirmed movement from a connected account toward or into a bank; separately pending, paid, or failed. |
| Grading cost incurred | Vendor-specific, evidenced, irreversible service-cost commitment event; independent of service receipt, result, or vendor payment timestamp. |
| Shipment leg | One custody movement: seller→buyer, seller→grader, grader→buyer, or return→seller. |
| Hold | Independently releasable block with scope, reason, source, and lifecycle; multiple holds can coexist. |
| Refund | Platform-authorized buyer credit against an original charge with exact component allocations. |
| Chargeback | External processor/bank dispute lifecycle, including provisional debits and final outcomes. |
| Recovery | Collection of an established liable party's obligation after proceeds have left the relevant held balance. |
| Ledger journal | Immutable balanced postings recording an economic event. Corrections use compensating journals. |

**Boundary rules:** One checkout can contain multiple sellers. Each fill has its own payable and independent shipment, refund, dispute, transfer allocations, and recovery records. Physical packages may contain several fills only for the same seller and compatible route, with an explicit quantity/value mapping. Never pool different sellers in one transfer instruction. One bank payout may include multiple transfers for the same seller only if a mapping preserves their identities. Seller acceptance of multiple bids creates independent buyer payment events, even if initiated through one batch UI. Bid partial fills at different times MUST create separate checkouts/executions/payments tied to the parent bid.

## 3. Exact financial formulas and rounding

### 3.1 Monetary representation

DEFAULT: launch monetary examples and initial implementation use USD, integer cents, positive integer physical quantities, UTC instants, and decimal/rational arithmetic. Other currencies require explicit provider/tax configuration, currency exponent support, and separate journals; do not infer USD from the workstation locale or accept a mismatched provider currency.

Never use binary floating point for money. Persist quoted unit prices as integer minor units. Any spot-based calculation uses a versioned decimal pricing rule and rounds to a unit price before freezing the execution. Freeze quote timestamp, source, freshness decision, and pricing rule. Tax amounts use the approved tax engine's authoritative rounding, not an independent percentage approximation.

`R(x)` means round nonnegative minor-unit rational `x` to the nearest integer, exact halves upward. Signed reversals negate original amounts; do not reround negatives. Fee rounding occurs once per seller fill, not once per unit and not across different sellers. Conservation takes precedence over independently rounding both 5% and 95%.

### 3.2 Per-fill and checkout equations

For fill `f` with quantity `q_f`:

```text
B_f = q_f * b_f                         buyer merchandise value
S_f = q_f * s_f                         seller gross execution value
D_f = max(B_f - S_f, 0)                 captured spread; reject B_f < S_f
F_f = R(S_f * 5 / 100)                  seller-funded marketplace fee
N_f = S_f - F_f                         seller net before legitimate recovery
B_f = N_f + F_f + D_f                   required exact cents identity
```

No fee on grading, tax, card surcharge, or insurance is added to `S_f`. No seller fee is added to `B_f`.

For grading, persist `grading_fee_basis` and the flat rate. The earlier explicit rule is a flat fee per item; **DEFAULT: `PER_UNIT`, `G_line = q_line × flat_unit_fee` for an elected eligible line, otherwise zero.** The latest wording also mentions item/order-line pricing. `PER_LINE`, where `G_line = flat_line_fee` regardless of quantity, is supported but **ADMIN/POLICY CONFIGURATION REQUIRED** before use. Never silently switch between them. Flat means no percentage of merchandise value. Grade all units in an elected line, including units allocated to different sellers; different product lines may make different elections.

```text
M = sum(B_f)
G = sum(G_line)
T = sum(authoritative tax component amounts)
O = sum(explicitly approved other buyer-paid charges)
P = M + G + T + O                       pre-card-fee total
r = 299 / 10000                        initial card rate, 2.99%
C_card = R(P * r / (1 - r))             gross-up in minor units
C_ACH = 0
A = P + C                              exact provider charge amount
```

`0 <= r < 1` is mandatory. `formula_id=GROSS_UP_PERCENT_FINAL`, rate, rounding version, and computed amounts are frozen. A different rate/formula requires approved configuration and prospective snapshots. Fixed processor costs are not implicitly added; if actual pricing includes them, Metex records actual cost and residual expense until a revised buyer-fee formula is approved. Method switching requires a new immutable snapshot version and buyer authorization of its exact total; retire the old payment safely before enabling the new version. Never mutate the amount of a payment already processing or successful.

Tax must be calculated for the approved address and product/service classification, including an approved decision on whether any surcharge is taxable. If that creates interdependence with gross-up, the tax/quote adapter must return a deterministic solved total and component breakdown under a separately tested approved formula. Do not invent a tax rate, assume exemption, silently return zero for missing address, or fall back to 8.25% on vendor failure. Block quote/payment on unavailable mandatory tax evidence.

### 3.3 Attribution and partial-quantity rounding

Allocate checkout-level surcharge `C` across fills and their components using their frozen pre-fee amounts as weights. Allocate line-level grading charges across seller fills by purchased quantity unless a vendor's approved fee basis provides exact allocations. Every other shared charge requires a stored allocation rule; DEFAULT quantity weighting within the affected line, never across unrelated sellers. Actual processor expenses use provider attribution where available, otherwise a stored proportional charge-value allocation. Package insurance expense uses insured-value weights among its mapped fills.

Use largest remainder for any allocation of integer `V` with nonnegative integer weights `w_i`:

1. Calculate exact `V*w_i/sum(w)`; take each floor.
2. Distribute remaining cents to descending fractional remainder; ties by ascending immutable `(line_id, fill_id, unit_ordinal, component_code)`.
3. Require the allocated total to equal `V`. For zero weights and nonzero `V`, reject rather than invent attribution.

Persist per-unit component slices before payment: `B_u`, `S_u`, `F_u`, `N_u=S_u-F_u`, `D_u=B_u-S_u`, grading, tax, other charges, and surcharge shares by underlying component. Allocate `F_f` across equal-price units; derive net as the complement. Never independently allocate net and fee in a way that breaks identities. Serialized units use stable serial identity; otherwise assign unit ordinals and DEFAULT select lowest remaining eligible ordinal for quantity operations. Lock them. A refunded unit cannot be refunded again.

Refunds reverse stored slices, not today's price or a freshly computed percentage. Full quantity reversal must sum exactly to the original fill amounts despite earlier partial refunds. A price concession without quantity return requires an explicit component allocation and approved policy; DEFAULT route to admin review, never infer an inventory return from a dollar amount.

### 3.4 Revenue, expenses, and liabilities

```text
Metex merchandise gross revenue = sum(F_f + D_f)
Metex approved gross revenue = merchandise gross revenue + approved_other_revenue
Transaction contribution = approved gross revenue
                         + card surcharge collections retained
                         - actual card processing cost
                         - actual ACH processing cost
                         - UPS insurance expense
                         - other Metex expenses
                         - applicable revenue reversals / unrecovered losses
```

The contribution formula is an operational measure, not a change to seller net. Surcharge collections and processing expense must be separately reported; DEFAULT record surcharge in a dedicated processing-cost-recovery clearing account pending approved accounting classification. Do not silently count it as 5% fee or spread revenue. Grading is a service liability by DEFAULT; principal/agent revenue recognition, vendor payable amount, and any service margin require the commercial agreement. Taxes are always separate liabilities, with remittance/receivable adjustments where tax has already been remitted. Gross fee/spread allocation starts only at verified payment success; accounting recognition timing beyond the operational ledger is an approved accounting configuration.

## 4. Canonical data model and database constraints

Names describe required logical entities; current tables may be migrated or mapped if all semantics and constraints are enforced. All entities have immutable ID, created/updated UTC timestamps, tenant/platform context where relevant, schema version, and optimistic `row_version`. Financial children also carry currency and their parent IDs as foreign keys.

| Entity | Required fields and relationships |
|---|---|
| `PolicyVersion` | Version, effective time, typed values, approval identity/time, reason, evidence, scope, prior version. Append-only approved versions. |
| `Bid` | Buyer, normalized product/specification, execution-price mandate, requested/committed/reserved/open quantities, expiration, payment mandate/reference, status, matching policy version. |
| `CheckoutAttempt` | Buyer, request key/hash, parent bid/batch references, snapshot version/hash, status, reservation IDs, quote expiry, failure/correction deadline, active payment attempt, superseded-by link. Durable before calling provider. |
| `ExecutionSnapshot` / `SnapshotLine` | Canonical immutable payload described in §5, original unit slices, pricing/tax/config/election evidence. Unique `(checkout_id, version)`. |
| `InventoryReservation` | Checkout, listing, seller, units/quantity, bid quantity claim if any, state, creation/expiry, payment-in-flight flag, commit/release reason. |
| `PaymentAttempt` | Checkout snapshot, provider/account/environment/customer, actual method/rail, intent/charge IDs, expected/received amounts, status, success/approval/return times, approval policy/evidence, operation ID. Multiple failed attempts allowed, one accepted success. |
| `Execution` / `Order` | Unique checkout version and accepted payment reference, buyer, snapshot hash, paid-at, child fill IDs; order summaries are projections. Recovery execution may have no fulfillable fills and an explicit compensation status. |
| `SellerFill` | Execution, line, seller, listing/spec snapshot, quantity/unit identities, `B,S,F,N,D,G,T,O,C`, lifecycle, fulfillment route, ship authorization/deadline, risk/return references. |
| `SellerPayable` / `PayableAllocation` | Unique fill, original net, held/encumbered/transferred/reversed/remaining amounts, unit allocations, release status, holds and operation references. No implicit payable before success. |
| `Shipment` / `ShipmentAllocation` | Leg type, custodian, authorized actor, sender/recipient/address snapshots, fill/unit mappings, carrier/service, normalized tracking, validation evidence, possession/delivery instants, state, insurance links. |
| `GradingLeg` / `GradingAllocation` | Vendor/service, elected line/fill/units, fee basis/rate, form/version/hash, specifications, approved buyer final address, intake/result evidence, cost-incurred events and amounts, state, outgoing/return shipment IDs. |
| `InsurancePolicy` / `InsuranceClaim` | Leg/shipment/fill allocation, provider/reference, coverage terms/version, eligible contents, insured value/limits/currency, premium, purchased/effective dates, origin/destination/tracking, claim deadline/status/evidence, recoveries and loss links. |
| `FinancialOperation` | Durable logical command, actor/cause, scope/component allocation, idempotency key/request hash, amount/currency, provider references, state, lease/fencing token, retry count/next time, errors, result, timestamps. |
| `Refund` / `RefundAllocation` | Reason, requester/approver, affected fills/units, component vector, return/policy/incurred-cost evidence, reserved capacity, provider refund IDs, status; seller recovery link when applicable. |
| `Dispute` / `DisputeAllocation` | Internal or processor type, external ID, reason, payment/fill/units/amount attribution, holds, evidence/deadlines, provisional debit, adjudication/liability/policy, resolution operation. |
| `Hold` | Scope (payment, fill, units, seller account), reason, source ID, amount if bounded, created/released instants, authority/evidence; unique active source/scope. |
| `Transfer` / `TransferAllocation` | One seller/connected account, source charge/funds reference, payable/unit amounts, operation, provider transfer ID, reversal amounts/status. |
| `Payout` / `PayoutAllocation` | Connected account, provider bank-payout ID, transfer provenance allocations, bank status, amount, estimated/actual arrival, failure code, retry link. Unmapped provider aggregation remains unresolved, never guessed. |
| `RecoveryCase` / `RecoveryCollection` | Liable party, source refund/chargeback/return/loss, policy/reason, assessed principal and other approved components, outstanding/collected amounts, ladder stage, operations, reserve advance, disposition. |
| `LedgerJournal` / `LedgerEntry` | Immutable double-entry records, required fields in §6; unique event/component posting identity. |
| `WebhookInbox` / `OutboxEvent` | Provider event ID/account/environment, authenticated payload digest and protected payload, arrival/provider times, processing state/error; outbox recipient/topic, business event key, delivery state. |
| `AuditEvent` / `ReconciliationCase` | Actor/source, before/after versions, transition/reason/evidence, linked operations; discrepancy type/amount, owner, age, remediation, verified resolution. |

Required database guarantees:

- Unique provider payment/charge binding scoped by provider account and environment; unique accepted payment per checkout version; unique execution/order per accepted payment; unique payable per fill.
- Unique request key per actor/operation scope with a stored request digest. Same key/different request is a conflict. Unique provider event per inbox and operation posting identity per journal event.
- Positive quantities; nonnegative component amounts; currency equality through a transaction; `B=S+D`, `S=N+F`, checkout component sums equal charge; bounds on refunded/reserved/refund-in-flight/transferred/recovered amounts.
- No overlapping active reservation for an individually identified unit. Listing counters and bid counters use atomic constraints/predicates, not read-then-write arithmetic.
- Allocation totals match parent amounts; enforce in the transaction/service plus database constraints/triggers where cross-row checks are required. Unit and shipment membership must belong to the indicated seller/fill.
- No cascading deletion of posted money, execution snapshots, evidence, or financial operation history. Restrict or tombstone linked business records. Retention and privacy policy controls access, not rewriting financial history.

## 5. Immutable snapshots, secure payment binding, and canonical commands

### 5.1 Snapshot content

Freeze: buyer/customer and platform account identity; seller/connected-account identities; products, seller representations/specifications and listing versions; distinct-line keys; quantities/unit ordinals; buyer/seller unit and aggregate execution values; fee/net/spread; grading election and fee basis/rate/allocations; tax calculation ID, address, jurisdiction/product codes and amounts; approved other charges; currency; payment method/rail; gross-up formula/rate; surcharge and final total; shipping destinations; quote/pricing source/freshness; all relevant policy versions, timestamps, and buyer terms/election assent.

Canonical serialization and a cryptographic digest are required. Provider metadata references checkout ID, snapshot version and digest, but metadata alone is not trusted proof: retrieve the payment with server credentials and compare with the server-owned immutable record. Do not trust submitted totals, seller IDs, customer IDs, provider IDs, method labels, browser success, or a mutable session cart. Unauthorized payment attachment must fail before mutation.

No snapshot is edited after payment preparation. Quantity, address, grading, rail, pricing, or tax changes create a successor quote/version with fresh consent and safe retirement of the predecessor. Approved delivery reroutes after shipment require a separately audited policy workflow and new insurance/tax validation; DEFAULT disallow silent reroutes. Historical snapshots remain unchanged.

### 5.2 Canonical service contract

All routes and workers call these logical commands (implementation names may differ):

| Command | Mandatory behavior |
|---|---|
| `prepare_checkout(actor, input, request_key)` | Authorize, normalize lines, validate quote/tax/config/account, lock inventory/bid, reserve, persist immutable snapshot and payment operation/outbox atomically. Return durable checkout identity and exact total. |
| `start_or_resume_payment(checkout, request_key)` | Reuse active operation; create/confirm only the bound provider payment. Return action-required/pending/result safely. No order from client success alone. |
| `apply_provider_event(event)` | Verify/authenticate, persist inbox, retrieve evidence if needed, bind identities, transition through shared commands; preserve early/unlinked events for recovery. |
| `finalize_verified_payment(payment)` | Under locks, validate exact successful evidence; atomically commit reservations, execution, order, fills, payables, journals, bid counters, and notifications. Replay returns existing IDs. |
| `authorize_shipment(fill)` | Enforce payment/ACH, no cancellation/risk blockers, approved route/form/insurance readiness; store authorization and snapshotted deadline once. |
| `submit_tracking(actor, shipment, evidence)` | Check ownership/membership/state; validate against carrier; do not treat arbitrary text or label creation as qualifying shipment. |
| `request_refund(actor, scope, reason, key)` | Authorize trigger, lock exact capacity/units, determine policy vector, hold payout immediately, store refund operation and allocation. |
| `execute_refund(operation)` | Only shared financial adapter may move cash; verify result before completion; synchronize journals, seller entitlement, recovery, tax adjustments and notifications. |
| `evaluate_release(payable_scope, now)` | Pure, explicit allow/block result with every gate reason and evidence/version. Used by UI and actual transfer boundary. |
| `submit_transfer(scope, key)` | Lock/encumber exact amount, recheck full gate, serialize against new holds, persist and submit one operation. |
| `record_bank_payout(event)` | Update separate bank payout state and mappings without creating another transfer. |
| `open_dispute` / `resolve_dispute` | Correct fill attribution, atomic holds, evidence, approved resolution; cash outcomes use refund/recovery commands. |
| `assess_recovery` / `collect_recovery` | Establish documented liability; cap collections; follow ladder; never take another seller's funds. |
| `expire_reservation` / `forfeit_fill` | Locked deadline/evidence check, payment-race handling, one inventory transition and canonical compensation/refund. |
| `reconcile(scope)` | Compare provider and internal facts; repair through the same idempotent commands, not ad hoc balance edits. |

### 5.3 Provider evidence required for success

Verify provider account and environment, original customer/buyer relationship, intent and charge association, expected amount actually received/captured, currency, rail, checkout version/digest, permitted successful status, and unique ownership. Authorization-only card state is not successful capture. A client-supplied foreign, one-cent, wrong-currency, already-used, or merely processing payment must never fund an order. A succeeded ACH payment may create a held payable while shipment stays blocked until ACH approval; do not equate the two events if the configured adapter distinguishes them.

On success with irrecoverably missing inventory, record the received cash and a compensation execution/case linked uniquely to that payment, create no unfundable seller payable, and initiate an exact full compensating refund for the unfulfillable snapshot. Do not substitute a seller, change prices, or ask the buyer to pay again. DEFAULT compensate the entire uncommitted execution if atomic finalization cannot fulfill it; after successful commitment, later failures resolve per fill.

## 6. Ledger, cash operations, and financial conservation

### 6.1 Required ledger fields

Each journal: ID, business event type/ID, operation ID, posting key, effective and recorded UTC times, currency, source system/provider event, checkout/execution/order, policy/snapshot versions and digest, reason, actor/service identity, correlation ID, reversal-of journal, reconciliation status. Each entry: journal ID, sequence, account code, debit or credit integer amount (exactly one positive), owner type/ID, buyer/seller/fill/line/unit or quantity allocation, component code, original allocation reference, payment/charge/refund/transfer/payout/recovery/shipment/insurance/tax references as applicable. Unattributed provider cash belongs in suspense with a reconciliation case, never anonymous revenue.

Required account classes: processor cash/receivable, platform bank cash/reserve, seller held payable, seller transfer clearing, buyer refund payable, tax payable/tax receivable, grading service liability/vendor payable, marketplace fee revenue, spread revenue, approved other revenue, surcharge recovery clearing, card and ACH expense, insurance expense, insurance claim receivable/recovery, chargeback suspense/loss, seller recovery receivable, approved other-party receivable. Balance and report by currency, owner, fill, and component. Connected-account/bank movements also require an attributable custody subledger; they are not automatically platform cash accounts.

### 6.2 Posting recipes

At verified payment success, gross basis:

```text
Dr processor cash/receivable                     A
  Cr seller held payable                         sum(N)
  Cr marketplace fee revenue                     sum(F)
  Cr captured spread revenue                     sum(D)
  Cr grading service liability                   G
  Cr tax payable                                 T
  Cr other approved charge account(s)             O
  Cr surcharge recovery clearing                 C
```

If provider settles net, separately record `Dr actual processing expense / Cr processor cash` and reconcile gross-to-net. Record insurance `Dr insurance expense / Cr cash or vendor payable`; attach leg/fill. Paying the grader reduces service/vendor liability under the approved agreement. None of these expenses reduce `N`.

At approved refund entitlement, reserve refund capacity and move exact amounts from original balances to buyer refund payable: debit affected seller held payable `N_ref`, fee contra-revenue `F_ref`, spread contra-revenue `D_ref`, refundable grading liability, tax liability/receivable, refundable other components, and refundable surcharge clearing; credit buyer refund payable for their sum. If seller proceeds were already transferred, replace the seller-held debit with a documented seller recovery receivable where liability applies, or an explicitly approved platform loss/reserve source. If liability is unresolved, use suspense and escalate; do not assess arbitrary seller debt. Refund approval and cash completion are distinct. At provider-confirmed buyer credit, debit buyer refund payable and credit processor cash. Failed/unknown cash refund leaves the buyer obligation and payout block outstanding. Denied requests create no refund entitlement journal; reversal of an approved entitlement requires an explicit audited decision, never an automatic consequence of a provider error.

Transfer submission encumbers the chosen payable allocation; confirmed transfer debits seller payable and credits processor cash with a transfer custody record. Unknown result stays encumbered. Failed bank payout does not recreate the original held payable or authorize another platform transfer: funds may still be in the connected account. Track provider location and resolve bank retry separately.

Provisional chargeback debit: debit chargeback suspense and credit processor cash for the provider's actual debit; fee is a separate expense. A win reverses the provisional debit with its actual provider credit. A final loss allocates suspense to documented refund-like economic reversals, liable-party receivables or platform loss under the configured reason policy; do not also submit an ordinary refund for the same credited amount. Chargeback fee treatment and liability need explicit policy. A win does not automatically remove unrelated holds or undo an ordinary refund already owed.

Recovery collection reduces the existing receivable only once. Provider transfer reversal debits recovered cash and credits recovery receivable when that receivable already represents the removed seller entitlement. Future offset debits that same seller's new payable and credits recovery receivable. Record negative seller balance as a projection of outstanding debt, not a second receivable. Insurance proceeds reduce the appropriate claim/loss receivable or book approved recovery classification; they do not create another buyer refund or seller entitlement.

### 6.3 Invariants and caps

Every posted journal balances exactly; posted entries are immutable. Open obligations and provider cash status may differ temporarily only through explicit pending/clearing/suspense accounts with monitored operations. No journal-only function may report cash refund completion.

For every component/unit, original refundable capacity minus succeeded and pending approved refund allocations cannot go negative. Before submitting a refund, account for overlapping processor credits/chargebacks so buyer compensation is not duplicated. For every transfer, cumulative reversals cannot exceed the confirmed transfer amount. For every recovery, collected plus reserved collection cannot exceed established liability. Seller available payable equals original net minus approved entitlement reductions, confirmed transfers, and transfer encumbrances; holds further restrict availability without themselves becoming expenses or lost money. Do not subtract both a reversal and its already recorded entitlement reduction from the original payable.

## 7. State machines and transition rules

Each transition is a typed command with expected version, authorized actor/source, preconditions, timestamp/evidence, resulting state, journal/operation effects, and outbox events committed atomically. Unlisted transitions are rejected. Duplicate events replay the prior outcome. Orthogonal state machines and holds must not be compressed into a single string. States below use `→` for permitted normal progression; listed exception branches are the only additional transitions unless introduced by a tested spec revision.

### 7.1 Checkout and payment

| Entity | Transition | Guard and effect |
|---|---|---|
| Checkout | `DRAFT → RESERVED → PAYMENT_PENDING` | Quote validated; reservation, immutable snapshot, and provider operation durable. |
| Checkout | `PAYMENT_PENDING → ACTION_REQUIRED → PAYMENT_PENDING` | Provider requests/receives authentication. Keep reservation subject to safe expiry. |
| Checkout | `PAYMENT_PENDING/ACTION_REQUIRED → CORRECTION_WINDOW` | Bid payment definitively fails or requires buyer correction; set deadline once. |
| Checkout | `CORRECTION_WINDOW → PAYMENT_PENDING` | Buyer supplies authorized correction before deadline, previous attempt confirmed non-success/retired. |
| Checkout | `PAYMENT_PENDING/ACTION_REQUIRED/CORRECTION_WINDOW → COMPLETED` | Exact verified success and atomic finalization; success during correction is permitted. |
| Checkout | `DRAFT/RESERVED/PAYMENT_PENDING/ACTION_REQUIRED/CORRECTION_WINDOW → EXPIRING → EXPIRED/CANCELLED` | Close payment safely before releasing reservation; unknown provider outcome goes to recovery, not assumed failure. |
| Checkout | Any in-flight state `→ RECOVERY_REQUIRED → COMPLETED/COMPENSATING` | Unknown outcome, crash, mismatched evidence, or unfulfillable successful charge. |
| Checkout | `COMPENSATING → COMPENSATED` | Full required compensating cash refund verified. Failure stays compensating with alert. |
| Payment | `CREATED → REQUIRES_METHOD/REQUIRES_ACTION/PROCESSING/SUCCEEDED/FAILED/CANCELLED` | Only adapter-verified provider evidence; supported rail maps documented. |
| Payment | `REQUIRES_METHOD/REQUIRES_ACTION → PROCESSING/SUCCEEDED/FAILED/CANCELLED` | Same bound attempt only; no simultaneous replacement confirmation. |
| Payment | `PROCESSING → SUCCEEDED/FAILED/CANCELLED` | Retrieved authoritative outcome. |
| Payment | Any nonterminal `→ UNKNOWN → verified state` | Network uncertainty, not a new charge opportunity. |
| Payment | ACH `SUCCEEDED → RETURNED` | Verified return event; record actual debit, hold/recovery. Success history remains immutable. |
| Payment approval | `NOT_APPROVED → PENDING → APPROVED → REVOKED` | Approval evidence/rail policy; revocation on return/risk evidence blocks further shipment/payout. |

Refund and chargeback status are separate from successful payment history. Do not overwrite a succeeded payment with an ordinary refund status and lose the charge evidence. Terminal provider attempts are not revived by stale webhooks; an apparent contradictory event requires provider retrieval and reconciliation.

### 7.2 Orders, seller fills, reservations, and bids

Order fulfillment projections: `OPEN`, `PARTIALLY_FULFILLED`, `FULFILLED`, `PARTIALLY_CANCELLED`, `CANCELLED`, `EXCEPTION`. Separate financial projections: `PAID`, `PARTIALLY_REFUNDED`, `REFUNDED`, `REFUND_PENDING`, `PAYMENT_RECOVERY`; separate active dispute/hold counts. `REFUNDED` means the entire refundable charge has been returned, not simply all merchandise cancelled; retained incurred grading must remain visible. Financial and fulfillment projections may coexist (e.g. partially cancelled and partially refunded). Close operational order only when all children have terminal fulfillment and no outstanding operations; later chargeback/recovery reopens an exception case without rewriting completed delivery history.

Seller fill progression:

```text
ALLOCATED_UNPAID → FUNDED_HELD → AUTHORIZED_TO_SHIP → IN_FULFILLMENT
non-graded: IN_FULFILLMENT → DELIVERED → FULFILLMENT_SATISFIED
 graded:   IN_FULFILLMENT → GRADING_PENDING → AUTHENTICATED
```

Only `FUNDED_HELD` creates a payable (as part of payment success). `DELIVERED` starts the 24-hour non-graded clock; `FULFILLMENT_SATISFIED` requires that clock. `AUTHENTICATED` meets the graded fulfillment gate immediately after final successful authentication, with no added buyer-delivery-day requirement. Both remain subject to all holds and payment/account gates. Subsequent grader-to-buyer failure may create a post-transfer case.

Before valid carrier possession: funded/authorized fills may enter `CANCELLATION_PENDING → CANCELLED` on approval, or return to prior state on denial. Qualifying shipment routes cancellation to the return/dispute workflow; an unverified label cannot do so. Deadline failure enters `FORFEITED` and mandatory refund processing. Failed grading enters `GRADING_FAILED → RETURN_PENDING → RETURNED_TO_SELLER`; refund obligation and payout cancellation start at failure, not at an invented buyer return condition. Loss/damage enters `FULFILLMENT_EXCEPTION` with a hold and claim. Partial quantity transitions live on allocation slices; fill projections become `PARTIALLY_CANCELLED/REFUNDED/FULFILLED` as appropriate. A refund is a separate money state, not proof of return or restored stock.

Reservation: `ACTIVE → COMMITTED` on successful atomic finalization; `ACTIVE → RELEASE_PENDING → RELEASED` after safe payment closure; `ACTIVE → QUARANTINED` on uncertainty; `QUARANTINED → COMMITTED/RELEASE_PENDING` after resolution. Exactly one commit or release. Do not decrement physical stock both on reservation and again on commitment; move quantity between inventory buckets.

Bid quantities must satisfy:

```text
requested = committed_fills + active_reserved + open_unfilled + closed_unfilled
matchable = open_unfilled, only while bid status permits matching
```

Bid states: `OPEN ↔ PARTIALLY_FILLED`, `OPEN/PARTIALLY_FILLED → FILLED/EXPIRED/CANCELLED/PAYMENT_REVIEW`; correction is also tracked per attempted execution. DEFAULT pause new matches for that bid during payment correction; successful correction resumes remaining open quantity. Failed correction closes the reservation and sets bid `PAYMENT_REVIEW`, leaving unfilled quantity recorded but not automatically charging again until buyer reconfirms. Cancelling/expiring a parent bid closes only unreserved remainder; resolve in-flight payments separately. Refunding a completed bid fill does not automatically reopen the bid. Matching priority, self-trade prohibition, minimum fills and manual acceptance price rules must be explicit; DEFAULT preserve documented price/time priority and reject self-trades, never infer missing seller consent.

### 7.3 Shipment, grading, and insurance

Shipment states: `PLANNED → INSURANCE_READY → AUTHORIZED → TRACKING_SUBMITTED → VALIDATING → CARRIER_ACCEPTED → IN_TRANSIT → DELIVERED`. `VALIDATING → INVALID` requests correction without stopping the deadline. `INVALID → TRACKING_SUBMITTED` permits a new audited submission. Carrier events can skip intermediate transit statuses only when authenticated evidence establishes the necessary facts. `CARRIER_ACCEPTED/IN_TRANSIT → EXCEPTION/LOST/DAMAGED/RETURNING`, with an independently tracked return shipment. Resolved exceptions return to the evidenced state. Corrections to delivery create a hold and re-evaluation; do not preserve a false release clock.

Grading service state: `PLANNED → FORM_READY → SHIPPED_TO_GRADER → RECEIVED → AUTHENTICATING → PASSED/FAILED`. `PASSED → FORWARDING → DELIVERED_TO_BUYER`; `FAILED → RETURNING_TO_SELLER → RETURNED_TO_SELLER`. Vendor exception is an overlay hold, not success. Vendor timeout or disputed/partial/inconclusive result cannot become `PASSED`. Results must identify all applicable units; passing units may meet their gate while failed/unresolved units remain held. All-or-none election does not imply all-or-none grading outcome.

Independent grading cost state: `NOT_INCURRED → INCURRED` based on the vendor's configured contractual event, with timestamp/evidence and allocated amount. No backward transition. Partial vendor commitment uses separate unit/service allocations. A vendor credit is a new accounting event and does not automatically make an incurred buyer grading fee refundable. Cancellation authorization and vendor-incurrence commands must serialize; in-flight/unknown vendor commitments require reconciliation before promising a refundable grading amount.

Insurance state: `REQUIRED → PURCHASE_PENDING → ACTIVE/FAILED`; later `EXPIRED/CANCELLED` records coverage facts without deleting history. Claim: `OPEN → SUBMITTED → UNDER_REVIEW → APPROVED/PARTIALLY_APPROVED/DENIED → PAID/CLOSED`, with appeal/reopen as an explicitly audited transition. Approved claim is not received cash. Insurance purchase failure blocks the leg's dispatch. Return-leg arrangements/coverage require configured terms; preserve required return-to-seller obligation and escalate inability to execute safely.

### 7.4 Refund, disputes, payout, and recovery

| Entity | Allowed progression and completion condition |
|---|---|
| Refund | `REQUESTED → POLICY_REVIEW/AWAITING_RETURN/APPROVED/DENIED`; review/return → approved or denied by authorized decision. `APPROVED → SUBMITTING → PENDING/SUCCEEDED/FAILED/UNKNOWN`; failed/unknown → retry or evidence resolution through same operation. `SUCCEEDED` requires confirmed provider credit. Approved liability persists through failure. |
| Internal dispute | `OPEN → EVIDENCE_REQUIRED → UNDER_REVIEW → RESOLVED_DENIED/RESOLUTION_PENDING`; resolution pending → `RESOLVED_REFUND` only when required refund succeeds, or another explicitly documented terminal remedy. Associated return/recovery cases may remain open and visible. |
| Processor dispute | `OPEN → EVIDENCE_DUE → SUBMITTED/UNDER_REVIEW → WON/LOST/CLOSED`; normalize actual provider event graph rather than require events that vendor does not emit. Track provisional/final cash separately, deadlines and evidence acceptance. |
| Payable release | `HELD → RELEASE_APPROVED → TRANSFER_PENDING → TRANSFERRED`; pre-transfer new hold invalidates approval and returns to held. Partial movements retain independent held and transferred slices. Untransferred entitlement can be `CANCELLED` by approved refund. |
| Transfer operation | `PLANNED → CLAIMED → SUBMITTED → SUCCEEDED/FAILED/UNKNOWN`; unknown resolves before any new command. Succeeded transfer may become `PARTIALLY_REVERSED/REVERSED` through a separate capped reversal operation. |
| Bank payout | `NOT_SCHEDULED → PENDING → PAID/FAILED/CANCELLED`; failed/cancelled retry uses a separate linked provider payout after balance/location verification. No transfer reissue. |
| Recovery | `ASSESSMENT_REQUIRED → ASSESSED → REVERSAL_ATTEMPT → CONNECTED_BALANCE_COLLECTION → FUTURE_OFFSET → NEGATIVE_BALANCE → REPAYMENT_REQUIRED → SUSPENDED`; skip unavailable steps with evidence, stop when `SATISFIED`; `PARTIALLY_COLLECTED` is an amount projection. Write-off requires approved authority and a separate loss journal. Suspension does not erase debt. |
| Financial operation | `PLANNED → CLAIMED → SUBMITTED → SUCCEEDED/FAILED/UNKNOWN`; expired leases reclaim with fencing and same key; failed definitive attempts may retry under provider-safe semantics; unknown always reconciles first. |

## 8. Inventory, concurrency, deadlines, and crash safety

### 8.1 Reservation and locking protocol

Use production database transactions and row locks or conditional updates with checked affected-row counts. Process-local locks and cookie/session nonces are insufficient. Establish one global acquisition order (DEFAULT bid IDs, listing IDs, checkout IDs, fill/unit IDs, payable IDs, operation IDs, each sorted) and use it everywhere; retry deadlocks with bounded jitter and identical command identity. If a command needs an additional earlier lock, restart rather than invert order.

1. Validate available listing and matchable bid quantities under lock; reserve both in one transaction. Record units and exact price/seller allocation before provider work.
2. Persist snapshot, operation, and outbox, then commit. Never hold a database transaction across an external network call.
3. A durable worker claims the operation using compare-and-swap, lease and fencing token. Provider idempotency protects external retries; fencing protects local stale-worker commits.
4. On verified success, lock the same scope and atomically commit reservations, bid quantities, order, fills, payable, ledger and outbox. An internal rollback cannot undo a provider charge; inbox/reconciler retries finalization.
5. On failure/expiry, retire/cancel the provider attempt and verify its state before releasing. Unknown results remain quarantined with an alert. If cancellation races with success, record success and either fulfill the still-reserved snapshot or compensate; never both release-and-sell and then fulfill the old charge.

Listing stock uses `available`, `reserved`, `committed`, `inactive/return_quarantine` counters or equivalent unit records. Cancellation before dispatch restores only evidenced available units exactly once. Failed fulfillment, returned, lost, or authenticity-rejected units go to quarantine/inactive by DEFAULT until seller reconfirmation and any required authenticity review. A return is not new sellable stock solely because a refund succeeded.

### 8.2 Time semantics

“One day” is exactly 24 elapsed hours (`86400` seconds), not next calendar day or business day. All persisted instants are timezone-aware UTC. DEFAULT compare `now >= deadline` for expiry; on-time action requires authoritative acceptance time `< deadline`. Missing/malformed/future-impossible evidence blocks release and opens review, never bypasses a hold.

- Bid correction deadline = first actionable failure/action-required notice event time + 24 hours. Persist and immediately enqueue buyer notification; repeated failures do not reset the clock. Delivery failure alerts operations and permits only an explicitly audited extension under approved policy, not silent early release.
- Non-graded eligibility = verified delivery-to-approved-buyer time + 24 hours. This is a payout eligibility delay, not a rule that all disputes expire after 24 hours.
- Tracking deadline = stored `authorized_to_ship_at + X*86400`, where positive `X` comes from the admin configuration version snapshotted at authorization. Configuration changes do not rewrite existing deadlines. DEFAULT no extra grace beyond configured X.
- Buy Now quote/reservation/3DS timeout: DEFAULT 15 minutes for sandbox; production value requires configuration. ACH pending reservations outlive ordinary checkout timeout and remain protected until terminal outcome or a verified cancellation/return-resolution process. A bid payment retry accepted during correction that is still genuinely processing at the deadline retains reservation until resolved; the buyer's opportunity closes at deadline but uncertain money must not be ignored.
- Timeout workers claim work atomically and recheck current provider/hold/shipment evidence. Carrier outage or unknown payment result triggers incident/review, not invented confirmation. Late valid evidence is preserved for administrative correction and canonical compensation; do not automatically revive a forfeited/refunded fill.

### 8.3 Financial idempotency and races

Key shapes are stable logical IDs, not current time, browser session, or freshly created order ID: `payment:checkout:version:attempt`, `refund:refund_id`, `transfer:payable_allocation:release_version`, `reversal:recovery_allocation_id`, `insurance:shipment:coverage_version`, `grading:allocation:commit_version`. Store full request digest and provider key before sending. Persist keys beyond the provider's deduplication retention; if provider retention elapsed with an unknown result, reconcile/search by original references or obtain verified resolution before reissuing. Do not assume the provider deduplicates forever.

Duplicate HTTP requests and webhook retries converge on one operation/result. Out-of-order events do not regress state; retrieve current authoritative evidence when contradictory. Webhook success acknowledgment requires verified signature and durable inbox storage; if storage fails return a retryable error. After durable storage, worker failures are retried internally and alerted; an early unlinked event is retained, not discarded. Dead-letter queues must have owners, replay controls, and age alerts.

Refunds and transfers contend on the same payable/unit locks and financial action claims. A refund/dispute accepted before transfer dispatch blocks dispatch. Since network effects cannot be atomic with the database, a newly arriving hold during an already dispatched transfer marks `TRANSFER_IN_FLIGHT_RISK`, prevents further releases and schedules reconciliation/reversal; do not pretend a hold can recall money instantly. Test both linearization orders. Never perform a second transfer because the first request timed out.

## 9. Authorization and payout gate

| Actor/source | Allowed actions and restrictions |
|---|---|
| Buyer | Own checkout/bid/payment method only; request cancellation/refund/dispute for owned fill/units; complete own 3DS. Cannot assert payment success, seller execution price, delivery, grading result or payout eligibility. |
| Seller or authorized seller staff | Own listings and allocated seller fills; accept eligible bids within stock; submit own required shipment tracking/form; approve/deny eligible cancellation and initiate voluntary refund for own allocation. Cannot mutate another seller, buyer final address, tax, ledger, incurred-cost evidence or authentication result. |
| Authorized Metex Administrator | Scoped policy configuration, evidence review, cancellation/dispute adjudication, explicit refund/recovery approval and release requests. Role checked server-side per action, with step-up for high-risk actions and reason/evidence. No generic bypass of payment binding, ownership, financial caps, active holds or required fulfillment evidence. |
| Grading adapter / authorized vendor operator | Only assigned grading allocations; authenticated intake/cost/result/forwarding evidence. Manual entry requires verified source evidence and audit; seller cannot impersonate grader. |
| Carrier/insurance adapter | Authenticated carrier events, policy purchase and claim facts for mapped shipments. User-entered tracking status cannot masquerade as carrier confirmation. |
| Payment adapter / financial worker | Provider evidence and shared money commands only, scoped service identity; no arbitrary ledger adjustment route. |
| Support/read-only admin | Restricted visibility and case assistance; no money-moving authority unless explicitly granted. |

Enforce active session validity, frozen/banned/account restrictions, CSRF where relevant, and object-level authorization on every mutation and sensitive retrieval. Never log card/bank secrets or give one seller another seller's financial or buyer data. Sellers see only addresses needed for their authorized leg; grader receives the approved final buyer address through the defined workflow.

**The actual transfer boundary MUST run the same complete gate as the UI/batch evaluator.** It requires all of:

1. Correct successful bound payment, reconciled funding, ACH approval and any configured ACH risk hold satisfied.
2. Positive remaining seller entitlement and exact allocation; no refund entitlement/operation competing for it; no duplicate transfer/encumbrance.
3. No applicable internal dispute, processor chargeback, payment return/risk, shipping failure, grading failure/unresolved result, restriction, reconciliation hold or administrative hold.
4. Non-graded units: valid owned shipment and carrier delivery to approved buyer address plus 24 hours. Graded units: valid seller-to-grader shipment and final successful authentication of those units; grader receipt alone fails.
5. Required insurance coverage evidence and no known unresolved relevant custody failure. Successful authentication does not require waiting for normal grader-to-buyer delivery, but a known failure blocks an unsubmitted release.
6. Verified current connected account/capabilities and payout/account restrictions; required source-funds reference and sufficient attributable funds.
7. Valid policy versions, evidence timestamps, no emergency stop, and current row versions under locks.

Return a set of machine-readable block reasons with evidence, not only the first reason. Releasing one hold must not clear others. A legitimate discretionary admin hold may be lifted by its authorized owner with evidence; mandatory constraints cannot be overridden through “force payout.”

## 10. Grading, shipment qualification, and insurance operations

Before grading election, conspicuously disclose: grading is an optional buyer-protection/authentication service; all units of the selected distinct line will be graded; failed specifications/authentication return the item to seller and trigger merchandise refund; **the grading fee is never compensated/refunded after its cost is incurred, even when the buyer receives no item**; cancellation before incurrence permits grading fee refund. Capture disclosure/version assent. The protection analogy must not misrepresent grading as the separately purchased shipping insurance policy.

Generate a premade Metex submission form for each vendor package, linked to exact fill/units and snapshot. Include relevant product type, metal, denomination, weight, purity, year/mint, quantity and seller-stated identifying specifications; seller cannot rewrite them after purchase. Include approved vendor/service, case/reference, and the buyer's approved final delivery address. Distinguish this success destination from the seller return destination on failure. Record generated form hash and seller acknowledgment/inclusion evidence under the configured vendor process.

Qualifying tracking requires authorized submitter, carrier/service validity, transaction/seller association, correct leg/origin/destination, non-reused incompatible tracking, carrier possession or equivalent verifiable progression, and attributable insurance. Label creation or arbitrary text is not qualifying tracking. Carrier validation acceptance time and submission time are separate. DEFAULT timely submission alone cannot defeat forfeiture until qualification is evidenced; if a validation outage prevents a timely decision, use `EVIDENCE_REVIEW` hold and escalate, rather than falsely asserting non-shipment. X still determines the seller obligation; no automatic extension is created. Verified late evidence requires an audited disposition.

Metex purchases UPS shipping insurance for every item transaction from its commission economics; no separate buyer or seller insurance charge. Store coverage and premium for every shipment leg and allocate to fills. Before dispatch, validate actual eligible contents/insured value/geography/carrier/service and coverage period against configured terms. Do not assume a purchased label, declared value, or a single seller-to-grader policy covers bullion or the grader-to-buyer leg. Grader-to-buyer dispatch has its own insurance readiness gate. Shipping postage payer, signatures, coverage limits/exclusions, return coverage, vendor identity/integration and claims procedures are **ADMIN/POLICY CONFIGURATION REQUIRED**. If coverage required for a route cannot be obtained, disable that route/order scope; do not dispatch uninsured.

On loss/damage: open affected claim and custody case, hold untransferred affected funds, preserve evidence and deadlines, notify buyer/seller/admin, and pursue applicable UPS recovery. Buyer resolution timing, return requirements, and ultimate liability are configuration decisions; a claim delay must not silently become an indefinite refund delay. Escalate against configured service deadlines. For a loss after authenticated graded payout, record provider/custody liability review and any reserve-funded buyer remedy separately; do not automatically charge the seller for grader-to-buyer loss. Claim proceeds and seller recovery cannot produce duplicate recovery of the same loss.

## 11. Refund, chargeback, and recovery rules

### 11.1 Canonical refund vector

For selected original unit slices `U`:

```text
R_merchandise = sum(B_u) = sum(N_u + F_u + D_u)
R_grading = sum(eligible unincurred grading allocations for cancelled service)
R_tax = approved tax reversal for affected components
R_other = policy-approved reversible original other-charge allocations
R_card = policy-selected original surcharge slices, never a new gross-up
R_total = R_merchandise + R_grading + R_tax + R_other + R_card
```

Policy must explicitly map reason, shipment/return stage, liability, incurred-cost status, and card component refundability. Exact surcharge treatment on voluntary cancellation versus seller fault remains **ADMIN/POLICY CONFIGURATION REQUIRED**. DEFAULT sandbox fixture refunds original surcharge slices attributable to refunded underlying components; this is a test/default policy, not commercial approval. Production automatic refund execution must have an approved mapping. Mandatory buyer merchandise refund cases must create the obligation immediately and escalate missing ancillary policy rather than drop the refund. Configure policy before enabling affected checkout so this gap cannot routinely occur after charging.

Seller principal reversal is net entitlement `N_u`; the corresponding `F_u` is separately reversed from Metex's fee, and `D_u` from spread. Never collect gross `S_u` from a seller who received only `N_u` for an ordinary transaction unwind. Additional seller damages/costs require explicit legitimate liability policy. Once proceeds transferred, pursue affected seller net through recovery instead of altering another fill's entitlement.

Grading price basis matters for partial cancellation: `PER_UNIT` unincurred cancelled units reverse their stored fee slices. `PER_LINE` surviving service may still cost the full flat fee, so allocation does not itself grant a proportional refund right; approved vendor cancellation policy must define the retained service obligation. DEFAULT disable automated partial grading-fee refund for that basis without configuration. All remaining units retain the original grading election. Incurred allocations remain nonrefundable, including failed authentication.

Tax reversal uses original transaction/component references and tax rules, including retained grading tax where applicable; do not blanket reverse tax on a nonrefunded service. Previously remitted tax uses the appropriate tax receivable/adjustment rather than an imaginary unremitted balance. Pending tax-provider adjustment is independently monitored; buyer credit status must remain truthful.

### 11.2 Trigger policies

Pre-shipment buyer cancellation is a request; seller approval or authorized admin adjudication is required under the configured response policy. A seller may not fabricate tracking to deny it. Seller voluntary refund, admin refund, dispute resolution, automatic tracking forfeiture, failed grading, and crash compensation all enter the same refund engine with different authority/reason. Post-shipment return window, evidence requirements, denial reasons, refund-without-return rules, and return costs are unresolved commercial policy. DEFAULT route to admin review with scoped payout hold. Return receipt must not automatically relist suspected counterfeit or nonconforming units.

Failed grading: return affected units to seller; mandatory buyer merchandise refund, reversal of seller payable/fee/spread, applicable tax adjustment, configured surcharge treatment; retain incurred grading fee; create compliance event. Seller gets no payout for failed units. Tracking forfeiture similarly cancels affected seller entitlement and initiates allocated refund; grading refundability still depends on actual incurrence. Neither case requires unrelated sellers to agree.

### 11.3 External disputes and post-payout recovery

Chargeback intake resolves provider payment to exact allocations; never choose the first seller by default. If provider disputes the whole checkout, all economically affected fills may need scoped holds. If precise scope is unknown, apply a documented payment-level investigation hold until attribution, not an arbitrary seller debit; narrow promptly. External debit is recorded even if refund execution is unavailable. Prevent refund plus chargeback duplicate compensation, and reconcile processor adjustments when one overlaps an existing refund.

Before transfer: hold affected available entitlement immediately. After transfer/bank payout: assess recovery only where reason-specific policy establishes seller liability. ACH returns can implicate buyer or platform risk and do not automatically create seller debt. Approval cannot mathematically eliminate later ACH returns; do not claim irreversible finality. Approved ACH means the configured provider/evidence/risk gate passed, never permission to ship while pending.

Recovery ladder: attempt amount-capped provider reversal if possible; collect available connected balance using supported authorized mechanisms; offset the same seller's future payable; expose negative seller balance; require repayment; suspend under policy. Record skipped/unavailable steps and partial recoveries. No unauthorized bank debit. DEFAULT maximum ordinary unwind seller principal is affected transferred net minus prior collections. Chargeback fees, shipping costs, unrecoverable debt, loss reason allocation and reserve thresholds need approved policies. Metex reserve may fund an approved immediate buyer obligation while collection continues. Reserve use does not invent liability or eliminate the receivable. Offset history must show new fill contractual 95% net and separate recovery deduction.

## 12. Required scenario matrix

Every row is mandatory end-to-end coverage. `Finalize` means §5 atomic commitment; `Refund` means §11 exact vector with approved policy, provider confirmation and §6 journals; `Recover` means liability-based §11.3 collection. These references are normative and define monetary effects, not permission for a separate implementation. All successful commands emit deduplicated notifications from §14.

| ID | Before state and trigger | Required result / money | Inventory and isolation | Failure/recovery |
|---|---|---|---|---|
| S01 | Buy Now, one buyer/seller; valid card or approved ACH succeeds | Finalize one execution, held `N`, fee `F`, spread `D`; authorize proper route | Reserved → committed once | Missing browser recovered from inbox |
| S02 | One seller, multiple independent buyers purchase | Separate buyer payments, orders, fills and payables | Lock shared listing; each buyer gets only their allocated quantity | One buyer failure cannot undo others |
| S03 | One checkout, multiple sellers/products | One accepted payment; independent fill economics and route | Atomic initial allocation; later fulfillment independent | Refund/hold only affected fill |
| S04 | Existing listing matches new bid, or new listing matches existing bid | Reserve bid and listing; own execution/payment; use agreed buyer and seller prices | No match beyond open quantity | Saved-method failure enters correction |
| S05 | Bid matched across multiple sellers in one event | One execution may contain multiple fills; spread calculated per fill | Each seller allocation locked | Initial all-or-compensate; later per-fill remedies |
| S06 | Parent bid partially fills now and later | Each time creates separate charge/execution; parent records cumulative committed quantity | Remaining open quantity persists | Refund never implicitly reopens bid |
| S07 | Seller accepts one bid partially or fully | Same commands and economics as automatic matching | Reserve both quantities atomically | No payable until verified success |
| S08 | Seller accepts several bids, same or different buyers | Independent payment events; successful ones finalize, failures do not | Reserve exact per-bid quantities; reject excess selection before charge | Failed member keeps correction reservation; no batch rollback of external successes |
| S09 | Two sellers accept same remaining bid / two buyers compete for last stock | At most available quantity succeeds | Sorted locks/conditional updates | Loser receives unavailable/requote; no excess charge |
| S10 | Unpaid checkout abandoned/cancelled | No revenue or payable; retire payment | Release once after verified terminal non-success | Unknown outcome quarantined |
| S11 | Buy Now immediate card decline | Failed attempt, no order/payable/revenue | Release under safe closure; retry with new valid reservation | Do not reuse stale price without quote |
| S12 | Card requires 3DS | Action-required; no shipment/payable before success | Reservation active within policy | Browser close recoverable; failure/expiry retires payment safely |
| S13 | Bid decline or off-session authentication required | 24-hour correction opportunity; no finalized revenue/payable | Keep matched quantity reserved | Notify action; expiry closes safely; pause bid by default |
| S14 | Correction succeeds inside window | Finalize frozen terms; changed rail uses successor approved snapshot | Reservation commits once | Still-processing retry at deadline reconciles, not blind release |
| S15 | Correction expires without successful/processing payment | Cancel attempted fill, no payable | Release listing and bid claim once; bid payment review | Late success compensated if no valid reserved allocation |
| S16 | ACH initiated/pending | No ship authorization; pending payment | Keep reservation beyond ordinary timeout | Failure: bid correction or safe Buy Now release |
| S17 | ACH succeeds, approval evidence pending | Held payable may be recorded; no shipping or release | Committed quantity protected | Approval worker/inbox eventually authorizes or flags risk |
| S18 | ACH approval passes | Ship authorization/deadline begins; no buyer surcharge | Normal fulfillment | Later return handled S19, not ignored |
| S19 | ACH return before shipment, in transit, or after transfer | Revoke approval, scoped hold; actual debit; stop dispatch if possible; policy-based buyer/platform/seller recovery | Unshipped units reviewed/released appropriately; shipped units not relisted | Reserve/case; no automatic second debit or seller liability |
| S20 | Payment success then browser/app/worker/database crash | Recover same charge and Finalize or compensate | Replay original reservation; no second decrement | Durable attempt/inbox/reconciler; never recharge for recovery |
| S21 | Success but allocation irrecoverably unavailable | Compensation execution and full approved compensating refund; no seller payable | Quarantine inconsistency; no substitution | Refund retries until confirmed; alert immediately |
| S22 | Duplicate request/webhook, early or out-of-order webhook | One charge/order/journal/result; no state regression | No duplicate quantity movement | Inbox replay plus provider retrieval |
| S23 | Buyer requests pre-shipment cancellation, seller approves | Scoped hold; Refund; cancelled entitlement | Restore only cancelled available units once | Provider failure remains pending; do not say refunded |
| S24 | Seller denies / qualifying shipment already exists | Record reason; release only request-specific hold after valid denial; route shipped issue to return/dispute | No stock restoration | Invalid text cannot count as shipment; unresolved denial escalates |
| S25 | Multi-seller mixed approvals, denials, shipments | A refunded, B continues, order shows partial status | No consensus requirement or cross-seller adjustment | Independent retry states |
| S26 | Partial quantity cancellation/refund | Reverse stored component slices only; preserve remaining net | Restore only approved unshipped quantity; return quarantine otherwise | Concurrent refund locks prevent duplicate slices |
| S27 | Voluntary seller refund before/after transfer | Same Refund; after transfer Recover affected net | Unrelated fills and buyers untouched | Collection may lag buyer credit via approved reserve |
| S28 | Admin/internal dispute refund after return / without return | Required authority and policy; pending remedy until provider success | Return receipt separate; no automatic relisting | Denial closes only relevant hold; other holds remain |
| S29 | Tracking absent, fake, reused, or never qualifies at deadline | Forfeit affected fill; no seller release; Refund; compliance event | Inactive/reconfirmation by default | Carrier outage review; late proof doesn't silently resurrect |
| S30 | Non-graded valid buyer delivery | At delivery +24h eligible if all gates pass | No stock change | New dispute or corrected delivery blocks actual transfer |
| S31 | Buyer grades one distinct line among different products | Grade all selected-line units; fee separate; others direct | Independent seller/route allocations | Reject 3-of-5 election; normalize duplicate lines |
| S32 | Grader receipt / inconclusive or pending result | No payout; cost-incurred flag independent | Grader custody recorded | Vendor timeout creates hold and admin case |
| S33 | Final successful authentication | Affected graded net eligible subject to all gates; forward to approved buyer | Both legs/policies attributable | Forwarding loss after transfer uses S36/S39 |
| S34 | Failed authentication/specifications after cost incurred | Refund merchandise/applicable components, cancel seller net/fee/spread; retain grading; return to seller | Nonconforming units quarantined on return | Result evidence and compliance event; no grader-receipt payout |
| S35 | Cancel elected grading before/after incurrence | Before: eligible service fee refunded; after: not refunded | Cancel vendor work only when safe; remaining units retain election | Incurrence/cancel race serialized and reconciled |
| S36 | Loss/damage seller→buyer, seller→grader, or grader→buyer | Scoped hold/claim; buyer remedy and liability per policy | No fictitious delivery/stock restoration | Separate coverage/claim each leg; escalate denied/insufficient claim |
| S37 | Eligible payable release, duplicate admin/worker request | One capped transfer to correct seller; bank pending separate | No inventory movement | Unknown result encumbered; provider lookup before retry |
| S38 | Bank payout fails after connected transfer | Bank payout failed; seller informed; connected funds reconciled | No new platform payable or transfer | Verified provider/bank retry, independently tracked |
| S39 | Refund/dispute after payout | Buyer obligation plus liable-seller recovery only for affected allocation | No other seller funds; same-seller future offset separately shown | Ladder/partial collection/reserve/negative balance |
| S40 | Processor chargeback before transfer | Hold affected scope; provisional cash debit/evidence case | Unrelated scope continues unless whole payment disputed | No ordinary refund duplication; deadline alerts |
| S41 | Processor chargeback after transfer | Record debit and assessed recovery per reason | Never recover entire unrelated transfer balance | Exact capped reversal; reserve where approved |
| S42 | Chargeback won/lost, overlaps partial refund | Win records actual credit; loss allocates actual loss; recalculate remaining exposure | Holds removed only when their source resolves | Prevent overcompensation and double collection |
| S43 | Tax, insurance, grading, payment provider unavailable | Block relevant quote/dispatch/approval; retain truthful pending state | No unsafe release due to outage | Durable retry, alert, admin evidence workflow |
| S44 | Refund races transfer / dispute races release / expiry races success | Serialized claims; hold wins before dispatch, otherwise recovery case | No negative inventory or payable | Test both event orders and provider-success/DB-failure boundary |
| S45 | Account frozen or emergency stop activated mid-flow | Block new charges/ship/release as appropriate; maintain remediation/refund/reconciliation | Existing obligations remain recorded | Alert; no bypass via old sessions or alternate route |
| S46 | Two successful payments for one checkout due to external anomaly | Accept one; record excess receipt in suspense and compensate duplicate payment | One execution of merchandise only | Provider-id-specific compensation; investigate source |

## 13. Admin configuration registry

Every value is typed, validated, versioned, approved, effective-dated, auditable, visible in the admin dashboard with its scope, and snapshotted when relevant. Secrets are referenced securely, never embedded in snapshots. Changes are prospective unless a separate authorized case explicitly changes a deadline/hold; no retroactive financial repricing.

| Key / policy | Required value or behavior |
|---|---|
| `seller_fee_rate` / spread | Approved 5% / 100% positive spread. Expose for visibility; changing economics requires a revised approved spec, not routine admin tuning. |
| `ach_buyer_surcharge` | Fixed approved zero. |
| `card_rate`, `card_formula`, `rounding_version` | Initial 0.0299 and `GROSS_UP_PERCENT_FINAL`, §3 rounding. Alternative pricing requires approved prospective policy. |
| `tracking_upload_deadline_days` | **ADMIN/POLICY CONFIGURATION REQUIRED** positive X; missing blocks ship authorization. Sandbox fixture X=3; no production assumption. |
| `non_graded_delivery_hold_seconds` | Approved 86400; no ordinary switch to shorter hold. |
| `bid_correction_seconds` | Approved 86400. Extensions require documented policy/decision; no retry resets. |
| `reservation_ttl`, `quote_freshness`, `3ds_timeout` | **ADMIN/POLICY CONFIGURATION REQUIRED** production timings; sandbox default 900 seconds. Unknown payment and ACH pending handling cannot be disabled by TTL. |
| `ach_approval_policy`, `ach_risk_hold` | **ADMIN/POLICY CONFIGURATION REQUIRED** provider statuses/evidence, settlement/risk conditions, monitoring and permitted manual verification. Missing disables ACH shipment approval; initiation is never approval. |
| `grading_vendor`, `service`, `flat_rate`, `basis` | **ADMIN/POLICY CONFIGURATION REQUIRED** agreement/integration/rate. Basis DEFAULT per unit; per-line requires express configuration. |
| `grading_incurrence_rule` | **ADMIN/POLICY CONFIGURATION REQUIRED** contractual event, evidence, partial-cost allocation; not inferred from a browser toggle. |
| `grading_result_and_form_mapping` | **ADMIN/POLICY CONFIGURATION REQUIRED** required specifications, authenticated result, addresses, forward/return process and timeout handling. |
| `refund_component_policy` | **ADMIN/POLICY CONFIGURATION REQUIRED** reason-specific card surcharge/other charges and commercial approvals. Sandbox proportional original-surcharge fixture only. Incurred grading nonrefundability is fixed. |
| `cancellation_and_return_policy` | **ADMIN/POLICY CONFIGURATION REQUIRED** seller response/escalation, buyer windows, evidence, return costs/receipt, partial-line service cancellation, counterfeit disposition process. Defaults are review/hold, not invented refund denial. |
| `tracking_qualification_policy` | **ADMIN/POLICY CONFIGURATION REQUIRED** carrier evidence mapping, anti-reuse checks, outage review; arbitrary text/label-only cannot satisfy it. |
| `ups_coverage_and_claim_policy` | **ADMIN/POLICY CONFIGURATION REQUIRED** actual contents/limits/value/carrier/route coverage, purchase/claim integration, per-leg coverage, return coverage, deadlines, premium attribution. |
| `shipping_postage_policy` | **ADMIN/POLICY CONFIGURATION REQUIRED** postage payer/rate and permitted charges. Required insurance must remain Metex-funded. |
| `chargeback_ach_loss_liability` | **ADMIN/POLICY CONFIGURATION REQUIRED** reason/party/leg mappings, fees, evidence, reserve funding, unrecoverable losses; unknown liability cannot debit seller automatically. |
| `recovery_policy` | **ADMIN/POLICY CONFIGURATION REQUIRED** authorized collection methods, future offsets, thresholds, repayment/suspension/write-off authority, buyer remedy deadlines. |
| `tax_policy` | **ADMIN/POLICY CONFIGURATION REQUIRED** enabled jurisdictions, registrations, product/service/surcharge classification, exemptions, calculation/posting/reversal/remittance and reporting agreement. No hardcoded failure fallback. |
| `accounting_classification` | **ADMIN/POLICY CONFIGURATION REQUIRED** grading principal/agent agreement, surcharge presentation, approved other revenue, statutory recognition and loss classification. Separate operational accounts exist regardless. |
| `matching_policy` | Explicit seller acceptance price, ordering/tie-break, bid expiration/minimum fills, product equivalence, self-trade control. No below-seller-value execution. |
| `payout_controls` | Schedule, live account validation, limits, approval roles, emergency stops; cannot bypass mandatory gate. |
| `operational_slas` | **ADMIN/POLICY CONFIGURATION REQUIRED** reconciliation cadence, pending-operation ages, case owners/deadlines, vendor outages, notifications, recovery objectives. DEFAULT reconcile daily plus continuous exception scans. |
| `launch_scope_and_evidence` | **ADMIN/POLICY CONFIGURATION REQUIRED** supported rails/currency/products/geography, provider acceptance, insurance/grading/tax readiness and approved customer disclosures. Disable unavailable scopes explicitly. |

A required scope's missing configuration must be detectable before accepting its payment. Existing obligations with gaps go to a staffed escalation queue; missing policy is never permission to erase buyer entitlement or release held seller funds.

## 14. Notifications and customer/admin truthfulness

Persist outbox event with the business transaction and deduplicate by `(business_event_id, recipient, channel, template_version)`. Retry delivery with backoff and an owned dead-letter queue. Sending a notification must not be the step that commits money or inventory. Server state drives all pages after browser return.

| Event | Recipients and required content |
|---|---|
| Payment pending / 3DS | Buyer: exact action/status and durable resume link. Seller: pending/no shipment where relevant. |
| Bid failure | Buyer: correction deadline in displayed timezone, unchanged reserved terms and secure action link; seller: reserved, awaiting payment, do not ship. |
| Verified funding / ACH approval | Buyer: exact receipt with merchandise/tax/grading/surcharge; seller: only own fill net and authorization when all ship gates pass. Pending ACH must never receive a ship instruction. |
| Shipment authorization | Seller: exact route, form if graded, qualifying tracking requirements and deadline. |
| Invalid tracking / nearing deadline / forfeiture | Seller: correction evidence/deadline; buyer: affected fill and actual refund status; admin: exception/compliance event. |
| Grading election/result | Buyer: incurred-fee disclosure, result and forwarding/return; seller: required form, outcome; admin: failure/inconclusive evidence and holds. |
| Delivery/release | Buyer: delivery and support access; seller: held/eligible/transfer status using accurate labels. |
| Refund requested/approved/pending/succeeded/failed | Affected buyer/seller; amount and components; never promise completed credit before verified success. Admin alert on failure/age. |
| Internal dispute / chargeback / ACH return | Affected parties where appropriate; evidence deadline/action; admin immediate risk/cash exposure notification. Do not expose unrelated seller records. |
| Transfer / bank payout | Seller: distinguish connected balance transfer, bank pending, bank paid, bank failed. |
| Insurance claim/recovery | Affected parties: custody/remedy status; admin: claim deadline, liability and shortfall. |
| Reconciliation/security anomaly | Admin/operations: scope, amount, owner, severity, next action and correlation ID; no secrets. |

## 15. Reconciliation, audit logging, and incident controls

Continuously scan stuck/unknown operations and at least daily reconcile provider gross charges, fees, refunds, disputes/debits/credits, returns, transfers/reversals, connected balances and bank payouts with the ledger and custody mappings. Reconcile tax calculations to posted transactions/reversals/remittance; grading incurrence/payments/results; UPS premiums/policies/claims/cash recoveries; inventory reservation/commit/release and bid counters; pending buyer obligations and seller recovery balances.

Required exception checks: received payment without execution/compensation; execution without matching payment; duplicate payment binding; amount/currency/method mismatch; unbalanced journal; negative or overlapping inventory; overdue correction/qualification; missing carrier/insurance evidence; eligible release with active hold; transferred amount above entitlement; refund completed internally but absent externally; chargeback plus refund overlap; unmapped bank payout; recovery exceeding debt; fee/spread/net identities failing; expired worker/inbox/outbox lease. A timing difference must carry an operation and expected resolution deadline.

Cases require discrepancy type, exact amount/currency, scope, evidence, assigned owner, severity, age and next action. Reconciliation may replay established commands; it must not fabricate provider success or edit posted balances directly. Store review and closure evidence. Emergency controls separately stop new charges, shipments and seller releases while allowing authorized refunds, ingestion and reconciliation to repair obligations.

Audit every financial command, access-sensitive mutation, policy change, hold, attempted override, tracking edit, grading event, adjudication, retry, manual evidence entry, and reconciliation adjustment. Capture actor/role/service, request/correlation/idempotency IDs, action/result, entity versions, before/after state, exact monetary vector, reason/evidence, policy/snapshot hashes, provider references, and UTC timestamps. Protect append-only audit storage and limit PII access. Never log raw card/bank details, secrets, unredacted credentials or authentication tokens.

Operations runbooks must cover provider timeout/success unknown; paid checkout not finalized; stuck refunds; shipment/insurance outage; chargeback deadlines; ACH return; bank failure; seller negative balance; replay/dead-letter recovery; emergency stop; database restore and subsequent provider reconciliation. A restore must not replay old outbox messages as new financial operations. Backup/restore drills and stated recovery objectives are launch evidence.

## 16. Concrete acceptance tests and exact-dollar fixtures

All amounts below are USD. Tax values are explicit test-provider outputs, not assumed production tax rates. Processing/insurance amounts are fixture expenses, not asserted vendor prices. Refund tests use named **sandbox policy `REFUND_ORIGINAL_SURCHARGE_ON_REFUNDED_COMPONENTS`** unless otherwise stated; production requires an approved mapping. Each test asserts database state, component journals, provider call count/arguments, inventory/bid quantities, holds, and notification outcomes. Test fixtures use immutable ordered IDs so cent allocation is reproducible.

### 16.1 Exact money tests

| Test | Input/action | Required exact result |
|---|---|---|
| T01 | Buy Now `S=B=$1,000`, ACH, no tax/grading | Charge $1,000.00; seller $950.00; fee $50.00; spread $0; buyer ACH fee $0. With actual ACH $5 and insurance $8: Metex contribution $37, seller still $950. |
| T02 | Bid `B=$1,001`, `S=$1,000`, ACH | Charge $1,001; net $950; fee $50; spread $1; gross revenue $51. ACH $5 + insurance $8 → contribution $38. |
| T03 | Card `P=$1,000`, `r=.0299` | Surcharge $30.82; charge $1,030.82. Not $29.90 surcharge. If actual processor fee $30.82, surcharge recovery balances it; fee/spread economics unchanged. |
| T04 | Card `B=$1,001`, `S=$1,000`, grading $50, tax $40 | `P=$1,091`, surcharge $33.63, charge $1,124.63. Seller $950, fee $50, spread $1, grading liability $50, tax $40. Credits sum $1,124.63. |
| T05 | Card merchandise $100, grading $20, tax $8, approved other $12 | Base $140, surcharge $4.32, charge $144.32. Every component is included. |
| T06 | Bid 10@$100: A 3@$96, B 4@$98, C 3@$100 | Buyer $1,000; seller gross A $288/B $392/C $300; fees $14.40/$19.60/$15; nets $273.60/$372.40/$285; spreads $12/$8/$0. Total net $931, fee $49, spread $20, revenue $69. |
| T07 | Refund B only from T06, ACH/no tax | Refund $400; reverse net $372.40 + fee $19.60 + spread $8. A/C net remains $558.60; retained fee $29.40 and spread $12. No A/C transfer reversal. |
| T08 | 10 units at buyer $101/seller $100; refund 4, ACH/no extras | Original charge $1,010; net $950, fee $50, spread $10. Refund $404; net reduction $380, fee $20, spread $4. Remaining net $570, fee $30, spread $6; six units continue. |
| T09 | Same T08 after all $950 transferred, seller liable | Refund $404; seller recovery $380, not $400/$404/$950. Platform reverses $20 fee and $4 spread. A reversal call specifies exactly $380. |
| T10 | T09: only $100 recoverable; later same seller earns $475 net from new $500 sale | Collect $100, outstanding $280; future offset $280, new transfer $195. New contractual net stays $475 and new fee $25. Debt zero; total recovery $380. |
| T11 | Two ordered fills A `P=$100`, B `P=$200`, card, no extras, `B=S` | Total surcharge $9.25, charge $309.25. Surcharge A $3.08/B $6.17. Refund A $103.08 under fixture; B charge allocation $206.17/net $190 remains. |
| T12 | One fill 3 units at seller/buyer $0.10, ACH | Gross $0.30; fee rounds $0.015→$0.02; net $0.28. Fee unit slices [.01,.01,.00], nets [.09,.09,.10]. Refund unit 1: $.10 = $.09 net + $.01 fee; all three refunds total $.30 exactly. |
| T13 | Two distinct fills each gross $.10 | Each fee $.01; total fee $.02. Do not round combined $.20 fee to $.01. Different fill boundaries are intentional and snapshotted. |
| T14 | Allocate $.01 equally across three ordered units | Shares [.01,.00,.00]. Repeated runs and reordered input produce same output after stable-ID sorting. |
| T15 | Buyer price $99, seller $100 | Reject before payment/reservation commitment; no negative spread and no hidden $1 subsidy. |
| T16 | Grade 5 identical units at $20 flat per unit | Grading $100; accept grade-all/none, reject grade-3. Separate line of 3 other units may remain ungraded. Seller fee excludes all $100. |
| T17 | T04, failed grading after $50 cost incurred; tax fixture: all $40 relates to merchandise | Refund merchandise $1,001 + tax $40 + refundable surcharge $32.09 = $1,073.09. Retain grading $50 + original grading surcharge $1.54 = $51.54. Seller net $0; fee/spread fully reversed. No grading fee refund. |
| T18 | T04 cancelled before grading cost incurred, full refundable fixture | Refund full $1,124.63; reverse $950 net/$50 fee/$1 spread/$50 grading/$40 tax/$33.63 surcharge. Actual nonreturned provider costs remain Metex expense. |
| T19 | T04 failed grading, configured test policy retains all card surcharge | Refund $1,041; retain incurred grading $50 and surcharge $33.63. Policy version recorded; never substitute this policy for T17 silently. |
| T20 | 5 graded units, fee $20/unit; cancel 2 before their service cost incurred, ACH/no tax, `B=S=$100/unit` | Refund $240 = merchandise $200 + grading $40; reverse net $190/fee $10. Remaining three units all graded, grading liability $60, net $285. |
| T21 | T02 refund before transfer | Refund $1,001; cancel net $950, reverse fee $50/spread $1. No seller transfer; actual ACH/insurance costs remain expenses unless actual vendor refunds posted separately. |
| T22 | Transfer $950 succeeded; bank payout fails | Transfer total remains $950; no new $950 transfer or reinstated payable. Bank status failed until evidence-backed retry completes. |
| T23 | T02 final chargeback loss, test policy seller liable for merchandise net only, no chargeback fee | Provider debit $1,001; recovery $950 after transfer, platform fee/spread reversals $51. Ordinary refund call count zero. Before transfer: hold/cancel affected $950 instead of post-transfer collection. |
| T24 | T23 provisional debit followed by win | Provider debit $1,001 then credit $1,001; net dispute cash $0. No duplicate refund/recovery; original net entitlement preserved/restored according to actual prior movements. |
| T25 | Insurance claim approved $1,000, cash received $600 then $400 | Claim approval is not cash. Recovery records total $1,000 once; no automatic additional buyer refund or seller fee. Liability/claim allocation fixture determines loss offset. |

### 16.2 Behavioral and adversarial test matrix

| Test | Given / when | Assertions required |
|---|---|---|
| T26 | Every registered checkout/direct-buy/form/bid route submits missing, foreign-customer, EUR, one-cent, processing, reused, or wrong-snapshot payment | Reject financial finalization; no order/payable/revenue/stock consumption. Reuse for same legitimate replay returns same order. |
| T27 | 100 concurrent double-submits and duplicate webhooks for T02 | Exactly one provider charge $1,001, one execution/order/payable, one committed quantity, one fee/spread journal and receipt event. |
| T28 | Kill process before provider call, after success before response, before DB commit, after commit before acknowledgment | Recover each checkpoint; same operation key; one cash effect. No browser/session needed. |
| T29 | Early webhook, duplicated webhook, stale failure after success, inbox DB unavailable, worker exception | Early event retained; no regression; storage failure retryable; persisted event internally retried; no silent loss. |
| T30 | 3DS succeeds after browser closes; another attempt expires | Success recovers full ledger/order/reservation; expiry safely retires payment and releases once. No fulfillment on action-required. |
| T31 | ACH pending beyond ordinary TTL, then success without approval, then approval | Reservation retained; no early ship/deadline; held net on success; first authorization and X-day clock only on approval. |
| T32 | ACH returns before ship / in transit / after transfer | Revoked approval and correct scoped hold/debit; no auto seller debt without liability policy; no stock relist in transit. |
| T33 | Bid failure at 2026-09-11 12:00Z | Correction expires 2026-09-12 12:00Z. At 11:59:59 reservation retained; timely success commits; at deadline no new correction allowed. Processing/unknown outcome reconciles before release. Retry does not reset deadline. |
| T34 | Two buyers compete for last unit; two sellers for last bid unit; batch exceeds seller stock | Total reserved+committed never exceeds supply/bid. Losing command never charges for unavailable quantity. Test on actual PostgreSQL connections. |
| T35 | Parent bid 10 units fills 3,4,3 on separate dates | Three independent payments/executions, remaining 7,3,0. Refunding first execution does not charge/refund others or automatically reopen bid. |
| T36 | Nonparticipant / other seller submits tracking, buyer changes final grading address | Forbidden; no tracking/status/cancellation mutations. Authorized seller can act only on owned leg. |
| T37 | X=3; ship authorization Sep 11 12:00Z; fake text/label-only then deadline Sep 14 12:00Z | Text does not qualify; forfeit/refund only affected fill; net cannot release; inventory inactive. Configuration change to X=5 does not change existing deadline. |
| T38 | Delivery Sep 11 12:00Z non-graded | Release blocked until Sep 12 12:00Z; at exact boundary allowed only with no other hold. Malformed timestamp blocks. DST/local timezone irrelevant. |
| T39 | Grader receives, then authenticates successfully | No release at receipt. Final passed units eligible without extra buyer-delivery-day requirement; failed/pending units remain blocked. |
| T40 | Incurrence and cancellation race; grader returns failure; vendor later credits Metex | Serialize service commitments; classify exact costs once. Incurred fee still not buyer-refundable; vendor credit separate. |
| T41 | Refund 4 units from T08 concurrently twice, using same and different request IDs | Same ID replays; different ID cannot select same unit slices; sum refunded ≤ original; six units unaffected. |
| T42 | Refund approved but provider fails/timeouts | Hold/entitlement remains; UI pending/failed truthfully; no `RESOLVED_REFUND` until confirmed cash result; same key on safe retry. |
| T43 | Dispute opens concurrently with admin/direct/batch transfer | Shared gate and serialization tested at all call sites; pre-dispatch hold blocks, already-dispatched uncertainty triggers recovery. No second transfer. |
| T44 | Partial refund after multi-fill payout; reversal API supports remaining full amount default | Explicit partial amount passed; unrelated seller and unrelated same-seller fill not reversed. |
| T45 | Two holds; resolve one, or chargeback win while shipping failure persists | Other hold remains and blocks transfer. |
| T46 | Loss on each graded leg; one policy only covers first leg | Second dispatch blocked without own configured coverage; separate claim attribution; later loss not automatically seller liability. |
| T47 | Chargeback plus already succeeded/pending partial refund | Actual provider credits/debits reconciled, no duplicate compensation or overcollection; attribution correct for all sellers. |
| T48 | Tax missing address, vendor error, wrong product code; tax reversal retries | No fake zero/8.25% quote; no charge without valid policy/evidence. One posted tax transaction/reversal per event. |
| T49 | Change policy, quote, listing price, cart, payment method, or address after preparation | Frozen old snapshot unchanged; successor consent/payment closure required. Same key with different payload conflicts. |
| T50 | Provider operation unknown past provider idempotency retention; stale worker lease | No fresh blind operation; reconcile first; fencing prevents stale writes. |
| T51 | Reconciliation sees orphan charge, orphan refund, duplicate allocation, unmatched payout, negative stock | Owned cases/alerts; replay safe commands; no invented cash or balance edits. |
| T52 | Restore backup and replay inbox/outbox | No second charge/refund/transfer; provider reconciliation catches effects newer than backup. |
| T53 | Clean PostgreSQL bootstrap and upgrade from audit-era schema | Ordered migrations succeed; constraints active; no swallowed errors; legacy ambiguous payments held; rollback does not enable bypass routes. |
| T54 | Frozen seller, revoked session, missing role, payment/insurance emergency stop | All alternate routes/workers enforce restrictions; remediation/inbox/reconciliation remain operable with proper authority. |
| T55 | Refund then physical return of failed-authentication unit | No double stock increase; unit remains quarantined pending approved review. |
| T56 | Card/ACH actual fee differs from quote | Exact actual expense posted and reconciliation variance surfaced; seller remains contractual 95%; no silent buyer recharge. |

## 17. Migration and deprecation of legacy transaction paths

Implement against current code after verifying registration; these audit-era locations identify likely consolidation work:

| Area / audited paths | Required migration outcome |
|---|---|
| `core/blueprints/checkout/routes.py`, `services/order_service.py` | Replace session-dependent finalize/prepare/3DS recovery with durable bound snapshot and atomic finalizer. No missing-payment bypass or arbitrary PI attachment. |
| `core/blueprints/buy/purchase.py`, `core/blueprints/buy/direct_purchase.py` | Route every reachable direct purchase through canonical checkout or disable mutation endpoints. Merely hiding buttons is insufficient. |
| `core/blueprints/bids/accept_bid.py`, `auto_match.py`, `place_bid.py` | One matching/reservation/payment service; durable payment recovery and 24-hour correction; concurrency-safe remaining quantities. |
| `core/blueprints/stripe_connect/routes.py` | Durable verified inbox and full payment/failure/return/dispute/transfer/payout event coverage. No acknowledge-and-drop unlinked successes or swallowed errors. |
| `core/services/ledger/escrow_control.py`, `order_creation.py`, `fee_config.py` | One journal/money engine; full gate at actual transfer; stable refund/reversal keys and explicit amounts; remove whole-order partial-refund behavior. Existing “escrow” labels confer no product/legal promise. |
| `routes/cancellation_routes.py`, `services/dispute_service.py`, `services/tracking_forfeiture_service.py` | Canonical refund entitlement/cash state, scoped holds, no refund-completed promises from ledger-only edits. |
| `core/blueprints/sell/routes.py`, `core/blueprints/admin/orders.py` | Owned valid tracking, evidenced delivery, independent fill decisions, no admin release bypass. |
| `services/order_state.py`, `services/ledger_constants.py` and UI/report consumers | One transition model/projections; distinguish partial refund, held/transferred/bank-paid/recovery states. |
| Checkout tax and `core/blueprints/admin/tax.py` | Authoritative addresses, tax classification, durable transaction/reversal lifecycle; delete error fallback assumptions. |
| `database.py`, schema/bootstrap and `migrations/` | Production PostgreSQL transactions/constraints; ordered unique migrations; clean install and upgrade; fail-fast schema checks. |
| Payment/refund/security tests and registered route manifest | Remove expectations that bless missing-payment orders; repair complete isolated fixtures and certify actual live entry points. |

Migration sequence:

1. Inventory every registered route, scheduled task, CLI/admin operation, direct provider SDK call, ledger mutation, legacy status and report consumer. Produce a mapping to canonical commands and prohibit new direct financial calls outside the adapter.
2. Add canonical tables, unique constraints, nullable legacy linkage, immutable snapshots for new transactions and inbox/outbox. Build the full production-equivalent test schema from migrations.
3. Backfill from original order/payment/ledger/provider evidence. Do not use today's price/fee to fabricate historical economics. Preserve historical original policy and evidence; no retroactive 5% repricing of completed legacy transactions.
4. Detect duplicate provider bindings, unpaid legacy orders, missing seller allocation, unbalanced entries and ambiguous paid-out labels. Quarantine and reconcile; never guess bank-paid status or automatically charge buyers/recover sellers to “fix” old records.
5. Record verified opening balances and explicit migration adjustments with provenance. Map legacy transfers to connected balances/bank payouts where evidence exists. Unmapped amounts remain held/suspense cases with owners.
6. Run shadow/read-only reconciliation of the new model; never dual-submit external money. Cut over all entry points together or disable unmigrated paths. Drain/claim old workers safely with shared operation identities and deployment fencing.
7. Update all buyer/seller/admin notifications, reports, disclosures and exports. Make legacy read adapters explicit and temporary. Remove or disable obsolete mutation routes/functions after replacement coverage; retain needed audit history.
8. Run fresh-install and upgrade drills, concurrent staging tests and provider sandbox lifecycle. Verify rollback can stop new operations but cannot revive bypasses or replay already submitted operations. Restore/reconcile before reopening money movement.

A coding agent must deliver migrations, implementation, tests, route/adapter inventory, policy registry, runbooks and evidence together. It must report remaining blocked configuration precisely, never mark a disabled required feature implemented end-to-end without disclosure.

## 18. Final P0 implementation checklist and definition of done

Check a box only with linked code/migration/test or external evidence in the implementation PR. “Not applicable” requires an explicitly disabled launch scope and explanation; it is not a silent omission. This checklist completes the flow-of-funds implementation; the broader audit's remaining security, hosting, onboarding and operational launch gates still apply.

- [ ] **P0-01 Secure binding:** every registered financial path rejects absent/foreign/wrong amount/currency/rail/snapshot/reused payments; T26 passes.
- [ ] **P0-02 Durable identity:** checkout and immutable snapshot exist before external call; unique accepted payment/execution/payable constraints; T27/T49 pass.
- [ ] **P0-03 Atomic commitments:** inventory, bids, orders, fills, payables, journal and outbox commit together; PostgreSQL contention and crash tests T28/T34/T35 pass.
- [ ] **P0-04 Webhook recovery:** durable authenticated inbox, early/duplicate/late/retry handling and orphan-payment recovery; T20/T22 scenarios and T28/T29/T51 pass.
- [ ] **P0-05 Payment lifecycle:** card/3DS and ACH pending/success/approval/failure/return, 24-hour bid correction and safe expiration implemented; T30–T33 pass.
- [ ] **P0-06 Financial formulas:** integer rounding, immutable unit allocations, 5% seller fee, positive spread, total-base gross-up, zero buyer ACH fee and separate expenses; T01–T21/T56 pass.
- [ ] **P0-07 Tracking and insurance:** server ownership/qualification, admin X deadline, forfeiture, per-leg UPS purchase/claims, grading forms/results/incurrence; T16–T20/T36–T40/T46/T55 pass.
- [ ] **P0-08 Payout consistency:** all gates enforced at transfer boundary, holds compose, exact 24-hour delivery/authentication rules, connected transfer distinct from bank payout; T22/T38/T39/T43/T45 pass.
- [ ] **P0-09 Money idempotency:** stable claimed operations for charge/refund/transfer/reversal, unknown result reconciliation and caps; T27/T28/T41–T44/T50 pass.
- [ ] **P0-10 Unified cancellation/refund:** buyer/seller/admin/dispute/forfeiture use one engine; partial quantity and multi-seller isolation, tax/service/surcharge allocation, truthful pending failures; T07–T11/T17–T21/T41/T42/T44/T48 pass.
- [ ] **P0-11 Disputes and chargebacks:** scoped automatic holds, external evidence/deadlines/debits/outcomes, overlap prevention and post-transfer recovery; T23/T24/T43/T45/T47 pass.
- [ ] **P0-12 Recovery:** capped same-seller collection ladder, explicit liability, reserve and negative balance without duplicate debt; T09/T10/T23 pass.
- [ ] **P0-13 Unified states and ledger:** transitions reject invalid actors/events; immutable balanced journals, exact conservation and projections; every scenario S01–S46 has assertions and no divergent status writes.
- [ ] **P0-14 Tax/configuration gates:** approved production mappings, no tax fallbacks, grading/insurance/ACH/refund/liability gaps surfaced before payment; T48/T49 pass; required scope configuration has evidence.
- [ ] **P0-15 Migration:** live route inventory complete; legacy bypass/ledger-only cash promises/blanket partial reversals disabled; clean PostgreSQL install and upgrade/rollback drills; T53 passes.
- [ ] **P0-16 Reconciliation/operations:** owned cases, alerts, outbox retries, emergency controls, backups/restore and replay runbooks tested; T51/T52/T54 pass.
- [ ] **P0-17 Staging evidence:** complete automated suite with repaired fixtures; actual PostgreSQL concurrency/fault tests; provider sandbox cards/3DS/ACH/refunds/transfers/bank event tests; browser-loss/mobile flow; vendor adapter tests and manual-evidence workflows. Mocks alone do not close integration gates.
- [ ] **P0-18 External launch evidence:** Authorized Metex Administrator records provider acceptance of intended marketplace/rails/hold model, seller onboarding readiness, actual UPS contents/leg coverage, grading agreement, tax and policy/disclosure approvals, reserve/recovery operations and staffed case ownership. This spec does not assert these approvals exist.

Implementation is complete only when required code and migrations are merged, T01–T56 and S01–S46 are covered with retained results, no unexplained reconciliation differences remain in staging, and every required production configuration is approved or its affected scope is explicitly disabled. Real-money launch additionally requires the external and broader audit gates; test counts or this document's existence alone do not establish readiness.
