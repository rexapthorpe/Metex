"""Canonical Metex flow-of-funds engine.

All values in this module are integer minor units.  Provider calls are claimed in
``financial_operations`` before execution and every database mutation is made in
the caller's transaction.  Legacy order tables are projections for the current UI;
the immutable checkout snapshot and balanced journal are authoritative.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import database as database_module
from database import get_db_connection

POLICY_VERSION = "flow-of-funds-v1"
SELLER_FEE_BPS = 500
CARD_RATE_BPS = 299

STATE_TRANSITIONS = {
 "checkout": {"RESERVED":{"PAYMENT_PENDING","FAILED"},"PAYMENT_PENDING":{"PAYMENT_PROCESSING","PAYMENT_CORRECTION","FINALIZED","FAILED"},"PAYMENT_PROCESSING":{"FINALIZED","PAYMENT_CORRECTION"},"PAYMENT_CORRECTION":{"PAYMENT_PENDING","FAILED"}},
 "payment": {"CLAIMED":{"SUBMITTED","FAILED"},"SUBMITTED":{"SUCCEEDED","FAILED","UNKNOWN"},"APPROVAL_PENDING":{"APPROVED","RETURNED"},"APPROVED":{"RETURNED"}},
 "fill": {"FUNDED":{"REFUND_PENDING","FORFEITED"},"REFUND_PENDING":{"PARTIALLY_REFUNDED","REFUNDED"}},
 "shipment": {"NOT_AUTHORIZED":{"AWAITING_TRACKING"},"AWAITING_TRACKING":{"TRACKING_VERIFICATION_PENDING","FORFEITED"},"TRACKING_VERIFICATION_PENDING":{"IN_TRANSIT","AWAITING_TRACKING"},"IN_TRANSIT":{"DELIVERED","LOST","DAMAGED","RETURNED"}},
 "grading": {"AWAITING_SHIP_AUTHORIZATION":{"IN_TRANSIT"},"IN_TRANSIT":{"RECEIVED"},"RECEIVED":{"AUTHENTICATED","FAILED"}},
 "refund": {"CLAIMED":{"SUBMITTED","FAILED"},"SUBMITTED":{"SUCCEEDED","FAILED","UNKNOWN"}},
 "payout": {"HELD":{"RELEASE_APPROVED","CANCELLED"},"RELEASE_APPROVED":{"TRANSFERRED_TO_CONNECTED_ACCOUNT","HELD"},"TRANSFERRED_TO_CONNECTED_ACCOUNT":{"BANK_PAYOUT_PENDING","RECOVERY_PENDING"},"BANK_PAYOUT_PENDING":{"BANK_PAYOUT_PAID","BANK_PAYOUT_FAILED"}},
 "recovery": {"OPEN":{"PARTIAL","RECOVERED","SUSPENDED"},"PARTIAL":{"RECOVERED","SUSPENDED"}},
}


class FlowError(Exception):
    def __init__(self, message, code="FLOW_ERROR", status=400):
        super().__init__(message)
        self.code, self.status = code, status


def assert_transition(machine, before, after):
    if before==after: return
    if after not in STATE_TRANSITIONS.get(machine,{}).get(before,set()):
        raise FlowError(f"Invalid {machine} transition: {before} -> {after}","INVALID_STATE_TRANSITION",409)


def money_to_cents(value) -> int:
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_ratio(numerator: int, denominator: int) -> int:
    return int((Decimal(numerator) / Decimal(denominator)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def seller_fee_cents(seller_gross_cents: int) -> int:
    return round_ratio(seller_gross_cents * SELLER_FEE_BPS, 10_000)


def card_surcharge_cents(pre_fee_total_cents: int, rate_bps: int = CARD_RATE_BPS) -> int:
    if not 0 <= rate_bps < 10_000:
        raise ValueError("card rate must be between 0 and 10000 basis points")
    return round_ratio(pre_fee_total_cents * rate_bps, 10_000 - rate_bps)


def allocate_largest_remainder(total_cents: int, weights: list[int]) -> list[int]:
    if total_cents < 0 or any(w < 0 for w in weights):
        raise ValueError("allocations cannot be negative")
    if not weights:
        return []
    weight_sum = sum(weights)
    if weight_sum == 0:
        base, remainder = divmod(total_cents, len(weights))
        return [base + (1 if i < remainder else 0) for i in range(len(weights))]
    raw = [Decimal(total_cents) * Decimal(w) / Decimal(weight_sum) for w in weights]
    floors = [int(v) for v in raw]
    remainder = total_cents - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: (raw[i] - floors[i], -i), reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return floors


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def ensure_flow_schema(conn):
    """Create additive canonical tables. Safe for SQLite and PostgreSQL."""
    statements = [
        """CREATE TABLE IF NOT EXISTS flow_policy_config (
          key TEXT PRIMARY KEY, value_json TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0,
          updated_by INTEGER, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS checkout_attempts (
          id TEXT PRIMARY KEY, buyer_id INTEGER NOT NULL, idempotency_key TEXT NOT NULL,
          request_hash TEXT NOT NULL, state TEXT NOT NULL, active_snapshot_id TEXT,
          provider_payment_id TEXT UNIQUE, expires_at TIMESTAMP, created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL, UNIQUE(buyer_id,idempotency_key))""",
        """CREATE TABLE IF NOT EXISTS execution_snapshots (
          id TEXT PRIMARY KEY, checkout_id TEXT NOT NULL, version INTEGER NOT NULL,
          snapshot_hash TEXT NOT NULL UNIQUE, currency TEXT NOT NULL, payment_rail TEXT NOT NULL,
          buyer_id INTEGER NOT NULL, merchandise_cents INTEGER NOT NULL, tax_cents INTEGER NOT NULL,
          grading_cents INTEGER NOT NULL, other_buyer_charges_cents INTEGER NOT NULL,
          card_surcharge_cents INTEGER NOT NULL, buyer_total_cents INTEGER NOT NULL,
          shipping_json TEXT NOT NULL, snapshot_json TEXT NOT NULL, created_at TIMESTAMP NOT NULL,
          UNIQUE(checkout_id,version))""",
        """CREATE TABLE IF NOT EXISTS snapshot_lines (
          id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, listing_id INTEGER NOT NULL,
          seller_id INTEGER NOT NULL, quantity INTEGER NOT NULL, buyer_unit_cents INTEGER NOT NULL,
          seller_unit_cents INTEGER NOT NULL, buyer_gross_cents INTEGER NOT NULL,
          seller_gross_cents INTEGER NOT NULL, seller_fee_cents INTEGER NOT NULL,
          seller_net_cents INTEGER NOT NULL, spread_cents INTEGER NOT NULL,
          tax_cents INTEGER NOT NULL DEFAULT 0, grading_cents INTEGER NOT NULL DEFAULT 0,
          card_surcharge_cents INTEGER NOT NULL DEFAULT 0, grading_requested INTEGER NOT NULL DEFAULT 0,
          grading_cost_incurred INTEGER NOT NULL DEFAULT 0, source_bid_id INTEGER,
          UNIQUE(snapshot_id,listing_id,seller_id))""",
        """CREATE TABLE IF NOT EXISTS inventory_reservations (
          id TEXT PRIMARY KEY, checkout_id TEXT NOT NULL, listing_id INTEGER NOT NULL,
          quantity INTEGER NOT NULL, state TEXT NOT NULL, expires_at TIMESTAMP,
          created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL,
          UNIQUE(checkout_id,listing_id))""",
        """CREATE TABLE IF NOT EXISTS bid_quantity_reservations (
          id TEXT PRIMARY KEY, checkout_id TEXT NOT NULL UNIQUE, bid_id INTEGER NOT NULL,
          quantity INTEGER NOT NULL, state TEXT NOT NULL, expires_at TIMESTAMP,
          created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS financial_operations (
          id TEXT PRIMARY KEY, operation_type TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
          aggregate_type TEXT NOT NULL, aggregate_id TEXT NOT NULL, amount_cents INTEGER NOT NULL,
          currency TEXT NOT NULL, state TEXT NOT NULL, provider TEXT, provider_object_id TEXT,
          request_hash TEXT NOT NULL, last_error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
          created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS executions (
          id TEXT PRIMARY KEY, checkout_id TEXT NOT NULL UNIQUE, snapshot_id TEXT NOT NULL UNIQUE,
          payment_operation_id TEXT NOT NULL UNIQUE, provider_payment_id TEXT NOT NULL UNIQUE,
          buyer_id INTEGER NOT NULL, legacy_order_id INTEGER UNIQUE, state TEXT NOT NULL,
          payment_state TEXT NOT NULL, payment_approved_at TIMESTAMP, created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS seller_fills (
          id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, snapshot_line_id TEXT NOT NULL UNIQUE,
          seller_id INTEGER NOT NULL, quantity INTEGER NOT NULL, state TEXT NOT NULL,
          seller_gross_cents INTEGER NOT NULL, seller_fee_cents INTEGER NOT NULL,
          seller_net_cents INTEGER NOT NULL, spread_cents INTEGER NOT NULL,
          refunded_quantity INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS seller_payables (
          id TEXT PRIMARY KEY, seller_fill_id TEXT NOT NULL UNIQUE, seller_id INTEGER NOT NULL,
          amount_cents INTEGER NOT NULL, released_cents INTEGER NOT NULL DEFAULT 0,
          recovered_cents INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL,
          block_reason TEXT, release_eligible_at TIMESTAMP, created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS holds (
          id TEXT PRIMARY KEY, seller_fill_id TEXT NOT NULL, hold_type TEXT NOT NULL,
          reason TEXT NOT NULL, state TEXT NOT NULL, source_id TEXT, created_at TIMESTAMP NOT NULL,
          released_at TIMESTAMP, UNIQUE(seller_fill_id,hold_type,source_id))""",
        """CREATE TABLE IF NOT EXISTS ledger_journals (
          id TEXT PRIMARY KEY, aggregate_type TEXT NOT NULL, aggregate_id TEXT NOT NULL,
          event_type TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
          created_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS ledger_entries (
          id TEXT PRIMARY KEY, journal_id TEXT NOT NULL, account_code TEXT NOT NULL,
          owner_type TEXT, owner_id TEXT, debit_cents INTEGER NOT NULL DEFAULT 0,
          credit_cents INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL,
          component TEXT NOT NULL, fill_id TEXT, created_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS webhook_inbox (
          provider TEXT NOT NULL, event_id TEXT NOT NULL, event_type TEXT NOT NULL,
          payload_json TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
          last_error TEXT, received_at TIMESTAMP NOT NULL, processed_at TIMESTAMP,
          PRIMARY KEY(provider,event_id))""",
        """CREATE TABLE IF NOT EXISTS outbox_events (
          id TEXT PRIMARY KEY, event_type TEXT NOT NULL, aggregate_type TEXT NOT NULL,
          aggregate_id TEXT NOT NULL, payload_json TEXT NOT NULL, state TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP NOT NULL, sent_at TIMESTAMP,
          UNIQUE(event_type,aggregate_type,aggregate_id))""",
        """CREATE TABLE IF NOT EXISTS flow_refunds (
          id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, financial_operation_id TEXT NOT NULL UNIQUE,
          reason_code TEXT NOT NULL, state TEXT NOT NULL, total_cents INTEGER NOT NULL,
          provider_refund_id TEXT, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS refund_allocations (
          id TEXT PRIMARY KEY, refund_id TEXT NOT NULL, seller_fill_id TEXT NOT NULL,
          quantity INTEGER NOT NULL, seller_net_cents INTEGER NOT NULL, seller_fee_cents INTEGER NOT NULL,
          spread_cents INTEGER NOT NULL, tax_cents INTEGER NOT NULL, grading_cents INTEGER NOT NULL,
          card_surcharge_cents INTEGER NOT NULL, other_cents INTEGER NOT NULL,
          total_cents INTEGER NOT NULL, UNIQUE(refund_id,seller_fill_id))""",
        """CREATE TABLE IF NOT EXISTS shipments (
          id TEXT PRIMARY KEY, seller_fill_id TEXT NOT NULL, leg_type TEXT NOT NULL,
          carrier TEXT, tracking_number TEXT, tracking_validated INTEGER NOT NULL DEFAULT 0,
          state TEXT NOT NULL, ship_authorized_at TIMESTAMP, tracking_due_at TIMESTAMP,
          delivered_at TIMESTAMP, destination_type TEXT NOT NULL, created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL, UNIQUE(seller_fill_id,leg_type))""",
        """CREATE TABLE IF NOT EXISTS insurance_policies (
          id TEXT PRIMARY KEY, shipment_id TEXT NOT NULL UNIQUE, provider TEXT NOT NULL DEFAULT 'UPS',
          policy_number TEXT, insured_value_cents INTEGER NOT NULL, premium_cents INTEGER,
          state TEXT NOT NULL, evidence_json TEXT, created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS insurance_claims (
          id TEXT PRIMARY KEY, insurance_policy_id TEXT NOT NULL, provider_claim_id TEXT UNIQUE,
          state TEXT NOT NULL, claimed_cents INTEGER NOT NULL, received_cents INTEGER NOT NULL DEFAULT 0,
          evidence_json TEXT, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS grading_legs (
          id TEXT PRIMARY KEY, seller_fill_id TEXT NOT NULL UNIQUE, vendor TEXT,
          seller_form_reference TEXT, state TEXT NOT NULL, cost_incurred_at TIMESTAMP,
          authenticated_at TIMESTAMP, failed_at TIMESTAMP, created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS transfers (
          id TEXT PRIMARY KEY, seller_payable_id TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE,
          provider_transfer_id TEXT UNIQUE, amount_cents INTEGER NOT NULL, state TEXT NOT NULL,
          created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS bank_payouts (
          id TEXT PRIMARY KEY, seller_id INTEGER NOT NULL, provider_payout_id TEXT NOT NULL UNIQUE,
          state TEXT NOT NULL, amount_cents INTEGER NOT NULL, arrival_at TIMESTAMP,
          created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS processor_disputes (
          id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, provider_dispute_id TEXT NOT NULL UNIQUE,
          state TEXT NOT NULL, amount_cents INTEGER NOT NULL, reason TEXT,
          created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS dispute_fill_links (
          dispute_id INTEGER NOT NULL, seller_fill_id TEXT NOT NULL, created_at TIMESTAMP NOT NULL,
          PRIMARY KEY(dispute_id,seller_fill_id))""",
        """CREATE TABLE IF NOT EXISTS recovery_obligations (
          id TEXT PRIMARY KEY, seller_id INTEGER, seller_fill_id TEXT, source_type TEXT NOT NULL,
          source_id TEXT NOT NULL, amount_cents INTEGER NOT NULL, recovered_cents INTEGER NOT NULL DEFAULT 0,
          state TEXT NOT NULL, liability_policy_key TEXT, created_at TIMESTAMP NOT NULL,
          updated_at TIMESTAMP NOT NULL, UNIQUE(source_type,source_id,seller_fill_id))""",
        """CREATE TABLE IF NOT EXISTS recovery_attempts (
          id TEXT PRIMARY KEY, recovery_id TEXT NOT NULL, method TEXT NOT NULL,
          amount_cents INTEGER NOT NULL, state TEXT NOT NULL, provider_object_id TEXT,
          evidence_json TEXT, created_at TIMESTAMP NOT NULL,
          UNIQUE(recovery_id,method,provider_object_id))""",
        """CREATE TABLE IF NOT EXISTS reconciliation_cases (
          id TEXT PRIMARY KEY, provider TEXT NOT NULL, object_type TEXT NOT NULL,
          object_id TEXT NOT NULL, variance_cents INTEGER NOT NULL, state TEXT NOT NULL,
          details_json TEXT NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL,
          UNIQUE(provider,object_type,object_id))""",
        """CREATE TABLE IF NOT EXISTS flow_audit_events (
          id TEXT PRIMARY KEY, aggregate_type TEXT NOT NULL, aggregate_id TEXT NOT NULL,
          event_type TEXT NOT NULL, actor_type TEXT NOT NULL, actor_id TEXT,
          correlation_id TEXT, before_json TEXT, after_json TEXT, metadata_json TEXT,
          created_at TIMESTAMP NOT NULL)""",
    ]
    for sql in statements:
        conn.execute(sql)
    defaults = {
        "seller_fee_bps": 500,
        "card_rate_bps": 299,
        "card_formula": "gross_up_final_charge",
        "tracking_upload_deadline_days": 3,
        "reservation_ttl_seconds": 900,
        "refund_component_policy": {
            "seller_or_metex_fault": "refund_allocated_original_card_surcharge",
            "buyer_voluntary_after_processor_cost": "retain_allocated_original_card_surcharge",
            "unmapped_reason": "admin_review",
        },
        "ach_approval_policy": "stripe_payment_intent_succeeded",
        "ups_coverage_and_claim_policy": "adapter_and_coverage_evidence_required_per_leg",
        "grading_vendor_policy": "disabled_for_launch",
        "chargeback_loss_liability": "reason_specific_admin_review",
        "launch_scope": {"country": "US", "currency": "usd", "rails": ["card", "us_bank_account"]},
        "shipping_postage_policy": "seller_pays",
        "signature_required_threshold_cents": 50000,
        "insurance_purchase_policy": {"carrier": "UPS", "required": True, "target_rate_bps": 100,
                                      "paid_by": "metex"},
        "shipping_loss_refund_trigger": "formal_carrier_or_insurer_loss_confirmation",
        "seller_fault_return_window_days": 3,
        "seller_fault_return_postage_policy": "seller_pays",
        "buyer_remorse_returns_enabled": False,
        "restocking_fee_enabled": False,
        "payout_schedule": "daily",
        "manual_payout_review_threshold_cents": 1000000,
        "negative_balance_policy": "internal_recovery_ledger_immediate_future_proceeds_offset",
        "spot_confirmation_policy": {"quote_ttl_seconds": 900, "recheck_immediately_before_confirmation": True,
                                     "changed_price_requires_reconfirmation": True},
    }
    for key, value in defaults.items():
        if not conn.execute("SELECT key FROM flow_policy_config WHERE key=?", (key,)).fetchone():
            fixed = key in {
                "seller_fee_bps", "card_rate_bps", "card_formula", "grading_vendor_policy",
                "tracking_upload_deadline_days", "reservation_ttl_seconds", "chargeback_loss_liability",
                "refund_component_policy", "ach_approval_policy",
                "launch_scope", "shipping_postage_policy", "signature_required_threshold_cents",
                "insurance_purchase_policy", "shipping_loss_refund_trigger",
                "seller_fault_return_window_days", "seller_fault_return_postage_policy",
                "buyer_remorse_returns_enabled", "restocking_fee_enabled", "payout_schedule",
                "manual_payout_review_threshold_cents", "negative_balance_policy",
                "spot_confirmation_policy",
            }
            conn.execute("INSERT INTO flow_policy_config (key,value_json,approved) VALUES (?,?,?)",
                         (key, _canonical(value), 1 if fixed else 0))
    # Apply the newly approved launch decisions to older databases once. An
    # already-approved administrator value (for example a later tracking-day
    # selection) is preserved.
    approved_launch_keys = {
        "tracking_upload_deadline_days", "reservation_ttl_seconds", "refund_component_policy",
        "ach_approval_policy", "chargeback_loss_liability", "launch_scope",
        "shipping_postage_policy", "signature_required_threshold_cents",
        "insurance_purchase_policy", "shipping_loss_refund_trigger",
        "seller_fault_return_window_days", "seller_fault_return_postage_policy",
        "buyer_remorse_returns_enabled", "restocking_fee_enabled", "payout_schedule",
        "manual_payout_review_threshold_cents", "negative_balance_policy",
        "spot_confirmation_policy",
    }
    for key in approved_launch_keys:
        policy_row = conn.execute(
            "SELECT approved FROM flow_policy_config WHERE key=?", (key,)
        ).fetchone()
        if policy_row and not policy_row["approved"]:
            conn.execute("""UPDATE flow_policy_config SET value_json=?,approved=1
                            WHERE key=?""", (_canonical(defaults[key]), key))
    # This product removal is an approved launch rule rather than a vendor
    # configuration gate. Make existing databases converge idempotently.
    grading_policy = conn.execute(
        "SELECT value_json,approved FROM flow_policy_config WHERE key='grading_vendor_policy'"
    ).fetchone()
    disabled_value = _canonical("disabled_for_launch")
    if (not grading_policy or grading_policy["value_json"] != disabled_value
            or not grading_policy["approved"]):
        conn.execute("""UPDATE flow_policy_config SET value_json=?, approved=1
                        WHERE key='grading_vendor_policy'""", (disabled_value,))


def require_approved_policy(conn, *keys):
    missing=[]
    for key in keys:
        row=conn.execute("SELECT approved FROM flow_policy_config WHERE key=?",(key,)).fetchone()
        if not row or not row["approved"]: missing.append(key)
    if missing:
        raise FlowError("Required policy configuration is not approved: "+", ".join(missing),
                        "POLICY_CONFIGURATION_REQUIRED",503)


def set_policy_config(key, value, approved, admin_id):
    allowed={
      "card_rate_bps","card_formula","tracking_upload_deadline_days","reservation_ttl_seconds",
      "refund_component_policy","ach_approval_policy","ups_coverage_and_claim_policy",
      "grading_vendor_policy","chargeback_loss_liability"
      ,"launch_scope","shipping_postage_policy","signature_required_threshold_cents",
      "insurance_purchase_policy","shipping_loss_refund_trigger","seller_fault_return_window_days",
      "seller_fault_return_postage_policy","buyer_remorse_returns_enabled","restocking_fee_enabled",
      "payout_schedule","manual_payout_review_threshold_cents","negative_balance_policy",
      "spot_confirmation_policy"
    }
    if key not in allowed: raise FlowError("Unknown policy key","UNKNOWN_POLICY_KEY")
    if key=="tracking_upload_deadline_days" and (not isinstance(value,int) or value<=0):
        raise FlowError("Tracking deadline must be a positive whole number","INVALID_POLICY_VALUE")
    if key=="card_rate_bps" and value!=299:
        raise FlowError("Approved card rate is 299 basis points","INVALID_POLICY_VALUE")
    conn=get_db_connection(); ensure_flow_schema(conn); old=conn.execute("SELECT * FROM flow_policy_config WHERE key=?",(key,)).fetchone(); now=_now()
    conn.execute("""INSERT INTO flow_policy_config (key,value_json,approved,updated_by,updated_at)
      VALUES (?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
      approved=excluded.approved,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
      (key,_canonical(value),1 if approved else 0,admin_id,now))
    _audit(conn,"policy",key,"POLICY_CONFIG_UPDATED","admin",admin_id,before=dict(old) if old else None,
           after={"value":value,"approved":bool(approved)})
    conn.commit(); conn.close()


def _audit(conn, aggregate_type, aggregate_id, event_type, actor_type, actor_id=None,
           before=None, after=None, metadata=None, correlation_id=None):
    conn.execute("""INSERT INTO flow_audit_events
      (id,aggregate_type,aggregate_id,event_type,actor_type,actor_id,correlation_id,
       before_json,after_json,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
      (_id("aud"), aggregate_type, str(aggregate_id), event_type, actor_type,
       str(actor_id) if actor_id is not None else None, correlation_id,
       _canonical(before) if before is not None else None,
       _canonical(after) if after is not None else None,
       _canonical(metadata or {}), _now()))


def claim_operation(conn, operation_type, idempotency_key, aggregate_type, aggregate_id,
                    amount_cents, request_payload, currency="usd", provider="stripe"):
    request_hash = _digest(request_payload)
    existing = conn.execute("SELECT * FROM financial_operations WHERE idempotency_key=?",
                            (idempotency_key,)).fetchone()
    if existing:
        if existing["request_hash"] != request_hash:
            raise FlowError("Idempotency key was reused with different inputs", "IDEMPOTENCY_CONFLICT", 409)
        return dict(existing), False
    op_id, now = _id("op"), _now()
    conn.execute("""INSERT INTO financial_operations
      (id,operation_type,idempotency_key,aggregate_type,aggregate_id,amount_cents,currency,
       state,provider,request_hash,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
      (op_id,operation_type,idempotency_key,aggregate_type,str(aggregate_id),amount_cents,
       currency,"CLAIMED",provider,request_hash,now,now))
    return dict(conn.execute("SELECT * FROM financial_operations WHERE id=?", (op_id,)).fetchone()), True


def _journal(conn, aggregate_type, aggregate_id, event_type, key, entries, currency="usd"):
    existing = conn.execute("SELECT id FROM ledger_journals WHERE idempotency_key=?", (key,)).fetchone()
    if existing:
        return existing["id"]
    debit = sum(e.get("debit", 0) for e in entries)
    credit = sum(e.get("credit", 0) for e in entries)
    if debit != credit:
        raise FlowError(f"Unbalanced journal: debit={debit} credit={credit}", "UNBALANCED_LEDGER", 500)
    journal_id, now = _id("jnl"), _now()
    conn.execute("INSERT INTO ledger_journals VALUES (?,?,?,?,?,?)",
                 (journal_id,aggregate_type,str(aggregate_id),event_type,key,now))
    for e in entries:
        conn.execute("""INSERT INTO ledger_entries
          (id,journal_id,account_code,owner_type,owner_id,debit_cents,credit_cents,
           currency,component,fill_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
          (_id("ent"),journal_id,e["account"],e.get("owner_type"),str(e.get("owner_id")) if e.get("owner_id") is not None else None,
           e.get("debit",0),e.get("credit",0),currency,e["component"],e.get("fill_id"),now))
    return journal_id


def prepare_checkout(buyer_id, items, payment_rail, tax_cents, shipping, idempotency_key,
                     grading_fee_per_unit_cents=0, other_buyer_charges_cents=0,
                     reservation_ttl_seconds=900, conn=None):
    own = conn is None
    conn = conn or get_db_connection()
    ensure_flow_schema(conn)
    normalized = sorted([{
        "listing_id": int(i["listing_id"]), "quantity": int(i["quantity"]),
        "buyer_unit_cents": money_to_cents(i["price_each"]),
        "seller_unit_cents": money_to_cents(i.get("seller_price_each", i["price_each"])),
        # Grading is absent from the launch product. Historical fields remain
        # readable, but no new execution can request the removed service.
        "grading_requested": False,
        "source_bid_id": i.get("source_bid_id"),
    } for i in items], key=lambda x: (x["listing_id"], x["seller_unit_cents"]))
    if not normalized or any(i["quantity"] <= 0 for i in normalized):
        raise FlowError("Checkout has no valid items", "EMPTY_CHECKOUT")
    if payment_rail not in ("card", "us_bank_account"):
        raise FlowError("Unsupported payment method", "UNSUPPORTED_PAYMENT_RAIL")
    request_body = {"buyer_id":buyer_id,"items":normalized,"payment_rail":payment_rail,
                    "tax_cents":int(tax_cents),"shipping":shipping,
                    "other_buyer_charges_cents":int(other_buyer_charges_cents)}
    request_hash = _digest(request_body)
    existing = conn.execute("SELECT * FROM checkout_attempts WHERE buyer_id=? AND idempotency_key=?",
                            (buyer_id,idempotency_key)).fetchone()
    if existing:
        if existing["request_hash"] != request_hash:
            raise FlowError("Checkout key was reused with different inputs", "IDEMPOTENCY_CONFLICT", 409)
        snapshot = conn.execute("SELECT * FROM execution_snapshots WHERE id=?", (existing["active_snapshot_id"],)).fetchone()
        if own: conn.commit(); conn.close()
        return dict(existing), dict(snapshot), False
    checkout_id, snapshot_id, now = _id("chk"), _id("snap"), _now()
    expires = (datetime.now(timezone.utc)+timedelta(seconds=reservation_ttl_seconds)).isoformat()
    lines, merchandise, grading = [], 0, 0
    for i in normalized:
        listing = conn.execute("SELECT seller_id,quantity,active FROM listings WHERE id=?", (i["listing_id"],)).fetchone()
        if not listing or not listing["active"] or listing["quantity"] < i["quantity"]:
            raise FlowError("Inventory is no longer available", "INVENTORY_UNAVAILABLE", 409)
        # Quantity is reserved by decrementing immediately. Finalization changes only reservation state;
        # release restores it exactly once. This is safe across SQLite and PostgreSQL.
        changed = conn.execute("""UPDATE listings SET quantity=quantity-?,
          active=CASE WHEN quantity-?<=0 THEN 0 ELSE active END
          WHERE id=? AND active=1 AND quantity>=?""",
          (i["quantity"],i["quantity"],i["listing_id"],i["quantity"]))
        if changed.rowcount != 1:
            raise FlowError("Inventory is no longer available", "INVENTORY_UNAVAILABLE", 409)
        seller_id = int(listing["seller_id"])
        buyer_gross = i["buyer_unit_cents"]*i["quantity"]
        seller_gross = i["seller_unit_cents"]*i["quantity"]
        if buyer_gross < seller_gross:
            raise FlowError("Buyer execution price cannot be below seller execution price", "NEGATIVE_SPREAD", 409)
        fee = seller_fee_cents(seller_gross)
        line_grading = grading_fee_per_unit_cents*i["quantity"] if i["grading_requested"] else 0
        line = dict(i, seller_id=seller_id, buyer_gross_cents=buyer_gross,
                    seller_gross_cents=seller_gross,seller_fee_cents=fee,
                    seller_net_cents=seller_gross-fee,spread_cents=max(0,buyer_gross-seller_gross),
                    grading_cents=line_grading)
        lines.append(line); merchandise += buyer_gross; grading += line_grading
    base = merchandise+int(tax_cents)+grading+int(other_buyer_charges_cents)
    surcharge = card_surcharge_cents(base) if payment_rail == "card" else 0
    total = base+surcharge
    tax_alloc = allocate_largest_remainder(int(tax_cents), [x["buyer_gross_cents"] for x in lines])
    surcharge_alloc = allocate_largest_remainder(surcharge, [x["buyer_gross_cents"]+tax_alloc[n]+x["grading_cents"] for n,x in enumerate(lines)])
    for n,line in enumerate(lines):
        line["tax_cents"], line["card_surcharge_cents"] = tax_alloc[n], surcharge_alloc[n]
    snapshot_data = dict(request_body,policy_version=POLICY_VERSION,currency="usd",
                         merchandise_cents=merchandise,grading_cents=grading,
                         card_surcharge_cents=surcharge,buyer_total_cents=total,lines=lines)
    snapshot_hash = _digest(snapshot_data)
    conn.execute("""INSERT INTO checkout_attempts
      (id,buyer_id,idempotency_key,request_hash,state,active_snapshot_id,expires_at,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?)""",(checkout_id,buyer_id,idempotency_key,request_hash,"RESERVED",snapshot_id,expires,now,now))
    conn.execute("""INSERT INTO execution_snapshots
      (id,checkout_id,version,snapshot_hash,currency,payment_rail,buyer_id,merchandise_cents,
       tax_cents,grading_cents,other_buyer_charges_cents,card_surcharge_cents,buyer_total_cents,
       shipping_json,snapshot_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (snapshot_id,checkout_id,1,snapshot_hash,"usd",payment_rail,buyer_id,merchandise,int(tax_cents),grading,
       int(other_buyer_charges_cents),surcharge,total,_canonical(shipping),_canonical(snapshot_data),now))
    for line in lines:
        line_id = _id("line")
        conn.execute("""INSERT INTO snapshot_lines
          (id,snapshot_id,listing_id,seller_id,quantity,buyer_unit_cents,seller_unit_cents,
           buyer_gross_cents,seller_gross_cents,seller_fee_cents,seller_net_cents,spread_cents,
           tax_cents,grading_cents,card_surcharge_cents,grading_requested,source_bid_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (line_id,snapshot_id,line["listing_id"],line["seller_id"],line["quantity"],line["buyer_unit_cents"],
           line["seller_unit_cents"],line["buyer_gross_cents"],line["seller_gross_cents"],line["seller_fee_cents"],
           line["seller_net_cents"],line["spread_cents"],line["tax_cents"],line["grading_cents"],
           line["card_surcharge_cents"],1 if line["grading_requested"] else 0,line["source_bid_id"]))
        conn.execute("INSERT INTO inventory_reservations VALUES (?,?,?,?,?,?,?,?)",
                     (_id("res"),checkout_id,line["listing_id"],line["quantity"],"HELD",expires,now,now))
    _audit(conn,"checkout",checkout_id,"CHECKOUT_RESERVED","buyer",buyer_id,after=snapshot_data,correlation_id=idempotency_key)
    if own: conn.commit(); conn.close()
    return {"id":checkout_id,"buyer_id":buyer_id,"state":"RESERVED"}, {
        "id":snapshot_id,"snapshot_hash":snapshot_hash,"buyer_total_cents":total,
        "card_surcharge_cents":surcharge,"tax_cents":int(tax_cents),"merchandise_cents":merchandise,
        "grading_cents":grading,"payment_rail":payment_rail}, True


def bind_provider_payment(checkout_id, provider_payment_id, operation_id, conn=None):
    own = conn is None; conn = conn or get_db_connection(); ensure_flow_schema(conn)
    checkout = conn.execute("SELECT * FROM checkout_attempts WHERE id=?",(checkout_id,)).fetchone()
    if not checkout: raise FlowError("Checkout not found","CHECKOUT_NOT_FOUND",404)
    if checkout["provider_payment_id"] and checkout["provider_payment_id"] != provider_payment_id:
        raise FlowError("Checkout already has a different payment","PAYMENT_BINDING_CONFLICT",409)
    conn.execute("UPDATE checkout_attempts SET provider_payment_id=?,state='PAYMENT_PENDING',updated_at=? WHERE id=?",
                 (provider_payment_id,_now(),checkout_id))
    conn.execute("UPDATE financial_operations SET provider_object_id=?,state='SUBMITTED',attempts=attempts+1,updated_at=? WHERE id=?",
                 (provider_payment_id,_now(),operation_id))
    if own: conn.commit(); conn.close()


def revise_payment_rail(checkout_id, payment_rail, conn=None):
    """Create a new immutable snapshot version when the buyer selects a rail."""
    if payment_rail not in ("card", "us_bank_account"):
        raise FlowError("Unsupported payment method", "UNSUPPORTED_PAYMENT_RAIL")
    own=conn is None; conn=conn or get_db_connection(); ensure_flow_schema(conn)
    checkout=conn.execute("SELECT * FROM checkout_attempts WHERE id=?",(checkout_id,)).fetchone()
    if not checkout or checkout["state"] not in ("RESERVED","PAYMENT_PENDING","PAYMENT_PROCESSING"):
        raise FlowError("Checkout cannot be changed", "CHECKOUT_NOT_MUTABLE", 409)
    current=conn.execute("SELECT * FROM execution_snapshots WHERE id=?",(checkout["active_snapshot_id"],)).fetchone()
    if current["payment_rail"]==payment_rail:
        if own: conn.close()
        return dict(current), False
    old_lines=conn.execute("SELECT * FROM snapshot_lines WHERE snapshot_id=? ORDER BY id",(current["id"],)).fetchall()
    base=current["merchandise_cents"]+current["tax_cents"]+current["grading_cents"]+current["other_buyer_charges_cents"]
    surcharge=card_surcharge_cents(base) if payment_rail=="card" else 0
    weights=[l["buyer_gross_cents"]+l["tax_cents"]+l["grading_cents"] for l in old_lines]
    alloc=allocate_largest_remainder(surcharge,weights)
    version=current["version"]+1; sid=_id("snap"); now=_now()
    payload=json.loads(current["snapshot_json"])
    payload["payment_rail"]=payment_rail; payload["card_surcharge_cents"]=surcharge
    payload["buyer_total_cents"]=base+surcharge
    for n,line in enumerate(payload["lines"]): line["card_surcharge_cents"]=alloc[n]
    digest=_digest(payload)
    conn.execute("""INSERT INTO execution_snapshots
      (id,checkout_id,version,snapshot_hash,currency,payment_rail,buyer_id,merchandise_cents,
       tax_cents,grading_cents,other_buyer_charges_cents,card_surcharge_cents,buyer_total_cents,
       shipping_json,snapshot_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (sid,checkout_id,version,digest,current["currency"],payment_rail,current["buyer_id"],current["merchandise_cents"],
       current["tax_cents"],current["grading_cents"],current["other_buyer_charges_cents"],surcharge,base+surcharge,
       current["shipping_json"],_canonical(payload),now))
    for n,line in enumerate(old_lines):
        conn.execute("""INSERT INTO snapshot_lines
          (id,snapshot_id,listing_id,seller_id,quantity,buyer_unit_cents,seller_unit_cents,
           buyer_gross_cents,seller_gross_cents,seller_fee_cents,seller_net_cents,spread_cents,
           tax_cents,grading_cents,card_surcharge_cents,grading_requested,grading_cost_incurred,source_bid_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (_id("line"),sid,line["listing_id"],line["seller_id"],line["quantity"],line["buyer_unit_cents"],
           line["seller_unit_cents"],line["buyer_gross_cents"],line["seller_gross_cents"],line["seller_fee_cents"],
           line["seller_net_cents"],line["spread_cents"],line["tax_cents"],line["grading_cents"],alloc[n],
           line["grading_requested"],line["grading_cost_incurred"],line["source_bid_id"]))
    conn.execute("UPDATE checkout_attempts SET active_snapshot_id=?,updated_at=? WHERE id=?",(sid,now,checkout_id))
    _audit(conn,"checkout",checkout_id,"PAYMENT_RAIL_SELECTED","buyer",current["buyer_id"],
           before={"rail":current["payment_rail"],"snapshot":current["snapshot_hash"]},
           after={"rail":payment_rail,"snapshot":digest})
    result=dict(conn.execute("SELECT * FROM execution_snapshots WHERE id=?",(sid,)).fetchone())
    if own: conn.commit(); conn.close()
    return result, True


def verify_provider_payment(checkout_id, payment, conn=None):
    own=conn is None; conn=conn or get_db_connection(); ensure_flow_schema(conn)
    checkout=conn.execute("SELECT * FROM checkout_attempts WHERE id=?",(checkout_id,)).fetchone()
    if not checkout:
        if own: conn.close()
        raise FlowError("Checkout not found","CHECKOUT_NOT_FOUND",404)
    snap=conn.execute("SELECT * FROM execution_snapshots WHERE id=?",(checkout["active_snapshot_id"],)).fetchone()
    buyer=conn.execute("SELECT stripe_customer_id FROM users WHERE id=?",(snap["buyer_id"],)).fetchone()
    expected_customer=buyer["stripe_customer_id"] if buyer and "stripe_customer_id" in buyer.keys() else None
    if own: conn.close()
    pdata = payment.to_dict() if hasattr(payment,"to_dict") else dict(payment)
    metadata = pdata.get("metadata") or {}
    expected = {"id":checkout["provider_payment_id"],"amount":snap["buyer_total_cents"],"currency":snap["currency"],
                "buyer":str(snap["buyer_id"]),"digest":snap["snapshot_hash"]}
    actual = {"id":pdata.get("id"),"amount":pdata.get("amount"),"currency":pdata.get("currency"),
              "buyer":str(metadata.get("buyer_id","")),"digest":metadata.get("snapshot_hash")}
    if expected != actual:
        raise FlowError("Payment does not match its immutable checkout snapshot","PAYMENT_BINDING_MISMATCH",409)
    if expected_customer and pdata.get("customer") != expected_customer:
        raise FlowError("Payment customer does not match the checkout buyer","PAYMENT_CUSTOMER_MISMATCH",409)
    return dict(checkout), dict(snap), pdata


def record_ach_processing(checkout_id, payment, conn=None):
    """Project an ACH sale while funds clear, without creating revenue/payables.

    The held inventory remains unavailable and the seller can see that it sold,
    but no execution, ledger journal, payable, or shipment authorization exists
    until Stripe reports the same bound PaymentIntent as succeeded.
    """
    checkout, snap, pdata = verify_provider_payment(checkout_id, payment, conn=conn)
    if snap["payment_rail"] != "us_bank_account" or pdata.get("status") != "processing":
        raise FlowError("Payment is not a processing ACH payment", "ACH_NOT_PROCESSING", 409)
    own = conn is None
    conn = conn or get_db_connection()
    ensure_flow_schema(conn)
    if database_module.IS_POSTGRES:
        conn.execute("SELECT id FROM checkout_attempts WHERE id=? FOR UPDATE", (checkout_id,)).fetchone()
    existing_execution = conn.execute(
        "SELECT id FROM executions WHERE checkout_id=?", (checkout_id,)
    ).fetchone()
    if existing_execution:
        if own:
            conn.close()
        return {"execution_id": existing_execution["id"]}, False
    existing_order = conn.execute(
        "SELECT id FROM orders WHERE stripe_payment_intent_id=?", (pdata["id"],)
    ).fetchone()
    now = _now()
    if existing_order:
        order_id = existing_order["id"]
    else:
        shipping = json.loads(snap["shipping_json"])
        cur = conn.execute("""INSERT INTO orders
          (buyer_id,total_price,buyer_card_fee,tax_amount,tax_rate,shipping_address,recipient_first_name,
           recipient_last_name,stripe_payment_intent_id,payment_method_type,requires_payment_clearance,
           payment_status,status,payout_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (snap["buyer_id"], snap["buyer_total_cents"] / 100,
           snap["card_surcharge_cents"] / 100, snap["tax_cents"] / 100, 0,
           shipping.get("shipping_address", ""), shipping.get("recipient_first", ""),
           shipping.get("recipient_last", ""), pdata["id"], "us_bank_account", 1,
           "processing", "sold_pending_ach", "not_ready_for_payout"))
        order_id = cur.lastrowid
        if not order_id:
            order_id = conn.execute(
                "SELECT id FROM orders WHERE stripe_payment_intent_id=?", (pdata["id"],)
            ).fetchone()["id"]
        lines = conn.execute(
            "SELECT * FROM snapshot_lines WHERE snapshot_id=? ORDER BY id", (snap["id"],)
        ).fetchall()
        for line in lines:
            conn.execute("""INSERT INTO order_items
              (order_id,listing_id,quantity,price_each,price_at_purchase,seller_price_each,
               third_party_grading_requested,grading_fee_charged,grading_status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
              (order_id, line["listing_id"], line["quantity"], line["buyer_unit_cents"] / 100,
               line["buyer_unit_cents"] / 100, line["seller_unit_cents"] / 100,
               0, 0, "not_requested"))
    conn.execute(
        "UPDATE checkout_attempts SET state='PAYMENT_PROCESSING',updated_at=? WHERE id=?",
        (now, checkout_id),
    )
    _audit(conn, "checkout", checkout_id, "ACH_PROCESSING", "provider", None,
           after={"legacy_order_id": order_id, "payment": pdata["id"]})
    if own:
        conn.commit()
        conn.close()
    return {"legacy_order_id": order_id, "payment_state": "PROCESSING"}, True


def finalize_payment(checkout_id, payment, actor_type="provider", conn=None):
    checkout,snap,pdata=verify_provider_payment(checkout_id,payment,conn=conn)
    status=pdata.get("status"); rail=snap["payment_rail"]
    if status != "succeeded":
        raise FlowError("Payment is not successful","PAYMENT_NOT_SUCCESSFUL",202 if status=="processing" else 402)
    if rail == "us_bank_account" and pdata.get("latest_charge") is None:
        # Success may create the payable, but shipment remains blocked until explicit approval.
        pass
    own=conn is None; conn=conn or get_db_connection(); ensure_flow_schema(conn)
    if database_module.IS_POSTGRES:
        conn.execute("SELECT id FROM checkout_attempts WHERE id=? FOR UPDATE",(checkout_id,)).fetchone()
    existing=conn.execute("SELECT * FROM executions WHERE checkout_id=?",(checkout_id,)).fetchone()
    if existing:
        if own: conn.close()
        return dict(existing), False
    now=_now(); op=conn.execute("SELECT * FROM financial_operations WHERE aggregate_id=? AND operation_type='PAYMENT'",
                               (checkout_id,)).fetchone()
    if not op: raise FlowError("Payment operation missing","PAYMENT_OPERATION_MISSING",500)
    lines=conn.execute("SELECT * FROM snapshot_lines WHERE snapshot_id=? ORDER BY id",(snap["id"],)).fetchall()
    shipping=json.loads(snap["shipping_json"]); execution_id=_id("exe")
    # Promote the ACH processing projection when present; otherwise create the
    # legacy projection in this same transaction.
    pending_order=conn.execute("SELECT id FROM orders WHERE stripe_payment_intent_id=?",(pdata["id"],)).fetchone()
    if pending_order:
        order_id=pending_order["id"]
        conn.execute("""UPDATE orders SET paid_at=?,payment_status='paid',status='paid',
          requires_payment_clearance=?,payout_status='not_ready_for_payout' WHERE id=?""",
          (now,0,order_id))
    else:
        cur=conn.execute("""INSERT INTO orders
          (buyer_id,total_price,buyer_card_fee,tax_amount,tax_rate,shipping_address,recipient_first_name,
           recipient_last_name,stripe_payment_intent_id,paid_at,payment_method_type,requires_payment_clearance,
           payment_status,status,payout_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (snap["buyer_id"],snap["buyer_total_cents"]/100,snap["card_surcharge_cents"]/100,snap["tax_cents"]/100,0,
           shipping.get("shipping_address",""),shipping.get("recipient_first",""),shipping.get("recipient_last",""),
           pdata["id"],now,rail,0,"paid","paid","not_ready_for_payout"))
        order_id=cur.lastrowid
    conn.execute("""INSERT INTO executions
      (id,checkout_id,snapshot_id,payment_operation_id,provider_payment_id,buyer_id,legacy_order_id,state,
       payment_state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
      (execution_id,checkout_id,snap["id"],op["id"],pdata["id"],snap["buyer_id"],order_id,"FUNDED","APPROVED",now,now))
    for line in lines:
        if not pending_order:
            conn.execute("""INSERT INTO order_items
              (order_id,listing_id,quantity,price_each,price_at_purchase,seller_price_each,
               third_party_grading_requested,grading_fee_charged,grading_status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
              (order_id,line["listing_id"],line["quantity"],line["buyer_unit_cents"]/100,
               line["buyer_unit_cents"]/100,line["seller_unit_cents"]/100,0,0,"not_requested"))
        fill_id=_id("fill")
        conn.execute("""INSERT INTO seller_fills
          (id,execution_id,snapshot_line_id,seller_id,quantity,state,seller_gross_cents,seller_fee_cents,
           seller_net_cents,spread_cents,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
          (fill_id,execution_id,line["id"],line["seller_id"],line["quantity"],"FUNDED",line["seller_gross_cents"],
           line["seller_fee_cents"],line["seller_net_cents"],line["spread_cents"],now,now))
        payable_id=_id("payable")
        block="FULFILLMENT_PENDING"
        conn.execute("INSERT INTO seller_payables VALUES (?,?,?,?,?,?,?,?,?,?,?)",
          (payable_id,fill_id,line["seller_id"],line["seller_net_cents"],0,0,"HELD",block,None,now,now))
        destination="GRADER" if line["grading_requested"] else "BUYER"
        conn.execute("""INSERT INTO shipments
          (id,seller_fill_id,leg_type,state,destination_type,created_at,updated_at)
          VALUES (?,?,?,?,?,?,?)""",(_id("ship"),fill_id,"SELLER_TO_GRADER" if line["grading_requested"] else "SELLER_TO_BUYER",
          "NOT_AUTHORIZED",destination,now,now))
        if line["grading_requested"]:
            conn.execute("INSERT INTO grading_legs (id,seller_fill_id,state,created_at,updated_at) VALUES (?,?,?,?,?)",
                         (_id("grade"),fill_id,"AWAITING_SHIP_AUTHORIZATION",now,now))
        _journal(conn,"seller_fill",fill_id,"PAYMENT_CAPTURED",f"payment:{pdata['id']}:{fill_id}",[
          {"account":"PROCESSOR_CASH","debit":line["buyer_gross_cents"]+line["tax_cents"]+line["grading_cents"]+line["card_surcharge_cents"],"component":"buyer_charge","fill_id":fill_id},
          {"account":"SELLER_PAYABLE","credit":line["seller_net_cents"],"component":"seller_net","fill_id":fill_id,"owner_type":"seller","owner_id":line["seller_id"]},
          {"account":"MARKETPLACE_FEE_REVENUE","credit":line["seller_fee_cents"],"component":"seller_fee","fill_id":fill_id},
          {"account":"SPREAD_REVENUE","credit":line["spread_cents"],"component":"spread","fill_id":fill_id},
          {"account":"TAX_PAYABLE","credit":line["tax_cents"],"component":"tax","fill_id":fill_id},
          {"account":"GRADING_PAYABLE","credit":line["grading_cents"],"component":"grading","fill_id":fill_id},
          {"account":"CARD_SURCHARGE","credit":line["card_surcharge_cents"],"component":"card_surcharge","fill_id":fill_id},
        ])
    # Each partial fill is its own execution/payment. Update the parent bid in
    # this transaction, after all independent fills and journals exist.
    bid_quantities={}
    for line in lines:
        if line["source_bid_id"] is not None:
            bid_quantities[line["source_bid_id"]]=bid_quantities.get(line["source_bid_id"],0)+line["quantity"]
    for bid_id,quantity in bid_quantities.items():
        reservation=conn.execute("SELECT id FROM bid_quantity_reservations WHERE checkout_id=? AND bid_id=? AND state='HELD'",
                                 (checkout_id,bid_id)).fetchone()
        if not reservation:
            raise FlowError("Bid quantity reservation is missing","BID_RESERVATION_MISSING",409)
        conn.execute("""UPDATE bids SET active=CASE WHEN remaining_quantity<=0 THEN 0 ELSE active END,
          status=CASE WHEN remaining_quantity<=0 THEN 'Filled' ELSE 'Partially Filled' END,
          bid_payment_status=CASE WHEN remaining_quantity<=0 THEN 'charged' ELSE 'pending' END,
          bid_payment_intent_id=CASE WHEN remaining_quantity<=0 THEN ? ELSE NULL END WHERE id=?""",
          (pdata["id"],bid_id))
        conn.execute("UPDATE bid_quantity_reservations SET state='COMMITTED',updated_at=? WHERE id=?",(now,reservation["id"]))
    conn.execute("UPDATE inventory_reservations SET state='COMMITTED',updated_at=? WHERE checkout_id=? AND state='HELD'",(now,checkout_id))
    conn.execute("UPDATE checkout_attempts SET state='FINALIZED',updated_at=? WHERE id=?",(now,checkout_id))
    conn.execute("UPDATE financial_operations SET state='SUCCEEDED',updated_at=? WHERE id=?",(now,op["id"]))
    conn.execute("DELETE FROM cart WHERE user_id=?",(snap["buyer_id"],))
    conn.execute("INSERT INTO outbox_events VALUES (?,?,?,?,?,?,?,?,?)",
      (_id("evt"),"EXECUTION_FUNDED","execution",execution_id,_canonical({"order_id":order_id}),"PENDING",0,now,None))
    _audit(conn,"execution",execution_id,"PAYMENT_FINALIZED",actor_type,None,after={"order_id":order_id,"payment":pdata["id"]})
    if own: conn.commit(); conn.close()
    return {"id":execution_id,"legacy_order_id":order_id,"payment_state":"APPROVED"}, True


def release_reservation(checkout_id, reason, conn=None):
    own=conn is None; conn=conn or get_db_connection(); ensure_flow_schema(conn); now=_now()
    rows=conn.execute("SELECT * FROM inventory_reservations WHERE checkout_id=? AND state='HELD'",(checkout_id,)).fetchall()
    for row in rows:
        conn.execute("UPDATE listings SET quantity=quantity+?,active=1 WHERE id=?",(row["quantity"],row["listing_id"]))
        conn.execute("UPDATE inventory_reservations SET state='RELEASED',updated_at=? WHERE id=?",(now,row["id"]))
    bids=conn.execute("SELECT * FROM bid_quantity_reservations WHERE checkout_id=? AND state='HELD'",(checkout_id,)).fetchall()
    for bid in bids:
        conn.execute("UPDATE bids SET remaining_quantity=remaining_quantity+?,active=1,status='Open',bid_payment_status='pending' WHERE id=?",
                     (bid["quantity"],bid["bid_id"]))
        conn.execute("UPDATE bid_quantity_reservations SET state='RELEASED',updated_at=? WHERE id=?",(now,bid["id"]))
    conn.execute("UPDATE checkout_attempts SET state='FAILED',updated_at=? WHERE id=? AND state<>'FINALIZED'",(now,checkout_id))
    _audit(conn,"checkout",checkout_id,"RESERVATION_RELEASED","system",metadata={"reason":reason})
    if own: conn.commit(); conn.close()
    return len(rows)


def record_webhook(event):
    data=event.to_dict() if hasattr(event,"to_dict") else dict(event); conn=get_db_connection(); ensure_flow_schema(conn)
    existing=conn.execute("SELECT state FROM webhook_inbox WHERE provider='stripe' AND event_id=?",(data["id"],)).fetchone()
    if not existing:
        conn.execute("INSERT INTO webhook_inbox VALUES (?,?,?,?,?,?,?,?,?)",
          ("stripe",data["id"],data["type"],_canonical(data),"RECEIVED",0,None,_now(),None)); conn.commit()
    conn.close(); return existing is None


def process_webhook(event):
    data=event.to_dict() if hasattr(event,"to_dict") else dict(event); event_id=data["id"]
    conn=get_db_connection(); ensure_flow_schema(conn)
    inbox=conn.execute("SELECT * FROM webhook_inbox WHERE provider='stripe' AND event_id=?",(event_id,)).fetchone()
    if inbox and inbox["state"]=="PROCESSED": conn.close(); return "duplicate"
    try:
        obj=data["data"]["object"]; typ=data["type"]
        if typ.startswith("payment_intent."):
            metadata=obj.get("metadata") or {}; checkout_id=metadata.get("checkout_id")
            if checkout_id:
                if typ=="payment_intent.succeeded": finalize_payment(checkout_id,obj,conn=conn)
                elif typ in ("payment_intent.payment_failed","payment_intent.canceled"):
                    exe=conn.execute("SELECT * FROM executions WHERE checkout_id=?",(checkout_id,)).fetchone()
                    if exe:
                        conn.execute("UPDATE executions SET payment_state='RETURNED',state='PAYMENT_RISK',updated_at=? WHERE id=?",(_now(),exe["id"]))
                        for fill in conn.execute("SELECT id FROM seller_fills WHERE execution_id=?",(exe["id"],)).fetchall():
                            conn.execute("INSERT INTO holds VALUES (?,?,?,?,?,?,?,?)",(_id("hold"),fill["id"],"ACH_RETURN",typ,"ACTIVE",event_id,_now(),None))
                            conn.execute("UPDATE seller_payables SET state='HELD',block_reason='ACH_RETURN',updated_at=? WHERE seller_fill_id=?",(_now(),fill["id"]))
                    else:
                        conn.execute("""UPDATE orders SET payment_status='failed',
                          status='payment_failed',payout_status='not_ready_for_payout'
                          WHERE stripe_payment_intent_id=?""",(obj.get("id"),))
                        bid_line=conn.execute("""SELECT l.id FROM snapshot_lines l JOIN checkout_attempts c ON c.active_snapshot_id=l.snapshot_id
                          WHERE c.id=? AND l.source_bid_id IS NOT NULL LIMIT 1""",(checkout_id,)).fetchone()
                        if bid_line:
                            expiry=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
                            conn.execute("UPDATE checkout_attempts SET state='PAYMENT_CORRECTION',expires_at=?,updated_at=? WHERE id=?",(expiry,_now(),checkout_id))
                            conn.execute("UPDATE inventory_reservations SET expires_at=?,updated_at=? WHERE checkout_id=? AND state='HELD'",(expiry,_now(),checkout_id))
                        else:
                            release_reservation(checkout_id,typ,conn=conn)
                elif typ=="payment_intent.processing":
                    record_ach_processing(checkout_id,obj,conn=conn)
        elif typ.startswith("charge.dispute."):
            charge=obj; pi=charge.get("payment_intent")
            exe=conn.execute("SELECT * FROM executions WHERE provider_payment_id=?",(pi,)).fetchone()
            if exe:
                did=charge["id"]; state="OPEN" if typ!="charge.dispute.closed" else ("WON" if charge.get("status")=="won" else "LOST")
                found=conn.execute("SELECT id FROM processor_disputes WHERE provider_dispute_id=?",(did,)).fetchone()
                if found: conn.execute("UPDATE processor_disputes SET state=?,updated_at=? WHERE id=?",(state,_now(),found["id"]))
                else: conn.execute("INSERT INTO processor_disputes VALUES (?,?,?,?,?,?,?,?)",(_id("disp"),exe["id"],did,state,charge.get("amount",0),charge.get("reason"),_now(),_now()))
                if state=="OPEN":
                    for fill in conn.execute("SELECT id FROM seller_fills WHERE execution_id=?",(exe["id"],)).fetchall():
                        conn.execute("INSERT INTO holds VALUES (?,?,?,?,?,?,?,?)",(_id("hold"),fill["id"],"CHARGEBACK",did,"ACTIVE",did,_now(),None))
                        conn.execute("UPDATE seller_payables SET state='HELD',block_reason='CHARGEBACK',updated_at=? WHERE seller_fill_id=?",(_now(),fill["id"]))
        elif typ in ("refund.created","refund.updated","refund.failed"):
            refund_id=(obj.get("metadata") or {}).get("flow_refund_id")
            if not refund_id:
                row=conn.execute("SELECT id FROM flow_refunds WHERE provider_refund_id=?",(obj.get("id"),)).fetchone()
                refund_id=row["id"] if row else None
            if refund_id:
                status=obj.get("status")
                if status=="succeeded":
                    complete_refund(refund_id,obj["id"],conn=conn)
                else:
                    state="FAILED" if status in ("failed","canceled") or typ=="refund.failed" else "PROCESSING"
                    conn.execute("UPDATE flow_refunds SET state=?,provider_refund_id=?,updated_at=? WHERE id=?",
                                 (state,obj.get("id"),_now(),refund_id))
                    conn.execute("""UPDATE financial_operations SET state=?,provider_object_id=?,last_error=?,updated_at=?
                      WHERE id=(SELECT financial_operation_id FROM flow_refunds WHERE id=?)""",
                      (state,obj.get("id"),obj.get("failure_reason"),_now(),refund_id))
        elif typ in ("payout.created","payout.updated","payout.paid","payout.failed"):
            state={"payout.created":"BANK_PAYOUT_PENDING","payout.updated":"BANK_PAYOUT_PENDING",
                   "payout.paid":"BANK_PAYOUT_PAID","payout.failed":"BANK_PAYOUT_FAILED"}[typ]
            seller_id=(obj.get("metadata") or {}).get("seller_id")
            if seller_id:
                row=conn.execute("SELECT id FROM bank_payouts WHERE provider_payout_id=?",(obj["id"],)).fetchone()
                if row: conn.execute("UPDATE bank_payouts SET state=?,arrival_at=?,updated_at=? WHERE id=?",(state,obj.get("arrival_date"),_now(),row["id"]))
                else: conn.execute("INSERT INTO bank_payouts VALUES (?,?,?,?,?,?,?,?)",(_id("bp"),seller_id,obj["id"],state,obj.get("amount",0),obj.get("arrival_date"),_now(),_now()))
        conn.execute("UPDATE webhook_inbox SET state='PROCESSED',attempts=attempts+1,processed_at=?,last_error=NULL WHERE provider='stripe' AND event_id=?",(_now(),event_id))
        conn.commit(); return "processed"
    except Exception as exc:
        conn.rollback()
        conn.execute("UPDATE webhook_inbox SET state='RETRY',attempts=attempts+1,last_error=? WHERE provider='stripe' AND event_id=?",(str(exc)[:1000],event_id)); conn.commit()
        raise
    finally: conn.close()


def replay_retry_webhooks(limit=100):
    """Replay durable webhook failures without accepting a second financial event."""
    conn=get_db_connection(); ensure_flow_schema(conn)
    rows=conn.execute("""SELECT payload_json FROM webhook_inbox
      WHERE provider='stripe' AND state='RETRY' ORDER BY received_at LIMIT ?""",(limit,)).fetchall()
    conn.close(); processed=0
    for row in rows:
        try:
            process_webhook(json.loads(row["payload_json"])); processed+=1
        except Exception:
            # The row remains RETRY with an incremented attempt count and error.
            continue
    return processed


def evaluate_payout(payable_id, now=None):
    conn=get_db_connection(); ensure_flow_schema(conn); now=now or datetime.now(timezone.utc)
    row=conn.execute("""SELECT p.*,f.execution_id,e.payment_state,l.grading_requested
      FROM seller_payables p JOIN seller_fills f ON f.id=p.seller_fill_id
      JOIN executions e ON e.id=f.execution_id JOIN snapshot_lines l ON l.id=f.snapshot_line_id WHERE p.id=?""",(payable_id,)).fetchone()
    if not row: conn.close(); return False,"PAYABLE_NOT_FOUND"
    if row["payment_state"]!="APPROVED": conn.close(); return False,"PAYMENT_NOT_APPROVED"
    if conn.execute("SELECT id FROM holds WHERE seller_fill_id=? AND state='ACTIVE'",(row["seller_fill_id"],)).fetchone(): conn.close(); return False,"ACTIVE_HOLD"
    shipment=conn.execute("SELECT * FROM shipments WHERE seller_fill_id=? ORDER BY leg_type DESC LIMIT 1",(row["seller_fill_id"],)).fetchone()
    if row["grading_requested"]:
        grade=conn.execute("SELECT * FROM grading_legs WHERE seller_fill_id=?",(row["seller_fill_id"],)).fetchone()
        ok=bool(grade and grade["state"]=="AUTHENTICATED")
        conn.close(); return ok,"" if ok else "GRADING_NOT_AUTHENTICATED"
    if not shipment or not shipment["delivered_at"]: conn.close(); return False,"DELIVERY_NOT_CONFIRMED"
    delivered=datetime.fromisoformat(str(shipment["delivered_at"]).replace("Z","+00:00"))
    ok=now>=delivered+timedelta(days=1); conn.close(); return ok,"" if ok else "DELIVERY_HOLD_24H"


def approve_ach_payment(execution_id, admin_id, evidence):
    """Approve ACH shipment eligibility only after configured evidence review."""
    conn=get_db_connection(); ensure_flow_schema(conn); require_approved_policy(conn,"ach_approval_policy")
    if not evidence:
        conn.close(); raise FlowError("ACH approval evidence is required","ACH_EVIDENCE_REQUIRED")
    exe=conn.execute("SELECT * FROM executions WHERE id=?",(execution_id,)).fetchone()
    if not exe: conn.close(); raise FlowError("Execution not found","EXECUTION_NOT_FOUND",404)
    before=dict(exe); now=_now()
    conn.execute("UPDATE executions SET payment_state='APPROVED',payment_approved_at=?,updated_at=? WHERE id=?",
                 (now,now,execution_id))
    conn.execute("UPDATE orders SET requires_payment_clearance=0,payment_cleared_at=?,payment_cleared_by_admin_id=? WHERE id=?",
                 (now,admin_id,exe["legacy_order_id"]))
    _audit(conn,"execution",execution_id,"ACH_APPROVED","admin",admin_id,before=before,
           after={"payment_state":"APPROVED"},metadata={"evidence":evidence})
    conn.commit(); conn.close(); return True


def record_insurance(shipment_id, admin_id, policy_number, insured_value_cents,
                     premium_cents, evidence):
    conn=get_db_connection(); ensure_flow_schema(conn); require_approved_policy(conn,"ups_coverage_and_claim_policy")
    ship=conn.execute("SELECT * FROM shipments WHERE id=?",(shipment_id,)).fetchone()
    if not ship: conn.close(); raise FlowError("Shipment not found","SHIPMENT_NOT_FOUND",404)
    if not policy_number or not evidence:
        conn.close(); raise FlowError("Qualifying insurance evidence is required","INSURANCE_EVIDENCE_REQUIRED")
    now=_now(); existing=conn.execute("SELECT id FROM insurance_policies WHERE shipment_id=?",(shipment_id,)).fetchone()
    if existing:
        conn.execute("""UPDATE insurance_policies SET policy_number=?,insured_value_cents=?,premium_cents=?,
          state='ACTIVE',evidence_json=?,updated_at=? WHERE id=?""",
          (policy_number,insured_value_cents,premium_cents,_canonical(evidence),now,existing["id"]))
    else:
        conn.execute("INSERT INTO insurance_policies VALUES (?,?,?,?,?,?,?,?,?,?)",
          (_id("ins"),shipment_id,"UPS",policy_number,insured_value_cents,premium_cents,"ACTIVE",_canonical(evidence),now,now))
    _journal(conn,"shipment",shipment_id,"INSURANCE_PURCHASED",f"insurance:{shipment_id}",[
      {"account":"SHIPPING_INSURANCE_EXPENSE","debit":premium_cents,"component":"ups_insurance"},
      {"account":"PROCESSOR_CASH","credit":premium_cents,"component":"ups_insurance"}])
    _audit(conn,"shipment",shipment_id,"INSURANCE_ACTIVATED","admin",admin_id,after={"policy_number":policy_number})
    conn.commit(); conn.close()


def authorize_shipment(shipment_id, admin_id):
    """Start the seller's X-day tracking clock after every funding/coverage gate."""
    conn=get_db_connection(); ensure_flow_schema(conn)
    require_approved_policy(conn,"tracking_upload_deadline_days","ups_coverage_and_claim_policy")
    row=conn.execute("""SELECT s.*,f.execution_id,e.payment_state FROM shipments s
      JOIN seller_fills f ON f.id=s.seller_fill_id JOIN executions e ON e.id=f.execution_id WHERE s.id=?""",(shipment_id,)).fetchone()
    if not row: conn.close(); raise FlowError("Shipment not found","SHIPMENT_NOT_FOUND",404)
    if row["payment_state"]!="APPROVED": conn.close(); raise FlowError("Payment is not approved","PAYMENT_NOT_APPROVED",409)
    ins=conn.execute("SELECT state FROM insurance_policies WHERE shipment_id=?",(shipment_id,)).fetchone()
    if not ins or ins["state"]!="ACTIVE": conn.close(); raise FlowError("UPS insurance is not active","INSURANCE_REQUIRED",409)
    cfg=conn.execute("SELECT value_json FROM flow_policy_config WHERE key='tracking_upload_deadline_days'").fetchone()
    days=int(json.loads(cfg["value_json"])); nowdt=datetime.now(timezone.utc); due=(nowdt+timedelta(days=days)).isoformat()
    conn.execute("UPDATE shipments SET state='AWAITING_TRACKING',ship_authorized_at=?,tracking_due_at=?,updated_at=? WHERE id=?",
                 (nowdt.isoformat(),due,nowdt.isoformat(),shipment_id))
    conn.execute("UPDATE seller_payables SET block_reason='FULFILLMENT_PENDING',updated_at=? WHERE seller_fill_id=?",
                 (nowdt.isoformat(),row["seller_fill_id"]))
    _audit(conn,"shipment",shipment_id,"SHIPMENT_AUTHORIZED","admin",admin_id,after={"tracking_due_at":due})
    conn.commit(); conn.close(); return due


def record_tracking(shipment_id, seller_id, carrier, tracking_number, carrier_evidence):
    conn=get_db_connection(); ensure_flow_schema(conn); require_approved_policy(conn,"tracking_upload_deadline_days")
    row=conn.execute("""SELECT s.*,f.seller_id FROM shipments s JOIN seller_fills f ON f.id=s.seller_fill_id
      WHERE s.id=?""",(shipment_id,)).fetchone()
    if not row or int(row["seller_id"])!=int(seller_id): conn.close(); raise FlowError("Shipment not found or access denied","TRACKING_FORBIDDEN",403)
    if row["state"]!="AWAITING_TRACKING": conn.close(); raise FlowError("Shipment is not authorized","SHIPMENT_NOT_AUTHORIZED",409)
    evidence=carrier_evidence or {}; normalized="".join(str(tracking_number).split()).upper()
    valid=carrier.upper()=="UPS" and normalized.startswith("1Z") and len(normalized)==18 and evidence.get("carrier_confirmed") is True
    reused=conn.execute("SELECT id FROM shipments WHERE carrier=? AND tracking_number=? AND id<>?",(carrier,normalized,shipment_id)).fetchone()
    if not valid or reused: conn.close(); raise FlowError("Tracking did not pass carrier qualification","TRACKING_NOT_QUALIFIED",409)
    now=_now(); conn.execute("UPDATE shipments SET carrier=?,tracking_number=?,tracking_validated=1,state='IN_TRANSIT',updated_at=? WHERE id=?",
                             (carrier,normalized,now,shipment_id))
    _audit(conn,"shipment",shipment_id,"TRACKING_ACCEPTED","seller",seller_id,after={"carrier":carrier,"tracking":normalized},metadata=evidence)
    conn.commit(); conn.close()


def submit_tracking_for_verification(shipment_id, seller_id, carrier, tracking_number):
    """Accept seller input as pending evidence; arbitrary text never satisfies tracking."""
    conn=get_db_connection(); ensure_flow_schema(conn)
    row=conn.execute("""SELECT s.*,f.seller_id FROM shipments s JOIN seller_fills f ON f.id=s.seller_fill_id
      WHERE s.id=?""",(shipment_id,)).fetchone()
    if not row or int(row["seller_id"])!=int(seller_id): conn.close(); raise FlowError("Shipment not found or access denied","TRACKING_FORBIDDEN",403)
    if row["state"]!="AWAITING_TRACKING": conn.close(); raise FlowError("Shipment is not authorized","SHIPMENT_NOT_AUTHORIZED",409)
    normalized="".join(str(tracking_number).split()).upper()
    if carrier.upper()!="UPS" or not normalized.startswith("1Z") or len(normalized)!=18:
        conn.close(); raise FlowError("Enter a valid UPS tracking format","TRACKING_FORMAT_INVALID",400)
    now=_now(); conn.execute("UPDATE shipments SET carrier=?,tracking_number=?,tracking_validated=0,state='TRACKING_VERIFICATION_PENDING',updated_at=? WHERE id=?",
                             (carrier,normalized,now,shipment_id))
    _audit(conn,"shipment",shipment_id,"TRACKING_SUBMITTED","seller",seller_id,after={"carrier":carrier,"tracking":normalized})
    conn.commit(); conn.close(); return True


def mark_tracking_forfeitures(now=None):
    now=(now or datetime.now(timezone.utc)).isoformat(); conn=get_db_connection(); ensure_flow_schema(conn)
    due=conn.execute("SELECT * FROM shipments WHERE state='AWAITING_TRACKING' AND tracking_due_at<?",(now,)).fetchall(); ids=[]
    for ship in due:
        conn.execute("UPDATE shipments SET state='FORFEITED',updated_at=? WHERE id=?",(now,ship["id"]))
        conn.execute("UPDATE seller_fills SET state='FORFEITED',updated_at=? WHERE id=?",(now,ship["seller_fill_id"]))
        conn.execute("UPDATE seller_payables SET state='CANCELLED',block_reason='TRACKING_FORFEITURE',updated_at=? WHERE seller_fill_id=?",(now,ship["seller_fill_id"]))
        conn.execute("INSERT INTO holds VALUES (?,?,?,?,?,?,?,?)",(_id("hold"),ship["seller_fill_id"],"REFUND","TRACKING_FORFEITURE","ACTIVE",ship["id"],now,None)); ids.append(ship["seller_fill_id"])
    conn.commit(); conn.close(); return ids


def process_tracking_forfeiture_refunds():
    """Refund forfeited fills once the configured component policy permits it."""
    import stripe
    conn=get_db_connection(); ensure_flow_schema(conn)
    rows=conn.execute("""SELECT f.id fill_id,f.quantity,f.refunded_quantity,f.snapshot_line_id,
      f.execution_id,e.provider_payment_id,l.listing_id
      FROM seller_fills f JOIN executions e ON e.id=f.execution_id
      JOIN snapshot_lines l ON l.id=f.snapshot_line_id
      WHERE f.state='FORFEITED' AND f.refunded_quantity<f.quantity""").fetchall()
    conn.close(); completed=[]
    for row in rows:
        key=f"tracking-forfeiture-refund:{row['fill_id']}"
        try:
            refund,_=create_refund(row["execution_id"],
              {row["fill_id"]:row["quantity"]-row["refunded_quantity"]},
              "TRACKING_FORFEITURE",key)
            provider=stripe.Refund.create(payment_intent=row["provider_payment_id"],
              amount=refund["total_cents"],metadata={"flow_refund_id":refund["id"],
              "seller_fill_id":row["fill_id"],"reason":"tracking_forfeiture"},
              idempotency_key=key)
            if record_refund_provider_result(refund["id"],provider):
                restore=get_db_connection()
                restore.execute("UPDATE listings SET quantity=quantity+?,active=1 WHERE id=?",
                                (row["quantity"]-row["refunded_quantity"],row["listing_id"]))
                restore.commit(); restore.close()
            completed.append(row["fill_id"])
        except FlowError:
            # An unresolved refund-component policy intentionally leaves the
            # affected payable held for an administrator instead of guessing.
            continue
        except Exception:
            # The claimed financial operation remains retryable with the same key.
            continue
    return completed


def record_shipment_event(shipment_id, state, evidence):
    if state not in ("IN_TRANSIT","DELIVERED","LOST","DAMAGED","RETURNED"):
        raise FlowError("Invalid shipment state","INVALID_SHIPMENT_STATE")
    conn=get_db_connection(); ensure_flow_schema(conn)
    ship=conn.execute("SELECT * FROM shipments WHERE id=?",(shipment_id,)).fetchone()
    if not ship: conn.close(); raise FlowError("Shipment not found","SHIPMENT_NOT_FOUND",404)
    if not evidence: conn.close(); raise FlowError("Carrier evidence is required","SHIPMENT_EVIDENCE_REQUIRED")
    now=_now(); delivered=now if state=="DELIVERED" else ship["delivered_at"]
    conn.execute("UPDATE shipments SET state=?,delivered_at=?,updated_at=? WHERE id=?",(state,delivered,now,shipment_id))
    if state in ("LOST","DAMAGED","RETURNED"):
        if not conn.execute("SELECT id FROM holds WHERE seller_fill_id=? AND hold_type='SHIPPING_FAILURE' AND source_id=?",(ship["seller_fill_id"],shipment_id)).fetchone():
            conn.execute("INSERT INTO holds VALUES (?,?,?,?,?,?,?,?)",(_id("hold"),ship["seller_fill_id"],"SHIPPING_FAILURE",state,"ACTIVE",shipment_id,now,None))
        conn.execute("UPDATE seller_payables SET state='HELD',block_reason='SHIPPING_FAILURE',updated_at=? WHERE seller_fill_id=?",(now,ship["seller_fill_id"]))
    _audit(conn,"shipment",shipment_id,"SHIPMENT_"+state,"carrier",metadata=evidence)
    conn.commit(); conn.close()


def record_insurance_claim(shipment_id, provider_claim_id, state, claimed_cents,
                           received_cents, evidence):
    conn=get_db_connection(); ensure_flow_schema(conn)
    policy=conn.execute("SELECT id FROM insurance_policies WHERE shipment_id=?",(shipment_id,)).fetchone()
    if not policy: conn.close(); raise FlowError("Shipment has no insurance policy","INSURANCE_POLICY_MISSING",409)
    row=conn.execute("SELECT id,received_cents FROM insurance_claims WHERE provider_claim_id=?",(provider_claim_id,)).fetchone(); now=_now()
    if row:
        delta=max(0,int(received_cents)-row["received_cents"])
        conn.execute("UPDATE insurance_claims SET state=?,claimed_cents=?,received_cents=?,evidence_json=?,updated_at=? WHERE id=?",
                     (state,claimed_cents,received_cents,_canonical(evidence or {}),now,row["id"]))
    else:
        delta=int(received_cents); conn.execute("INSERT INTO insurance_claims VALUES (?,?,?,?,?,?,?,?,?)",
          (_id("claim"),policy["id"],provider_claim_id,state,claimed_cents,received_cents,_canonical(evidence or {}),now,now))
    if delta:
        _journal(conn,"shipment",shipment_id,"INSURANCE_CASH_RECEIVED",f"insurance-claim:{provider_claim_id}:{received_cents}",[
          {"account":"PROCESSOR_CASH","debit":delta,"component":"insurance_recovery"},
          {"account":"INSURANCE_RECOVERY","credit":delta,"component":"insurance_recovery"}])
    conn.commit(); conn.close(); return delta


def record_grading_result(seller_fill_id, actor_id, result, evidence, cost_incurred=False):
    if result not in ("AUTHENTICATED","FAILED"):
        raise FlowError("Invalid grading result","INVALID_GRADING_RESULT")
    conn=get_db_connection(); ensure_flow_schema(conn); require_approved_policy(conn,"grading_vendor_policy")
    row=conn.execute("SELECT * FROM grading_legs WHERE seller_fill_id=?",(seller_fill_id,)).fetchone()
    if not row: conn.close(); raise FlowError("Grading leg not found","GRADING_NOT_FOUND",404)
    now=_now(); conn.execute("""UPDATE grading_legs SET state=?,cost_incurred_at=CASE WHEN ?=1 THEN COALESCE(cost_incurred_at,?) ELSE cost_incurred_at END,
      authenticated_at=CASE WHEN ?='AUTHENTICATED' THEN ? ELSE authenticated_at END,
      failed_at=CASE WHEN ?='FAILED' THEN ? ELSE failed_at END,updated_at=? WHERE id=?""",
      (result,1 if cost_incurred else 0,now,result,now,result,now,now,row["id"]))
    if cost_incurred:
        conn.execute("""UPDATE snapshot_lines SET grading_cost_incurred=1 WHERE id=(
          SELECT snapshot_line_id FROM seller_fills WHERE id=?)""",(seller_fill_id,))
    if result=="FAILED":
        conn.execute("INSERT INTO holds VALUES (?,?,?,?,?,?,?,?)",(_id("hold"),seller_fill_id,"GRADING_FAILURE","Grader rejected seller specifications","ACTIVE",row["id"],now,None))
        conn.execute("UPDATE seller_payables SET state='CANCELLED',block_reason='GRADING_FAILURE',updated_at=? WHERE seller_fill_id=?",(now,seller_fill_id))
    else:
        # The grader-to-buyer custody leg has its own coverage record and cannot
        # inherit the seller-to-grader policy implicitly.
        if not conn.execute("SELECT id FROM shipments WHERE seller_fill_id=? AND leg_type='GRADER_TO_BUYER'",(seller_fill_id,)).fetchone():
            conn.execute("""INSERT INTO shipments
              (id,seller_fill_id,leg_type,state,destination_type,created_at,updated_at)
              VALUES (?,?,?,?,?,?,?)""",(_id("ship"),seller_fill_id,"GRADER_TO_BUYER","NOT_AUTHORIZED","BUYER",now,now))
        conn.execute("UPDATE seller_payables SET state='HELD',block_reason='RELEASE_REVIEW',release_eligible_at=?,updated_at=? WHERE seller_fill_id=?",
                     (now,now,seller_fill_id))
    _audit(conn,"grading",row["id"],"GRADING_"+result,"grader",actor_id,after={"state":result,"cost_incurred":cost_incurred},metadata=evidence)
    conn.commit(); conn.close()


def create_refund(execution_id, quantities_by_fill, reason_code, idempotency_key,
                  refund_card_surcharge=None, conn=None):
    """Create exact component allocations and a claimed provider refund operation."""
    own=conn is None; conn=conn or get_db_connection(); ensure_flow_schema(conn)
    if refund_card_surcharge is None:
        require_approved_policy(conn,"refund_component_policy")
        cfg=conn.execute("SELECT value_json FROM flow_policy_config WHERE key='refund_component_policy'").fetchone()
        refund_card_surcharge=json.loads(cfg["value_json"])=="proportional_original_surcharge"
    request_payload={"quantities":quantities_by_fill,"reason":reason_code,"card":refund_card_surcharge}
    existing=conn.execute("""SELECT r.*,o.request_hash FROM flow_refunds r JOIN financial_operations o ON o.id=r.financial_operation_id
      WHERE o.idempotency_key=?""",(idempotency_key,)).fetchone()
    if existing:
        if existing["request_hash"]!=_digest(request_payload):
            raise FlowError("Refund idempotency key was reused with different inputs","IDEMPOTENCY_CONFLICT",409)
        if own: conn.close()
        return dict(existing),False
    exe=conn.execute("SELECT * FROM executions WHERE id=?",(execution_id,)).fetchone()
    if not exe: raise FlowError("Execution not found","EXECUTION_NOT_FOUND",404)
    allocations=[]; total=0
    for fill_id,qty in sorted(quantities_by_fill.items()):
        fill=conn.execute("""SELECT f.*,l.tax_cents,l.grading_cents,l.card_surcharge_cents,l.grading_cost_incurred
          FROM seller_fills f JOIN snapshot_lines l ON l.id=f.snapshot_line_id WHERE f.id=? AND f.execution_id=?""",(fill_id,execution_id)).fetchone()
        qty=int(qty)
        if not fill or qty<=0 or fill["refunded_quantity"]+qty>fill["quantity"]:
            raise FlowError("Invalid refund quantity","INVALID_REFUND_QUANTITY",409)
        start=fill["refunded_quantity"]
        def sl(component): return sum(allocate_largest_remainder(fill[component],[1]*fill["quantity"])[start:start+qty])
        net,fee,spread,tax=sl("seller_net_cents"),sl("seller_fee_cents"),sl("spread_cents"),sl("tax_cents")
        grading=0 if fill["grading_cost_incurred"] else sl("grading_cents")
        card=sl("card_surcharge_cents") if refund_card_surcharge else 0
        amount=net+fee+spread+tax+grading+card; total+=amount
        allocations.append((fill,qty,net,fee,spread,tax,grading,card,amount))
    op,_=claim_operation(conn,"REFUND",idempotency_key,"execution",execution_id,total,
                         request_payload)
    rid=_id("refund"); now=_now(); conn.execute("INSERT INTO flow_refunds VALUES (?,?,?,?,?,?,?,?,?)",
      (rid,execution_id,op["id"],reason_code,"CLAIMED",total,None,now,now))
    for fill,qty,net,fee,spread,tax,grading,card,amount in allocations:
        conn.execute("INSERT INTO refund_allocations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
          (_id("ra"),rid,fill["id"],qty,net,fee,spread,tax,grading,card,0,amount))
        conn.execute("UPDATE seller_fills SET refunded_quantity=refunded_quantity+?,state='REFUND_PENDING',updated_at=? WHERE id=?",
                     (qty,now,fill["id"]))
        conn.execute("UPDATE seller_payables SET state='HELD',block_reason='REFUND_PENDING',updated_at=? WHERE seller_fill_id=?",(now,fill["id"]))
    _audit(conn,"refund",rid,"REFUND_CLAIMED","system",metadata={"reason":reason_code,"total_cents":total})
    if own: conn.commit(); conn.close()
    return {"id":rid,"operation_id":op["id"],"total_cents":total},True


def complete_refund(refund_id, provider_refund_id, conn=None):
    own=conn is None; conn=conn or get_db_connection(); ensure_flow_schema(conn); refund=conn.execute("SELECT * FROM flow_refunds WHERE id=?",(refund_id,)).fetchone()
    if not refund:
        if own: conn.close()
        raise FlowError("Refund not found","REFUND_NOT_FOUND",404)
    if refund["state"]=="SUCCEEDED":
        if own: conn.close()
        return False
    now=_now(); allocations=conn.execute("SELECT * FROM refund_allocations WHERE refund_id=?",(refund_id,)).fetchall()
    for a in allocations:
        _journal(conn,"refund",refund_id,"REFUND_SUCCEEDED",f"refund:{refund_id}:{a['seller_fill_id']}",[
          {"account":"SELLER_PAYABLE","debit":a["seller_net_cents"],"component":"seller_net","fill_id":a["seller_fill_id"]},
          {"account":"MARKETPLACE_FEE_REVENUE","debit":a["seller_fee_cents"],"component":"seller_fee","fill_id":a["seller_fill_id"]},
          {"account":"SPREAD_REVENUE","debit":a["spread_cents"],"component":"spread","fill_id":a["seller_fill_id"]},
          {"account":"TAX_PAYABLE","debit":a["tax_cents"],"component":"tax","fill_id":a["seller_fill_id"]},
          {"account":"GRADING_PAYABLE","debit":a["grading_cents"],"component":"grading","fill_id":a["seller_fill_id"]},
          {"account":"CARD_SURCHARGE","debit":a["card_surcharge_cents"],"component":"card_surcharge","fill_id":a["seller_fill_id"]},
          {"account":"PROCESSOR_CASH","credit":a["total_cents"],"component":"buyer_refund","fill_id":a["seller_fill_id"]}])
        conn.execute("UPDATE seller_fills SET state=CASE WHEN refunded_quantity=quantity THEN 'REFUNDED' ELSE 'PARTIALLY_REFUNDED' END,updated_at=? WHERE id=?",(now,a["seller_fill_id"]))
    conn.execute("UPDATE flow_refunds SET state='SUCCEEDED',provider_refund_id=?,updated_at=? WHERE id=?",(provider_refund_id,now,refund_id))
    conn.execute("UPDATE financial_operations SET state='SUCCEEDED',provider_object_id=?,updated_at=? WHERE id=?",(provider_refund_id,now,refund["financial_operation_id"]))
    _audit(conn,"refund",refund_id,"REFUND_SUCCEEDED","provider",metadata={"provider_refund_id":provider_refund_id})
    if own: conn.commit(); conn.close()
    return True


def record_refund_provider_result(refund_id, provider_refund):
    """Persist submission status and post money only after provider success."""
    pdata=provider_refund.to_dict() if hasattr(provider_refund,"to_dict") else dict(provider_refund)
    if pdata.get("status")=="succeeded":
        return complete_refund(refund_id,pdata["id"])
    state="FAILED" if pdata.get("status") in ("failed","canceled") else "PROCESSING"
    conn=get_db_connection(); ensure_flow_schema(conn)
    conn.execute("UPDATE flow_refunds SET state=?,provider_refund_id=?,updated_at=? WHERE id=?",
                 (state,pdata.get("id"),_now(),refund_id))
    conn.execute("""UPDATE financial_operations SET state=?,provider_object_id=?,last_error=?,updated_at=?
      WHERE id=(SELECT financial_operation_id FROM flow_refunds WHERE id=?)""",
      (state,pdata.get("id"),pdata.get("failure_reason"),_now(),refund_id))
    conn.commit(); conn.close(); return False


def claim_seller_transfer(payable_id, idempotency_key):
    eligible,reason=evaluate_payout(payable_id)
    if not eligible: raise FlowError("Payout is blocked: "+reason,"PAYOUT_BLOCKED",409)
    conn=get_db_connection(); ensure_flow_schema(conn)
    payable=conn.execute("SELECT * FROM seller_payables WHERE id=?",(payable_id,)).fetchone()
    remaining=payable["amount_cents"]-payable["released_cents"]-payable["recovered_cents"]
    op,created=claim_operation(conn,"SELLER_TRANSFER",idempotency_key,"seller_payable",payable_id,remaining,
                               {"payable_id":payable_id,"amount_cents":remaining})
    if created:
        transfer_id=_id("tr"); now=_now()
        conn.execute("INSERT INTO transfers VALUES (?,?,?,?,?,?,?,?)",
          (transfer_id,payable_id,op["id"],None,remaining,"CLAIMED",now,now))
        conn.execute("UPDATE seller_payables SET state='RELEASE_APPROVED',updated_at=? WHERE id=?",(now,payable_id))
    else:
        transfer_id=conn.execute("SELECT id FROM transfers WHERE operation_id=?",(op["id"],)).fetchone()["id"]
    conn.commit(); conn.close(); return {"id":transfer_id,"operation_id":op["id"],"amount_cents":remaining},created


def complete_seller_transfer(transfer_id, provider_transfer_id):
    """A connected-account transfer is explicitly not a final bank payout."""
    conn=get_db_connection(); ensure_flow_schema(conn); row=conn.execute("SELECT * FROM transfers WHERE id=?",(transfer_id,)).fetchone()
    if not row: conn.close(); raise FlowError("Transfer not found","TRANSFER_NOT_FOUND",404)
    if row["state"]=="TRANSFER_CONFIRMED": conn.close(); return False
    now=_now(); conn.execute("UPDATE transfers SET provider_transfer_id=?,state='TRANSFER_CONFIRMED',updated_at=? WHERE id=?",
                             (provider_transfer_id,now,transfer_id))
    conn.execute("UPDATE seller_payables SET state='TRANSFERRED_TO_CONNECTED_ACCOUNT',released_cents=released_cents+?,updated_at=? WHERE id=?",
                 (row["amount_cents"],now,row["seller_payable_id"]))
    conn.execute("UPDATE financial_operations SET provider_object_id=?,state='SUCCEEDED',updated_at=? WHERE id=?",
                 (provider_transfer_id,now,row["operation_id"]))
    _journal(conn,"transfer",transfer_id,"TRANSFER_CONFIRMED",f"transfer:{provider_transfer_id}",[
      {"account":"SELLER_PAYABLE","debit":row["amount_cents"],"component":"seller_transfer"},
      {"account":"CONNECTED_ACCOUNT_FUNDS","credit":row["amount_cents"],"component":"seller_transfer"}])
    conn.commit(); conn.close(); return True


def record_bank_payout_event(provider_payout_id, seller_id, amount_cents, state, arrival_at=None):
    if state not in ("BANK_PAYOUT_PENDING","BANK_PAYOUT_PAID","BANK_PAYOUT_FAILED"):
        raise FlowError("Invalid bank payout state","INVALID_PAYOUT_STATE")
    conn=get_db_connection(); ensure_flow_schema(conn); now=_now()
    row=conn.execute("SELECT id FROM bank_payouts WHERE provider_payout_id=?",(provider_payout_id,)).fetchone()
    if row: conn.execute("UPDATE bank_payouts SET state=?,arrival_at=?,updated_at=? WHERE id=?",(state,arrival_at,now,row["id"]))
    else: conn.execute("INSERT INTO bank_payouts VALUES (?,?,?,?,?,?,?,?)",(_id("bp"),seller_id,provider_payout_id,state,amount_cents,arrival_at,now,now))
    conn.commit(); conn.close()


def create_recovery_obligation(seller_fill_id, source_type, source_id, amount_cents,
                               liability_policy_key=None):
    """Create post-transfer debt only when a reason-specific policy authorizes it."""
    if not liability_policy_key:
        raise FlowError("Seller liability requires an approved reason mapping","LIABILITY_POLICY_REQUIRED",409)
    conn=get_db_connection(); ensure_flow_schema(conn); require_approved_policy(conn,"chargeback_loss_liability")
    fill=conn.execute("SELECT seller_id FROM seller_fills WHERE id=?",(seller_fill_id,)).fetchone()
    if not fill: conn.close(); raise FlowError("Fill not found","FILL_NOT_FOUND",404)
    existing=conn.execute("SELECT * FROM recovery_obligations WHERE source_type=? AND source_id=? AND seller_fill_id=?",
                          (source_type,source_id,seller_fill_id)).fetchone()
    if existing: conn.close(); return dict(existing),False
    rid=_id("rec"); now=_now(); conn.execute("INSERT INTO recovery_obligations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
      (rid,fill["seller_id"],seller_fill_id,source_type,source_id,amount_cents,0,"OPEN",liability_policy_key,now,now))
    conn.execute("UPDATE seller_payables SET state='RECOVERY_PENDING',block_reason='RECOVERY_OBLIGATION',updated_at=? WHERE seller_fill_id=?",(now,seller_fill_id))
    conn.commit(); conn.close(); return {"id":rid,"state":"OPEN"},True


def record_recovery_attempt(recovery_id, method, amount_cents, state,
                            provider_object_id=None, evidence=None):
    ladder=("PROVIDER_REVERSAL","CONNECTED_BALANCE","FUTURE_PAYOUT_OFFSET",
            "NEGATIVE_SELLER_BALANCE","REPAYMENT","SUSPENSION")
    if method not in ladder: raise FlowError("Invalid recovery method","INVALID_RECOVERY_METHOD")
    conn=get_db_connection(); ensure_flow_schema(conn); rec=conn.execute("SELECT * FROM recovery_obligations WHERE id=?",(recovery_id,)).fetchone()
    if not rec: conn.close(); raise FlowError("Recovery not found","RECOVERY_NOT_FOUND",404)
    recovered=int(amount_cents) if state=="SUCCEEDED" else 0; now=_now()
    conn.execute("INSERT INTO recovery_attempts VALUES (?,?,?,?,?,?,?,?)",
      (_id("rat"),recovery_id,method,int(amount_cents),state,provider_object_id,_canonical(evidence or {}),now))
    if recovered:
        new=min(rec["amount_cents"],rec["recovered_cents"]+recovered)
        conn.execute("UPDATE recovery_obligations SET recovered_cents=?,state=?,updated_at=? WHERE id=?",
                     (new,"RECOVERED" if new>=rec["amount_cents"] else "PARTIAL",now,recovery_id))
    conn.commit(); conn.close()


def reconcile_internal():
    conn=get_db_connection(); ensure_flow_schema(conn); cases=[]
    for j in conn.execute("""SELECT j.id,COALESCE(SUM(e.debit_cents),0) d,COALESCE(SUM(e.credit_cents),0) c
      FROM ledger_journals j LEFT JOIN ledger_entries e ON e.journal_id=j.id GROUP BY j.id
      HAVING COALESCE(SUM(e.debit_cents),0)<>COALESCE(SUM(e.credit_cents),0)""").fetchall():
        cases.append({"journal_id":j["id"],"variance_cents":j["d"]-j["c"]})
    conn.close(); return cases


def expire_due_reservations(now=None):
    """Release only unpaid expirations; pending/unknown ACH is never TTL-released."""
    now=(now or datetime.now(timezone.utc)).isoformat(); conn=get_db_connection(); ensure_flow_schema(conn)
    rows=conn.execute("""SELECT id FROM checkout_attempts WHERE expires_at<?
      AND state IN ('RESERVED','FAILED','PAYMENT_CORRECTION')""",(now,)).fetchall(); conn.close()
    return sum(release_reservation(r["id"],"RESERVATION_EXPIRED") for r in rows)


def reconcile_provider_payment(payment):
    pdata=payment.to_dict() if hasattr(payment,"to_dict") else dict(payment)
    pi_id=pdata["id"]; conn=get_db_connection(); ensure_flow_schema(conn)
    checkout=conn.execute("SELECT * FROM checkout_attempts WHERE provider_payment_id=?",(pi_id,)).fetchone()
    if not checkout:
        variance=pdata.get("amount_received",pdata.get("amount",0)); details={"reason":"provider payment has no checkout"}
    else:
        snap=conn.execute("SELECT * FROM execution_snapshots WHERE id=?",(checkout["active_snapshot_id"],)).fetchone()
        variance=pdata.get("amount",0)-snap["buyer_total_cents"]; details={"checkout_id":checkout["id"],"expected":snap["buyer_total_cents"],"actual":pdata.get("amount")}
    if variance:
        row=conn.execute("SELECT id FROM reconciliation_cases WHERE provider='stripe' AND object_type='payment_intent' AND object_id=?",(pi_id,)).fetchone(); now=_now()
        if row: conn.execute("UPDATE reconciliation_cases SET variance_cents=?,details_json=?,updated_at=? WHERE id=?",(variance,_canonical(details),now,row["id"]))
        else: conn.execute("INSERT INTO reconciliation_cases VALUES (?,?,?,?,?,?,?,?,?)",(_id("recon"),"stripe","payment_intent",pi_id,variance,"OPEN",_canonical(details),now,now))
    conn.commit(); conn.close(); return variance


def record_provider_expense(execution_id, expense_type, amount_cents, provider_object_id,
                            idempotency_key):
    """Post actual processor/insurance costs separately from contractual revenue."""
    account={"ACH_PROCESSING":"ACH_PROCESSING_EXPENSE","CARD_PROCESSING":"CARD_PROCESSING_EXPENSE",
             "UPS_INSURANCE":"SHIPPING_INSURANCE_EXPENSE"}.get(expense_type)
    if not account: raise FlowError("Unknown expense type","UNKNOWN_EXPENSE_TYPE")
    conn=get_db_connection(); ensure_flow_schema(conn)
    op,created=claim_operation(conn,"EXPENSE",idempotency_key,"execution",execution_id,amount_cents,
                               {"type":expense_type,"provider_object_id":provider_object_id})
    if created:
        _journal(conn,"execution",execution_id,"EXPENSE_POSTED",idempotency_key,[
          {"account":account,"debit":amount_cents,"component":expense_type.lower()},
          {"account":"PROCESSOR_CASH","credit":amount_cents,"component":expense_type.lower()}])
        conn.execute("UPDATE financial_operations SET state='SUCCEEDED',provider_object_id=?,updated_at=? WHERE id=?",
                     (provider_object_id,_now(),op["id"]))
    conn.commit(); conn.close(); return created


def execute_bid_fill(bid_id, buyer_id, seller_id, items, payment_rail, tax_cents,
                     shipping, payment_method_id, customer_id):
    """Create one independent payment/execution for one bid partial fill."""
    import stripe
    quantity=sum(int(i["quantity"]) for i in items)
    if not quantity: raise FlowError("No bid quantity selected","EMPTY_BID_FILL")
    conn=get_db_connection(); ensure_flow_schema(conn)
    require_approved_policy(conn,"tracking_upload_deadline_days","ups_coverage_and_claim_policy")
    if payment_rail=="us_bank_account": require_approved_policy(conn,"ach_approval_policy")
    if any(bool(item.get("requires_grading")) for item in items):
        require_approved_policy(conn,"grading_vendor_policy")
    if database_module.IS_POSTGRES:
        bid=conn.execute("SELECT * FROM bids WHERE id=? FOR UPDATE",(bid_id,)).fetchone()
    else: bid=conn.execute("SELECT * FROM bids WHERE id=?",(bid_id,)).fetchone()
    if not bid or int(bid["buyer_id"])!=int(buyer_id) or bid["remaining_quantity"]<quantity:
        conn.close(); raise FlowError("Bid quantity is no longer available","BID_CONCURRENCY_CONFLICT",409)
    listing_ids=[int(item["listing_id"]) for item in items]
    placeholders=",".join("?" for _ in listing_ids)
    sellers=conn.execute(f"SELECT DISTINCT seller_id FROM listings WHERE id IN ({placeholders})",listing_ids).fetchall()
    if len(sellers)!=1 or int(sellers[0]["seller_id"])!=int(seller_id) or int(seller_id)==int(buyer_id):
        conn.close(); raise FlowError("Bid fill seller ownership is invalid","BID_SELLER_MISMATCH",409)
    ordinal=bid["remaining_quantity"]
    for item in items: item["source_bid_id"]=bid_id
    checkout,snapshot,_=prepare_checkout(buyer_id,items,payment_rail,tax_cents,shipping,
      f"bid:{bid_id}:seller:{seller_id}:remaining:{ordinal}:quantity:{quantity}",conn=conn)
    expires=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    changed=conn.execute("UPDATE bids SET remaining_quantity=remaining_quantity-?,status='Payment Pending',bid_payment_status='pending' WHERE id=? AND remaining_quantity>=?",
                         (quantity,bid_id,quantity))
    if changed.rowcount!=1: conn.rollback(); conn.close(); raise FlowError("Bid changed concurrently","BID_CONCURRENCY_CONFLICT",409)
    conn.execute("INSERT INTO bid_quantity_reservations VALUES (?,?,?,?,?,?,?,?)",
      (_id("bres"),checkout["id"],bid_id,quantity,"HELD",expires,_now(),_now()))
    op,_=claim_operation(conn,"PAYMENT",f"payment:{checkout['id']}","checkout",checkout["id"],snapshot["buyer_total_cents"],
                         {"snapshot_hash":snapshot["snapshot_hash"]})
    conn.commit(); conn.close()
    kwargs=dict(amount=snapshot["buyer_total_cents"],currency="usd",customer=customer_id,
      payment_method=payment_method_id,payment_method_types=[payment_rail],confirm=True,
      metadata={"checkout_id":checkout["id"],"snapshot_hash":snapshot["snapshot_hash"],
                "buyer_id":str(buyer_id),"bid_id":str(bid_id),"policy_version":POLICY_VERSION})
    if payment_rail=="card": kwargs["off_session"]=True
    else:
        # Off-session ACH needs the mandate created with the buyer's saved bank method.
        try:
            for setup_intent in stripe.SetupIntent.list(customer=customer_id,limit=50).auto_paging_iter():
                if (setup_intent.get("payment_method")==payment_method_id and
                        setup_intent.get("status")=="succeeded" and setup_intent.get("mandate")):
                    kwargs["mandate"]=setup_intent.get("mandate")
                    break
        except Exception as exc:
            conn=get_db_connection(); conn.execute("UPDATE checkout_attempts SET state='PAYMENT_CORRECTION',expires_at=?,updated_at=? WHERE id=?",
                                                  (expires,_now(),checkout["id"])); conn.commit(); conn.close()
            raise FlowError("ACH mandate verification is temporarily unavailable","ACH_MANDATE_VERIFICATION_FAILED",503) from exc
        if "mandate" not in kwargs:
            conn=get_db_connection(); conn.execute("UPDATE checkout_attempts SET state='PAYMENT_CORRECTION',expires_at=?,updated_at=? WHERE id=?",
                                                  (expires,_now(),checkout["id"])); conn.commit(); conn.close()
            raise FlowError("ACH payment mandate is missing","ACH_MANDATE_REQUIRED",409)
    try:
        pi=stripe.PaymentIntent.create(**kwargs,idempotency_key=op["idempotency_key"])
        bind_provider_payment(checkout["id"],pi.id,op["id"])
        if pi.status=="succeeded": result,_=finalize_payment(checkout["id"],pi); return {"state":"FUNDED","execution":result,"payment_intent_id":pi.id}
        conn=get_db_connection(); conn.execute("UPDATE checkout_attempts SET state='PAYMENT_CORRECTION',expires_at=?,updated_at=? WHERE id=?",
                                              (expires,_now(),checkout["id"])); conn.commit(); conn.close()
        return {"state":"PAYMENT_CORRECTION","checkout_id":checkout["id"],"payment_intent_id":pi.id}
    except Exception:
        conn=get_db_connection(); conn.execute("UPDATE checkout_attempts SET state='PAYMENT_CORRECTION',expires_at=?,updated_at=? WHERE id=?",
                                              (expires,_now(),checkout["id"])); conn.commit(); conn.close(); raise


def dispatch_outbox(limit=100):
    """Deliver committed notifications; retries never repeat financial writes."""
    from services.notification_service import create_notification
    conn=get_db_connection(); ensure_flow_schema(conn)
    rows=conn.execute("SELECT * FROM outbox_events WHERE state IN ('PENDING','RETRY') ORDER BY created_at LIMIT ?",(limit,)).fetchall()
    sent=0
    for row in rows:
        try:
            if row["event_type"]=="EXECUTION_FUNDED":
                exe=conn.execute("SELECT buyer_id,legacy_order_id FROM executions WHERE id=?",(row["aggregate_id"],)).fetchone()
                create_notification(user_id=exe["buyer_id"],notification_type="order_confirmed",
                  title="Payment confirmed",message=f"Order #{exe['legacy_order_id']} has been created.",related_order_id=exe["legacy_order_id"])
                for fill in conn.execute("SELECT DISTINCT seller_id FROM seller_fills WHERE execution_id=?",(row["aggregate_id"],)).fetchall():
                    create_notification(user_id=fill["seller_id"],notification_type="listing_sold",
                      title="Item sold",message=f"You have a funded fill on order #{exe['legacy_order_id']}. Wait for shipping authorization.",related_order_id=exe["legacy_order_id"])
            conn.execute("UPDATE outbox_events SET state='SENT',sent_at=? WHERE id=?",(_now(),row["id"])); sent+=1
        except Exception:
            conn.execute("UPDATE outbox_events SET state='RETRY',attempts=attempts+1 WHERE id=?",(row["id"],))
    conn.commit(); conn.close(); return sent
