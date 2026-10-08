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
            logger.error("[flow_worker] Provider reconciliation failed for %s: %s", payment_id, type(exc).__name__)


def run_once(app):
    """One leased cycle; durable identities make crashed-provider retries safe."""
    global _last_provider_reconciliation
    from database import get_db_connection
    from services.flow_of_funds import ensure_flow_schema
    import uuid
    token=uuid.uuid4().hex; now=datetime.now(timezone.utc)
    conn=get_db_connection(); ensure_flow_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS flow_worker_lease (id INTEGER PRIMARY KEY,token TEXT,expires_at TIMESTAMP,last_success TIMESTAMP)")
    conn.execute("INSERT INTO flow_worker_lease(id) VALUES (1) ON CONFLICT(id) DO NOTHING")
    claimed=conn.execute("UPDATE flow_worker_lease SET token=?,expires_at=? WHERE id=1 AND (expires_at IS NULL OR expires_at<?)",(token,(now+timedelta(minutes=10)).isoformat(),now.isoformat()))
    conn.commit(); conn.close()
    if claimed.rowcount!=1: return False
    try:
        with app.app_context():
            from services.flow_of_funds import (dispatch_outbox,expire_due_reservations,mark_tracking_forfeitures,
              process_tracking_forfeiture_refunds,reconcile_internal,replay_retry_webhooks,retry_pending_refunds)
            from services.compensation_service import retry_compensations
            from services.tax_service import sync_tax_records
            from services.delivery_service import dispatch_email_queue
            from services.smart_pricing_service import run_due
            run_due()
            replay_retry_webhooks(); expire_due_reservations(); mark_tracking_forfeitures()
            process_tracking_forfeiture_refunds(); retry_pending_refunds(); retry_compensations(); sync_tax_records()
            dispatch_outbox(); dispatch_email_queue()
            from services.payout_service import run_daily_releases
            run_daily_releases()
            unbalanced=reconcile_internal()
            if unbalanced: logger.critical('Unbalanced journals require review: %s',unbalanced)
            if _last_provider_reconciliation is None or now-_last_provider_reconciliation>=timedelta(days=1):
                _provider_reconciliation(); _last_provider_reconciliation=now
            conn=get_db_connection()
            conn.execute('UPDATE flow_worker_lease SET last_success=? WHERE id=1 AND token=?',(datetime.now(timezone.utc).isoformat(),token))
            conn.commit(); conn.close()
        return True
    finally:
        conn=get_db_connection()
        conn.execute('UPDATE flow_worker_lease SET expires_at=NULL WHERE id=1 AND token=?',(token,))
        conn.commit(); conn.close()


def _tick(app):
    try: run_once(app)
    except Exception: logger.exception('Recovery tick failed')
    finally: _schedule(app)


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
