"""Operational reconciliation entry point (safe to schedule repeatedly)."""
import sys
import stripe

from database import get_db_connection
from services.flow_of_funds import (
    dispatch_outbox, ensure_flow_schema, expire_due_reservations, mark_tracking_forfeitures,
    reconcile_internal, reconcile_provider_payment,
)


def run():
    conn=get_db_connection(); ensure_flow_schema(conn)
    ids=[r["provider_payment_id"] for r in conn.execute(
        "SELECT provider_payment_id FROM checkout_attempts WHERE provider_payment_id IS NOT NULL"
    ).fetchall()]; conn.commit(); conn.close()
    internal=reconcile_internal()
    if internal:
        raise RuntimeError(f"unbalanced journals: {internal}")
    for payment_id in ids:
        reconcile_provider_payment(stripe.PaymentIntent.retrieve(payment_id))
    released=expire_due_reservations(); forfeited=mark_tracking_forfeitures(); notifications=dispatch_outbox()
    print({"payments":len(ids),"reservations_released":released,"tracking_forfeitures":len(forfeited),"notifications":notifications})
    return 0


if __name__ == "__main__":
    sys.exit(run())
