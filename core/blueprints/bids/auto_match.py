"""Secure automatic bid matching through the canonical flow-of-funds engine."""

import logging
import os
import threading
from decimal import Decimal, ROUND_HALF_UP

import stripe

from database import get_db_connection
from services.notification_types import notify_bid_payment_failed
from services.pricing_service import can_bid_fill_listing

logger = logging.getLogger(__name__)
_rematch_lock = threading.Lock()

if int(os.environ.get("WEB_CONCURRENCY", 1)) > 1:
    logger.warning("[bid_rematch] Use one web worker or a distributed scheduler lease")


def _spot_prices(conn):
    try:
        rows = conn.execute(
            "SELECT metal,price_usd FROM spot_price_snapshots "
            "WHERE id IN (SELECT MAX(id) FROM spot_price_snapshots GROUP BY metal)"
        ).fetchall()
        if rows:
            return {row["metal"].lower(): float(row["price_usd"]) for row in rows}
    except Exception:
        pass
    try:
        rows = conn.execute("SELECT metal,price_usd_per_oz FROM spot_prices").fetchall()
        return {row["metal"].lower(): float(row["price_usd_per_oz"]) for row in rows}
    except Exception:
        return {}


def _shipping(bid):
    import re
    address = bid["delivery_address"] or ""
    match = re.search(r"\b([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*$", address)
    if not match:
        raise ValueError("The bid delivery address is incomplete; automatic payment was not attempted.")
    return {
        "shipping_address": address,
        "recipient_first": bid["recipient_first_name"],
        "recipient_last": bid["recipient_last_name"],
        "state": match.group(1),
        "postal_code": match.group(2),
        "country": "US",
    }


def _tax_cents(subtotal_cents, shipping):
    calc = stripe.tax.Calculation.create(
        currency="usd",
        line_items=[{"amount": subtotal_cents, "reference": "bid_merchandise"}],
        customer_details={"address": {
            "postal_code": shipping["postal_code"], "state": shipping["state"], "country": "US"
        }, "address_source": "shipping"},
    )
    return int(calc.tax_amount_exclusive)


def _candidate_listings(conn, bid, only_listing_id=None):
    category_ids = [bid["category_id"]]
    if bid["random_year"]:
        category = conn.execute(
            "SELECT metal,product_line,product_type,weight,purity,mint,finish FROM categories WHERE id=?",
            (bid["category_id"],),
        ).fetchone()
        if category:
            rows = conn.execute(
                """SELECT id FROM categories WHERE metal IS ? AND product_line IS ?
                   AND product_type IS ? AND weight IS ? AND purity IS ? AND mint IS ? AND finish IS ?""",
                tuple(category[key] for key in ("metal", "product_line", "product_type", "weight", "purity", "mint", "finish")),
            ).fetchall()
            category_ids = [row["id"] for row in rows] or category_ids
    placeholders = ",".join("?" for _ in category_ids)
    params = list(category_ids) + [bid["buyer_id"]]
    where_listing = ""
    if only_listing_id is not None:
        where_listing = " AND l.id=?"
        params.append(only_listing_id)
    return conn.execute(
        f"""SELECT l.*,c.metal,c.weight,c.product_type FROM listings l
             JOIN categories c ON c.id=l.category_id
             WHERE l.category_id IN ({placeholders}) AND l.seller_id<>?
               AND l.active=1 AND l.quantity>0 {where_listing}""",
        params,
    ).fetchall()


def secure_auto_match_bid(bid_id, only_listing_id=None):
    """Create at most one independent canonical payment per matched listing."""
    from services.flow_of_funds import FlowError, execute_bid_fill

    conn = get_db_connection()
    bid = conn.execute(
        """SELECT b.*,c.metal,c.weight,c.product_type,u.stripe_customer_id
           FROM bids b JOIN categories c ON c.id=b.category_id
           JOIN users u ON u.id=b.buyer_id WHERE b.id=?""", (bid_id,),
    ).fetchone()
    if not bid or not bid["active"] or int(bid["remaining_quantity"] or 0) <= 0:
        conn.close()
        return {"filled_quantity": 0, "orders_created": 0, "message": "No open quantity"}
    if not bid["bid_payment_method_id"] or not bid["stripe_customer_id"]:
        conn.close()
        return {"filled_quantity": 0, "orders_created": 0, "message": "Buyer payment method is missing"}
    spots = _spot_prices(conn)
    matched = []
    for row in _candidate_listings(conn, bid, only_listing_id):
        listing = dict(row)
        pricing = can_bid_fill_listing(dict(bid), listing, spot_prices=spots)
        if pricing["can_fill"]:
            matched.append((listing, pricing))
    conn.close()
    matched.sort(key=lambda item: (item[1]["listing_effective_price"], item[0]["id"]))
    if not matched:
        return {"filled_quantity": 0, "orders_created": 0, "message": "No matching listing"}

    payment_method = stripe.PaymentMethod.retrieve(bid["bid_payment_method_id"])
    rail = payment_method.type
    if rail not in ("card", "us_bank_account"):
        return {"filled_quantity": 0, "orders_created": 0, "message": "Unsupported payment method"}
    shipping = _shipping(bid)
    remaining = int(bid["remaining_quantity"])
    filled = 0
    executions = []
    failures = []
    for listing, pricing in matched:
        if remaining <= 0:
            break
        quantity = min(remaining, int(listing["quantity"]))
        item = {
            "listing_id": listing["id"], "quantity": quantity,
            "price_each": pricing["bid_effective_price"],
            "seller_price_each": pricing["listing_effective_price"],
            "source_bid_id": bid_id, "requires_grading": bool(bid["requires_grading"]),
        }
        try:
            subtotal_cents = int(
                (Decimal(str(pricing["bid_effective_price"])) * 100).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            ) * quantity
            tax = _tax_cents(subtotal_cents, shipping)
            outcome = execute_bid_fill(
                bid_id, bid["buyer_id"], listing["seller_id"], [item], rail, tax,
                shipping, bid["bid_payment_method_id"], bid["stripe_customer_id"],
            )
            executions.append(outcome)
            filled += quantity
            remaining -= quantity
        except FlowError as exc:
            failures.append({"listing_id": listing["id"], "code": exc.code, "message": str(exc)})
            if exc.code in ("BID_CONCURRENCY_CONFLICT", "INVENTORY_UNAVAILABLE"):
                break
        except Exception as exc:
            logger.exception("[auto_match] Bid %s payment attempt failed", bid_id)
            failures.append({"listing_id": listing["id"], "code": "PAYMENT_FAILED", "message": str(exc)})
            try:
                notify_bid_payment_failed(bid["buyer_id"], bid_id, str(exc))
            except Exception:
                logger.exception("[auto_match] Failed to notify buyer for bid %s", bid_id)
            break
    return {
        "filled_quantity": filled, "orders_created": len(executions),
        "message": "Automatic match completed" if filled else "Automatic match was not funded",
        "executions": executions, "failures": failures, "notifications": [], "ledger_orders": [],
    }


def auto_match_bid_to_listings(bid_id, cursor=None):
    return secure_auto_match_bid(bid_id)


def auto_match_listing_to_bids(listing_id, cursor=None):
    conn = get_db_connection()
    listing = conn.execute("SELECT category_id,seller_id FROM listings WHERE id=?", (listing_id,)).fetchone()
    if not listing:
        conn.close()
        return {"filled_quantity": 0, "orders_created": 0, "message": "Listing not found", "notifications": []}
    bids = conn.execute(
        """SELECT b.id FROM bids b JOIN categories bc ON bc.id=b.category_id
           JOIN categories lc ON lc.id=? WHERE b.active=1 AND b.remaining_quantity>0
           AND b.buyer_id<>? AND (b.category_id=? OR (b.random_year=1 AND bc.metal IS lc.metal
           AND bc.product_line IS lc.product_line AND bc.product_type IS lc.product_type
           AND bc.weight IS lc.weight AND bc.purity IS lc.purity AND bc.mint IS lc.mint
           AND bc.finish IS lc.finish)) ORDER BY b.created_at,b.id""",
        (listing["category_id"], listing["seller_id"], listing["category_id"]),
    ).fetchall()
    conn.close()
    total = orders = 0
    failures = []
    for bid in bids:
        result = secure_auto_match_bid(bid["id"], only_listing_id=listing_id)
        total += result.get("filled_quantity", 0)
        orders += result.get("orders_created", 0)
        failures.extend(result.get("failures", []))
        check = get_db_connection()
        available = check.execute("SELECT quantity,active FROM listings WHERE id=?", (listing_id,)).fetchone()
        check.close()
        if not available or not available["active"] or available["quantity"] <= 0:
            break
    return {"filled_quantity": total, "orders_created": orders,
            "message": "Automatic listing match completed", "failures": failures, "notifications": []}


def check_all_pending_matches(conn=None):
    own = conn is None
    conn = conn or get_db_connection()
    ids = [row["id"] for row in conn.execute(
        """SELECT id FROM bids WHERE active=1 AND remaining_quantity>0
           AND status IN ('Open','Partially Filled') ORDER BY created_at,id"""
    ).fetchall()]
    if own:
        conn.close()
    else:
        conn.commit()
    total = orders = matched = 0
    failures = []
    for bid_id in ids:
        result = secure_auto_match_bid(bid_id)
        total += result.get("filled_quantity", 0)
        orders += result.get("orders_created", 0)
        matched += 1 if result.get("filled_quantity", 0) else 0
        failures.extend(result.get("failures", []))
    return {"total_filled": total, "orders_created": orders, "bids_matched": matched,
            "failures": failures, "notifications": []}


def run_bid_rematch_after_spot_update(metals=None):
    if not _rematch_lock.acquire(blocking=False):
        return {"total_filled": 0, "orders_created": 0, "bids_matched": 0, "notifications": []}
    try:
        result = check_all_pending_matches()
        if result["bids_matched"]:
            logger.info("[bid_rematch] %s bids matched after spot update for %s", result["bids_matched"], metals)
        return result
    except Exception:
        logger.exception("[bid_rematch] Failed after spot update for %s", metals)
        return {"total_filled": 0, "orders_created": 0, "bids_matched": 0, "notifications": []}
    finally:
        _rematch_lock.release()
