"""Background recovery and reconciliation worker for the canonical money flow."""

import logging
import os
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
_timer = None
_started = False
_lock = threading.Lock()
_last_provider_reconciliation = None


def _provider_reconciliation():
    import stripe
    from database import get_db_connection
    from services.flow_of_funds import ensure_flow_schema, reconcile_provider_payment

    conn = get_db_connection(); ensure_flow_schema(conn)
    ids = [row["provider_payment_id"] for row in conn.execute(
        "SELECT provider_payment_id FROM checkout_attempts WHERE provider_payment_id IS NOT NULL"
    ).fetchall()]
    conn.close()
    for payment_id in ids:
        try:
            reconcile_provider_payment(stripe.PaymentIntent.retrieve(payment_id))
        except Exception as exc:
            logger.error("[flow_worker] Provider reconciliation failed for %s: %s", payment_id, exc)


def _tick(app):
    global _last_provider_reconciliation
    try:
        with app.app_context():
            from services.flow_of_funds import (
                dispatch_outbox, expire_due_reservations, mark_tracking_forfeitures,
                process_tracking_forfeiture_refunds,
                reconcile_internal, replay_retry_webhooks,
            )
            retries = replay_retry_webhooks()
            released = expire_due_reservations()
            forfeited = mark_tracking_forfeitures()
            forfeiture_refunds = process_tracking_forfeiture_refunds()
            sent = dispatch_outbox()
            unbalanced = reconcile_internal()
            if unbalanced:
                logger.critical("[flow_worker] Unbalanced journals: %s", unbalanced)
            now = datetime.now(timezone.utc)
            if _last_provider_reconciliation is None or now - _last_provider_reconciliation >= timedelta(days=1):
                _provider_reconciliation()
                _last_provider_reconciliation = now
            logger.info(
                "[flow_worker] retries=%s reservations=%s forfeitures=%s forfeiture_refunds=%s notifications=%s",
                retries, released, len(forfeited), len(forfeiture_refunds), sent,
            )
    except Exception:
        logger.exception("[flow_worker] Recovery tick failed")
    finally:
        _schedule(app)


def _schedule(app, delay_seconds=300):
    global _timer
    timer = threading.Timer(delay_seconds, _tick, args=(app,))
    timer.daemon = True
    timer.name = "flow_of_funds_worker"
    with _lock:
        _timer = timer
    timer.start()


def start_worker(app):
    """Start once per process; financial operations remain DB-idempotent across workers."""
    global _started
    is_debug = os.getenv("FLASK_ENV") == "development" or os.getenv("FLASK_DEBUG", "").lower() in ("1", "true")
    if is_debug and not os.getenv("WERKZEUG_RUN_MAIN"):
        return
    with _lock:
        if _started:
            return
        _started = True
    logger.info("[flow_worker] Starting canonical recovery worker")
    _schedule(app, delay_seconds=15)


def cancel_worker():
    global _timer, _started
    with _lock:
        if _timer:
            _timer.cancel()
            _timer = None
        _started = False
