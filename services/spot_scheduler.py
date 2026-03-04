"""
Spot Price Snapshot Scheduler

Runs a background daemon thread that calls spot_snapshot_service.run_snapshot()
every N minutes, where N is loaded from system_settings on each tick so that
admin interval changes take effect automatically.

Safe startup contract:
  - Call start_scheduler(app) once from the app factory.
  - Guards against Flask's debug-reload double-start (checks WERKZEUG_RUN_MAIN).
  - Uses a module-level flag to prevent double-start within the same process.
  - Daemon thread — dies when main process exits.
  - DB run-lock in spot_snapshot_service prevents concurrent runs from multiple
    Gunicorn/uWSGI workers.

To change the interval at runtime, simply update system_settings; the scheduler
reads it on every reschedule tick so no restart is needed.
"""

import os
import threading
import logging

logger = logging.getLogger(__name__)

# Module-level state — one scheduler per process
_timer = None  # type: threading.Timer
_started = False
_lock = threading.Lock()


def _tick(app_ctx=None):
    """One scheduler tick: run snapshot, then reschedule."""
    global _timer

    # Run inside an app context so Flask globals work
    if app_ctx is not None:
        with app_ctx:
            _do_snapshot()
    else:
        _do_snapshot()

    # Reschedule with the latest interval from DB
    _schedule_next(app_ctx)


def _do_snapshot():
    """Execute the snapshot (errors are caught so the scheduler keeps running)."""
    try:
        from services.spot_snapshot_service import run_snapshot
        result = run_snapshot(use_lock=True, verbose=False, force=True)
        logger.debug(
            "[spot_scheduler] tick: inserted=%s skipped=%s locked_out=%s error=%s",
            result.get("inserted"), result.get("skipped"),
            result.get("locked_out"), result.get("error"),
        )
    except Exception as exc:
        logger.error("[spot_scheduler] Unexpected error during snapshot: %s", exc)


def _schedule_next(app_ctx=None):
    """Schedule the next tick using the current interval from system settings."""
    global _timer

    try:
        from services.system_settings_service import get_spot_snapshot_interval
        interval_mins = get_spot_snapshot_interval()
    except Exception:
        interval_mins = 10  # fallback if DB is unavailable

    delay_secs = interval_mins * 60
    t = threading.Timer(delay_secs, _tick, kwargs={"app_ctx": app_ctx})
    t.daemon = True
    t.name = "spot_snapshot_scheduler"

    with _lock:
        _timer = t

    t.start()
    logger.debug("[spot_scheduler] Next tick in %d minutes.", interval_mins)


def start_scheduler(app=None):
    """
    Start the background snapshot scheduler.

    Should be called once from the app factory after all blueprints are registered.

    Args:
        app: The Flask app instance (used to push an app context for each tick).
    """
    global _started

    # Guard 1: Flask debug reloader creates two processes.
    # WERKZEUG_RUN_MAIN is set only in the child (the actual app process).
    # We skip scheduling in the watcher parent to avoid double-running.
    flask_env = os.environ.get("FLASK_ENV", "")
    werkzeug_main = os.environ.get("WERKZEUG_RUN_MAIN", "")
    is_debug_mode = flask_env == "development" or os.environ.get("FLASK_DEBUG", "") in ("1", "true")

    if is_debug_mode and not werkzeug_main:
        logger.info(
            "[spot_scheduler] Debug reloader watcher process detected — "
            "skipping scheduler start (will start in app process)."
        )
        return

    # Guard 2: Only start once per process.
    with _lock:
        if _started:
            logger.info("[spot_scheduler] Already started — skipping.")
            return
        _started = True

    # Build a push-able app context for use in daemon threads
    app_ctx = app.app_context() if app is not None else None

    logger.info("[spot_scheduler] Starting background spot snapshot scheduler.")
    _schedule_next(app_ctx)


def cancel_scheduler():
    """Cancel the pending timer (used in tests and for clean shutdown)."""
    global _timer, _started
    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
        _started = False
