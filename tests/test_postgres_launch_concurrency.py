"""Run separately with DATABASE_URL pointing at a disposable local PostgreSQL."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import pytest
import database
from services import flow_of_funds as flow
from tests.test_flow_of_funds_acceptance import payment

pytestmark=pytest.mark.skipif(not database.IS_POSTGRES,reason='Dedicated PostgreSQL test job required')


@pytest.fixture
def pg(monkeypatch):
    import psycopg2
    url=database.DATABASE_URL
    if urlparse(url).hostname not in ('localhost','127.0.0.1'):
        pytest.fail('These isolated schema tests require localhost PostgreSQL')
    schema='launch_test_'+uuid.uuid4().hex
    original=psycopg2.connect(url); original.autocommit=True
    original.cursor().execute(f'CREATE SCHEMA {schema}')
    def connect():
        return database._PGConnection(psycopg2.connect(url,options=f'-csearch_path={schema} -clock_timeout=10000 -cstatement_timeout=20000'))
    monkeypatch.setattr(flow,'get_db_connection',connect)
    c=connect()
    statements=[
      'CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT, stripe_customer_id TEXT, stripe_account_id TEXT,stripe_charges_enabled INTEGER,stripe_payouts_enabled INTEGER)',
      'CREATE TABLE listings(id INTEGER PRIMARY KEY,seller_id INTEGER,quantity INTEGER,active INTEGER)',
      'CREATE TABLE orders(id SERIAL PRIMARY KEY,buyer_id INTEGER,total_price REAL,buyer_card_fee REAL,tax_amount REAL,tax_rate REAL,shipping_address TEXT,recipient_first_name TEXT,recipient_last_name TEXT,stripe_payment_intent_id TEXT,paid_at TEXT,payment_method_type TEXT,requires_payment_clearance INTEGER,payment_status TEXT,status TEXT,payout_status TEXT,payment_cleared_at TEXT,payment_cleared_by_admin_id INTEGER)',
      'CREATE TABLE order_items(id SERIAL PRIMARY KEY,order_id INTEGER,listing_id INTEGER,quantity INTEGER,price_each REAL,price_at_purchase REAL,seller_price_each REAL,third_party_grading_requested INTEGER,grading_fee_charged REAL,grading_status TEXT)',
      'CREATE TABLE cart(id INTEGER PRIMARY KEY,user_id INTEGER,listing_id INTEGER,quantity INTEGER)']
    for sql in statements: c.execute(sql)
    c.execute("INSERT INTO users VALUES (1,'buyer',NULL,'acct_1',1,1),(2,'seller',NULL,'acct_2',1,1)")
    c.execute('INSERT INTO listings VALUES (10,2,1,1)')
    flow.ensure_flow_schema(c)
    c.execute("INSERT INTO system_settings(key,value) VALUES ('checkout_enabled','1'),('manual_payouts_enabled','1'),('shipments_enabled','1')")
    c.commit(); c.close()
    yield connect
    original.cursor().execute(f'DROP SCHEMA {schema} CASCADE'); original.close()


def prepare(key):
    return flow.prepare_checkout(1,[{'listing_id':10,'quantity':1,'price_each':100}],'card',0,{'shipping_address':'1 Main'},key)


def test_concurrent_buyers_cannot_oversell(pg):
    def buy(key):
        try: return prepare(key)[0]['id']
        except flow.FlowError as exc: return exc.code
    with ThreadPoolExecutor(max_workers=2) as workers: results=list(workers.map(buy,['buyer-a','buyer-b']))
    assert results.count('INVENTORY_UNAVAILABLE')==1
    c=pg(); assert c.execute('SELECT quantity FROM listings').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM checkout_attempts').fetchone()[0]==1; c.close()


def test_duplicate_execution_and_refund_races_are_serialized(pg):
    checkout,snap,_=prepare('checkout')
    c=pg(); op,_=flow.claim_operation(c,'PAYMENT','payment-key','checkout',checkout['id'],snap['buyer_total_cents'],{'snapshot_hash':snap['snapshot_hash']})
    flow.bind_provider_payment(checkout['id'],'pi_1',op['id'],conn=c); c.commit(); c.close()
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=list(workers.map(lambda _:flow.finalize_payment(checkout['id'],payment(checkout,snap)),range(2)))
    assert sum(int(new) for _,new in results)==1
    c=pg(); fill=c.execute('SELECT id FROM seller_fills').fetchone()[0]; exe=c.execute('SELECT id FROM executions').fetchone()[0]; c.close()
    def refund(key):
        try: return flow.create_refund(exe,{fill:1},'SELLER_FAULT',key)[0]['id']
        except flow.FlowError as exc: return exc.code
    with ThreadPoolExecutor(max_workers=2) as workers: results=list(workers.map(refund,['refund-a','refund-b']))
    c=pg(); assert c.execute('SELECT COUNT(*) FROM flow_refunds').fetchone()[0]==1
    assert c.execute('SELECT refunded_quantity FROM seller_fills').fetchone()[0]==1; c.close()
    assert flow.reconcile_internal()==[]


def test_concurrent_transfer_claim_and_confirmation_release_once(pg):
    from datetime import datetime,timedelta,timezone
    checkout,snap,_=prepare('checkout')
    c=pg(); op,_=flow.claim_operation(c,'PAYMENT','payment','checkout',checkout['id'],snap['buyer_total_cents'],{})
    flow.bind_provider_payment(checkout['id'],'pi_1',op['id'],conn=c); c.commit(); c.close()
    flow.finalize_payment(checkout['id'],payment(checkout,snap))
    c=pg(); payable=c.execute('SELECT id FROM seller_payables').fetchone()[0]; shipment=c.execute('SELECT id FROM shipments').fetchone()[0]
    c.execute("UPDATE shipments SET state='DELIVERED',tracking_validated=1,delivered_at=?",((datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),))
    c.execute("INSERT INTO insurance_policies VALUES ('insured',?,'UPS','policy',10000,100,'ACTIVE','{\"covered\":true}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",(shipment,))
    c.commit(); c.close()
    with ThreadPoolExecutor(max_workers=2) as workers:
        claimed=list(workers.map(lambda _:flow.claim_seller_transfer(payable,'stable-transfer'),range(2)))
    assert sum(int(new) for _,new in claimed)==1
    tid=claimed[0][0]['id']; flow.begin_seller_transfer(tid)
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(lambda _:flow.complete_seller_transfer(tid,'tr_single'),range(2)))
    c=pg(); assert c.execute('SELECT released_cents FROM seller_payables').fetchone()[0]==9500
    assert c.execute('SELECT COUNT(*) FROM transfers').fetchone()[0]==1; c.close()
    assert flow.reconcile_internal()==[]


def test_concurrent_category_creation_preserves_finish_and_grade(pg):
    from utils.category_manager import get_or_create_category
    c=pg(); c.execute('CREATE TABLE categories(id SERIAL PRIMARY KEY,bucket_id INTEGER,name TEXT,metal TEXT,product_line TEXT,product_type TEXT,weight TEXT,purity TEXT,mint TEXT,year TEXT,finish TEXT,grade TEXT,condition_category TEXT,series_variant TEXT,is_isolated INTEGER DEFAULT 0)'); c.commit(); c.close()
    spec={'metal':'Silver','product_line':'Eagle','product_type':'Coin','weight':'1 oz','purity':'.999','mint':'US','year':'2026','finish':'BU','grade':'Raw','condition_category':None,'series_variant':None}
    def create(value):
        c=pg()
        try:
            result=get_or_create_category(c,value); c.commit(); return result
        finally: c.close()
    with ThreadPoolExecutor(max_workers=2) as workers: same=list(workers.map(create,[spec,spec]))
    assert same[0]==same[1]
    with ThreadPoolExecutor(max_workers=2) as workers: different=list(workers.map(create,[dict(spec,finish='Proof'),dict(spec,grade='MS70')]))
    assert len(set([same[0],*different]))==3
    c=pg(); assert c.execute('SELECT COUNT(DISTINCT bucket_id) FROM categories').fetchone()[0]==3; c.close()


def smart_market(pg,monkeypatch):
    from services import smart_pricing_service as smart
    monkeypatch.setattr(database,'get_db_connection',pg)
    c=pg()
    c.execute('CREATE TABLE categories(id INTEGER PRIMARY KEY,metal TEXT,weight TEXT,purity TEXT,product_type TEXT,mint TEXT,year TEXT)')
    for declaration in ('category_id INTEGER','pricing_mode TEXT','spot_premium NUMERIC(14,2)','floor_price NUMERIC(14,2)','price_per_coin NUMERIC(14,2)','pricing_metal TEXT','isolated_type TEXT'):
        c.execute('ALTER TABLE listings ADD COLUMN '+declaration)
    c.execute("INSERT INTO categories VALUES(1,'Gold','1 oz','.9999','Bar','Mint','2026')")
    c.execute("CREATE TABLE spot_price_snapshots(metal TEXT,price_usd NUMERIC(14,2),as_of TEXT,source TEXT)")
    c.execute("INSERT INTO spot_price_snapshots VALUES('gold',4000,?,'fixture')",(smart.now_utc().isoformat(),))
    c.execute("INSERT INTO users(id,email,stripe_account_id,stripe_charges_enabled,stripe_payouts_enabled) VALUES(3,'s3','acct_3',1,1),(4,'s4','acct_4',1,1),(5,'s5','acct_5',1,1)")
    c.execute("UPDATE listings SET quantity=5,category_id=1,pricing_mode='premium_to_spot',spot_premium=20,floor_price=.01,price_per_coin=4020,pricing_metal='Gold' WHERE id=10")
    for ident,seller,premium in [(11,3,10),(12,4,20),(13,5,30)]:
        c.execute("INSERT INTO listings(id,seller_id,category_id,quantity,active,pricing_mode,spot_premium,floor_price,price_per_coin,pricing_metal) VALUES(?,?,1,5,1,'premium_to_spot',?,.01,?,'Gold')",(ident,seller,premium,4000+premium))
    smart.ensure_schema(c,create_indexes=True)
    smart.configure(c,10,('fast',1000)); c.commit(); c.close()
    return smart


def test_smart_duplicate_repricing_serializes_on_postgres(pg,monkeypatch):
    smart=smart_market(pg,monkeypatch)
    with ThreadPoolExecutor(max_workers=4) as workers:
        results=list(workers.map(lambda _:smart.evaluate(10),range(4)))
    assert results.count('adjusted')==1 and results.count('cooldown')==3
    c=pg(); assert c.execute('SELECT spot_premium FROM listings WHERE id=10').fetchone()[0]==15
    assert c.execute('SELECT COUNT(*) FROM smart_pricing_history').fetchone()[0]==1; c.close()


def test_smart_quote_change_rejected_before_reservation(pg,monkeypatch):
    smart=smart_market(pg,monkeypatch)
    assert smart.evaluate(10)=='adjusted'
    with pytest.raises(flow.FlowError) as error:
        flow.prepare_checkout(1,[{'listing_id':10,'quantity':1,'price_each':4020}],'card',0,{'shipping_address':'1 Main'},'stale-smart')
    assert error.value.code=='SMART_PRICE_CHANGED'
    c=pg(); assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==5
    assert c.execute('SELECT COUNT(*) FROM checkout_attempts').fetchone()[0]==0; c.close()
    checkout,snapshot,_=flow.prepare_checkout(1,[{'listing_id':10,'quantity':1,'price_each':4015}],'card',0,{'shipping_address':'1 Main'},'fresh-smart')
    c=pg(); assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==4; c.close()
    assert smart.evaluate(10)=='reserved'
    assert snapshot['buyer_total_cents']>401500


def test_smart_initial_price_and_history_commit_together_on_postgres(pg,monkeypatch):
    smart=smart_market(pg,monkeypatch)
    c=pg()
    c.execute("INSERT INTO listings(id,seller_id,category_id,quantity,active,pricing_mode,spot_premium,floor_price,price_per_coin,pricing_metal) VALUES(20,2,1,1,1,'premium_to_spot',0,.01,.01,'Gold')")
    smart.configure(c,20,('balanced',0),initial=True)
    c.commit()
    assert c.execute('SELECT spot_premium FROM listings WHERE id=20').fetchone()[0]==20
    assert c.execute('SELECT new_cents FROM smart_pricing_history WHERE listing_id=20').fetchone()[0]==2000
    c.close()


def test_smart_mixed_metal_set_checkout_and_hold_on_postgres(pg,monkeypatch):
    smart=smart_market(pg,monkeypatch)
    c=pg()
    c.execute('CREATE TABLE listing_set_items(id INTEGER PRIMARY KEY,listing_id INTEGER,position_index INTEGER,metal TEXT,weight TEXT,purity TEXT,product_type TEXT,mint TEXT,year TEXT,quantity INTEGER)')
    c.execute("UPDATE listings SET isolated_type='set' WHERE id=10")
    c.execute("INSERT INTO listing_set_items VALUES(1,10,0,'Gold','1 oz','.9999','Coin','Mint','2026',2),(2,10,1,'Silver','1 oz','.999','Coin','Mint','2026',3)")
    c.execute("INSERT INTO spot_price_snapshots VALUES('silver',50,?,'fixture')",(smart.now_utc().isoformat(),))
    smart.configure(c,10,('balanced',1000),initial=True)
    assert c.execute('SELECT price_per_coin FROM listings WHERE id=10').fetchone()[0]==8170
    c.execute("UPDATE spot_price_snapshots SET price_usd=60 WHERE metal='silver'");c.commit();c.close()
    with pytest.raises(flow.FlowError) as error:
        flow.prepare_checkout(1,[{'listing_id':10,'quantity':1,'price_each':8170}],'card',0,{'shipping_address':'1 Main'},'set-stale')
    assert error.value.code=='SMART_PRICE_CHANGED'
    c=pg();assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==5;c.close()
    checkout,snapshot,created=flow.prepare_checkout(1,[{'listing_id':10,'quantity':1,'price_each':8200}],'card',0,{'shipping_address':'1 Main'},'set-current')
    assert checkout['id'] and created
    assert smart.evaluate(10)=='reserved'
    c=pg();assert c.execute('SELECT COUNT(*) FROM inventory_reservations WHERE listing_id=10').fetchone()[0]==1;c.close()
