"""
Reference Price Service

Computes the canonical "Reference Price" P(t) for a bucket at any point in time:

  P(t) = (BestAsk(t) + BestBid(t)) / 2   -- when both sides exist
       = LastClearedPrice(t)              -- else, last executed trade
       = BestAsk(t)  |  BestBid(t)       -- fallback to whichever side exists

BestAsk(t)  — minimum effective price among active listings, using the spot
              price snapshot at or before t for variable-spot listings.
BestBid(t)  — maximum active bid at or before t.
LastClearedPrice(t) — most recent order_items.price_each at or before t.

Approximations (documented):
- Listing activity history is not tracked. We use the current set of active
  listings throughout the requested range. Prices that changed due to listing
  create/edit/delete events are captured in bucket_price_history events, but
  exact listing start/end times are not available.
- Bid deactivation timestamps are not stored. We treat currently-active bids
  as having been active since their creation date.

The chart endpoint calls get_reference_price_history() and never touches the
external spot API directly.
"""

import database as _db_module
from datetime import datetime, timedelta
from services.pricing_service import get_effective_price


def _get_conn():
    return _db_module.get_db_connection()


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def get_spot_at_time(conn, metal, as_of):
    """
    Return the most recent spot price (USD/oz) for `metal` at or before `as_of`.

    Reads from spot_price_snapshots — never calls the external API.

    Args:
        conn:  open DB connection
        metal: metal name ('gold', 'silver', etc.)
        as_of: datetime or ISO-8601 string

    Returns:
        float or None
    """
    row = conn.execute(
        """
        SELECT price_usd FROM spot_price_snapshots
        WHERE metal = ? AND as_of <= ?
        ORDER BY as_of DESC
        LIMIT 1
        """,
        (metal, as_of)
    ).fetchone()
    return row['price_usd'] if row else None


def get_best_ask_at_time(conn, bucket_id, listings, as_of):
    """
    Compute the minimum effective listing price for a bucket at `as_of`.

    For variable-spot listings the spot price from spot_price_snapshots is
    used (i.e. the most recent snapshot at or before as_of). Static listings
    use their fixed price_per_coin.

    Args:
        conn:      open DB connection
        bucket_id: bucket ID (used only for fallback logging)
        listings:  list of listing dicts (from the current active set)
        as_of:     datetime or ISO-8601 string for historical spot lookup

    Returns:
        float or None
    """
    min_price = None

    for listing in listings:
        listing_dict = dict(listing)
        pricing_mode = listing_dict.get('pricing_mode', 'static')

        if pricing_mode == 'premium_to_spot':
            metal = (listing_dict.get('pricing_metal') or listing_dict.get('metal', 'gold')).lower()
            spot = get_spot_at_time(conn, metal, as_of)
            if spot is not None:
                effective = get_effective_price(listing_dict, spot_prices={metal: spot})
            else:
                # No snapshot available — fall back to static floor or price_per_coin
                effective = listing_dict.get('floor_price') or listing_dict.get('price_per_coin')
        else:
            effective = get_effective_price(listing_dict)

        if effective is not None and (min_price is None or effective < min_price):
            min_price = effective

    return min_price


def get_best_bid_at_time(conn, bucket_id, as_of):
    """
    Return the highest bid price for a bucket from bids created at or before `as_of`.

    Approximation: uses bids that are currently active (active=1) but
    were created before the target time. Bids deactivated since their
    creation will be incorrectly excluded; no deactivation timestamp exists.

    Args:
        conn:      open DB connection
        bucket_id: bucket ID
        as_of:     datetime or ISO-8601 string

    Returns:
        float or None
    """
    row = conn.execute(
        """
        SELECT MAX(b.price_per_coin) AS max_bid
        FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE c.bucket_id = ?
          AND b.active = 1
          AND b.created_at <= ?
        """,
        (bucket_id, as_of)
    ).fetchone()
    if row and row['max_bid'] is not None:
        return float(row['max_bid'])
    return None


def get_last_cleared_price_at_time(conn, bucket_id, as_of):
    """
    Return the price of the most recently executed trade for this bucket
    at or before `as_of`.

    Uses order_items.price_each joined through listings → categories.

    Args:
        conn:      open DB connection
        bucket_id: bucket ID
        as_of:     datetime or ISO-8601 string

    Returns:
        float or None
    """
    row = conn.execute(
        """
        SELECT oi.price_each
        FROM order_items oi
        JOIN orders o     ON oi.order_id  = o.id
        JOIN listings l   ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ?
          AND o.created_at <= ?
        ORDER BY o.created_at DESC
        LIMIT 1
        """,
        (bucket_id, as_of)
    ).fetchone()
    return float(row['price_each']) if row else None


def compute_reference_price(best_ask, best_bid, last_cleared):
    """
    Apply the reference price rules.

    Priority:
      1. Both sides → midpoint
      2. Last cleared trade (no active market)
      3. Whichever side exists
      4. None (no data)
    """
    if best_ask is not None and best_bid is not None:
        return (best_ask + best_bid) / 2.0
    if last_cleared is not None:
        return last_cleared
    if best_ask is not None:
        return best_ask
    if best_bid is not None:
        return best_bid
    return None


# ---------------------------------------------------------------------------
# Main time-series builder
# ---------------------------------------------------------------------------

def get_reference_price_history(bucket_id, days=30):
    """
    Build and return the Reference Price time series for a bucket.

    Returns a dict with:
      primary_series      — [{'t': ISO-8601 str, 'price': float}] chronological
      latest_spot_as_of   — ISO-8601 str or None (most recent spot snapshot used)
      latest_bid_as_of    — ISO-8601 str or None (most recent bid event)
      latest_clear_as_of  — ISO-8601 str or None (most recent trade)

    Args:
        bucket_id: bucket ID
        days:      number of days of history to return (e.g. 30 for 1m)
    """
    conn = _get_conn()

    now   = datetime.now()
    start = now - timedelta(days=days)
    start_iso = start.isoformat()
    now_iso   = now.isoformat()

    # ------------------------------------------------------------------
    # 1. Load currently-active listings for the bucket
    # ------------------------------------------------------------------
    listings = conn.execute(
        """
        SELECT l.price_per_coin, l.pricing_mode,
               l.spot_premium, l.floor_price, l.pricing_metal,
               c.metal, c.weight, c.product_type
        FROM listings l
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ?
          AND l.active = 1
          AND l.quantity > 0
        """,
        (bucket_id,)
    ).fetchall()

    has_variable = any(
        dict(l).get('pricing_mode') == 'premium_to_spot'
        for l in listings
    )

    # ------------------------------------------------------------------
    # 2. Collect event timestamps that define state changes
    # ------------------------------------------------------------------
    event_times = set()

    # a) Spot price snapshots (only for variable-spot buckets — they change BestAsk)
    latest_spot_as_of = None
    if has_variable:
        # Determine which metals are needed
        metals = set()
        for l in listings:
            ld = dict(l)
            if ld.get('pricing_mode') == 'premium_to_spot':
                m = (ld.get('pricing_metal') or ld.get('metal', 'gold')).lower()
                metals.add(m)

        for metal in metals:
            rows = conn.execute(
                """
                SELECT as_of FROM spot_price_snapshots
                WHERE metal = ? AND as_of >= ?
                ORDER BY as_of ASC
                """,
                (metal, start_iso)
            ).fetchall()
            for row in rows:
                as_of_val = row['as_of']
                event_times.add(as_of_val if isinstance(as_of_val, str) else as_of_val.isoformat())

        # Track the most recent spot snapshot (for polling metadata)
        row = conn.execute(
            """
            SELECT MAX(as_of) AS latest FROM spot_price_snapshots
            WHERE metal IN ({})
            """.format(','.join('?' * len(metals))),
            list(metals)
        ).fetchone() if metals else None
        if row and row['latest']:
            latest_spot_as_of = row['latest'] if isinstance(row['latest'], str) else row['latest'].isoformat()

    # b) Bid creation events for this bucket
    latest_bid_as_of = None
    bid_rows = conn.execute(
        """
        SELECT b.created_at FROM bids b
        JOIN categories c ON b.category_id = c.id
        WHERE c.bucket_id = ? AND b.created_at >= ?
        ORDER BY b.created_at ASC
        """,
        (bucket_id, start_iso)
    ).fetchall()
    for row in bid_rows:
        val = row['created_at']
        event_times.add(val if isinstance(val, str) else val.isoformat())
    if bid_rows:
        val = bid_rows[-1]['created_at']
        latest_bid_as_of = val if isinstance(val, str) else val.isoformat()

    # c) Executed trade timestamps
    latest_clear_as_of = None
    trade_rows = conn.execute(
        """
        SELECT o.created_at FROM order_items oi
        JOIN orders o     ON oi.order_id  = o.id
        JOIN listings l   ON oi.listing_id = l.id
        JOIN categories c ON l.category_id = c.id
        WHERE c.bucket_id = ? AND o.created_at >= ?
        GROUP BY o.id
        ORDER BY o.created_at ASC
        """,
        (bucket_id, start_iso)
    ).fetchall()
    for row in trade_rows:
        val = row['created_at']
        event_times.add(val if isinstance(val, str) else val.isoformat())
    if trade_rows:
        val = trade_rows[-1]['created_at']
        latest_clear_as_of = val if isinstance(val, str) else val.isoformat()

    # d) Existing bucket_price_history events (captures listing create/edit/delete)
    ph_rows = conn.execute(
        """
        SELECT timestamp FROM bucket_price_history
        WHERE bucket_id = ? AND timestamp >= ?
        ORDER BY timestamp ASC
        """,
        (bucket_id, start_iso)
    ).fetchall()
    for row in ph_rows:
        val = row['timestamp']
        event_times.add(val if isinstance(val, str) else val.isoformat())

    # e) Always include "now" so the series extends to the present
    event_times.add(now_iso)

    # ------------------------------------------------------------------
    # 3. If no events at all, seed a synthetic start point
    # ------------------------------------------------------------------
    if len(event_times) <= 1:
        # Only "now" — compute once and return a single point
        event_times.add(start_iso)

    sorted_times = sorted(event_times)

    # ------------------------------------------------------------------
    # 4. Build series: compute P(t) at each event timestamp
    # ------------------------------------------------------------------
    listings_list = [dict(l) for l in listings]

    series = []
    for t_str in sorted_times:
        best_ask    = get_best_ask_at_time(conn, bucket_id, listings_list, t_str)
        best_bid    = get_best_bid_at_time(conn, bucket_id, t_str)
        last_cleared = get_last_cleared_price_at_time(conn, bucket_id, t_str)

        ref = compute_reference_price(best_ask, best_bid, last_cleared)
        if ref is not None:
            series.append({'t': t_str, 'price': round(ref, 4)})

    conn.close()

    return {
        'primary_series':    series,
        'latest_spot_as_of': latest_spot_as_of,
        'latest_bid_as_of':  latest_bid_as_of,
        'latest_clear_as_of': latest_clear_as_of,
    }
