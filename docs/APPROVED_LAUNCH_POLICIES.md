# Metex Approved Launch Policies

Approved September 14, 2026. This file records business decisions and is
subordinate only to `FLOW_OF_FUNDS_IMPLEMENTATION_SPEC.md`, including its
launch amendment. A conflicting legacy path must be changed or disabled.

## Scope and pricing

- Launch scope is United States, USD, precious-metal coins and bullion.
- Existing sell-page item filters remain available. The product's intrinsic
  grade/certification is an item attribute; it is distinct from the removed
  optional grading-service add-on.
- Launch payment rails are cards and ACH.
- Card surcharge is the approved 2.99% gross-up against the entire pre-card-fee
  checkout total. ACH buyer surcharge is zero.
- Quotes, inventory reservations, and unfinished 3DS authorizations expire
  after 900 seconds. Every spot-linked price is rechecked immediately before
  confirmation. A cent-level change requires a new displayed total and renewed
  consent.

## Fulfillment and insurance

- Seller pays ordinary shipping.
- Metex authorizes shipment only after payment approval. An ACH order is shown
  as sold/pending while ACH is pending; the tracking deadline does not begin.
- Seller must upload qualifying tracking within three calendar days after ship
  authorization. The admin dashboard exposes a whole-day dropdown for this
  value.
- Qualifying tracking is accepted by UPS, belongs to the affected seller and
  destination, and has not been used for another order. Arbitrary text and a
  label without carrier acceptance do not qualify.
- Signature is required when merchandise value is at least $500.
- Metex purchases insurance for every shipment, targeted at full merchandise
  replacement value. Expected premium is approximately 1% of item value and is
  a Metex expense funded from marketplace economics, never a buyer or seller
  charge.
- Buyer refund follows the carrier's formal loss confirmation. Actual coverage,
  eligible bullion, limits, integration, and claim evidence remain an external
  UPS contract gate.

## Grading

- The optional third-party grading add-on is removed from launch in full.
- New pages and APIs cannot select, charge, ship to, or create a custody leg for
  the removed service. Historical compatibility columns do not authorize use.

## Cancellations, returns, disputes, and recovery

- Refund the attributable card surcharge when Metex or seller causes the
  cancellation.
- Retain the attributable card surcharge for a voluntary buyer cancellation
  after the processing cost was incurred.
- Buyer-remorse returns are not allowed.
- Seller-fault returns are allowed for counterfeit, wrong item, material
  misdescription, damage, or failed authentication. Buyer must report within
  three calendar days after delivery. Seller pays confirmed seller-fault return
  shipping. There is no restocking fee.
- Seller liability for chargebacks applies to counterfeit, wrong item,
  misdescription, and failure to fulfill. Buyer/payment fraud is initially a
  Metex exposure subject to evidence. ACH returns and other reasons require
  reason-specific review; the seller is never debited automatically for an
  unknown reason.
- Recovery methods, in order, are provider transfer reversal, connected-account
  available balance, future seller-proceeds offsets, an internal negative
  recovery ledger, repayment request, and suspension. This internal ledger is
  not a spendable customer wallet. Any unresolved negative recovery obligation
  suspends new selling and payout activity until resolved.

## Payouts and operations

- Eligible seller funds are evaluated for release daily.
- All mandatory payment, tracking, delivery, dispute, account, and insurance
  gates apply. A payout above $10,000 requires manual review.
- Use Stripe Tax where Metex has a collection obligation, subject to tax-adviser
  review.
- Card surcharge is processing-cost recovery, not marketplace revenue.
- Bid priority is highest effective buyer price, then earliest bid. Minimum
  partial fill is one whole item. Self-trading is prohibited.
- Reconcile daily and scan continuously for discrepancies. Financial exceptions
  receive human review within one business day.
- Public transactions remain disabled until live Stripe tests, UPS coverage,
  tax/legal review, tested Render backups, and production monitoring are ready.

