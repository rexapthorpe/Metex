"""Smart premium engine and owner-control regression tests on real SQL transactions."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import pytest
import database
from core.blueprints.listings import listings_bp
from services import smart_pricing_service as smart
from services.flow_of_funds import ensure_flow_schema
from services.pricing_service import get_effective_price


@pytest.fixture
def market(tmp_path, monkeypatch):
    path = tmp_path / 'smart.db'
    def connect():
        conn = sqlite3.connect(path, timeout=20)
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(database, 'get_db_connection', connect)
    conn = connect()
    conn.executescript('''
      CREATE TABLE users(id INTEGER PRIMARY KEY,is_banned INTEGER DEFAULT 0,is_frozen INTEGER DEFAULT 0);
      CREATE TABLE categories(id INTEGER PRIMARY KEY,metal TEXT,weight TEXT,purity TEXT,product_type TEXT,mint TEXT,year TEXT);
      CREATE TABLE listings(id INTEGER PRIMARY KEY,category_id INTEGER,seller_id INTEGER,quantity INTEGER,active INTEGER,
        pricing_mode TEXT,spot_premium REAL,floor_price REAL,price_per_coin REAL,pricing_metal TEXT,isolated_type TEXT);
      CREATE TABLE spot_price_snapshots(metal TEXT,price_usd REAL,as_of TEXT,source TEXT);
      INSERT INTO categories VALUES(1,'Gold','1 oz','.9999','Bar','Mint','2026');
      INSERT INTO users(id) VALUES(1),(2),(3),(4),(5);
      INSERT INTO listings VALUES(10,1,1,5,1,'premium_to_spot',20,.01,4020,'Gold',NULL);
      INSERT INTO listings VALUES(11,1,2,5,1,'premium_to_spot',10,.01,4010,'Gold',NULL);
      INSERT INTO listings VALUES(12,1,3,5,1,'premium_to_spot',20,.01,4020,'Gold',NULL);
      INSERT INTO listings VALUES(13,1,4,5,1,'premium_to_spot',30,.01,4030,'Gold',NULL);
    ''')
    ensure_flow_schema(conn); smart.ensure_schema(conn)
    conn.execute('INSERT INTO spot_price_snapshots VALUES(?,?,?,?)', ('gold',4000,smart.now_utc().isoformat(),'fixture'))
    smart.configure(conn,10,('balanced',1000)); conn.commit(); conn.close()
    return connect


def state(market):
    conn = market()
    result = dict(conn.execute('SELECT * FROM listings WHERE id=10').fetchone())
    result['settings'] = smart.dashboard(conn,10)
    conn.close()
    return result


@pytest.mark.parametrize('strategy,expected', [('fast',15),('balanced',20),('big',21.60)])
def test_strategies_from_identical_comps(market,strategy,expected):
    conn=market(); smart.configure(conn,10,(strategy,1000)); conn.commit(); conn.close()
    smart.evaluate(10)
    assert state(market)['spot_premium']==expected
    assert state(market)['settings']['estimate_cents']==2000


def test_spot_movement_changes_total_not_premium_or_history(market):
    item=state(market); item.update(metal='Gold',weight='1 oz')
    assert get_effective_price(item,{'gold':4000})==4020
    assert get_effective_price(item,{'gold':4100})==4120
    assert smart.evaluate(10)=='held'
    assert not state(market)['settings']['history']


def test_automated_adjustment_history_replay_and_cooldown(market):
    conn=market(); smart.configure(conn,10,('fast',1000)); conn.commit(); conn.close()
    now=smart.now_utc()
    assert smart.evaluate(10,now)=='adjusted'
    assert smart.evaluate(10,now)=='cooldown'
    item=state(market)
    event=item['settings']['history'][0]
    assert (event['previous_cents'],event['new_cents'],event['estimate_cents'])==(2000,1500,2000)
    assert event['engine_version']==smart.VERSION
    assert json.loads(event['reason_json'])['source']=='asks_exact'
    assert get_effective_price(dict(item,metal='Gold',weight='1 oz'),{'gold':4100})==4115
    assert len(item['settings']['history'])==1


def test_minimum_enforced_on_enable_and_evaluation(market):
    conn=market(); smart.configure(conn,10,('fast',2500)); conn.commit(); conn.close()
    assert state(market)['spot_premium']==25
    smart.evaluate(10)
    assert state(market)['spot_premium']>=25


@pytest.mark.parametrize('column,value',[('active',0),('quantity',0),('pricing_mode','static')])
def test_ineligible_never_repriced(market,column,value):
    conn=market(); conn.execute(f'UPDATE listings SET {column}=? WHERE id=10',(value,)); conn.commit(); conn.close()
    assert smart.evaluate(10)=='ineligible'
    assert not state(market)['settings']['history']


def test_manual_and_disable_are_never_repriced(market):
    conn=market(); smart.configure(conn,10,None); conn.commit(); conn.close()
    assert smart.evaluate(10)=='ineligible'
    assert smart.evaluate(11)=='ineligible'
    assert state(market)['spot_premium']==20
    assert get_effective_price({'pricing_mode':'static','price_per_coin':123.45},{'gold':4000})==123.45


def test_reserved_inventory_and_banned_seller(market):
    conn=market()
    conn.execute("INSERT INTO inventory_reservations(id,checkout_id,listing_id,quantity,state,created_at,updated_at) VALUES('r','c',10,1,'HELD','t','t')")
    conn.commit(); conn.close()
    assert smart.evaluate(10)=='reserved'
    conn=market(); conn.execute("DELETE FROM inventory_reservations"); conn.execute('UPDATE users SET is_banned=1 WHERE id=1'); conn.commit(); conn.close()
    assert smart.evaluate(10)=='seller_unavailable'
    assert not state(market)['settings']['history']


def test_stale_spot_is_held_not_guessed(market):
    conn=market(); conn.execute('UPDATE spot_price_snapshots SET as_of=?',((smart.now_utc()-timedelta(hours=2)).isoformat(),)); conn.commit(); conn.close()
    assert smart.evaluate(10)=='held'
    assert 'Fresh spot' in state(market)['settings']['review']['reason']
    assert state(market)['spot_premium']==20


def test_insufficient_comps_and_own_seller_inventory_excluded(market):
    conn=market(); conn.execute('UPDATE listings SET seller_id=1 WHERE id IN (11,12)'); conn.commit(); conn.close()
    assert smart.evaluate(10)=='held'
    assert state(market)['settings']['estimate_cents'] is None


def test_duplicate_jobs_concurrent_single_adjustment(market):
    conn=market(); smart.configure(conn,10,('fast',1000)); conn.commit(); conn.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _: smart.evaluate(10),range(4)))
    assert results.count('adjusted')==1
    assert results.count('cooldown')==3
    assert len(state(market)['settings']['history'])==1


def test_provider_free_retry_rollback_if_history_write_fails(market):
    conn=market(); smart.configure(conn,10,('fast',1000))
    conn.execute("CREATE TRIGGER fail_history BEFORE INSERT ON smart_pricing_history BEGIN SELECT RAISE(ABORT,'simulated failure'); END")
    conn.commit(); conn.close()
    with pytest.raises(sqlite3.IntegrityError): smart.evaluate(10)
    assert state(market)['spot_premium']==20
    assert state(market)['settings']['last_review'] is None
    conn=market(); conn.execute('DROP TRIGGER fail_history'); conn.commit(); conn.close()
    assert smart.evaluate(10)=='adjusted'


def test_historical_normalization_uses_frozen_spot_not_today(market):
    conn=market(); item=smart.product(conn,10)
    for n,price in enumerate([4010,4020,4030]):
        sid=f's{n}'; eid=f'e{n}'; lid=f'l{n}'; stamp=smart.now_utc().isoformat()
        basis={'product':smart.signature(item),'metal_value_cents':400000}
        data=json.dumps({'lines':[{'listing_id':11+n,'smart_pricing_basis':basis}]})
        conn.execute('''INSERT INTO execution_snapshots(id,checkout_id,version,snapshot_hash,currency,payment_rail,buyer_id,merchandise_cents,tax_cents,grading_cents,other_buyer_charges_cents,card_surcharge_cents,buyer_total_cents,shipping_json,snapshot_json,created_at) VALUES(?,?,1,?,'usd','card',5,0,0,0,0,0,0,'{}',?,?)''',(sid,sid,sid,data,stamp))
        conn.execute("INSERT INTO executions(id,checkout_id,snapshot_id,payment_operation_id,provider_payment_id,buyer_id,state,payment_state,created_at,updated_at) VALUES(?,?,?,?,?,5,'ACTIVE','APPROVED',?,?)",(eid,eid,sid,eid,eid,stamp,stamp))
        conn.execute('''INSERT INTO snapshot_lines(id,snapshot_id,listing_id,seller_id,quantity,buyer_unit_cents,seller_unit_cents,buyer_gross_cents,seller_gross_cents,seller_fee_cents,seller_net_cents,spread_cents) VALUES(?,?,?,?,1,?,?,0,0,0,0,0)''',(lid,sid,11+n,2+n,price*100,price*100))
        conn.execute("INSERT INTO seller_fills(id,execution_id,snapshot_line_id,seller_id,quantity,state,seller_gross_cents,seller_fee_cents,seller_net_cents,spread_cents,created_at,updated_at) VALUES(?,?,?,2,1,'FUNDED',0,0,0,0,?,?)",(eid,eid,lid,stamp,stamp))
        conn.execute("INSERT INTO shipments(id,seller_fill_id,leg_type,state,destination_type,created_at,updated_at) VALUES(?,?,'SELLER_TO_BUYER','DELIVERED','BUYER',?,?)",(eid,eid,stamp,stamp))
    conn.execute('UPDATE spot_price_snapshots SET price_usd=4100'); conn.commit()
    source,values=smart.evidence(conn,10,item,smart.now_utc())
    assert source=='sales_exact'
    assert sorted(v['premium'] for v in values if v['source']=='sales_exact')==[1000,2000,3000]
    assert len(values)==3 # Exact completed evidence stops expansion before active asks.
    assert all(Decimal(v['weight'])>2 for v in values if v['source']=='sales_exact')
    conn.close()
    smart.evaluate(10)
    assert state(market)['settings']['estimate_cents']==2000


@pytest.mark.parametrize('raw',['NaN','Infinity','-0.01','0.001','','10000001'])
def test_invalid_minimum_rejected(raw):
    with pytest.raises(ValueError): smart.parse_form({'smart_pricing_enabled':'1','smart_minimum':raw})


def test_decimal_money_weight_and_outlier_rules():
    assert smart.cents(Decimal('.10')+Decimal('.20'))==30
    assert smart.metal_value_cents({'weight':'1/10 oz'},'1234.56')==12346
    assert smart.metal_value_cents({'weight':'1 g'},'1000')==3215
    assert smart.recommendation([{'premium':v} for v in [1000,1100,1200,1300,999999]],'balanced')==(1150,1150)
    assert smart.comparable_tier({'grade':'ms70'},{'grade':'ms69'}) is None


def test_worker_due_run_does_not_repeat_and_schema_upgrade_idempotent(market):
    conn=market(); smart.ensure_schema(conn); smart.ensure_schema(conn); conn.commit(); conn.close()
    assert smart.run_due()=={'held':1}
    assert smart.run_due()=={}


def test_capture_sale_basis_is_frozen_and_missing_metadata_is_not_invented(market):
    conn=market(); first=smart.capture_sale_basis(conn,10)
    assert first['metal_value_cents']==400000
    conn.execute("UPDATE categories SET weight='unknown'")
    assert smart.capture_sale_basis(conn,10) is None
    conn.close()


@pytest.fixture
def seller_client(market,monkeypatch):
    from flask import Flask
    from core.blueprints.listings import listings_bp
    import core.blueprints.listings.routes as routes
    monkeypatch.setattr(routes,'get_db_connection',market)
    app=Flask(__name__); app.config['SECRET_KEY']='isolated-test-session'
    app.register_blueprint(listings_bp,url_prefix='/listings')
    app.add_url_rule('/account',endpoint='account.account',view_func=lambda:'account')
    return app.test_client()


def test_owner_control_auth_minimum_strategy_and_disable(market,seller_client):
    path='/listings/10/smart-pricing'
    data={'smart_pricing_enabled':'1','smart_pricing_strategy':'big','smart_minimum':'30.00'}
    assert seller_client.post(path,data=data).status_code==401
    with seller_client.session_transaction() as session: session['user_id']=2
    assert seller_client.post(path,data=data).status_code==404
    with seller_client.session_transaction() as session: session['user_id']=1
    assert seller_client.post(path,data=data).status_code==302
    item=state(market)
    assert item['spot_premium']==30 and item['settings']['strategy']=='big'
    assert seller_client.post(path,data={'smart_pricing_enabled':'0','manual_mode':'premium_to_spot'}).status_code==302
    assert state(market)['spot_premium']==30 and not state(market)['settings']['enabled']
    assert seller_client.post(path,data={'smart_pricing_enabled':'0','manual_mode':'static','manual_price':'4150.25'}).status_code==302
    assert state(market)['pricing_mode']=='static'
    assert state(market)['price_per_coin']==4150.25
    assert smart.evaluate(10)=='ineligible'


def test_failed_control_rolls_back_mode_and_minimum(market,seller_client):
    with seller_client.session_transaction() as session: session['user_id']=1
    conn=market(); conn.execute('UPDATE spot_price_snapshots SET as_of=?',((smart.now_utc()-timedelta(days=1)).isoformat(),)); conn.commit(); conn.close()
    response=seller_client.post('/listings/10/smart-pricing',data={'smart_pricing_enabled':'1','smart_minimum':'100.00'})
    assert response.status_code==400
    item=state(market)
    assert item['spot_premium']==20 and item['settings']['minimum_cents']==1000


def test_control_refuses_pending_purchase(market,seller_client):
    with seller_client.session_transaction() as session: session['user_id']=1
    conn=market(); conn.execute("INSERT INTO inventory_reservations(id,checkout_id,listing_id,quantity,state,created_at,updated_at) VALUES('r','c',10,1,'HELD','t','t')"); conn.commit(); conn.close()
    assert seller_client.post('/listings/10/smart-pricing',data={'smart_pricing_enabled':'0'}).status_code==409
    assert state(market)['settings']['enabled']


def test_three_samples_with_an_extreme_outlier_hold_safely():
    assert smart.recommendation([{'premium':p} for p in [1000,2000,999999]],'big') is None


def test_new_evidence_can_raise_premium_and_changes_in_settings_force_review(market):
    conn=market(); conn.execute('UPDATE listings SET spot_premium=spot_premium+100 WHERE id<>10')
    smart.configure(conn,10,('balanced',1000)); conn.commit(); conn.close()
    assert smart.evaluate(10)=='adjusted'
    assert state(market)['spot_premium']==38 # 15% of new $120 fair-market premium, not perpetual discounting.
    conn=market(); smart.configure(conn,10,('big',4000)); conn.commit(); conn.close()
    assert state(market)['spot_premium']==40
    assert state(market)['settings']['last_review'] is None
    smart.evaluate(10)
    assert state(market)['spot_premium']>=40


@pytest.mark.parametrize('mode,smart_on,expected_mode,expected_premium',[
    ('static','0','static',None),('premium_to_spot','0','premium_to_spot',12.34),('static','1','premium_to_spot',25.00)])
def test_listing_creation_integrates_existing_and_smart_modes(auth_client,monkeypatch,mode,smart_on,expected_mode,expected_premium):
    import io
    from core.blueprints.sell import listing_creation as creation
    import services.connect_service as connect_service
    import core.blueprints.bids.auto_match as matches
    import utils.upload_security as upload
    import services.notification_types as notifications
    import services.pricing_service as pricing
    client,user_id=auth_client
    monkeypatch.setattr(creation,'get_db_connection',database.get_db_connection)
    monkeypatch.setattr(creation,'get_dropdown_options',lambda:{})
    monkeypatch.setattr(creation,'validate_category_specification',lambda spec,options:(True,''))
    monkeypatch.setattr(connect_service,'refresh_seller',lambda conn,user_id:True)
    monkeypatch.setattr(matches,'auto_match_listing_to_bids',lambda listing_id:None)
    monkeypatch.setattr(upload,'save_secure_upload',lambda *args,**kwargs:{'success':True,'filename':'test-only.png','path':'test-only.png'})
    monkeypatch.setattr(notifications,'notify_listing_created',lambda *args:None)
    monkeypatch.setattr(creation,'update_bucket_price',lambda *args:None)
    monkeypatch.setattr(pricing,'get_current_spot_prices',lambda:{'gold':4000})
    conn=database.get_db_connection()
    ensure_flow_schema(conn)
    conn.execute("INSERT INTO spot_price_snapshots(metal,price_usd,as_of,source) VALUES('gold',4000,?,'fixture')",(smart.now_utc().isoformat(),))
    conn.commit();conn.close()
    data={'metal':'Gold','product_line':'Smart regression','product_type':'Bar','weight':'1 oz','purity':'.9999','mint':'Test Mint','year':'2026','finish':'BU','quantity':'2','pricing_mode':mode,'price_per_coin':'4123.45','spot_premium':'12.34','floor_price':'3500','pricing_metal':'Gold','smart_pricing_enabled':smart_on,'smart_pricing_strategy':'balanced','smart_minimum':'25.00','item_photo_1':(io.BytesIO(b'fixture'),'fixture.png')}
    if smart_on=='1':
        import core.blueprints.sell.routes as sell_routes
        monkeypatch.setattr(sell_routes,'get_db_connection',database.get_db_connection)
        data['smart_starting']='25.00'
        preview=client.post('/sell/smart-pricing-preview',data={k:v for k,v in data.items() if k!='item_photo_1'})
        assert preview.status_code==200,preview.get_json()
        data['smart_preview_token']=preview.get_json()['token']
    response=client.post('/sell',data=data,headers={'X-Requested-With':'XMLHttpRequest'})
    assert response.status_code==200,response.get_json()
    conn=database.get_db_connection()
    listing=dict(conn.execute('SELECT * FROM listings WHERE seller_id=? ORDER BY id DESC LIMIT 1',(user_id,)).fetchone())
    assert listing['pricing_mode']==expected_mode
    assert listing['spot_premium']==expected_premium
    if smart_on=='1':
        settings=smart.dashboard(conn,listing['id'])
        assert settings['enabled']==1 and settings['minimum_cents']==2500
        assert listing['price_per_coin']==4025
    elif mode=='static':
        assert listing['price_per_coin']==4123.45
    conn.close()
    if smart_on=='1':
        import core.blueprints.listings.routes as edits
        monkeypatch.setattr(edits,'get_db_connection',database.get_db_connection)
        monkeypatch.setattr(edits,'get_dropdown_options',lambda:{})
        monkeypatch.setattr(edits,'validate_category_specification',lambda spec,options:(True,''))
        monkeypatch.setattr(edits,'update_bucket_price',lambda *args:None)
        edit_data={key:value for key,value in data.items() if key!='item_photo_1'}
        edit_data.update(smart_minimum='40.00',smart_pricing_strategy='fast',edit_listing_id=str(listing['id']))
        preview=client.post('/sell/smart-pricing-preview',data=edit_data)
        assert preview.status_code==200,preview.get_json()
        edit_data['smart_preview_token']=preview.get_json()['token']
        response=client.post(f'/listings/edit_listing/{listing["id"]}',data=edit_data,headers={'X-Requested-With':'XMLHttpRequest'})
        assert response.status_code==200,response.get_json()
        conn=database.get_db_connection()
        assert conn.execute('SELECT spot_premium FROM listings WHERE id=?',(listing['id'],)).fetchone()[0]==40
        assert smart.dashboard(conn,listing['id'])['strategy']=='fast'
        conn.close()
        edit_data.update(smart_pricing_enabled='0',pricing_mode='static',price_per_coin='4300.25')
        response=client.post(f'/listings/edit_listing/{listing["id"]}',data=edit_data,headers={'X-Requested-With':'XMLHttpRequest'})
        assert response.status_code==200,response.get_json()
        conn=database.get_db_connection()
        assert conn.execute('SELECT price_per_coin FROM listings WHERE id=?',(listing['id'],)).fetchone()[0]==4300.25
        assert not smart.dashboard(conn,listing['id'])['enabled']
        conn.close()


def test_smart_worker_kill_switch_preserves_premium(market,monkeypatch):
    monkeypatch.setenv('SMART_REPRICING_ENABLED','false')
    assert smart.run_due()=={'paused':1}
    assert state(market)['spot_premium']==20
    assert state(market)['settings']['last_review'] is None


def test_existing_leased_worker_executes_smart_review_and_replay_once(market,monkeypatch):
    from flask import Flask
    from services import flow_worker,flow_of_funds,compensation_service,tax_service,delivery_service,payout_service
    monkeypatch.setattr(flow_of_funds,'get_db_connection',market)
    for name in ('replay_retry_webhooks','expire_due_reservations','mark_tracking_forfeitures','process_tracking_forfeiture_refunds','retry_pending_refunds','dispatch_outbox'):
        monkeypatch.setattr(flow_of_funds,name,lambda:0)
    monkeypatch.setattr(flow_of_funds,'reconcile_internal',lambda:[])
    monkeypatch.setattr(compensation_service,'retry_compensations',lambda:0)
    monkeypatch.setattr(tax_service,'sync_tax_records',lambda:0)
    monkeypatch.setattr(delivery_service,'dispatch_email_queue',lambda:0)
    monkeypatch.setattr(payout_service,'run_daily_releases',lambda:0)
    monkeypatch.setattr(flow_worker,'_provider_reconciliation',lambda:None)
    conn=market(); smart.configure(conn,10,('fast',1000));conn.commit();conn.close()
    app=Flask(__name__)
    assert flow_worker.run_once(app)
    assert state(market)['spot_premium']==15
    assert flow_worker.run_once(app)
    assert len(state(market)['settings']['history'])==1
    conn=market(); lease=conn.execute('SELECT * FROM flow_worker_lease').fetchone();conn.close()
    assert lease['last_success'] and lease['expires_at'] is None


def test_initial_smart_listing_uses_evidence_before_publication_not_bare_minimum(market):
    conn=market()
    conn.execute("INSERT INTO listings VALUES(20,1,1,1,1,'premium_to_spot',0,.01,.01,'Gold',NULL)")
    smart.configure(conn,20,('balanced',0),initial=True)
    assert conn.execute('SELECT spot_premium FROM listings WHERE id=20').fetchone()[0]==20
    data=smart.dashboard(conn,20)
    assert data['estimate_cents']==2000
    assert len(data['history'])==1
    assert data['history'][0]['previous_cents']==0
    conn.rollback();conn.close()
    conn=market();assert conn.execute('SELECT id FROM listings WHERE id=20').fetchone() is None;conn.close()


def weighted_comps(source='sales_exact', recency='1'):
    return [{'premium':p,'source':source,'weight':str(smart.EVIDENCE_WEIGHTS[source]),'recency':recency}
            for p in (15000,16500,19000,22000,24000)]


@pytest.mark.parametrize('strategy,key',[('fast','p25_cents'),('balanced','p50_cents'),('big','p75_cents')])
def test_weighted_initial_targets_shared_distribution(strategy,key):
    result=smart.target_details(weighted_comps(),strategy)
    assert result['target_cents']==result[key]
    assert result['age_adjustment_cents']==0
    assert result['demand_adjustment_cents']==0
    assert result['confidence_label']=='high'


def test_sales_match_and_recency_weights_influence_distribution():
    sales=weighted_comps()
    asks=[dict(v,premium=v['premium']+2000,source='asks_exact',weight='2') for v in sales]
    combined=smart.distribution(sales+asks)
    assert 19000 < combined['p50_cents'] < 20000
    stale=[dict(v,weight='1',recency='.125') for v in sales]
    assert smart.distribution(stale+asks)['p50_cents']>combined['p50_cents']
    assert smart.distribution(weighted_comps('sales_year'))['confidence'] < smart.distribution(sales)['confidence']
    assert smart.distribution(weighted_comps('asks_grade')) is None


def test_bounded_progressive_age_pressure_strategy_order_and_floor():
    values=weighted_comps()
    penalties=[]
    for strategy in ('fast','balanced','big'):
        assert smart.target_details(values,strategy,age_days=1)['age_adjustment_cents']==0
        younger=smart.target_details(values,strategy,age_days=30)
        older=smart.target_details(values,strategy,age_days=300)
        assert older['age_adjustment_cents'] <= younger['age_adjustment_cents'] <= 0
        assert abs(older['age_adjustment_cents']) <= int((older['p75_cents']-older['p25_cents'])*smart.STRATEGIES[strategy]['age_max_spread'])
        assert older['market_lower_cents']<=older['target_cents']<=older['market_upper_cents']
        penalties.append(abs(younger['age_adjustment_cents']))
        assert smart.target_details(values,strategy,minimum=100000,age_days=300)['target_cents']==100000
    assert penalties[0]>penalties[1]>penalties[2]


def test_low_confidence_reduces_age_and_movement(market):
    high=smart.target_details(weighted_comps(), 'fast',age_days=30)
    low=smart.target_details(weighted_comps('asks_family'), 'fast',age_days=30)
    assert abs(low['age_adjustment_cents']) < abs(high['age_adjustment_cents'])
    conn=market();conn.execute("ALTER TABLE categories ADD COLUMN product_line TEXT")
    conn.execute("ALTER TABLE categories ADD COLUMN finish TEXT")
    conn.execute("UPDATE categories SET product_line='American Gold Eagle',year='2025',finish='BU'")
    conn.execute("INSERT INTO categories VALUES(2,'Gold','1 oz','.9999','Bar','Mint','2026','American Gold Eagle','BU')")
    conn.execute('UPDATE listings SET category_id=2 WHERE id=10')
    smart.configure(conn,10,('fast',0));conn.commit();conn.close()
    smart.evaluate(10)
    assert state(market)['spot_premium']==17.5
    assert state(market)['settings']['review']['confidence_label']=='low'



@pytest.mark.parametrize('strategy,hours',[('fast',24),('balanced',48),('big',72)])
def test_exact_review_interval_and_due_selection(market,strategy,hours,monkeypatch):
    now=smart.now_utc()
    conn=market();smart.configure(conn,10,(strategy,0));conn.commit();conn.close()
    smart.evaluate(10,now)
    assert smart.evaluate(10,now+timedelta(hours=hours,seconds=-1))=='cooldown'
    conn=market();conn.execute('UPDATE spot_price_snapshots SET as_of=?',((now+timedelta(hours=hours)).isoformat(),));conn.commit();conn.close()
    monkeypatch.setattr(smart,'now_utc',lambda:now+timedelta(hours=hours))
    assert sum(smart.run_due().values())==1
    assert smart.run_due()=={}


@pytest.mark.parametrize('strategy', ['fast','balanced','big'])
@pytest.mark.parametrize('direction', [-1,1])
def test_new_market_targets_move_both_directions_with_bounded_steps(market,strategy,direction):
    conn=market();smart.configure(conn,10,(strategy,0))
    conn.execute('UPDATE listings SET spot_premium=? WHERE id<>10',(20+direction*10,))
    conn.commit();conn.close()
    assert smart.evaluate(10)=='adjusted'
    item=state(market)
    new=smart.cents(item['spot_premium'])
    assert (new-2000)*direction>0
    review=item['settings']['review']
    assert abs(new-2000)<=review['step_limit_cents']
    assert new!=review['target_cents']
    assert review['demand_adjustment_cents']==0


def test_listing_creation_age_survives_strategy_change(market):
    conn=market();conn.execute('ALTER TABLE listings ADD COLUMN created_at TEXT')
    created=(smart.now_utc()-timedelta(days=60)).isoformat()
    conn.execute('UPDATE listings SET created_at=? WHERE id=10',(created,))
    smart.configure(conn,10,('fast',0));conn.commit();conn.close()
    smart.evaluate(10)
    review=state(market)['settings']['review']
    assert review['age_basis']=='listing_created_at'
    assert review['age_adjustment_cents']<0
    assert Decimal(review['age_days'])>=60


def test_insufficient_effective_evidence_and_outlier_hold():
    assert smart.distribution([{'premium':1000,'weight':'1000'},{'premium':1100,'weight':'1'},{'premium':1200,'weight':'1'}]) is None
    result=smart.distribution(weighted_comps()+[{'premium':999999,'source':'sales_exact','weight':'8'}])
    assert result['rejected_comps']==1
    assert result['p50_cents']==19000


@pytest.fixture
def hierarchy_market(market):
    conn=market()
    for column in ('product_line','coin_series','grade','finish','condition_category','series_variant','special_designation','denomination'):
        conn.execute(f'ALTER TABLE categories ADD COLUMN {column} TEXT')
    for column,kind in [('graded','INTEGER'),('grading_service','TEXT'),('packaging_type','TEXT'),('name','TEXT'),('condition_notes','TEXT'),('issue_total','INTEGER'),('edition_total','INTEGER')]:
        conn.execute(f'ALTER TABLE listings ADD COLUMN {column} {kind}')
    conn.execute("UPDATE categories SET product_line='American Gold Eagle',product_type='Coin',finish='BU'")
    conn.execute('UPDATE listings SET active=0 WHERE id<>10')
    conn.executescript('''CREATE TABLE listing_set_items(id INTEGER PRIMARY KEY,listing_id INTEGER,position_index INTEGER,
      metal TEXT,weight TEXT,purity TEXT,product_type TEXT,mint TEXT,year TEXT,product_line TEXT,grade TEXT,finish TEXT,
      quantity INTEGER DEFAULT 1,packaging_type TEXT,condition_notes TEXT,edition_total INTEGER,graded INTEGER,grading_service TEXT);''')
    conn.commit();conn.close()
    return market


def add_completed(conn, item, premium, number, age_days=0):
    stamp=(smart.now_utc()-timedelta(days=age_days)).isoformat()
    sid,eid,lid=f'hs{number}',f'he{number}',f'hl{number}'
    listing_id=100+number
    basis={'product':smart.signature(item),'metal_value_cents':400000}
    data=json.dumps({'lines':[{'listing_id':listing_id,'smart_pricing_basis':basis}]})
    conn.execute('''INSERT INTO execution_snapshots(id,checkout_id,version,snapshot_hash,currency,payment_rail,buyer_id,merchandise_cents,tax_cents,grading_cents,other_buyer_charges_cents,card_surcharge_cents,buyer_total_cents,shipping_json,snapshot_json,created_at) VALUES(?,?,1,?,'usd','card',5,0,0,0,0,0,0,'{}',?,?)''',(sid,sid,sid,data,stamp))
    conn.execute("INSERT INTO executions(id,checkout_id,snapshot_id,payment_operation_id,provider_payment_id,buyer_id,state,payment_state,created_at,updated_at) VALUES(?,?,?,?,?,5,'ACTIVE','APPROVED',?,?)",(eid,eid,sid,eid,eid,stamp,stamp))
    conn.execute('''INSERT INTO snapshot_lines(id,snapshot_id,listing_id,seller_id,quantity,buyer_unit_cents,seller_unit_cents,buyer_gross_cents,seller_gross_cents,seller_fee_cents,seller_net_cents,spread_cents) VALUES(?,?,?,2,1,?,?,0,0,0,0,0)''',(lid,sid,listing_id,400000+premium,400000+premium))
    conn.execute("INSERT INTO seller_fills(id,execution_id,snapshot_line_id,seller_id,quantity,state,seller_gross_cents,seller_fee_cents,seller_net_cents,spread_cents,created_at,updated_at) VALUES(?,?,?,2,1,'FUNDED',0,0,0,0,?,?)",(eid,eid,lid,stamp,stamp))
    conn.execute("INSERT INTO shipments(id,seller_fill_id,leg_type,state,destination_type,created_at,updated_at) VALUES(?,?,'SELLER_TO_BUYER','DELIVERED','BUYER',?,?)",(eid,eid,stamp,stamp))


@pytest.mark.parametrize('tier,change',[
    ('exact',{}),('year',{'year':'2025'}),('grade',{'grade':'MS68'}),('family',{'packaging_type':'Capsule'})])
def test_explicit_completed_hierarchy(hierarchy_market,tier,change):
    conn=hierarchy_market()
    if tier=='grade':
        conn.execute("UPDATE categories SET grade='MS69'")
        conn.execute("UPDATE listings SET graded=1,grading_service='PCGS'")
    item=smart.product(conn,10)
    for n in range(3):add_completed(conn,dict(item,**change),2000+n*100,n)
    source,values=smart.evidence(conn,10,item,smart.now_utc())
    assert source==('insufficient' if tier=='grade' else 'sales_'+tier)
    assert len(values)==3
    assert (smart.distribution(values) is None)==(tier=='grade')
    conn.close()


@pytest.mark.parametrize('change',[
    {'mint':'Other'}, {'product_line':'Generic gold bar','product_type':'Bar'},
    {'grade':'MS65'}, {'grade':''}, {'grading_service':'NGC'}, {'finish':'Proof'},
    {'finish':'Reverse Proof'}, {'special_designation':'Key Date'}, {'series_variant':'Limited issue'}])
def test_material_identity_differences_rejected(hierarchy_market,change):
    conn=hierarchy_market();item=smart.product(conn,10)
    item.update(grade='MS69',graded=1,grading_service='PCGS')
    assert smart.comparable_tier(smart.signature(item),smart.signature(dict(item,**change))) is None
    conn.close()


@pytest.mark.parametrize('field,value',[('series_variant','Known key-date Eagle'),('isolated_type','one_of_a_kind'),('issue_total',100),('edition_total',50),('special_designation','Rare die error'),('key_date',True)])
def test_rare_detection_warns_and_blocks_year_relaxation(hierarchy_market,field,value):
    conn=hierarchy_market();item=dict(smart.product(conn,10),**{field:value})
    assert smart.nonstandard(item)
    assert smart.comparable_tier(smart.signature(item),smart.signature(dict(item,year='2025'))) is None
    # Exact rare evidence is still usable, never ordinary bullion evidence.
    assert smart.comparable_tier(smart.signature(item),smart.signature(item))=='exact'
    conn.close()


@pytest.mark.parametrize('count,kind,expected',[(0,'sales','insufficient'),(1,'sales','insufficient'),(2,'sales','medium'),(3,'sales','high'),(2,'asks','low'),(3,'asks','medium')])
def test_quality_quantity_confidence_rules(count,kind,expected):
    values=[{'premium':2000+n*20,'source':kind+'_exact','weight':str(smart.EVIDENCE_WEIGHTS[kind+'_exact'])} for n in range(count)]
    result=smart.distribution(values)
    assert (result['confidence_label'] if result else 'insufficient')==expected


def test_completed_evidence_stops_before_asks_and_year_expansion(hierarchy_market):
    conn=hierarchy_market();item=smart.product(conn,10)
    for n in range(2):add_completed(conn,item,2000+n*50,n)
    for n in range(2,5):add_completed(conn,dict(item,year='2025'),5000,n)
    conn.execute('UPDATE listings SET active=1,spot_premium=1000 WHERE id<>10')
    source,values=smart.evidence(conn,10,item,smart.now_utc())
    assert source=='sales_exact' and len(values)==2
    assert smart.distribution(values)['confidence_label']=='medium'
    conn.close()


def test_single_sale_plus_exact_asks_can_be_defensible(hierarchy_market):
    conn=hierarchy_market();item=smart.product(conn,10)
    add_completed(conn,item,2000,0)
    conn.execute('UPDATE listings SET active=1,spot_premium=21 WHERE id IN (11,12)')
    source,values=smart.evidence(conn,10,item,smart.now_utc())
    assert source=='asks_exact'
    assert len(values)==3
    assert max(Decimal(v['weight']) for v in values if v['source'].startswith('sales'))>max(Decimal(v['weight']) for v in values if v['source'].startswith('asks'))
    assert smart.distribution(values)
    conn.close()


def test_asks_extreme_outlier_and_different_mint_do_not_force_recommendation(hierarchy_market):
    conn=hierarchy_market();item=smart.product(conn,10)
    conn.execute('UPDATE listings SET active=1,spot_premium=20 WHERE id<>10')
    conn.execute('UPDATE listings SET spot_premium=99999 WHERE id=13')
    source,values=smart.evidence(conn,10,item,smart.now_utc())
    result=smart.distribution(values)
    assert source=='asks_exact' and result['p50_cents']==2000
    assert result['rejected_comps']==1
    conn.execute("UPDATE categories SET mint='Other' WHERE id=1")
    source,values=smart.evidence(conn,10,item,smart.now_utc())
    assert source=='insufficient' and values==[]
    conn.close()


def test_insufficient_hold_then_evidence_transition(hierarchy_market):
    conn=hierarchy_market();smart.configure(conn,10,('fast',0),initial=True)
    item=smart.product(conn,10)
    conn.execute("UPDATE smart_pricing_settings SET enabled_at=?,last_review=NULL",((smart.now_utc()-timedelta(days=365)).isoformat(),))
    conn.commit();conn.close()
    assert smart.evaluate(10)=='held'
    assert state(hierarchy_market)['spot_premium']==20
    assert state(hierarchy_market)['settings']['review']['confidence_label']=='insufficient'
    conn=hierarchy_market()
    for n in range(3):add_completed(conn,item,3000,n)
    conn.execute('UPDATE smart_pricing_settings SET last_review=NULL');conn.commit();conn.close()
    assert smart.evaluate(10)=='adjusted'
    assert 20<state(hierarchy_market)['spot_premium']<30


@pytest.fixture
def preview_client(hierarchy_market,monkeypatch):
    from flask import Flask
    from core.blueprints.sell import sell_bp
    import core.blueprints.sell.routes as routes
    import utils.auth_utils as auth
    monkeypatch.setattr(routes,'get_db_connection',hierarchy_market)
    monkeypatch.setattr(auth,'is_user_frozen',lambda user_id:False)
    app=Flask(__name__);app.config['SECRET_KEY']='isolated-preview-test'
    app.register_blueprint(sell_bp)
    client=app.test_client()
    with client.session_transaction() as session:session['user_id']=1
    return client


def preview_data(**changes):
    return dict(metal='Gold',weight='1 oz',purity='.9999',product_type='Coin',mint='Mint',year='2026',
                product_line='American Gold Eagle',finish='BU',smart_pricing_strategy='balanced',smart_minimum='10.00',**changes)


def test_preview_insufficient_requires_seed_and_displays_exact_total(preview_client,hierarchy_market):
    response=preview_client.post('/sell/smart-pricing-preview',data=preview_data())
    assert response.status_code==200
    assert response.json['needs_starting'] and 'token' not in response.json
    data=preview_data(smart_starting='25.00')
    response=preview_client.post('/sell/smart-pricing-preview',data=data)
    quote=response.json
    assert quote['seeded'] and quote['confidence_label']=='insufficient'
    assert quote['initial_premium_cents']==2500 and quote['initial_price_cents']==402500
    assert 'fair_premium_cents' not in quote
    with preview_client.application.app_context():
        conn=hierarchy_market();item=smart.form_item(data,1)
        approved=smart.validate_preview(conn,item,('balanced',1000),dict(data,smart_preview_token=quote['token']))
        assert approved['initial_price_cents']==quote['initial_price_cents']
        with pytest.raises(ValueError,match='starting premium'):smart.initial_quote(conn,item,'balanced',1000)
        conn.close()


def test_strategy_minimum_preview_changes_and_publication_equality(preview_client,hierarchy_market):
    conn=hierarchy_market();item=smart.product(conn,10)
    for n,p in enumerate((1000,2000,3000)):add_completed(conn,item,p,n)
    conn.commit();conn.close()
    prices=[]
    for strategy in ('fast','balanced','big'):
        data=preview_data();data['smart_pricing_strategy']=strategy
        quote=preview_client.post('/sell/smart-pricing-preview',data=data).json
        assert not quote['seeded'] and quote['fair_premium_cents']==2000
        prices.append(quote['initial_premium_cents'])
        assert quote['initial_price_cents']==400000+quote['initial_premium_cents']
        with preview_client.application.app_context():
            conn=hierarchy_market();approval=smart.validate_preview(conn,smart.product(conn,10),(strategy,1000),dict(data,smart_preview_token=quote['token']))
            smart.configure(conn,10,(strategy,1000),approval=approval)
            assert smart.cents(conn.execute('SELECT price_per_coin FROM listings WHERE id=10').fetchone()[0])==quote['initial_price_cents']
            conn.commit();conn.close()
    assert prices[0]<prices[1]<prices[2]
    data=preview_data();data['smart_minimum']='50.00'
    assert preview_client.post('/sell/smart-pricing-preview',data=data).json['initial_premium_cents']==5000


def test_preview_token_tampering_spot_change_and_wrong_owner_block(preview_client,hierarchy_market):
    data=preview_data(smart_starting='25.00')
    quote=preview_client.post('/sell/smart-pricing-preview',data=data).json
    with preview_client.application.app_context():
        conn=hierarchy_market();item=smart.form_item(data,1)
        with pytest.raises(ValueError):smart.validate_preview(conn,item,('balanced',1000),dict(data,smart_preview_token='forged'))
        with pytest.raises(ValueError):smart.validate_preview(conn,dict(item,seller_id=2),('balanced',1000),dict(data,smart_preview_token=quote['token']))
        conn.execute('UPDATE spot_price_snapshots SET price_usd=4100')
        with pytest.raises(ValueError,match='changed'):smart.validate_preview(conn,item,('balanced',1000),dict(data,smart_preview_token=quote['token']))
        conn.close()


@pytest.mark.parametrize('mode',['one_of_a_kind','set'])
def test_nonstandard_warning_requires_active_acknowledgment(preview_client,hierarchy_market,mode):
    data=preview_data(is_isolated='1',listing_title='Special product')
    if mode=='set':data['is_set']='1'
    response=preview_client.post('/sell/smart-pricing-preview',data=data)
    assert response.json=={'success':True,'warning_required':True}
    assert 'token' not in response.json
    if mode=='one_of_a_kind':
        data.update(smart_warning_acknowledged='1',smart_starting='30.00')
        quote=preview_client.post('/sell/smart-pricing-preview',data=data).json
        assert quote['warning_required'] and quote['token']
        with preview_client.application.app_context():
            conn=hierarchy_market();item=smart.form_item(data,1)
            approval=smart.validate_preview(conn,item,('balanced',1000),dict(data,smart_preview_token=quote['token']))
            assert approval['warning_acknowledged']
            conn.close()


def set_parts():
    return [dict(metal='Gold',weight='1 oz',purity='.9999',product_type='Coin',mint='Mint',year='2026',product_line='American Gold Eagle',finish='BU',quantity=2),
            dict(metal='Silver',weight='1 oz',purity='.999',product_type='Coin',mint='Mint',year='2026',product_line='American Silver Eagle',finish='BU',quantity=3)]


def test_exact_set_preview_uses_all_metal_contents_not_unrelated_premiums(preview_client,hierarchy_market,monkeypatch):
    conn=hierarchy_market();conn.execute("INSERT INTO spot_price_snapshots VALUES('silver',50,?,'fixture')",(smart.now_utc().isoformat(),))
    conn.commit();conn.close()
    data=preview_data(is_set='1',is_isolated='1',listing_title='Eagle set',smart_warning_acknowledged='1',smart_starting='100.00',set_items_json=json.dumps(set_parts()))
    quote=preview_client.post('/sell/smart-pricing-preview',data=data).json
    assert quote['seeded'] and quote['metal_value_cents']==815000 and quote['initial_price_cents']==825000
    item=smart.form_item(data,1)
    conn=hierarchy_market()
    assert smart.comparable_tier(smart.signature(item),smart.signature(smart.product(conn,10))) is None
    for n in range(3):add_completed(conn,item,15000+n*100,n)
    conn.commit();conn.close()
    quote=preview_client.post('/sell/smart-pricing-preview',data=data).json
    assert not quote['seeded'] and quote['source']=='sales_exact' and quote['fair_premium_cents']==15100
    # Full normalized set configuration is required, even if only count differs.
    changed=set_parts();changed[0]['quantity']=1
    other=smart.form_item(dict(data,set_items_json=json.dumps(changed)),1)
    assert smart.comparable_tier(smart.signature(item),smart.signature(other)) is None


def test_exact_rare_completed_evidence_survives_warning(preview_client,hierarchy_market):
    data=preview_data(is_isolated='1',listing_title='Rare Eagle',smart_warning_acknowledged='1')
    item=smart.form_item(data,1)
    conn=hierarchy_market()
    for n in range(2):add_completed(conn,item,50000+n*100,n)
    conn.commit();conn.close()
    quote=preview_client.post('/sell/smart-pricing-preview',data=data).json
    assert not quote['seeded'] and quote['initial_premium_cents']==50050
    assert quote['confidence_label']=='medium'


def test_engine_preview_queries_no_external_comparable_or_spot_provider(preview_client,hierarchy_market,monkeypatch):
    import requests
    import services.spot_price_service as spot
    def forbidden(*args,**kwargs):raise AssertionError('Provider should not be queried')
    monkeypatch.setattr(requests.sessions.Session,'request',forbidden)
    monkeypatch.setattr(spot,'get_current_spot_prices',forbidden)
    assert preview_client.post('/sell/smart-pricing-preview',data=preview_data(smart_starting='20.00')).status_code==200
    assert smart.evaluate(10)=='held'


@pytest.mark.parametrize('stale',[False,True])
def test_set_creation_preview_publication_and_atomic_rejection(auth_client,monkeypatch,stale):
    import io
    from core.blueprints.sell import listing_creation as creation
    import core.blueprints.sell.routes as sell_routes
    import core.blueprints.listings.routes as edits
    import services.connect_service as connect
    import services.pricing_service as pricing
    import core.blueprints.bids.auto_match as matches
    import utils.upload_security as upload
    import services.notification_types as notifications
    from core.blueprints.checkout.routes import _fetch_listing_pricing_meta, _pricing_metals
    client,user_id=auth_client
    for module in (creation,sell_routes,edits,pricing):monkeypatch.setattr(module,'get_db_connection',database.get_db_connection)
    monkeypatch.setattr(creation,'get_dropdown_options',lambda:{})
    monkeypatch.setattr(creation,'validate_category_specification',lambda *a:(True,''))
    monkeypatch.setattr(connect,'refresh_seller',lambda *a:True)
    monkeypatch.setattr(matches,'auto_match_listing_to_bids',lambda *a:None)
    monkeypatch.setattr(upload,'save_secure_upload',lambda *a,**k:{'success':True,'filename':'test-only.png','path':'test-only.png'})
    monkeypatch.setattr(notifications,'notify_listing_created',lambda *a:None)
    monkeypatch.setattr(creation,'update_bucket_price',lambda *a:None)
    monkeypatch.setattr(pricing,'get_current_spot_prices',lambda:{'gold':4000,'silver':50})
    conn=database.get_db_connection();ensure_flow_schema(conn)
    for metal,price in [('gold',4000),('silver',50)]:
        conn.execute('INSERT INTO spot_price_snapshots(metal,price_usd,as_of,source) VALUES(?,?,?,?)',(metal,price,smart.now_utc().isoformat(),'fixture'))
    before=conn.execute('SELECT COUNT(*) FROM listings WHERE seller_id=?',(user_id,)).fetchone()[0]
    conn.commit();conn.close()
    parts=set_parts()
    data=dict(is_set='1',is_isolated='1',listing_title='Eagle set',quantity='1',pricing_mode='premium_to_spot',spot_premium='100',floor_price='.01',
              smart_pricing_enabled='1',smart_pricing_strategy='balanced',smart_minimum='50.00',smart_starting='100.00',smart_warning_acknowledged='1',set_items_json=json.dumps(parts))
    quote=client.post('/sell/smart-pricing-preview',data=data)
    assert quote.status_code==200,quote.json
    data['smart_preview_token']=quote.json['token']
    if stale:
        conn=database.get_db_connection();conn.execute("UPDATE spot_price_snapshots SET price_usd=60 WHERE metal='silver'");conn.commit();conn.close()
    for key in ('cover_photo','set_item_photo_1_1','set_item_photo_2_1'):data[key]=(io.BytesIO(b'fixture'),key+'.png')
    response=client.post('/sell',data=data,headers={'X-Requested-With':'XMLHttpRequest'})
    conn=database.get_db_connection()
    if stale:
        assert response.status_code==400,response.json
        assert conn.execute('SELECT COUNT(*) FROM listings WHERE seller_id=?',(user_id,)).fetchone()[0]==before
        assert 'changed' in response.json['message']
        conn.close();return
    assert response.status_code==200,response.json
    row=dict(conn.execute('SELECT * FROM listings WHERE seller_id=? ORDER BY id DESC LIMIT 1',(user_id,)).fetchone())
    item=smart.product(conn,row['id'])
    assert smart.cents(row['price_per_coin'])==quote.json['initial_price_cents']==825000
    assert pricing.get_effective_price(item,{'gold':4000,'silver':50})==8250
    assert pricing.get_effective_price(item,{'gold':4100,'silver':60})==8480
    meta=_fetch_listing_pricing_meta(conn,[row['id']])[row['id']]
    assert _pricing_metals(meta)=={'gold','silver'}
    assert pricing.get_effective_price(meta,{'gold':4000,'silver':50})==8250
    basis=smart.capture_sale_basis(conn,row['id'])
    assert basis['metal_value_cents']==815000 and len(basis['spot_snapshots'])==2
    review=smart.dashboard(conn,row['id'])
    assert json.loads(review['history'][0]['reason_json'])['warning_acknowledged']
    assert review['review']['seeded']
    conn.close()
    # Same exact set can be repriced later; scarcity never becomes a reason to discount.
    assert smart.evaluate(row['id'])=='cooldown'
    # Editing set contents must validate and save the same exact preview atomically.
    monkeypatch.setattr(edits,'get_dropdown_options',lambda:{})
    monkeypatch.setattr(edits,'validate_category_specification',lambda *a:(True,''))
    monkeypatch.setattr(edits,'update_bucket_price',lambda *a:None)
    edit_data={k:v for k,v in data.items() if not isinstance(v,tuple)}
    edit_data.update(edit_listing_id=str(row['id']),smart_starting='120.00',spot_premium='120')
    conn=database.get_db_connection()
    saved_parts=smart.product(conn,row['id'])['set_items'];conn.close()
    saved_parts[0]['quantity']=3
    edit_data['set_items_json']=json.dumps(saved_parts)
    quote=client.post('/sell/smart-pricing-preview',data=edit_data)
    assert quote.status_code==200,quote.json
    edit_data['smart_preview_token']=quote.json['token']
    response=client.post(f"/listings/edit_listing/{row['id']}",data=edit_data,headers={'X-Requested-With':'XMLHttpRequest'})
    assert response.status_code==200,response.json
    conn=database.get_db_connection()
    item=smart.product(conn,row['id'])
    assert smart.cents(pricing.get_effective_price(item,{'gold':4000,'silver':50}))==quote.json['initial_price_cents']==1227000
    assert item['set_items'][0]['quantity']==3
    conn.close()


def test_legacy_frozen_signatures_normalize_without_inventing_collector_identity(hierarchy_market):
    conn=hierarchy_market();item=smart.product(conn,10);current=smart.signature(item)
    old={k:v for k,v in current.items() if k not in ('issue_total','edition_total','set_configuration','rare_identity')}
    old['weight']='1 oz'
    assert smart.comparable_tier(current,old)=='exact'
    assert smart.comparable_tier(smart.signature(dict(item,isolated_type='one_of_a_kind',name='Rare Eagle')),old) is None
    conn.close()


def test_expired_preview_never_authorizes_activation(preview_client,hierarchy_market,monkeypatch):
    from itsdangerous import TimestampSigner
    import time
    data=preview_data(smart_starting='20.00')
    with monkeypatch.context() as patch:
        patch.setattr(TimestampSigner,'get_timestamp',lambda self:int(time.time())-901)
        with preview_client.application.app_context():
            conn=hierarchy_market();quote=smart.preview_quote(conn,smart.form_item(data,1),'balanced',1000,'20.00');conn.close()
    with preview_client.application.app_context():
        conn=hierarchy_market()
        with pytest.raises(ValueError,match='confirm'):smart.validate_preview(conn,smart.form_item(data,1),('balanced',1000),dict(data,smart_preview_token=quote['token']))
        conn.close()


def test_fractional_weight_preview_and_dynamic_listing_round_identically():
    from services.pricing_service import get_effective_price
    item={'pricing_mode':'premium_to_spot','pricing_metal':'gold','metal':'Gold','weight':'1/2 oz','spot_premium':20,'floor_price':0}
    assert smart.metal_value_cents(item,4000.01)==200001
    assert get_effective_price(item,{'gold':4000.01})==2020.01
    assert get_effective_price(dict(item,pricing_mode='static',price_per_coin=2500),{'gold':4000.01})==2500


@pytest.mark.parametrize('change,kind,reason',[
    ({},'STANDARDIZED','STANDARD_BULLION_PRODUCT'),
    ({'year':'2021'},'STANDARDIZED','STANDARD_BULLION_PRODUCT'),
    ({'year':'1986'},'STANDARDIZED','STANDARD_BULLION_PRODUCT'),
    ({'key_date':True},'RARE_OR_SPECIAL','KEY_DATE'),
    ({'finish':'Proof'},'RARE_OR_SPECIAL','PROOF'),
    ({'finish':'Reverse Proof'},'RARE_OR_SPECIAL','REVERSE_PROOF'),
    ({'finish':'Burnished'},'RARE_OR_SPECIAL','SPECIAL_STRIKE'),
    ({'edition_total':100},'RARE_OR_SPECIAL','NUMBERED_ITEM'),
    ({'issue_number':5},'RARE_OR_SPECIAL','NUMBERED_ITEM'),
    ({'series_variant':'Limited Edition'},'RARE_OR_SPECIAL','LIMITED_EDITION'),
    ({'special_designation':'Anniversary'},'RARE_OR_SPECIAL','COMMEMORATIVE'),
    ({'low_mintage':True},'RARE_OR_SPECIAL','LOW_MINTAGE'),
    ({'is_error':True},'RARE_OR_SPECIAL','RARE_VARIANT'),
    ({'isolated_type':'set'},'SET','MULTI_ITEM_CONFIGURATION'),
    ({'set_items':[{},{}]},'SET','MULTI_ITEM_CONFIGURATION'),
    ({'is_isolated':1},'ONE_OF_A_KIND','EXPLICIT_UNIQUE_ITEM_FLAG'),
    ({'product_line':'Unrecognized coin'},'UNKNOWN_NONSTANDARD','UNKNOWN_PRODUCT_CLASS'),
    ({'finish':''},'UNKNOWN_NONSTANDARD','UNKNOWN_PRODUCT_CLASS'),
    ({'listing_description':'EXTREMELY RARE BEAUTIFUL COIN!!! one of a kind set'},'STANDARDIZED','STANDARD_BULLION_PRODUCT'),
    ({'condition_notes':'rare die error'},'STANDARDIZED','STANDARD_BULLION_PRODUCT'),
])
def test_structured_classification_year_rules(hierarchy_market,change,kind,reason):
    conn=hierarchy_market();item=dict(smart.product(conn,10),**change)
    result=smart.classify_smart_pricing_item(item)
    assert result['classification']==kind and reason in result['reasons']
    assert smart.classify_year_comparability(item)['classification']==('YEAR_RELAXABLE' if kind=='STANDARDIZED' else 'YEAR_SENSITIVE')
    if kind=='STANDARDIZED':
        assert smart.comparable_tier(smart.signature(dict(item,year='2021')),smart.signature(dict(item,year='2025')))=='year'
    else:
        assert smart.comparable_tier(smart.signature(dict(item,year='2021')),smart.signature(dict(item,year='2025'))) is None
    conn.close()


@pytest.mark.parametrize('grade,other',[('MS69','MS70'),('MS70','MS69'),('MS68','MS69')])
def test_adjacent_only_insufficient_and_exact_grade_primary(hierarchy_market,grade,other):
    conn=hierarchy_market();item=dict(smart.product(conn,10),grade=grade,graded=1,grading_service='PCGS')
    assert smart.comparable_tier(smart.signature(item),smart.signature(dict(item,grade=other)))=='grade'
    conn.execute('UPDATE listings SET active=0 WHERE id<>10')
    for n in range(5):add_completed(conn,dict(item,grade=other),2000+n*10,n)
    source,values=smart.evidence(conn,10,item,smart.now_utc())
    assert source=='insufficient' and smart.distribution(values) is None
    for n in range(3):add_completed(conn,item,2200+n*10,10+n)
    source,values=smart.evidence(conn,10,item,smart.now_utc())
    assert source=='sales_exact' and len(values)==3
    conn.close()


@pytest.mark.parametrize('count',[2,5,100])
def test_grade_corroboration_is_capped_and_never_high(count):
    exact=[{'premium':2200,'source':'sales_exact','weight':'8'}]
    adjacent=[{'premium':2100+n%3*10,'source':'sales_grade','weight':'2'} for n in range(count)]
    result=smart.distribution(exact+adjacent)
    assert result and result['confidence_label'] in ('low','medium')
    qualified=result['qualified_comps']
    assert sum(Decimal(v['weight']) for v in qualified if v['source']=='sales_grade')<=4
    assert result['p50_cents']>=2150
    assert adjacent[0]['weight']=='2'  # Scoring does not mutate pooled audit observations.
    assert smart.distribution([dict(v,premium=10000) for v in adjacent]+exact) is None


@pytest.mark.parametrize('change',[{'grade':''},{'grading_service':'NGC'},{'finish':'Proof'},{'finish':'Reverse Proof'},{'special_designation':'First Strike'}])
def test_grade_identity_guards(hierarchy_market,change):
    conn=hierarchy_market();item=dict(smart.product(conn,10),grade='MS70',graded=1,grading_service='PCGS')
    assert smart.comparable_tier(smart.signature(item),smart.signature(dict(item,**({'grade':'MS69'}|change|({'graded':0} if 'grade' in change else {}))))) is None
    conn.close()


@pytest.mark.parametrize('missing',[False,True])
def test_spot_outage_friendly_and_inline_retry_recovers(preview_client,hierarchy_market,missing):
    conn=hierarchy_market()
    if missing:conn.execute('DELETE FROM spot_price_snapshots')
    else:conn.execute('UPDATE spot_price_snapshots SET as_of=?',((smart.now_utc()-timedelta(hours=2)).isoformat(),))
    conn.commit();conn.close()
    data=preview_data(smart_starting='20.00')
    response=preview_client.post('/sell/smart-pricing-preview',data=data)
    assert response.status_code==400 and response.json['code']=='SMART_SPOT_UNAVAILABLE'
    assert response.json['title']=='Current metal pricing is temporarily unavailable'
    assert 'token' not in response.json
    assert not any(word in response.json['message'].lower() for word in ('null','nan','snapshot','provider','traceback','database','stale'))
    conn=hierarchy_market();conn.execute('INSERT INTO spot_price_snapshots VALUES(?,?,?,?)',('gold',4100,smart.now_utc().isoformat(),'fixture'));conn.commit();conn.close()
    response=preview_client.post('/sell/smart-pricing-preview',data=data)
    assert response.status_code==200 and response.json['token']
    assert response.json['initial_price_cents']==response.json['metal_value_cents']+response.json['initial_premium_cents']
    assert response.json['metal_value_cents']==410000


def test_classifier_audit_and_marketing_does_not_change_algorithm(hierarchy_market):
    conn=hierarchy_market();item=smart.product(conn,10)
    marketing=dict(item,name='EXTREMELY RARE!',description='one of a kind set',condition_notes='Rare Beautiful Coin!')
    assert smart.signature(marketing)==smart.signature(item)
    assert smart.classify_smart_pricing_item(marketing)['secondary_signals']==['POSSIBLE_SPECIAL_ITEM_UNCONFIRMED']
    assert smart.nonstandard(marketing) is False
    smart.configure(conn,10,('balanced',1000),initial=True)
    assert smart.dashboard(conn,10)['review']['classification']['classification']=='STANDARDIZED'
    conn.commit();conn.close()
    smart.evaluate(10,smart.now_utc()+timedelta(days=3))
    conn=hierarchy_market();assert smart.dashboard(conn,10)['review']['classification']['reasons']==['STANDARD_BULLION_PRODUCT'];conn.close()


def test_preview_unexpected_error_never_exposes_details(preview_client,monkeypatch):
    monkeypatch.setattr(smart,'preview_quote',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('provider secret database traceback')))
    response=preview_client.post('/sell/smart-pricing-preview',data=preview_data(smart_starting='20.00'))
    assert response.status_code==503
    assert response.json['message']=='Please try again shortly or use manual pricing.'


def test_fractional_bid_price_uses_actual_weight_and_ceiling():
    from services.pricing_service import get_effective_bid_price
    bid={'pricing_mode':'premium_to_spot','pricing_metal':'gold','spot_premium':20,'ceiling_price':3000,'weight':'1/2 oz'}
    assert get_effective_bid_price(bid,{'gold':4000.01})==2020.01
    assert get_effective_bid_price(dict(bid,ceiling_price=2000),{'gold':4000.01})==2000


def test_adjacent_grade_requires_explicit_certification(hierarchy_market):
    conn=hierarchy_market();item=dict(smart.product(conn,10),grade='MS70',graded=0,grading_service='PCGS')
    assert smart.comparable_tier(smart.signature(item),smart.signature(dict(item,grade='MS69'))) is None
    conn.close()


@pytest.mark.parametrize('field,value',[('as_of','invalid internal feed timestamp'),('price_usd',None),('price_usd',-1)])
def test_unusable_spot_records_are_friendly(preview_client,hierarchy_market,field,value):
    conn=hierarchy_market();conn.execute(f'UPDATE spot_price_snapshots SET {field}=?',(value,));conn.commit();conn.close()
    response=preview_client.post('/sell/smart-pricing-preview',data=preview_data(smart_starting='20.00'))
    assert response.status_code==400 and response.json['code']=='SMART_SPOT_UNAVAILABLE'
    assert response.json['message']==smart.SPOT_MESSAGE


@pytest.mark.parametrize('strategy', ['fast','balanced','big'])
def test_recommended_proceeds_use_canonical_fee(preview_client,hierarchy_market,strategy):
    from services.flow_of_funds import seller_fee_cents
    conn=hierarchy_market();item=smart.product(conn,10)
    for n in range(3):add_completed(conn,item,20000+n*1000,n)
    conn.commit();conn.close()
    response=preview_client.post('/sell/smart-pricing-preview',data=preview_data(quantity='3')|{'smart_pricing_strategy':strategy})
    assert response.status_code==200,response.json
    quote=response.json;price=quote['initial_price_cents']
    assert not quote['seeded']
    assert quote['seller_fee_cents']==seller_fee_cents(price)
    assert quote['estimated_net_cents']==price-seller_fee_cents(price)
    assert quote['estimated_total_net_cents']==price*3-seller_fee_cents(price*3)


def test_smart_ui_has_no_dollar_entry_fields():
    from pathlib import Path
    from bs4 import BeautifulSoup
    html=BeautifulSoup(Path('templates/sell.html').read_text(),'html.parser')
    panel=html.select_one('#smart-pricing-panel')
    assert not panel.select('input[type="number"],input[type="text"]')
    assert panel.select_one('#smart-minimum')['type']=='hidden'
    assert panel.select_one('#smart-starting')['type']=='hidden'
    assert panel.select_one('#smart-preview-net')


@pytest.mark.parametrize('old_cache',[False,True])
def test_shared_sell_spot_cache_refreshes_canonical_preview(hierarchy_market,monkeypatch,old_cache):
    import services.spot_price_service as spot
    conn=hierarchy_market();item=smart.product(conn,10)
    conn.execute('CREATE TABLE spot_prices(metal TEXT PRIMARY KEY,price_usd_per_oz REAL,updated_at TEXT,source TEXT)')
    stamp=smart.now_utc()-timedelta(hours=2) if old_cache else smart.now_utc()
    conn.execute('INSERT INTO spot_prices VALUES(?,?,?,?)',('gold',4197.80,stamp.isoformat(),'fixture-live-cache'))
    conn.execute('UPDATE spot_price_snapshots SET as_of=?',((smart.now_utc()-timedelta(hours=3)).isoformat(),));conn.commit()
    calls=[]
    def refresh():
        calls.append(True)
        other=hierarchy_market();other.execute('UPDATE spot_prices SET updated_at=?',(smart.now_utc().isoformat(),));other.commit();other.close()
        return {'gold':4197.80}
    monkeypatch.setattr(spot,'get_current_spot_prices',refresh)
    smart.refresh_preview_spot_prices(conn,item)
    assert bool(calls)==old_cache
    basis,_=smart.metal_basis(conn,item,smart.now_utc())
    assert basis==419780
    assert smart.fresh_spot(conn,item,smart.now_utc())['source']=='fixture-live-cache'
    conn.close()


def test_stale_cache_fallback_does_not_masquerade_as_fresh_spot(hierarchy_market,monkeypatch):
    import services.spot_price_service as spot
    conn=hierarchy_market();item=smart.product(conn,10)
    conn.execute('CREATE TABLE spot_prices(metal TEXT PRIMARY KEY,price_usd_per_oz REAL,updated_at TEXT,source TEXT)')
    old=(smart.now_utc()-timedelta(hours=2)).isoformat()
    conn.execute('INSERT INTO spot_prices VALUES(?,?,?,?)',('gold',4197.80,old,'fixture'))
    conn.execute('UPDATE spot_price_snapshots SET as_of=?',(old,));conn.commit()
    monkeypatch.setattr(spot,'get_current_spot_prices',lambda:{'gold':4197.80})
    smart.refresh_preview_spot_prices(conn,item)
    with pytest.raises(smart.SpotUnavailable):smart.metal_basis(conn,item,smart.now_utc())
    assert conn.execute('SELECT COUNT(*) FROM spot_price_snapshots').fetchone()[0]==1
    conn.close()


@pytest.mark.parametrize('minutes,fresh',[(-1,False),(1,True),(120,False)])
def test_spot_cache_freshness_uses_utc_and_rejects_future_times(hierarchy_market,monkeypatch,minutes,fresh):
    import services.spot_price_service as spot
    conn=hierarchy_market();conn.execute('CREATE TABLE spot_prices(metal TEXT PRIMARY KEY,price_usd_per_oz REAL,updated_at TEXT,source TEXT)')
    # SQLite CURRENT_TIMESTAMP stores naive UTC, not the machine's local clock.
    stamp=(smart.now_utc()-timedelta(minutes=minutes)).replace(tzinfo=None).isoformat()
    conn.execute('INSERT INTO spot_prices VALUES(?,?,?,?)',('gold',4197.8,stamp,'fixture'));conn.commit();conn.close()
    monkeypatch.setattr(spot,'get_db_connection',hierarchy_market)
    assert spot.is_cache_fresh()[0]==fresh
