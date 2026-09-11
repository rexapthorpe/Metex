import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import services.flow_of_funds as flow


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path=tmp_path/'flow.db'
    def connect():
        c=sqlite3.connect(path); c.row_factory=sqlite3.Row; return c
    monkeypatch.setattr(flow,'get_db_connection',connect)
    c=connect()
    c.executescript('''
      CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT,password TEXT,username TEXT,stripe_customer_id TEXT);
      CREATE TABLE categories(id INTEGER PRIMARY KEY,metal TEXT,product_type TEXT);
      CREATE TABLE listings(id INTEGER PRIMARY KEY,seller_id INTEGER,category_id INTEGER,quantity INTEGER,active INTEGER,price_per_coin REAL);
      CREATE TABLE orders(id INTEGER PRIMARY KEY AUTOINCREMENT,buyer_id INTEGER,total_price REAL,buyer_card_fee REAL,tax_amount REAL,tax_rate REAL,
        shipping_address TEXT,recipient_first_name TEXT,recipient_last_name TEXT,stripe_payment_intent_id TEXT,paid_at TEXT,payment_method_type TEXT,
        requires_payment_clearance INTEGER,payment_status TEXT,status TEXT,payout_status TEXT,payment_cleared_at TEXT,payment_cleared_by_admin_id INTEGER);
      CREATE TABLE order_items(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER,listing_id INTEGER,quantity INTEGER,price_each REAL,
        price_at_purchase REAL,seller_price_each REAL,third_party_grading_requested INTEGER,grading_fee_charged REAL,grading_status TEXT);
      CREATE TABLE cart(id INTEGER PRIMARY KEY,user_id INTEGER,listing_id INTEGER,quantity INTEGER);
    ''')
    c.executemany('INSERT INTO users VALUES (?,?,?,?,?)',[(1,'b@x','x','b',None),(2,'s@x','x','s',None),(3,'s2@x','x','s2',None)])
    c.executemany('INSERT INTO listings VALUES (?,?,?,?,?,?)',[(10,2,1,20,1,100.0),(11,3,1,20,1,200.0)])
    flow.ensure_flow_schema(c); c.commit(); c.close()
    return connect


def approve(c,*keys):
    for key in keys: c.execute('UPDATE flow_policy_config SET approved=1 WHERE key=?',(key,))
    c.commit()


def prep(connect,items=None,rail='us_bank_account',tax=0,key='k1',grading=0):
    c=connect()
    checkout,snapshot,_=flow.prepare_checkout(1,items or [{'listing_id':10,'quantity':1,'price_each':100}],rail,tax,
        {'shipping_address':'1 Main','recipient_first':'A','recipient_last':'B'},key,grading_fee_per_unit_cents=grading,conn=c)
    op,_=flow.claim_operation(c,'PAYMENT','payment:'+checkout['id'],'checkout',checkout['id'],snapshot['buyer_total_cents'],
                              {'snapshot_hash':snapshot['snapshot_hash']})
    flow.bind_provider_payment(checkout['id'],'pi_1',op['id'],conn=c); c.commit(); c.close()
    return checkout,snapshot


def payment(checkout,snapshot,status='succeeded'):
    return {'id':'pi_1','amount':snapshot['buyer_total_cents'],'currency':'usd','status':status,
            'metadata':{'checkout_id':checkout['id'],'buyer_id':'1','snapshot_hash':snapshot['snapshot_hash']},
            'latest_charge':'ch_1'}


def test_t01_ach_1000_fee_and_net():
    assert flow.seller_fee_cents(100_000)==5_000
    assert 100_000-flow.seller_fee_cents(100_000)==95_000
    assert flow.card_surcharge_cents(100_000,0)==0


def test_card_gross_up_exact_examples():
    assert flow.card_surcharge_cents(100_000)==3_082
    assert flow.card_surcharge_cents(10_000)==308
    assert round((100_000+3_082)*.0299)==3_082


def test_t02_positive_bid_ask_spread(db):
    checkout,snapshot=prep(db,[{'listing_id':10,'quantity':1,'price_each':1001,'seller_price_each':1000}])
    c=db(); line=c.execute('SELECT * FROM snapshot_lines').fetchone(); c.close()
    assert line['seller_fee_cents']==5_000
    assert line['seller_net_cents']==95_000
    assert line['spread_cents']==100
    assert snapshot['buyer_total_cents']==100_100


def test_negative_spread_rejected(db):
    with pytest.raises(flow.FlowError,match='cannot be below'):
        prep(db,[{'listing_id':10,'quantity':1,'price_each':99,'seller_price_each':100}])


def test_reservation_is_atomic_and_releases_once(db):
    checkout,_=prep(db,[{'listing_id':10,'quantity':3,'price_each':100}])
    c=db(); assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==17; c.close()
    assert flow.release_reservation(checkout['id'],'failure')==1
    assert flow.release_reservation(checkout['id'],'duplicate')==0
    c=db(); assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==20; c.close()


def test_payment_binding_rejects_amount_currency_buyer_and_digest(db):
    checkout,snapshot=prep(db)
    for field,value in [('amount',9999),('currency','eur')]:
        p=payment(checkout,snapshot); p[field]=value
        with pytest.raises(flow.FlowError) as e: flow.verify_provider_payment(checkout['id'],p)
        assert e.value.code=='PAYMENT_BINDING_MISMATCH'
    p=payment(checkout,snapshot); p['metadata']['buyer_id']='99'
    with pytest.raises(flow.FlowError): flow.verify_provider_payment(checkout['id'],p)


def test_one_payment_creates_one_execution_and_balanced_ledger(db):
    checkout,snapshot=prep(db)
    first,created=flow.finalize_payment(checkout['id'],payment(checkout,snapshot)); assert created
    second,created=flow.finalize_payment(checkout['id'],payment(checkout,snapshot)); assert not created
    assert first['id']==second['id']
    c=db()
    assert c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==1
    assert c.execute('SELECT COUNT(*) FROM executions').fetchone()[0]==1
    sums=c.execute('SELECT SUM(debit_cents),SUM(credit_cents) FROM ledger_entries').fetchone()
    assert sums[0]==sums[1]==10_000
    assert flow.reconcile_internal()==[]
    c.close()


def test_multi_seller_independent_fills(db):
    items=[{'listing_id':10,'quantity':2,'price_each':100},{'listing_id':11,'quantity':1,'price_each':200}]
    checkout,snapshot=prep(db,items)
    result,_=flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    c=db(); fills=c.execute('SELECT * FROM seller_fills WHERE execution_id=? ORDER BY seller_id',(result['id'],)).fetchall(); c.close()
    assert [(x['seller_id'],x['seller_net_cents']) for x in fills]==[(2,19000),(3,19000)]


def test_ach_success_does_not_authorize_shipping(db):
    checkout,snapshot=prep(db)
    result,_=flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    c=db(); exe=c.execute('SELECT payment_state FROM executions WHERE id=?',(result['id'],)).fetchone(); ship=c.execute('SELECT state FROM shipments').fetchone(); c.close()
    assert exe[0]=='APPROVAL_PENDING'; assert ship[0]=='NOT_AUTHORIZED'


def test_ach_approval_requires_approved_policy_and_evidence(db):
    checkout,snapshot=prep(db); result,_=flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    with pytest.raises(flow.FlowError) as e: flow.approve_ach_payment(result['id'],9,{'settled':True})
    assert e.value.code=='POLICY_CONFIGURATION_REQUIRED'
    c=db(); approve(c,'ach_approval_policy'); c.close()
    with pytest.raises(flow.FlowError): flow.approve_ach_payment(result['id'],9,{})
    assert flow.approve_ach_payment(result['id'],9,{'settled':True})


def test_card_and_ach_snapshots_are_immutable_versions(db):
    checkout,card=prep(db,rail='card')
    ach,changed=flow.revise_payment_rail(checkout['id'],'us_bank_account')
    assert changed and ach['version']==2 and ach['card_surcharge_cents']==0
    c=db(); old=c.execute('SELECT * FROM execution_snapshots WHERE id=?',(card['id'],)).fetchone(); c.close()
    assert old['payment_rail']=='card' and old['card_surcharge_cents']>0


def test_t12_unit_rounding_conserves_cents():
    assert flow.seller_fee_cents(30)==2
    slices=flow.allocate_largest_remainder(2,[1,1,1])
    assert slices==[1,1,0] and sum(slices)==2


def test_partial_refund_exact_components(db):
    checkout,snapshot=prep(db,[{'listing_id':10,'quantity':10,'price_each':101,'seller_price_each':100}])
    result,_=flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    c=db(); fill=c.execute('SELECT id FROM seller_fills').fetchone()[0]; c.close()
    refund,_=flow.create_refund(result['id'],{fill:4},'PARTIAL','refund-1',refund_card_surcharge=False)
    assert refund['total_cents']==40_400
    c=db(); a=c.execute('SELECT * FROM refund_allocations').fetchone(); c.close()
    assert (a['seller_net_cents'],a['seller_fee_cents'],a['spread_cents'])==(38_000,2_000,400)


def test_grading_fee_not_refunded_after_cost_incurred(db):
    checkout,snapshot=prep(db,[{'listing_id':10,'quantity':2,'price_each':100,'requires_grading':True}],grading=2000)
    result,_=flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    c=db(); fill=c.execute('SELECT id,snapshot_line_id FROM seller_fills').fetchone(); c.execute('UPDATE snapshot_lines SET grading_cost_incurred=1 WHERE id=?',(fill['snapshot_line_id'],)); c.commit(); c.close()
    refund,_=flow.create_refund(result['id'],{fill['id']:2},'GRADING_FAILURE','refund-grade',refund_card_surcharge=False)
    assert refund['total_cents']==20_000


def test_non_graded_payout_waits_full_day_after_delivery(db):
    checkout,snapshot=prep(db,rail='card'); result,_=flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    c=db(); payable=c.execute('SELECT id,seller_fill_id FROM seller_payables').fetchone(); now=datetime.now(timezone.utc); c.execute("UPDATE shipments SET delivered_at=?,state='DELIVERED' WHERE seller_fill_id=?",((now-timedelta(hours=23)).isoformat(),payable['seller_fill_id'])); c.commit(); c.close()
    assert flow.evaluate_payout(payable['id'],now)==(False,'DELIVERY_HOLD_24H')
    assert flow.evaluate_payout(payable['id'],now+timedelta(hours=2))==(True,'')


def test_tracking_requires_owner_authorization_real_ups_and_evidence(db):
    checkout,snapshot=prep(db,rail='card'); result,_=flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    c=db(); approve(c,'tracking_upload_deadline_days','ups_coverage_and_claim_policy'); ship=c.execute('SELECT id FROM shipments').fetchone()[0]; c.close()
    flow.record_insurance(ship,9,'pol_1',10000,800,{'covered':True})
    flow.authorize_shipment(ship,9)
    with pytest.raises(flow.FlowError): flow.record_tracking(ship,3,'UPS','hello',{'carrier_confirmed':True})
    with pytest.raises(flow.FlowError): flow.record_tracking(ship,2,'UPS','hello',{'carrier_confirmed':True})
    flow.record_tracking(ship,2,'UPS','1Z999AA10123456784',{'carrier_confirmed':True})


def test_transfer_is_not_final_bank_payout(db):
    checkout,snapshot=prep(db,rail='card'); result,_=flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    c=db(); payable=c.execute('SELECT id,seller_fill_id FROM seller_payables').fetchone(); c.execute("UPDATE shipments SET delivered_at=?,state='DELIVERED' WHERE seller_fill_id=?",((datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),payable['seller_fill_id'])); c.commit(); c.close()
    tr,_=flow.claim_seller_transfer(payable['id'],'transfer-1'); flow.complete_seller_transfer(tr['id'],'tr_stripe')
    c=db(); state=c.execute('SELECT state FROM seller_payables WHERE id=?',(payable['id'],)).fetchone()[0]; assert state=='TRANSFERRED_TO_CONNECTED_ACCOUNT'; assert c.execute('SELECT COUNT(*) FROM bank_payouts').fetchone()[0]==0; c.close()

def test_idempotency_key_conflict_rejected(db):
    prep(db,key='same')
    with pytest.raises(flow.FlowError) as e:
        prep(db,[{'listing_id':10,'quantity':2,'price_each':100}],key='same')
    assert e.value.code=='IDEMPOTENCY_CONFLICT'


def test_multi_seller_partial_refund_does_not_touch_other_fill(db):
    checkout,snapshot=prep(db,[{'listing_id':10,'quantity':2,'price_each':100},{'listing_id':11,'quantity':2,'price_each':200}])
    result,_=flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    c=db(); fills=c.execute('SELECT id,seller_id,state FROM seller_fills ORDER BY seller_id').fetchall(); c.close()
    refund,_=flow.create_refund(result['id'],{fills[0]['id']:1},'PARTIAL','isolate',refund_card_surcharge=False)
    flow.complete_refund(refund['id'],'re_1')
    c=db(); states=c.execute('SELECT seller_id,state,refunded_quantity FROM seller_fills ORDER BY seller_id').fetchall(); c.close()
    assert tuple(states[0])==(2,'PARTIALLY_REFUNDED',1)
    assert tuple(states[1])==(3,'FUNDED',0)


def test_grading_is_all_or_none_per_line(db):
    checkout,_=prep(db,[{'listing_id':10,'quantity':5,'price_each':100,'requires_grading':True}],grading=2000)
    c=db(); line=c.execute('SELECT quantity,grading_requested,grading_cents FROM snapshot_lines').fetchone(); c.close()
    assert tuple(line)==(5,1,10000)


def test_each_graded_fill_has_separate_first_shipment_leg(db):
    checkout,snapshot=prep(db,[{'listing_id':10,'quantity':1,'price_each':100,'requires_grading':True},
                               {'listing_id':11,'quantity':1,'price_each':200,'requires_grading':True}],grading=2000)
    flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    c=db(); legs=c.execute('SELECT leg_type,destination_type FROM shipments ORDER BY id').fetchall(); c.close()
    assert [tuple(x) for x in legs]==[('SELLER_TO_GRADER','GRADER'),('SELLER_TO_GRADER','GRADER')]


def test_webhook_duplicate_is_processed_once(db):
    checkout,snapshot=prep(db); event={'id':'evt_1','type':'payment_intent.succeeded','data':{'object':payment(checkout,snapshot)}}
    assert flow.record_webhook(event); assert flow.process_webhook(event)=='processed'
    assert not flow.record_webhook(event); assert flow.process_webhook(event)=='duplicate'
    c=db(); assert c.execute('SELECT COUNT(*) FROM executions').fetchone()[0]==1; c.close()


def test_ach_return_after_funding_holds_affected_payable(db):
    checkout,snapshot=prep(db); flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    failed=payment(checkout,snapshot,status='requires_payment_method')
    event={'id':'evt_return','type':'payment_intent.payment_failed','data':{'object':failed}}
    flow.record_webhook(event); flow.process_webhook(event)
    c=db(); assert c.execute('SELECT payment_state FROM executions').fetchone()[0]=='RETURNED'; assert c.execute('SELECT block_reason FROM seller_payables').fetchone()[0]=='ACH_RETURN'; c.close()


def test_tracking_deadline_forfeiture_blocks_payable(db):
    checkout,snapshot=prep(db,rail='card'); flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    c=db(); c.execute("UPDATE shipments SET state='AWAITING_TRACKING',tracking_due_at=?",((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),)); c.commit(); c.close()
    assert len(flow.mark_tracking_forfeitures())==1
    c=db(); assert c.execute('SELECT state FROM seller_payables').fetchone()[0]=='CANCELLED'; c.close()


def test_post_payout_recovery_requires_liability_policy(db):
    checkout,snapshot=prep(db,rail='card'); flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    c=db(); fill=c.execute('SELECT id FROM seller_fills').fetchone()[0]; c.close()
    with pytest.raises(flow.FlowError) as e: flow.create_recovery_obligation(fill,'CHARGEBACK','dp_1',10000)
    assert e.value.code=='LIABILITY_POLICY_REQUIRED'


def test_actual_ach_cost_is_expense_not_seller_reduction(db):
    checkout,snapshot=prep(db); result,_=flow.finalize_payment(checkout['id'],payment(checkout,snapshot))
    assert flow.record_provider_expense(result['id'],'ACH_PROCESSING',500,'txn_1','ach-cost-1')
    c=db(); payable=c.execute('SELECT amount_cents FROM seller_payables').fetchone()[0]; expense=c.execute("SELECT debit_cents FROM ledger_entries WHERE account_code='ACH_PROCESSING_EXPENSE'").fetchone()[0]; c.close()
    assert payable==9500 and expense==500


def test_provider_variance_opens_reconciliation_case(db):
    checkout,snapshot=prep(db)
    wrong=payment(checkout,snapshot); wrong['amount']=snapshot['buyer_total_cents']+7
    assert flow.reconcile_provider_payment(wrong)==7
    c=db(); case=c.execute('SELECT variance_cents,state FROM reconciliation_cases').fetchone(); c.close()
    assert tuple(case)==(7,'OPEN')

def test_invalid_state_transition_is_rejected():
    with pytest.raises(flow.FlowError) as e: flow.assert_transition('shipment','NOT_AUTHORIZED','DELIVERED')
    assert e.value.code=='INVALID_STATE_TRANSITION'
