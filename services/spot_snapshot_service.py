"""
Spot Snapshot Service

Core logic for writing rows into spot_price_snapshots.
Called by:
  - services/spot_scheduler.py  (background timer, force=True)
  - scripts/update_spot_prices.py (cron / manual, force=False)

Threshold guard (force=False only):
  Skip insert if |new - old| / old <= 0.0005 (0.05%) AND
  last snapshot was less than MAX_QUIET_MINS minutes ago.
  This prevents inserting identical rows on rapid manual/cron calls.

Scheduler mode (force=True):
  Always insert a row on every tick so that latest_spot_as_of
  advances at the admin-configured cadence even when spot prices
  are unchanged.  Same price_usd is acceptable — timestamps must advance.

Stale-primary fallback:
  If the primary source (metalpriceapi.com) has returned the same price for
  PRIMARY_STALE_MINS minutes (indicating a free-tier hourly/daily cache), the
  snapshot job automatically tries a secondary source (api.metals.live — free,
  no API key required).  The secondary is called at most once per run_snapshot
  invocation and only when staleness is detected; it is never called during
  chart rendering.  Each snapshot row records its source in the `source` column.
"""

from datetime import datetime, timedelta
import logging
import database as _db_module

logger = logging.getLogger(__name__)

THRESHOLD_PCT  = 0.0005   # 0.05% minimum price change
MAX_QUIET_MINS = 20       # Always insert if no snapshot in this many minutes

# Secondary-source staleness detection
# Tune this to control how long primary must be constant before secondary is tried.
PRIMARY_STALE_MINS = 15   # configurable: minutes of constant primary price → stale

# Secondary free spot-price source (no API key required)
_SECONDARY_URL = "https://api.metals.live/v1/spot"

# Scheduler-level mutex key stored in system_settings
_LOCK_KEY = "snapshot_running_lock"
_LOCK_TTL_SECS = 45  # lock expires after this many seconds


def _get_conn():
    return _db_module.get_db_connection()


def _get_last_snapshot(conn, metal):
    """Return (price_usd, as_of_str) of the most recent snapshot for a metal, or (None, None)."""
    row = conn.execute(
        "SELECT price_usd, as_of FROM spot_price_snapshots "
        "WHERE metal = ? ORDER BY as_of DESC LIMIT 1",
        (metal,)
    ).fetchone()
    if row is None:
        return None, None
    return row["price_usd"], row["as_of"]


def _primary_is_stale(conn, metal, current_primary_price):
    """
    Return True when the primary source (metalpriceapi) appears to be serving
    stale/cached data for this metal.

    Stale is defined as:
      - At least 2 snapshots with source='metalpriceapi' exist within the last
        PRIMARY_STALE_MINS minutes, AND
      - ALL of those snapshots have the same price_usd, AND
      - That price matches current_primary_price (i.e. the provider hasn't updated).

    The last condition ensures that if the provider does eventually return a new
    price the stale flag resets immediately and the primary source is used again.
    """
    cutoff = (datetime.now() - timedelta(minutes=PRIMARY_STALE_MINS)).isoformat()
    rows = conn.execute(
        "SELECT price_usd FROM spot_price_snapshots "
        "WHERE metal=? AND source='metalpriceapi' AND as_of>=?",
        (metal, cutoff)
    ).fetchall()

    if len(rows) < 2:
        return False  # not enough history to judge

    stored_prices = [float(r["price_usd"]) for r in rows]
    reference = stored_prices[0]

    all_same = all(abs(p - reference) < 0.01 for p in stored_prices)
    primary_unchanged = abs(current_primary_price - reference) < 0.01

    return all_same and primary_unchanged


def _fetch_secondary_prices():
    """
    Fetch spot prices from secondary free sources (no API key required).
    Tries api.metals.live first, falls back to Yahoo Finance futures.

    Returns {metal: price_usd} or None on any failure.
    Only called by run_snapshot() when primary is stale; never called during
    chart rendering.
    """
    from services.spot_price_service import fetch_spot_prices_from_yahoo
    import requests as _req
    _SUPPORTED = {"gold", "silver", "platinum", "palladium"}

    # Try api.metals.live first
    try:
        resp = _req.get(_SECONDARY_URL, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            prices = {}
            if isinstance(data, list):
                for item in data:
                    for k, v in item.items():
                        if k.lower() in _SUPPORTED and isinstance(v, (int, float)):
                            prices[k.lower()] = float(v)
            elif isinstance(data, dict):
                for k, v in data.items():
                    if k.lower() in _SUPPORTED and isinstance(v, (int, float)):
                        prices[k.lower()] = float(v)
            if prices:
                return prices
        else:
            logger.warning(
                "[spot_snapshot] metals.live returned HTTP %s", resp.status_code
            )
    except Exception as exc:
        logger.warning("[spot_snapshot] metals.live fetch failed: %s", exc)

    # Fall back to Yahoo Finance
    logger.info("[spot_snapshot] Trying Yahoo Finance as secondary fallback...")
    try:
        prices = fetch_spot_prices_from_yahoo()
        if prices:
            logger.info("[spot_snapshot] Yahoo Finance returned prices for: %s", sorted(prices.keys()))
            return prices
    except Exception as exc:
        logger.warning("[spot_snapshot] Yahoo Finance fetch failed: %s", exc)

    return None


def _should_insert(last_price, last_as_of, new_price):
    """Return True if a new snapshot row should be inserted."""
    if last_price is None:
        return True

    try:
        if isinstance(last_as_of, str):
            last_time = datetime.fromisoformat(last_as_of)
        else:
            last_time = last_as_of
        age_mins = (datetime.now() - last_time).total_seconds() / 60
    except Exception:
        return True  # can't parse — insert to be safe

    if age_mins >= MAX_QUIET_MINS:
        return True

    if last_price > 0:
        change_pct = abs(new_price - last_price) / last_price
        return change_pct > THRESHOLD_PCT

    return True


def _try_acquire_run_lock(conn) -> bool:
    """
    Attempt to acquire a short-lived run-lock to prevent concurrent snapshot
    runs across multiple processes/workers (e.g. Gunicorn multi-worker).

    Returns True if lock acquired, False if another process is already running.
    Uses SQLite's atomic UPSERT; safe because SQLite is single-writer.
    """
    now = datetime.now()
    cutoff = (now - timedelta(seconds=_LOCK_TTL_SECS)).isoformat()

    # Check if a fresh lock exists
    row = conn.execute(
        "SELECT value FROM system_settings WHERE key = ?", (_LOCK_KEY,)
    ).fetchone()

    if row:
        try:
            lock_time = datetime.fromisoformat(row["value"])
            if (now - lock_time).total_seconds() < _LOCK_TTL_SECS:
                return False  # fresh lock held by another process
        except Exception:
            pass  # malformed timestamp — overwrite

    # Acquire the lock
    conn.execute(
        """
        INSERT INTO system_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (_LOCK_KEY, now.isoformat(), now.isoformat()),
    )
    conn.commit()
    return True


def _release_run_lock(conn) -> None:
    """Release the run-lock by clearing it."""
    conn.execute("DELETE FROM system_settings WHERE key = ?", (_LOCK_KEY,))
    conn.commit()


def _trigger_bid_rematch_sync(metals):
    """
    After a snapshot commit, synchronously re-evaluate open bids against the
    updated spot prices.  Uses a fresh DB connection (the snapshot conn has
    already committed so its write lock is released).

    Errors are caught and logged — snapshot runs must never be blocked.
    """
    try:
        from core.blueprints.bids.auto_match import run_bid_rematch_after_spot_update
        run_bid_rematch_after_spot_update(metals=list(metals) if metals else None)
    except Exception as exc:
        logger.error("[spot_snapshot] Bid re-match trigger failed: %s", exc)


def run_snapshot(use_lock=True, verbose=False, force=False):
    """
    Fetch current spot prices and write new rows to spot_price_snapshots.

    Args:
        use_lock:  When True, acquires the DB run-lock to prevent concurrent runs.
        verbose:   When True, prints progress to stdout.
        force:     When True, always insert a row regardless of price change or quiet
                   window.  The scheduler passes force=True so that latest_spot_as_of
                   advances on every tick at the admin-configured cadence.
                   The cron script uses force=False (default) to retain dedup behaviour.

    Returns:
        dict with keys: inserted (int), skipped (int), locked_out (bool), error (str|None)
    """
    from services.spot_price_service import get_current_spot_prices

    conn = _get_conn()
    now = datetime.now()

    try:
        if use_lock:
            if not _try_acquire_run_lock(conn):
                if verbose:
                    print("[spot_snapshot] Another process holds the lock — skipping.")
                return {"inserted": 0, "skipped": 0, "locked_out": True, "error": None}

        if verbose:
            print(f"[spot_snapshot] Starting at {now.isoformat()}")

        spot_prices = get_current_spot_prices(force_refresh=True)

        if not spot_prices:
            if verbose:
                print("[spot_snapshot] No spot prices available — aborting.")
            return {"inserted": 0, "skipped": 0, "locked_out": False, "error": "no_prices"}

        # ------------------------------------------------------------------
        # Stale-primary detection: identify metals whose primary source has
        # been returning the same price for >= PRIMARY_STALE_MINS minutes.
        # ------------------------------------------------------------------
        stale_metals = {
            m for m, price in spot_prices.items()
            if _primary_is_stale(conn, m, price)
        }

        # Try secondary source once if any metals are stale
        secondary_prices = None
        if stale_metals:
            logger.info(
                "[spot_snapshot] Primary stale for %s — trying secondary source.",
                sorted(stale_metals),
            )
            secondary_prices = _fetch_secondary_prices()
            if secondary_prices:
                logger.info(
                    "[spot_snapshot] Secondary source returned prices for: %s",
                    sorted(secondary_prices.keys()),
                )
            else:
                logger.warning(
                    "[spot_snapshot] Secondary source unavailable; "
                    "keeping primary (stale) price."
                )

        # ------------------------------------------------------------------
        # Insert snapshots
        # ------------------------------------------------------------------
        inserted = 0
        skipped = 0

        for metal, primary_price in spot_prices.items():
            # Use secondary when: primary is stale AND secondary has this metal
            if metal in stale_metals and secondary_prices and metal in secondary_prices:
                use_price = secondary_prices[metal]
                use_source = "metals_live"
            else:
                use_price = primary_price
                use_source = "metalpriceapi"

            last_price, last_as_of = _get_last_snapshot(conn, metal)

            if force or _should_insert(last_price, last_as_of, use_price):
                conn.execute(
                    "INSERT INTO spot_price_snapshots (metal, price_usd, as_of, source) "
                    "VALUES (?, ?, ?, ?)",
                    (metal, use_price, now.isoformat(), use_source),
                )
                if verbose:
                    delta = f" (Δ {use_price - last_price:+.4f})" if last_price else " (first)"
                    src_tag = f" [{use_source}]" if use_source != "metalpriceapi" else ""
                    print(f"  ✓ {metal}: ${use_price:.4f}{delta}{src_tag}")
                inserted += 1
            else:
                if verbose:
                    print(f"  - {metal}: ${use_price:.4f} — unchanged, skipped")
                skipped += 1

        conn.commit()

        # After committing new snapshots, re-evaluate open bids that may now
        # be marketable at the updated spot price.
        if inserted > 0:
            _trigger_bid_rematch_sync(spot_prices.keys())

        if verbose:
            print(f"[spot_snapshot] Done — {inserted} inserted, {skipped} skipped.")

        return {"inserted": inserted, "skipped": skipped, "locked_out": False, "error": None}

    except Exception as exc:
        if verbose:
            print(f"[spot_snapshot] Error: {exc}")
        return {"inserted": 0, "skipped": 0, "locked_out": False, "error": str(exc)}

    finally:
        if use_lock:
            try:
                _release_run_lock(conn)
            except Exception:
                pass
        conn.close()
