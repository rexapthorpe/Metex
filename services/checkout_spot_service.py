"""
Checkout Spot Service

Provides a bounded, concurrency-safe spot price for use ONLY during checkout
pricing.  Checkout code MUST call get_spot_for_checkout() (or the convenience
wrapper get_spot_map_for_checkout()) instead of calling get_current_spot_prices()
or any external provider directly.

Guarantees (Policy A):
  1. Bounded staleness: uses DB snapshot if fresh (age <= max_age_seconds).
     max_age_seconds is read from system_settings at call time so admins can
     adjust it without a restart.
  2. Single-flight refresh: at most ONE concurrent external refresh is triggered
     even when many checkout requests arrive simultaneously with stale data.
     Uses the same DB run-lock as spot_snapshot_service so the guarantee holds
     across multiple Gunicorn workers/threads.
  3. Block on failure: if the snapshot remains stale after the refresh attempt
     (or no snapshot exists at all), SpotUnavailableError is raised.  Callers
     MUST block checkout — stale fallback pricing is not permitted.
  4. Auditability: on success, returns {price_usd, as_of, source, was_refreshed,
     stale_fallback} so callers can store the exact spot used on the order record.
     stale_fallback is always False on a successful return.

Algorithm inside get_spot_for_checkout(metal):
  1. Read latest snapshot for metal from spot_price_snapshots.
  2. If age <= max_age → return immediately (0 external API calls).
  3. If stale:
     a. Attempt to acquire the DB run-lock (same key as spot_snapshot_service).
     b. If acquired: call run_snapshot(force=True, use_lock=False), release lock,
        re-read snapshot.
     c. If NOT acquired (another request is refreshing): poll DB for a fresh
        snapshot for up to spot_refresh_timeout_seconds.
  4. Re-read snapshot. If still stale or absent → raise SpotUnavailableError.

Never import get_current_spot_prices / fetch_spot_prices_from_api from this
module.  The only external-API pathway is via run_snapshot().
"""

import time
import logging
from datetime import datetime

import database as _db_module

logger = logging.getLogger(__name__)


class SpotExpiredError(RuntimeError):
    """
    Raised by check_spot_freshness() when the DB snapshot is stale but NO
    refresh has been attempted.  This is the "modal-first" error: the frontend
    must show a Recalculate prompt rather than silently refreshing and
    proceeding.  Distinct from SpotUnavailableError, which means a refresh WAS
    attempted and failed.

    Attributes:
        metal            – lower-case metal name that is stale
        latest_as_of     – ISO timestamp of the stale snapshot (or None)
        max_age_seconds  – configured max-age SLA at call time
        USER_MESSAGE     – safe, user-facing message for JSON responses
    """

    USER_MESSAGE = (
        "Spot prices have expired. Please recalculate to see the latest prices."
    )

    def __init__(self, metal: str, latest_as_of=None, max_age_seconds=None):
        super().__init__(
            f"Spot expired for '{metal}' (age exceeds {max_age_seconds}s SLA)"
        )
        self.metal = metal
        self.latest_as_of = latest_as_of
        self.max_age_seconds = max_age_seconds


class SpotUnavailableError(RuntimeError):
    """
    Raised by get_spot_for_checkout() when the spot price cannot be refreshed
    within the configured SLA (snapshot remains stale after refresh attempt,
    or no snapshot exists at all after refresh).

    Policy A: checkout MUST be blocked; callers must NOT proceed with stale data.

    Attributes:
        metal                – the metal name that failed
        reason               – internal diagnostic string
        latest_as_of         – ISO timestamp of the best available snapshot (or None)
        max_age_seconds      – the configured max-age SLA
        refresh_timeout_seconds – the configured refresh timeout
        USER_MESSAGE         – safe, user-facing message for flash() / JSON responses
    """

    USER_MESSAGE = (
        "Live pricing temporarily unavailable. Please try again in a moment."
    )

    def __init__(self, metal: str, reason: str,
                 latest_as_of=None, max_age_seconds=None, refresh_timeout_seconds=None):
        super().__init__(f"Spot unavailable for '{metal}': {reason}")
        self.metal = metal
        self.reason = reason
        self.latest_as_of = latest_as_of
        self.max_age_seconds = max_age_seconds
        self.refresh_timeout_seconds = refresh_timeout_seconds


def _get_conn():
    return _db_module.get_db_connection()


def _get_latest_snapshot(conn, metal: str):
    """Return (price_usd, as_of, source) for the newest snapshot, or (None, None, None)."""
    row = conn.execute(
        "SELECT price_usd, as_of, source FROM spot_price_snapshots "
        "WHERE metal = ? ORDER BY as_of DESC LIMIT 1",
        (metal,),
    ).fetchone()
    if row is None:
        return None, None, None
    return float(row["price_usd"]), row["as_of"], row["source"]


def _snapshot_age_seconds(as_of_str: str) -> float:
    """Return age of a snapshot in seconds, or infinity on parse failure."""
    if not as_of_str:
        return float("inf")
    try:
        # Handle both "YYYY-MM-DD HH:MM:SS" and "YYYY-MM-DDTHH:MM:SS" formats
        as_of = datetime.fromisoformat(str(as_of_str).replace(" ", "T"))
        return (datetime.now() - as_of).total_seconds()
    except Exception:
        return float("inf")


def _get_max_age() -> int:
    from services.system_settings_service import get_checkout_spot_max_age
    return get_checkout_spot_max_age()


def _get_refresh_timeout() -> int:
    from services.system_settings_service import get_checkout_spot_refresh_timeout
    return get_checkout_spot_refresh_timeout()


def get_spot_for_checkout(metal: str) -> dict:
    """
    Return a spot price for the given metal guaranteed to satisfy the configured
    max-age SLA.  Raises SpotUnavailableError (Policy A) if the SLA cannot be met.

    Args:
        metal: Lower-case metal name e.g. 'gold', 'silver', 'platinum', 'palladium'.

    Returns:
        dict with keys:
            price_usd      – float, spot price per troy oz
            as_of          – ISO-8601 string, when this snapshot was recorded
            source         – 'metalpriceapi' | 'metals_live' | ...
            was_refreshed  – bool, True if a live refresh was triggered this call
            stale_fallback – bool, always False (stale data raises SpotUnavailableError)

    Raises:
        SpotUnavailableError: if no fresh snapshot could be obtained within the SLA.
    """
    metal = metal.lower()
    max_age = _get_max_age()
    refresh_timeout = _get_refresh_timeout()

    conn = _get_conn()
    try:
        price_usd, as_of, source = _get_latest_snapshot(conn, metal)

        # Step 2: fresh snapshot → return immediately (no external API call)
        if price_usd is not None and _snapshot_age_seconds(as_of) <= max_age:
            return {
                "price_usd": price_usd,
                "as_of": as_of,
                "source": source,
                "was_refreshed": False,
                "stale_fallback": False,
            }

        age_secs = _snapshot_age_seconds(as_of) if as_of else None
        logger.info(
            "[checkout_spot] Snapshot for '%s' stale (age=%s s, max=%d s) — attempting refresh.",
            metal,
            f"{age_secs:.0f}" if age_secs is not None else "N/A",
            max_age,
        )

        # Step 3a: try to acquire the DB run-lock
        from services.spot_snapshot_service import (
            _try_acquire_run_lock,
            _release_run_lock,
            run_snapshot,
        )

        lock_acquired = _try_acquire_run_lock(conn)
        was_refreshed = False

        if lock_acquired:
            # We hold the lock — trigger a refresh (skip inner lock to avoid deadlock)
            try:
                result = run_snapshot(use_lock=False, verbose=False, force=True)
                was_refreshed = result.get("inserted", 0) > 0
                logger.info(
                    "[checkout_spot] Refresh complete: inserted=%s error=%s",
                    result.get("inserted"),
                    result.get("error"),
                )
            except Exception as exc:
                logger.warning("[checkout_spot] Refresh raised: %s", exc)
            finally:
                _release_run_lock(conn)

        else:
            # Step 3c: another worker is refreshing — poll for a fresh snapshot
            logger.info(
                "[checkout_spot] Lock held by another process; polling up to %ds.",
                refresh_timeout,
            )
            deadline = time.monotonic() + refresh_timeout
            poll_conn = _get_conn()
            try:
                while time.monotonic() < deadline:
                    time.sleep(0.25)
                    new_price, new_as_of, new_source = _get_latest_snapshot(poll_conn, metal)
                    if new_price is not None and _snapshot_age_seconds(new_as_of) <= max_age:
                        return {
                            "price_usd": new_price,
                            "as_of": new_as_of,
                            "source": new_source,
                            "was_refreshed": False,
                            "stale_fallback": False,
                        }
            finally:
                poll_conn.close()

        # Step 4: re-read after refresh attempt
        price_usd, as_of, source = _get_latest_snapshot(conn, metal)

        if price_usd is None:
            raise SpotUnavailableError(
                metal=metal,
                reason="no snapshot available after refresh attempt",
                max_age_seconds=max_age,
                refresh_timeout_seconds=refresh_timeout,
            )

        age_after = _snapshot_age_seconds(as_of)
        if age_after > max_age:
            logger.warning(
                "[checkout_spot] Snapshot for '%s' still stale after refresh (age=%.0fs, max=%ds). "
                "Blocking checkout (Policy A).",
                metal, age_after, max_age,
            )
            raise SpotUnavailableError(
                metal=metal,
                reason=f"snapshot still stale after refresh attempt (age={age_after:.0f}s, max={max_age}s)",
                latest_as_of=as_of,
                max_age_seconds=max_age,
                refresh_timeout_seconds=refresh_timeout,
            )

        return {
            "price_usd": price_usd,
            "as_of": as_of,
            "source": source,
            "was_refreshed": was_refreshed,
            "stale_fallback": False,
        }

    finally:
        conn.close()


def get_spot_map_for_checkout(metals) -> dict:
    """
    Convenience wrapper: call get_spot_for_checkout() for each metal.

    Args:
        metals: iterable of metal name strings (case-insensitive).

    Returns:
        {metal_lower: spot_info_dict}  — all metals have fresh prices.

    Raises:
        SpotUnavailableError: if any metal cannot be priced within the SLA.
            Callers must block checkout; no partial results are returned.
    """
    result = {}
    for metal in set(m.lower() for m in metals if m):
        result[metal] = get_spot_for_checkout(metal)  # SpotUnavailableError propagates
    return result


# ---------------------------------------------------------------------------
# Modal-first freshness checks (no auto-refresh)
# ---------------------------------------------------------------------------

def check_spot_freshness(metal: str) -> dict:
    """
    Check whether the spot snapshot for *metal* satisfies the configured SLA
    WITHOUT triggering any external refresh.

    Use this at finalize time (modal-first flow): if stale, raise
    SpotExpiredError so the frontend can show the Recalculate modal.
    Call get_spot_for_checkout() in the /recalculate-spot endpoint instead
    (which DOES refresh).

    Returns:
        Same dict format as get_spot_for_checkout() on success.

    Raises:
        SpotExpiredError: snapshot is stale or absent (no refresh attempted).
    """
    metal = metal.lower()
    max_age = _get_max_age()
    conn = _get_conn()
    try:
        price_usd, as_of, source = _get_latest_snapshot(conn, metal)
        if price_usd is not None and _snapshot_age_seconds(as_of) <= max_age:
            return {
                "price_usd": price_usd,
                "as_of": as_of,
                "source": source,
                "was_refreshed": False,
                "stale_fallback": False,
            }
        raise SpotExpiredError(
            metal=metal,
            latest_as_of=as_of,
            max_age_seconds=max_age,
        )
    finally:
        conn.close()


def check_spot_map_freshness(metals) -> dict:
    """
    Convenience wrapper: call check_spot_freshness() for each metal.
    SpotExpiredError propagates if any metal's snapshot is stale or absent.
    """
    result = {}
    for metal in set(m.lower() for m in metals if m):
        result[metal] = check_spot_freshness(metal)  # SpotExpiredError propagates
    return result
