import sqlite3
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from services import spot_price_service as service


def test_yahoo_preserves_quote_age_and_futures_source(tmp_path):
    stamp = int(datetime.now(timezone.utc).timestamp()) - 660
    response = Mock(status_code=200)
    response.json.return_value = {'chart': {'result': [{'meta': {'regularMarketPrice': 4000, 'regularMarketTime': stamp}}]}}
    with patch.object(service.requests, 'get', return_value=response):
        prices = service.fetch_spot_prices_from_yahoo()
    path = str(tmp_path / 'cache.db')
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE spot_prices(metal TEXT PRIMARY KEY, price_usd_per_oz REAL, updated_at TEXT, source TEXT)')
    conn.commit(); conn.close()
    def connect():
        db = sqlite3.connect(path); db.row_factory = sqlite3.Row; return db
    with patch.object(service, 'get_db_connection', side_effect=connect):
        assert service.save_spot_prices_to_cache(prices)
        assert not service.is_cache_fresh()[0]
        cached = service.get_cached_spot_prices()
        assert cached.metadata['gold']['source'] == 'yahoo_futures'
        assert datetime.fromisoformat(cached.metadata['gold']['as_of']).timestamp() == stamp


def test_unknown_timestamp_is_not_freshened(tmp_path):
    path = str(tmp_path / 'cache.db')
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE spot_prices(metal TEXT PRIMARY KEY, price_usd_per_oz REAL, updated_at TEXT, source TEXT)')
    conn.commit(); conn.close()
    def connect():
        db = sqlite3.connect(path); db.row_factory = sqlite3.Row; return db
    with patch.object(service, 'get_db_connection', side_effect=connect):
        assert service.save_spot_prices_to_cache({'gold':4000})
        assert not service.is_cache_fresh()[0]
        assert service.get_cached_spot_prices().metadata['gold']['source'] == 'unknown'


def test_yahoo_rejects_missing_provider_timestamp():
    response = Mock(status_code=200)
    response.json.return_value = {'chart': {'result': [{'meta': {'regularMarketPrice': 4000}}]}}
    with patch.object(service.requests, 'get', return_value=response):
        assert service.fetch_spot_prices_from_yahoo() is None


def test_primary_preserves_provider_timestamp():
    stamp = int(datetime.now(timezone.utc).timestamp()) - 60
    response = Mock(status_code=200)
    response.json.return_value = {'success':True,'timestamp':stamp,'rates':{'XAU':0.00025}}
    with patch.object(service, 'get_api_key', return_value='test'), patch.object(service.requests, 'get', return_value=response):
        prices = service.fetch_spot_prices_from_api()
    assert prices['gold'] == 4000
    assert prices.metadata['gold']['source'] == 'metalpriceapi'
    assert datetime.fromisoformat(prices.metadata['gold']['as_of']).timestamp() == stamp


def test_snapshot_deduplicates_timezone_aware_provider_time():
    from services.spot_snapshot_service import _should_insert
    assert not _should_insert(4000, datetime.now(timezone.utc).isoformat(), 4000)
