"""
Comprehensive notification system tests.

Tests cover:
  1.  listing_created_success fires; toggle OFF suppresses it
  2.  bid_placed → bid_placed_success to bidder; bid_received to seller; toggles suppress
  3.  bid_accepted full → bid_fully_filled; partial → bid_partially_accepted
  4.  outbid event suppressed by toggle
  5.  multi-seller order → seller_order_received for each seller; buyer gets order_created once
  6.  cancellation multi-seller: request, deny, approve flows
  7.  new_order_message fires; toggle suppress works
  8.  mark read / mark all read endpoints

All tests use an in-process SQLite DB created from a minimal schema — no Flask app needed
for pure service-layer tests.  HTTP endpoint tests use the conftest app fixture.
"""

import sys
import os
import sqlite3
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Minimal in-memory DB schema for pure service-layer tests
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL UNIQUE,
    email        TEXT,
    password     TEXT DEFAULT '',
    password_hash TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS notifications (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    type                TEXT    NOT NULL,
    title               TEXT    NOT NULL,
    message             TEXT    NOT NULL,
    is_read             INTEGER DEFAULT 0,
    related_order_id    INTEGER,
    related_bid_id      INTEGER,
    related_listing_id  INTEGER,
    metadata            TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at             TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notification_settings (
    user_id           INTEGER NOT NULL,
    notification_type TEXT    NOT NULL,
    enabled           INTEGER NOT NULL DEFAULT 1,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, notification_type)
);
"""


# ---------------------------------------------------------------------------
# Fixture: patch database.get_db_connection to use an in-memory SQLite DB
# ---------------------------------------------------------------------------

@pytest.fixture
def inmem_db(monkeypatch):
    """
    Create a fresh in-memory SQLite database for each test.
    Patches database.get_db_connection via the module-level attribute so that
    notification_service._get_conn() and notification_types._get_conn() both
    see the in-memory DB (both use _db_module.get_db_connection()).
    """
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()

    # Keep the connection alive across repeated calls by returning a no-close proxy.
    class _Proxy:
        """Forwards everything to `conn` but silences close() to keep the DB alive."""
        def __init__(self, real): self._c = real
        def __getattr__(self, n): return getattr(self._c, n)
        def close(self): pass
        def commit(self): self._c.commit()
        def execute(self, *a, **k): return self._c.execute(*a, **k)
        def executescript(self, *a, **k): return self._c.executescript(*a, **k)
        def __enter__(self): return self
        def __exit__(self, *a): pass
        @property
        def row_factory(self): return self._c.row_factory
        @row_factory.setter
        def row_factory(self, v): self._c.row_factory = v

    proxy = _Proxy(conn)

    import database
    # Patch the attribute on the database module.
    # notification_service and notification_types both call
    # _db_module.get_db_connection() which is a live lookup on the module object.
    monkeypatch.setattr(database, 'get_db_connection', lambda: proxy)

    # Also patch notification_service._db_module and notification_types._db_module
    # (they import `database as _db_module` at module load time; that binding
    # IS the same module object as `database`, so patching database.get_db_connection
    # is sufficient — both modules do _db_module.get_db_connection() via attribute
    # access on the module object).

    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(conn, username):
    cur = conn.execute(
        "INSERT INTO users (username, email) VALUES (?, ?)",
        (username, f'{username}@test.com'),
    )
    conn.commit()
    return cur.lastrowid


def _get_notifs(conn, user_id, ntype=None):
    if ntype:
        return conn.execute(
            'SELECT * FROM notifications WHERE user_id = ? AND type = ? ORDER BY id',
            (user_id, ntype),
        ).fetchall()
    return conn.execute(
        'SELECT * FROM notifications WHERE user_id = ? ORDER BY id',
        (user_id,),
    ).fetchall()


def _disable(conn, user_id, ntype):
    conn.execute(
        '''INSERT INTO notification_settings (user_id, notification_type, enabled)
           VALUES (?, ?, 0)
           ON CONFLICT(user_id, notification_type) DO UPDATE SET enabled = 0''',
        (user_id, ntype),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 1. listing_created_success fires; toggle OFF suppresses it
# ---------------------------------------------------------------------------

class TestListingCreated:
    def test_fires(self, inmem_db):
        from services.notification_types import notify_listing_created
        seller_id = _make_user(inmem_db, 'seller_lc')

        nid = notify_listing_created(seller_id, listing_id=42, item_description='1 oz Gold Eagle')
        assert nid is not None

        rows = _get_notifs(inmem_db, seller_id, 'listing_created_success')
        assert len(rows) == 1
        assert 'Gold Eagle' in rows[0]['message']

    def test_suppressed_when_disabled(self, inmem_db):
        from services.notification_types import notify_listing_created
        seller_id = _make_user(inmem_db, 'seller_lc2')
        _disable(inmem_db, seller_id, 'listing_created_success')

        nid = notify_listing_created(seller_id, listing_id=99, item_description='Silver Bar')
        assert nid is None

        rows = _get_notifs(inmem_db, seller_id, 'listing_created_success')
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# 2. bid_placed → bid_placed_success to bidder; bid_received to seller; toggles
# ---------------------------------------------------------------------------

class TestBidPlaced:
    def test_bidder_gets_bid_placed_success(self, inmem_db):
        from services.notification_types import notify_bid_placed
        bidder_id = _make_user(inmem_db, 'bidder1')

        nid = notify_bid_placed(bidder_id, bid_id=10, bucket_id=1,
                                item_description='1 oz Gold', quantity=2,
                                price_per_unit=2000.0)
        assert nid is not None
        rows = _get_notifs(inmem_db, bidder_id, 'bid_placed_success')
        assert len(rows) == 1

    def test_seller_gets_bid_received(self, inmem_db):
        from services.notification_types import notify_bid_received
        seller_id = _make_user(inmem_db, 'seller_br')

        nid = notify_bid_received(seller_id, bidder_username='buyer_x', bid_id=11,
                                  bucket_id=1, item_description='Silver Bar',
                                  bid_price=25.0, quantity=5)
        assert nid is not None
        rows = _get_notifs(inmem_db, seller_id, 'bid_received')
        assert len(rows) == 1
        assert 'buyer_x' in rows[0]['message']

    def test_bid_placed_toggle_suppresses(self, inmem_db):
        from services.notification_types import notify_bid_placed
        bidder_id = _make_user(inmem_db, 'bidder_off')
        _disable(inmem_db, bidder_id, 'bid_placed_success')

        nid = notify_bid_placed(bidder_id, bid_id=20, bucket_id=2,
                                item_description='Platinum', quantity=1,
                                price_per_unit=1000.0)
        assert nid is None
        assert len(_get_notifs(inmem_db, bidder_id, 'bid_placed_success')) == 0

    def test_bid_received_toggle_suppresses(self, inmem_db):
        from services.notification_types import notify_bid_received
        seller_id = _make_user(inmem_db, 'seller_off')
        _disable(inmem_db, seller_id, 'bid_received')

        nid = notify_bid_received(seller_id, bidder_username='bob', bid_id=21,
                                  bucket_id=3, item_description='Palladium',
                                  bid_price=500.0, quantity=1)
        assert nid is None


# ---------------------------------------------------------------------------
# 3. bid_accepted full → bid_fully_filled; partial → bid_partially_accepted
# ---------------------------------------------------------------------------

class TestBidAccepted:
    def test_full_fill(self, inmem_db):
        from services.notification_types import notify_bid_accepted
        buyer_id = _make_user(inmem_db, 'buyer_full')

        nid = notify_bid_accepted(buyer_id, order_id=100, bid_id=30,
                                  item_description='1 oz Gold', quantity_filled=3,
                                  price_per_unit=2000.0, total_amount=6000.0,
                                  is_partial=False)
        assert nid is not None
        rows = _get_notifs(inmem_db, buyer_id, 'bid_fully_filled')
        assert len(rows) == 1

    def test_partial_fill(self, inmem_db):
        from services.notification_types import notify_bid_accepted
        buyer_id = _make_user(inmem_db, 'buyer_partial')

        nid = notify_bid_accepted(buyer_id, order_id=101, bid_id=31,
                                  item_description='Silver Eagle', quantity_filled=2,
                                  price_per_unit=30.0, total_amount=60.0,
                                  is_partial=True, remaining_quantity=3)
        assert nid is not None
        rows = _get_notifs(inmem_db, buyer_id, 'bid_partially_accepted')
        assert len(rows) == 1
        assert 'partially' in rows[0]['message'].lower()

    def test_full_fill_suppressed(self, inmem_db):
        from services.notification_types import notify_bid_accepted
        buyer_id = _make_user(inmem_db, 'buyer_full_off')
        _disable(inmem_db, buyer_id, 'bid_fully_filled')

        nid = notify_bid_accepted(buyer_id, order_id=102, bid_id=32,
                                  item_description='Coin', quantity_filled=1,
                                  price_per_unit=100.0, total_amount=100.0)
        assert nid is None

    def test_partial_fill_suppressed(self, inmem_db):
        from services.notification_types import notify_bid_accepted
        buyer_id = _make_user(inmem_db, 'buyer_partial_off')
        _disable(inmem_db, buyer_id, 'bid_partially_accepted')

        nid = notify_bid_accepted(buyer_id, order_id=103, bid_id=33,
                                  item_description='Coin', quantity_filled=1,
                                  price_per_unit=100.0, total_amount=100.0,
                                  is_partial=True, remaining_quantity=2)
        assert nid is None


# ---------------------------------------------------------------------------
# 4. outbid event suppressed by toggle
# ---------------------------------------------------------------------------

class TestOutbid:
    def test_fires(self, inmem_db):
        from services.notification_types import notify_outbid
        bidder_id = _make_user(inmem_db, 'bidder_ob')

        nid = notify_outbid(bidder_id, bid_id=40, item_description='Gold Bar',
                            old_price=1900.0, new_price=1950.0)
        assert nid is not None
        rows = _get_notifs(inmem_db, bidder_id, 'outbid')
        assert len(rows) == 1

    def test_suppressed(self, inmem_db):
        from services.notification_types import notify_outbid
        bidder_id = _make_user(inmem_db, 'bidder_ob_off')
        _disable(inmem_db, bidder_id, 'outbid')

        nid = notify_outbid(bidder_id, bid_id=41, item_description='Silver Bar',
                            old_price=25.0, new_price=26.0)
        assert nid is None


# ---------------------------------------------------------------------------
# 5. Multi-seller order: seller_order_received per seller; buyer gets order_created once
# ---------------------------------------------------------------------------

class TestMultiSellerOrder:
    def test_each_seller_notified(self, inmem_db):
        from services.notification_types import notify_seller_order_received, notify_order_created
        seller_a = _make_user(inmem_db, 'seller_ms_a')
        seller_b = _make_user(inmem_db, 'seller_ms_b')
        buyer_id = _make_user(inmem_db, 'buyer_ms')

        # Simulate two sellers each getting notified for their portion
        nid_a = notify_seller_order_received(
            seller_a, order_id=200, listing_id=10,
            item_description='1 oz Gold Eagle', quantity_sold=2,
            price_per_unit=2000.0, total_amount=4000.0)
        nid_b = notify_seller_order_received(
            seller_b, order_id=200, listing_id=11,
            item_description='Silver Bar', quantity_sold=5,
            price_per_unit=30.0, total_amount=150.0)

        assert nid_a is not None
        assert nid_b is not None

        a_rows = _get_notifs(inmem_db, seller_a, 'seller_order_received')
        b_rows = _get_notifs(inmem_db, seller_b, 'seller_order_received')
        assert len(a_rows) == 1
        assert len(b_rows) == 1

        # Buyer gets exactly one order_created notification
        nid_buyer = notify_order_created(
            buyer_id, order_id=200, item_description='Multiple Items',
            quantity=7, price_per_unit=0, total_amount=4150.0)
        assert nid_buyer is not None
        buyer_rows = _get_notifs(inmem_db, buyer_id, 'order_created')
        assert len(buyer_rows) == 1

    def test_seller_b_disabled_does_not_affect_seller_a(self, inmem_db):
        from services.notification_types import notify_seller_order_received
        seller_a = _make_user(inmem_db, 'seller_ms2_a')
        seller_b = _make_user(inmem_db, 'seller_ms2_b')
        _disable(inmem_db, seller_b, 'seller_order_received')

        nid_a = notify_seller_order_received(
            seller_a, order_id=201, listing_id=12,
            item_description='Gold', quantity_sold=1,
            price_per_unit=2000.0, total_amount=2000.0)
        nid_b = notify_seller_order_received(
            seller_b, order_id=201, listing_id=13,
            item_description='Silver', quantity_sold=3,
            price_per_unit=30.0, total_amount=90.0)

        assert nid_a is not None
        assert nid_b is None   # B disabled
        assert len(_get_notifs(inmem_db, seller_a, 'seller_order_received')) == 1
        assert len(_get_notifs(inmem_db, seller_b, 'seller_order_received')) == 0


# ---------------------------------------------------------------------------
# 6. Cancellation multi-seller: request, deny, approve flows
# ---------------------------------------------------------------------------

class TestCancellationMultiSeller:
    def test_request_emits_to_buyer_and_all_sellers(self, inmem_db):
        from services.notification_types import (
            notify_cancel_request_submitted,
            notify_cancellation_requested_seller,
        )
        buyer_id   = _make_user(inmem_db, 'buyer_cr')
        seller_a   = _make_user(inmem_db, 'seller_cr_a')
        seller_b   = _make_user(inmem_db, 'seller_cr_b')

        # Buyer submits request
        nid_buyer = notify_cancel_request_submitted(buyer_id, order_id=300,
                                                     item_description='Gold')
        # Both sellers notified
        nid_sa = notify_cancellation_requested_seller(seller_a, order_id=300,
                                                       item_description='Gold',
                                                       reason='Changed mind')
        nid_sb = notify_cancellation_requested_seller(seller_b, order_id=300,
                                                       item_description='Gold',
                                                       reason='Changed mind')

        assert nid_buyer is not None
        assert nid_sa is not None
        assert nid_sb is not None

        buyer_rows = _get_notifs(inmem_db, buyer_id, 'cancel_request_submitted')
        assert len(buyer_rows) == 1

        sa_rows = _get_notifs(inmem_db, seller_a, 'seller_cancellation_request_received')
        sb_rows = _get_notifs(inmem_db, seller_b, 'seller_cancellation_request_received')
        assert len(sa_rows) == 1
        assert len(sb_rows) == 1

    def test_one_seller_denies_triggers_denied_to_buyer_and_sellers(self, inmem_db):
        from services.notification_types import (
            notify_cancellation_denied,
            notify_seller_cancellation_finalized,
        )
        buyer_id = _make_user(inmem_db, 'buyer_cd')
        seller_a = _make_user(inmem_db, 'seller_cd_a')
        seller_b = _make_user(inmem_db, 'seller_cd_b')

        # Seller A denies → global denial
        nid_buyer = notify_cancellation_denied(buyer_id, order_id=301,
                                               item_description='Gold Bar')
        nid_sa = notify_seller_cancellation_finalized(seller_a, order_id=301,
                                                       item_description='Gold Bar',
                                                       approved=False)
        nid_sb = notify_seller_cancellation_finalized(seller_b, order_id=301,
                                                       item_description='Gold Bar',
                                                       approved=False)

        assert nid_buyer is not None
        assert nid_sa is not None
        assert nid_sb is not None

        buyer_rows = _get_notifs(inmem_db, buyer_id, 'cancellation_denied')
        assert len(buyer_rows) == 1
        assert 'denied' in buyer_rows[0]['message'].lower()

    def test_all_sellers_approve_triggers_approved_to_buyer_and_sellers(self, inmem_db):
        from services.notification_types import (
            notify_cancellation_approved,
            notify_seller_cancellation_finalized,
        )
        buyer_id = _make_user(inmem_db, 'buyer_ca')
        seller_a = _make_user(inmem_db, 'seller_ca_a')
        seller_b = _make_user(inmem_db, 'seller_ca_b')

        nid_buyer = notify_cancellation_approved(buyer_id, order_id=302,
                                                 item_description='Silver')
        nid_sa = notify_seller_cancellation_finalized(seller_a, order_id=302,
                                                       item_description='Silver',
                                                       approved=True)
        nid_sb = notify_seller_cancellation_finalized(seller_b, order_id=302,
                                                       item_description='Silver',
                                                       approved=True)

        assert all(n is not None for n in [nid_buyer, nid_sa, nid_sb])
        rows = _get_notifs(inmem_db, buyer_id, 'cancellation_approved')
        assert len(rows) == 1

    def test_buyer_cancellation_denied_suppressed_by_toggle(self, inmem_db):
        from services.notification_types import notify_cancellation_denied
        buyer_id = _make_user(inmem_db, 'buyer_cd_off')
        _disable(inmem_db, buyer_id, 'cancellation_denied')

        nid = notify_cancellation_denied(buyer_id, order_id=303,
                                         item_description='Gold')
        assert nid is None
        assert len(_get_notifs(inmem_db, buyer_id, 'cancellation_denied')) == 0


# ---------------------------------------------------------------------------
# 7. new_order_message fires; toggle suppress works
# ---------------------------------------------------------------------------

class TestMessaging:
    def test_new_order_message_fires(self, inmem_db):
        from services.notification_types import notify_new_message
        receiver_id = _make_user(inmem_db, 'recv_msg')
        sender_id   = _make_user(inmem_db, 'sender_msg')

        nid = notify_new_message(receiver_id, sender_id=sender_id,
                                 order_id=400, message_preview='Hello there!')
        assert nid is not None
        rows = _get_notifs(inmem_db, receiver_id, 'new_order_message')
        assert len(rows) == 1
        assert 'sender_msg' in rows[0]['title']

    def test_direct_message_when_no_order(self, inmem_db):
        from services.notification_types import notify_new_message
        receiver_id = _make_user(inmem_db, 'recv_dm')
        sender_id   = _make_user(inmem_db, 'sender_dm')

        nid = notify_new_message(receiver_id, sender_id=sender_id,
                                 order_id=None, message_preview='Hey')
        assert nid is not None
        rows = _get_notifs(inmem_db, receiver_id, 'new_direct_message')
        assert len(rows) == 1

    def test_message_toggle_suppresses(self, inmem_db):
        from services.notification_types import notify_new_message
        receiver_id = _make_user(inmem_db, 'recv_msg_off')
        sender_id   = _make_user(inmem_db, 'sender_msg_off')
        _disable(inmem_db, receiver_id, 'new_order_message')

        nid = notify_new_message(receiver_id, sender_id=sender_id,
                                 order_id=401, message_preview='Suppressed')
        assert nid is None
        assert len(_get_notifs(inmem_db, receiver_id)) == 0


# ---------------------------------------------------------------------------
# 8. Mark read / mark all read (service-layer unit tests)
# ---------------------------------------------------------------------------

class TestMarkRead:
    def _seed_notifs(self, inmem_db, user_id, count=3):
        from services.notification_service import _insert_notification
        ids = []
        for i in range(count):
            nid = _insert_notification(
                user_id=user_id,
                notification_type='order_created',
                title=f'Notif {i}',
                message=f'Message {i}',
            )
            ids.append(nid)
        return ids

    def test_mark_single_read(self, inmem_db):
        from services.notification_service import mark_notification_read
        user_id = _make_user(inmem_db, 'user_mr')
        ids = self._seed_notifs(inmem_db, user_id, count=2)

        mark_notification_read(ids[0])

        row0 = inmem_db.execute('SELECT is_read FROM notifications WHERE id = ?', (ids[0],)).fetchone()
        row1 = inmem_db.execute('SELECT is_read FROM notifications WHERE id = ?', (ids[1],)).fetchone()
        assert row0['is_read'] == 1
        assert row1['is_read'] == 0

    def test_mark_all_read(self, inmem_db):
        from services.notification_service import mark_all_notifications_read, get_unread_count
        user_id = _make_user(inmem_db, 'user_mar')
        self._seed_notifs(inmem_db, user_id, count=4)

        assert get_unread_count(user_id) == 4
        mark_all_notifications_read(user_id)
        assert get_unread_count(user_id) == 0

    def test_mark_all_read_does_not_affect_other_users(self, inmem_db):
        from services.notification_service import mark_all_notifications_read, get_unread_count
        user_a = _make_user(inmem_db, 'user_mar_a')
        user_b = _make_user(inmem_db, 'user_mar_b')
        self._seed_notifs(inmem_db, user_a, count=2)
        self._seed_notifs(inmem_db, user_b, count=3)

        mark_all_notifications_read(user_a)

        assert get_unread_count(user_a) == 0
        assert get_unread_count(user_b) == 3


# ---------------------------------------------------------------------------
# 9. HTTP endpoint tests (require Flask app from conftest)
# ---------------------------------------------------------------------------

class TestNotificationEndpoints:
    def test_get_notifications_unauth(self, client):
        resp = client.get('/notifications')
        assert resp.status_code == 401

    def test_get_notifications_auth(self, auth_client):
        client, user_id = auth_client
        resp = client.get('/notifications')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert isinstance(data['notifications'], list)

    def test_unread_count_auth(self, auth_client):
        client, user_id = auth_client
        resp = client.get('/notifications/unread-count')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'count' in data

    def test_mark_all_read_endpoint(self, auth_client):
        client, _ = auth_client
        resp = client.post('/notifications/mark-all-read')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_settings_get_returns_defaults(self, auth_client):
        client, _ = auth_client
        resp = client.get('/notifications/settings')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        settings = data['settings']
        # Core essentials should default ON
        assert settings.get('order_created') is True
        assert settings.get('bid_placed_success') is True
        assert settings.get('cancellation_denied') is True
        # Noisy ones should default OFF
        assert settings.get('listing_edited') is False
        assert settings.get('tracking_updated') is False

    def test_settings_post_updates_toggle(self, auth_client):
        client, _ = auth_client
        # Turn off order_created
        resp = client.post(
            '/notifications/settings',
            json={'order_created': False},
        )
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        # Verify it was stored
        get_resp = client.get('/notifications/settings')
        settings = get_resp.get_json()['settings']
        assert settings.get('order_created') is False

        # Turn it back on
        client.post('/notifications/settings', json={'order_created': True})
        settings2 = client.get('/notifications/settings').get_json()['settings']
        assert settings2.get('order_created') is True

    def test_settings_post_unknown_type_rejected(self, auth_client):
        """Unknown notification type keys must now be explicitly rejected (400)."""
        client, _ = auth_client
        resp = client.post(
            '/notifications/settings',
            json={'completely_fake_type': True},
        )
        assert resp.status_code == 400
        assert 'Unknown' in resp.get_json().get('error', '') or \
               'unknown' in resp.get_json().get('error', '')

    def test_settings_post_unauthenticated(self, client):
        resp = client.post('/notifications/settings', json={'order_created': False})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 10. notify() central function and is_notification_enabled() unit tests
# ---------------------------------------------------------------------------

class TestNotifyAndSettings:
    def test_notify_creates_row_when_enabled(self, inmem_db):
        from services.notification_service import notify
        user_id = _make_user(inmem_db, 'u_notify_on')

        nid = notify(user_id, 'order_created', 'Title', 'Body', related_order_id=1)
        assert nid is not None
        rows = _get_notifs(inmem_db, user_id, 'order_created')
        assert len(rows) == 1

    def test_notify_suppressed_when_disabled(self, inmem_db):
        from services.notification_service import notify
        user_id = _make_user(inmem_db, 'u_notify_off')
        _disable(inmem_db, user_id, 'order_created')

        nid = notify(user_id, 'order_created', 'Title', 'Body')
        assert nid is None
        assert len(_get_notifs(inmem_db, user_id, 'order_created')) == 0

    def test_is_notification_enabled_default_on(self, inmem_db):
        from services.notification_service import is_notification_enabled
        user_id = _make_user(inmem_db, 'u_isen_on')
        assert is_notification_enabled(user_id, 'order_created') is True

    def test_is_notification_enabled_default_off(self, inmem_db):
        from services.notification_service import is_notification_enabled
        user_id = _make_user(inmem_db, 'u_isen_off')
        assert is_notification_enabled(user_id, 'listing_edited') is False

    def test_is_notification_enabled_respects_user_override(self, inmem_db):
        from services.notification_service import is_notification_enabled
        user_id = _make_user(inmem_db, 'u_isen_ov')
        _disable(inmem_db, user_id, 'order_created')
        assert is_notification_enabled(user_id, 'order_created') is False

    def test_update_notification_settings_idempotent(self, inmem_db):
        from services.notification_service import (
            update_notification_settings, is_notification_enabled,
        )
        user_id = _make_user(inmem_db, 'u_uns')
        update_notification_settings(user_id, {'order_created': False})
        assert is_notification_enabled(user_id, 'order_created') is False
        update_notification_settings(user_id, {'order_created': True})
        assert is_notification_enabled(user_id, 'order_created') is True

    def test_get_user_notification_settings_returns_all_defaults(self, inmem_db):
        from services.notification_service import (
            get_user_notification_settings, NOTIFICATION_DEFAULTS,
        )
        user_id = _make_user(inmem_db, 'u_gns')
        settings = get_user_notification_settings(user_id)

        # All keys from NOTIFICATION_DEFAULTS must be present
        for k in NOTIFICATION_DEFAULTS:
            assert k in settings, f'Missing key: {k}'
            assert settings[k] == NOTIFICATION_DEFAULTS[k]

    def test_get_user_notification_settings_with_overrides(self, inmem_db):
        from services.notification_service import (
            update_notification_settings, get_user_notification_settings,
        )
        user_id = _make_user(inmem_db, 'u_gns2')
        update_notification_settings(user_id, {
            'order_created': False,
            'listing_edited': True,  # normally OFF by default
        })
        settings = get_user_notification_settings(user_id)
        assert settings['order_created'] is False
        assert settings['listing_edited'] is True

    def test_unknown_notification_type_defaults_to_enabled(self, inmem_db):
        from services.notification_service import is_notification_enabled
        user_id = _make_user(inmem_db, 'u_unknown')
        # 'some_future_type' not in NOTIFICATION_DEFAULTS → defaults True
        assert is_notification_enabled(user_id, 'some_future_type') is True
