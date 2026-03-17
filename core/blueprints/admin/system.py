"""
Admin System Settings Routes

Provides API endpoints for reading and writing system-level settings,
including the spot snapshot interval.

Routes:
  GET  /admin/api/system-settings/spot-interval  — return current value + bounds
  POST /admin/api/system-settings/spot-interval  — update value
"""

from flask import jsonify, request
from utils.auth_utils import admin_required
from . import admin_bp


@admin_bp.route("/api/system-settings/spot-interval", methods=["GET"])
@admin_required
def get_spot_interval():
    """Return current spot snapshot interval and allowed bounds."""
    from services.system_settings_service import (
        get_spot_snapshot_interval,
        SPOT_SNAPSHOT_INTERVAL_MIN,
        SPOT_SNAPSHOT_INTERVAL_MAX,
        SPOT_SNAPSHOT_INTERVAL_DEFAULT,
    )
    return jsonify({
        "success": True,
        "interval_minutes": get_spot_snapshot_interval(),
        "min_minutes": SPOT_SNAPSHOT_INTERVAL_MIN,
        "max_minutes": SPOT_SNAPSHOT_INTERVAL_MAX,
        "default_minutes": SPOT_SNAPSHOT_INTERVAL_DEFAULT,
    })


@admin_bp.route("/api/system-settings/spot-interval", methods=["POST"])
@admin_required
def set_spot_interval():
    """Update the spot snapshot interval. Clamps to [MIN, MAX]."""
    from services.system_settings_service import (
        set_spot_snapshot_interval,
        SPOT_SNAPSHOT_INTERVAL_MIN,
        SPOT_SNAPSHOT_INTERVAL_MAX,
    )

    data = request.get_json(silent=True) or {}
    raw = data.get("interval_minutes")

    if raw is None:
        return jsonify({"success": False, "message": "interval_minutes is required"}), 400

    try:
        raw = int(raw)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "interval_minutes must be an integer"}), 400

    saved = set_spot_snapshot_interval(raw)

    # Optionally trigger an immediate snapshot run (fire-and-forget thread)
    # so the admin can see the effect quickly.
    _trigger_immediate_snapshot_async()

    return jsonify({
        "success": True,
        "interval_minutes": saved,
        "min_minutes": SPOT_SNAPSHOT_INTERVAL_MIN,
        "max_minutes": SPOT_SNAPSHOT_INTERVAL_MAX,
        "message": f"Updated spot snapshot interval to {saved} minute{'s' if saved != 1 else ''}.",
    })


@admin_bp.route("/api/system-settings/checkout-spot", methods=["GET"])
@admin_required
def get_checkout_spot_settings():
    """Return current checkout spot staleness settings + allowed bounds."""
    from services.system_settings_service import (
        get_checkout_spot_max_age,
        get_checkout_spot_refresh_timeout,
        CHECKOUT_SPOT_MAX_AGE_MIN,
        CHECKOUT_SPOT_MAX_AGE_MAX,
        CHECKOUT_SPOT_MAX_AGE_DEFAULT,
        CHECKOUT_SPOT_REFRESH_TIMEOUT_MIN,
        CHECKOUT_SPOT_REFRESH_TIMEOUT_MAX,
        CHECKOUT_SPOT_REFRESH_TIMEOUT_DEFAULT,
    )
    return jsonify({
        "success": True,
        "max_age_seconds": get_checkout_spot_max_age(),
        "max_age_min": CHECKOUT_SPOT_MAX_AGE_MIN,
        "max_age_max": CHECKOUT_SPOT_MAX_AGE_MAX,
        "max_age_default": CHECKOUT_SPOT_MAX_AGE_DEFAULT,
        "refresh_timeout_seconds": get_checkout_spot_refresh_timeout(),
        "refresh_timeout_min": CHECKOUT_SPOT_REFRESH_TIMEOUT_MIN,
        "refresh_timeout_max": CHECKOUT_SPOT_REFRESH_TIMEOUT_MAX,
        "refresh_timeout_default": CHECKOUT_SPOT_REFRESH_TIMEOUT_DEFAULT,
    })


@admin_bp.route("/api/system-settings/checkout-spot", methods=["POST"])
@admin_required
def set_checkout_spot_settings():
    """Update checkout spot staleness settings."""
    from services.system_settings_service import (
        set_checkout_spot_max_age,
        set_checkout_spot_refresh_timeout,
        CHECKOUT_SPOT_MAX_AGE_MIN,
        CHECKOUT_SPOT_MAX_AGE_MAX,
        CHECKOUT_SPOT_REFRESH_TIMEOUT_MIN,
        CHECKOUT_SPOT_REFRESH_TIMEOUT_MAX,
    )

    data = request.get_json(silent=True) or {}
    errors = []
    saved = {}

    if "max_age_seconds" in data:
        try:
            saved["max_age_seconds"] = set_checkout_spot_max_age(int(data["max_age_seconds"]))
        except (ValueError, TypeError):
            errors.append("max_age_seconds must be an integer")

    if "refresh_timeout_seconds" in data:
        try:
            saved["refresh_timeout_seconds"] = set_checkout_spot_refresh_timeout(
                int(data["refresh_timeout_seconds"])
            )
        except (ValueError, TypeError):
            errors.append("refresh_timeout_seconds must be an integer")

    if errors:
        return jsonify({"success": False, "message": "; ".join(errors)}), 400

    if not saved:
        return jsonify({"success": False, "message": "No fields provided"}), 400

    parts = []
    if "max_age_seconds" in saved:
        parts.append(f"max age {saved['max_age_seconds']}s")
    if "refresh_timeout_seconds" in saved:
        parts.append(f"refresh timeout {saved['refresh_timeout_seconds']}s")

    return jsonify({
        "success": True,
        "message": f"Updated checkout spot: {', '.join(parts)}.",
        "max_age_min": CHECKOUT_SPOT_MAX_AGE_MIN,
        "max_age_max": CHECKOUT_SPOT_MAX_AGE_MAX,
        "refresh_timeout_min": CHECKOUT_SPOT_REFRESH_TIMEOUT_MIN,
        "refresh_timeout_max": CHECKOUT_SPOT_REFRESH_TIMEOUT_MAX,
        **saved,
    })


@admin_bp.route("/api/system-settings/manual-spot", methods=["POST"])
@admin_required
def insert_manual_spot():
    """
    Insert a manual spot price snapshot (DEV / DEBUG mode only).

    Returns 404 in production so the endpoint is invisible to scanners.
    Returns 403 if the caller is not an admin (handled by @admin_required).

    Request JSON: {"metal": "gold", "price_usd": 5300.25}
    Response:     {"success": true, "inserted": {id, metal, price_usd, as_of, source}}
    """
    from flask import current_app
    if not (current_app.debug or current_app.config.get("ENV") == "development"):
        from flask import abort
        abort(404)

    from database import get_db_connection
    from services.manual_spot_service import insert_manual_spot_snapshot

    data      = request.get_json(silent=True) or {}
    metal_raw = (data.get("metal") or "").strip()
    price_raw = data.get("price_usd")

    if not metal_raw:
        return jsonify({"success": False, "message": "metal is required"}), 400

    try:
        price_usd = float(price_raw)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "price_usd must be a number"}), 400

    conn = get_db_connection()
    try:
        inserted = insert_manual_spot_snapshot(conn, metal_raw, price_usd)
        conn.close()
        return jsonify({"success": True, "inserted": inserted})
    except ValueError as exc:
        conn.close()
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        conn.close()
        return jsonify({"success": False, "message": f"DB error: {exc}"}), 500


@admin_bp.route("/api/system-settings/maintenance-mode", methods=["GET"])
@admin_required
def get_maintenance_mode():
    """Return current maintenance mode state."""
    from services.system_settings_service import get_maintenance_mode as _get
    return jsonify({"success": True, "enabled": _get()})


@admin_bp.route("/api/system-settings/maintenance-mode", methods=["POST"])
@admin_required
def set_maintenance_mode():
    """Enable or disable maintenance mode."""
    from services.system_settings_service import set_maintenance_mode as _set
    data = request.get_json(silent=True) or {}
    if "enabled" not in data:
        return jsonify({"success": False, "message": "enabled is required"}), 400
    new_state = bool(data["enabled"])
    _set(new_state)
    return jsonify({
        "success": True,
        "enabled": new_state,
        "message": "Maintenance mode enabled." if new_state else "Maintenance mode disabled.",
    })


@admin_bp.route("/api/system-settings/default-fee", methods=["GET"])
@admin_required
def get_default_fee():
    """Return current global default platform fee from fee_config table."""
    import database
    conn = database.get_db_connection()
    try:
        row = conn.execute(
            "SELECT fee_type, fee_value FROM fee_config WHERE config_key = 'default_platform_fee' AND active = 1"
        ).fetchone()
        if row:
            return jsonify({"success": True, "fee_type": row["fee_type"], "fee_value": row["fee_value"]})
        from services.ledger_constants import DEFAULT_PLATFORM_FEE_TYPE, DEFAULT_PLATFORM_FEE_VALUE
        return jsonify({"success": True, "fee_type": DEFAULT_PLATFORM_FEE_TYPE.value, "fee_value": DEFAULT_PLATFORM_FEE_VALUE})
    finally:
        conn.close()


@admin_bp.route("/api/system-settings/default-fee", methods=["POST"])
@admin_required
def set_default_fee():
    """Update the global default platform fee in fee_config table."""
    import database

    data = request.get_json(silent=True) or {}
    fee_type = data.get("fee_type", "percent")
    fee_value = data.get("fee_value")

    if fee_type not in ("percent", "flat"):
        return jsonify({"success": False, "message": "fee_type must be 'percent' or 'flat'"}), 400
    try:
        fee_value = float(fee_value)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "fee_value must be a number"}), 400
    if fee_value < 0 or fee_value > 100:
        return jsonify({"success": False, "message": "fee_value must be between 0 and 100"}), 400

    conn = database.get_db_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM fee_config WHERE config_key = 'default_platform_fee'"
        ).fetchone()
        if existing:
            conn.execute("""
                UPDATE fee_config
                SET fee_type = ?, fee_value = ?, updated_at = CURRENT_TIMESTAMP
                WHERE config_key = 'default_platform_fee'
            """, (fee_type, fee_value))
        else:
            conn.execute("""
                INSERT INTO fee_config (config_key, fee_type, fee_value, description, active)
                VALUES ('default_platform_fee', ?, ?, 'Default platform fee applied to all transactions', 1)
            """, (fee_type, fee_value))
        conn.commit()
        return jsonify({"success": True, "fee_type": fee_type, "fee_value": fee_value,
                        "message": f"Default platform fee updated to {fee_value}%."})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()


@admin_bp.route("/api/system-settings/tracking-forfeit", methods=["GET"])
@admin_required
def get_tracking_forfeit():
    """Return current tracking forfeit window decomposed into days/hours/minutes."""
    from services.system_settings_service import (
        get_tracking_forfeit_window,
        TRACKING_FORFEIT_WINDOW_MIN,
        TRACKING_FORFEIT_WINDOW_MAX,
        TRACKING_FORFEIT_WINDOW_DEFAULT,
    )
    total = get_tracking_forfeit_window()
    return jsonify({
        "success": True,
        "total_seconds": total,
        "days": total // 86400,
        "hours": (total % 86400) // 3600,
        "minutes": (total % 3600) // 60,
        "min_seconds": TRACKING_FORFEIT_WINDOW_MIN,
        "max_seconds": TRACKING_FORFEIT_WINDOW_MAX,
        "default_seconds": TRACKING_FORFEIT_WINDOW_DEFAULT,
    })


@admin_bp.route("/api/system-settings/tracking-forfeit", methods=["POST"])
@admin_required
def set_tracking_forfeit():
    """Update the tracking forfeit window from days/hours/minutes."""
    from services.system_settings_service import (
        set_tracking_forfeit_window,
        TRACKING_FORFEIT_WINDOW_MIN,
        TRACKING_FORFEIT_WINDOW_MAX,
    )
    data = request.get_json(silent=True) or {}
    try:
        days    = int(data.get("days", 0))
        hours   = int(data.get("hours", 0))
        minutes = int(data.get("minutes", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "days, hours, minutes must be integers"}), 400

    total = days * 86400 + hours * 3600 + minutes * 60
    saved = set_tracking_forfeit_window(total)

    s_days    = saved // 86400
    s_hours   = (saved % 86400) // 3600
    s_minutes = (saved % 3600) // 60

    parts = []
    if s_days:    parts.append(f"{s_days}d")
    if s_hours:   parts.append(f"{s_hours}h")
    if s_minutes: parts.append(f"{s_minutes}m")
    label = " ".join(parts) if parts else f"{saved}s"

    return jsonify({
        "success": True,
        "total_seconds": saved,
        "days": s_days,
        "hours": s_hours,
        "minutes": s_minutes,
        "min_seconds": TRACKING_FORFEIT_WINDOW_MIN,
        "max_seconds": TRACKING_FORFEIT_WINDOW_MAX,
        "message": f"Tracking forfeit window updated to {label}.",
    })


def _trigger_immediate_snapshot_async():
    """
    Fire-and-forget: run one snapshot in a background thread immediately
    after an interval change so the admin sees updated data quickly.
    Rate-limited by the DB run-lock (skips if another run is in progress).
    """
    import threading

    def _run():
        try:
            from services.spot_snapshot_service import run_snapshot
            run_snapshot(use_lock=True, verbose=False)
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True, name="spot_snapshot_immediate")
    t.start()
