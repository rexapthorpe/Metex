from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from tests.test_flow_of_funds_acceptance import db,prep,payment,approve
import services.flow_of_funds as flow


def funded(db,rail='card',quantity=1):
    checkout,snap=prep(db,[{'listing_id':10,'quantity':quantity,'price_each':100}],rail=rail)
    exe,_=flow.finalize_payment(checkout['id'],payment(checkout,snap))
    c=db(); fill=c.execute('SELECT id FROM seller_fills').fetchone()[0]; c.close()
    return exe,fill,snap


def test_fault_refund_returns_surcharge_and_unknown_requires_review(db):
    exe,fill,snap=funded(db)
    with pytest.raises(flow.FlowError,match='approved refund reason'):
        flow.create_refund(exe['id'],{fill:1},'arbitrary','unknown')
    refund,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','fault')
    assert refund['total_cents']==snap['buyer_total_cents']==10308
    replay,new=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','fault')
    assert not new and replay['id']==refund['id']
    with pytest.raises(flow.FlowError): flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','different')


def test_failure_releases_units_once_and_success_updates_entitlement(db):
    exe,fill,_=funded(db,quantity=3)
    first,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','first')
    flow.record_refund_provider_result(first['id'],{'id':'re_failed','status':'failed'})
    flow.record_refund_provider_result(first['id'],{'id':'re_failed','status':'failed'})
    c=db(); assert c.execute('SELECT refunded_quantity FROM seller_fills').fetchone()[0]==0; c.close()
    with pytest.raises(flow.FlowError): flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','first')
    second,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','second')
    flow.record_refund_provider_result(second['id'],{'id':'re_ok','status':'succeeded'})
    flow.record_refund_provider_result(second['id'],{'id':'re_ok','status':'pending'})
    c=db(); assert c.execute('SELECT amount_cents FROM seller_payables').fetchone()[0]==19000
    assert c.execute("SELECT COUNT(*) FROM ledger_journals WHERE event_type='REFUND_SUCCEEDED'").fetchone()[0]==1; c.close()
    assert flow.reconcile_internal()==[]


def event(db,typ,obj,event_id=None,account=None):
    data={'id':event_id or typ,'type':typ,'data':{'object':obj}}
    if account: data['account']=account
    flow.record_webhook(data); return flow.process_webhook(data)


def test_won_dispute_releases_only_its_hold_and_old_events_do_not_reopen(db):
    exe,fill,_=funded(db)
    obj={'id':'dp1','payment_intent':'pi_1','amount':10308,'status':'needs_response'}
    event(db,'charge.dispute.created',obj)
    c=db(); c.execute("INSERT INTO holds VALUES ('other',?,'SHIPPING_FAILURE','lost','ACTIVE','shipping',?,NULL)",(fill,datetime.now(timezone.utc).isoformat())); c.commit(); c.close()
    event(db,'charge.dispute.closed',dict(obj,status='won'))
    event(db,'charge.dispute.updated',obj)
    c=db(); assert c.execute("SELECT state FROM holds WHERE hold_type='CHARGEBACK'").fetchone()[0]=='RELEASED'
    assert c.execute("SELECT state FROM holds WHERE id='other'").fetchone()[0]=='ACTIVE'; c.close()


def test_dispute_cash_and_loss_are_balanced_once_and_refund_is_blocked(db):
    exe,fill,_=funded(db)
    obj={'id':'dp1','payment_intent':'pi_1','amount':10308,'status':'needs_response'}
    event(db,'charge.dispute.created',obj)
    event(db,'charge.dispute.funds_withdrawn',obj)
    event(db,'charge.dispute.funds_withdrawn',obj,event_id='withdrawal-replay')
    event(db,'charge.dispute.closed',dict(obj,status='lost'))
    with pytest.raises(flow.FlowError) as exc: flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','overlap')
    assert exc.value.code=='REFUND_DISPUTE_OVERLAP'
    c=db(); assert c.execute("SELECT COUNT(*) FROM ledger_journals WHERE aggregate_type='processor_dispute'").fetchone()[0]==2; c.close()
    assert flow.reconcile_internal()==[]


def test_ach_return_cannot_be_manually_reapproved(db):
    exe,fill,_=funded(db,rail='us_bank_account')
    c=db(); c.execute("UPDATE executions SET payment_state='RETURNED'"); c.commit(); c.close()
    with pytest.raises(flow.FlowError) as exc: flow.approve_ach_payment(exe['id'],9,{'settled':True})
    assert exc.value.code=='INVALID_STATE_TRANSITION'


def test_connected_payout_routes_by_account_without_metadata_and_does_not_regress(db):
    c=db(); c.execute("UPDATE users SET stripe_account_id='acct_seller' WHERE id=2"); c.commit(); c.close()
    obj={'id':'po1','amount':9500,'status':'paid','metadata':{},'arrival_date':1790800000}
    event(db,'payout.paid',obj,account='acct_seller')
    event(db,'payout.created',dict(obj,status='pending'),account='acct_seller')
    c=db(); row=c.execute('SELECT seller_id,state FROM bank_payouts').fetchone(); assert tuple(row)==(2,'BANK_PAYOUT_PAID'); c.close()


def test_pending_tracking_confirms_and_delivery_cannot_skip_validation(db):
    exe,fill,_=funded(db)
    c=db(); approve(c,'ups_coverage_and_claim_policy'); ship=c.execute('SELECT id FROM shipments').fetchone()[0]; c.close()
    flow.record_insurance(ship,9,'policy',10000,100,{'covered':True})
    due=flow.authorize_shipment(ship,9); assert flow.authorize_shipment(ship,9)==due
    evidence={'reference':'UPS observed acceptance','carrier_confirmed':True,'destination_matches':True}
    with pytest.raises(flow.FlowError): flow.record_shipment_event(ship,'DELIVERED',evidence)
    flow.submit_tracking_for_verification(ship,2,'UPS','1Z999AA10123456784')
    flow.record_tracking(ship,2,'UPS','1Z999AA10123456784',evidence)
    flow.record_tracking(ship,2,'UPS','1Z999AA10123456784',evidence)
    flow.record_shipment_event(ship,'DELIVERED',evidence)
    flow.record_shipment_event(ship,'DELIVERED',evidence)
    c=db(); assert c.execute('SELECT tracking_validated,state FROM shipments').fetchone()[0]==1; c.close()


def test_paused_checkout_and_self_trade_roll_back_stock(db):
    c=db(); c.execute("UPDATE system_settings SET value='0' WHERE key='checkout_enabled'"); c.commit(); c.close()
    with pytest.raises(flow.FlowError): flow.prepare_checkout(1,[{'listing_id':10,'quantity':1,'price_each':100}],'card',0,{},'paused')
    c=db(); assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==20
    c.execute("UPDATE system_settings SET value='1' WHERE key='checkout_enabled'"); c.commit(); c.close()
    with pytest.raises(flow.FlowError): flow.prepare_checkout(2,[{'listing_id':10,'quantity':1,'price_each':100}],'card',0,{},'self')
    c=db(); assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==20; c.close()


def test_refund_unknown_provider_retry_uses_original_key(db,monkeypatch):
    exe,fill,_=funded(db)
    refund,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','stable')
    calls=[]
    def create(**kwargs):
        calls.append(kwargs)
        if len(calls)==1: raise TimeoutError('unknown provider result')
        return SimpleNamespace(id='re1',status='succeeded',amount=10308,payment_intent='pi_1',to_dict=lambda:{'id':'re1','status':'succeeded','amount':10308,'payment_intent':'pi_1'})
    import stripe
    monkeypatch.setattr(stripe.Refund,'create',create)
    with pytest.raises(TimeoutError): flow.submit_refund(refund['id'])
    c=db(); assert c.execute('SELECT refunded_quantity FROM seller_fills').fetchone()[0]==1; c.close()
    flow.submit_refund(refund['id'])
    assert [x['idempotency_key'] for x in calls]==['stable','stable']
    assert flow.reconcile_internal()==[]


def test_expiry_unknown_payment_creation_retains_inventory(db):
    checkout,_=prep(db)
    c=db(); c.execute("UPDATE checkout_attempts SET provider_payment_id=NULL,expires_at='2000-01-01'"); c.commit(); c.close()
    assert flow.expire_due_reservations()==0
    c=db(); assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==19; c.close()


def test_expiry_failed_provider_cancellation_retains_inventory(db,monkeypatch):
    checkout,_=prep(db)
    c=db(); c.execute("UPDATE checkout_attempts SET expires_at='2000-01-01'"); c.commit(); c.close()
    import stripe
    monkeypatch.setattr(stripe.PaymentIntent,'retrieve',lambda _:SimpleNamespace(id='pi_1',status='requires_payment_method'))
    def cancel(*a,**kw): raise TimeoutError('Unknown cancellation outcome')
    monkeypatch.setattr(stripe.PaymentIntent,'cancel',cancel)
    assert flow.expire_due_reservations()==0
    c=db(); assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==19; c.close()


def test_late_payment_compensates_without_selling_released_inventory(db):
    from services.compensation_service import finish_compensation
    checkout,snap=prep(db,rail='card')
    flow.release_reservation(checkout['id'],'expired')
    result,new=flow.finalize_payment(checkout['id'],payment(checkout,snap))
    assert not new and result['state']=='COMPENSATION_REQUIRED'
    c=db(); assert c.execute('SELECT COUNT(*) FROM executions').fetchone()[0]==0
    assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==20; c.close()
    provider=SimpleNamespace(id='re_late',amount=snap['buyer_total_cents'],payment_intent='pi_1',status='succeeded')
    assert finish_compensation(checkout['id'],provider)
    assert not finish_compensation(checkout['id'],provider)
    provider.id='re_different'
    with pytest.raises(flow.FlowError): finish_compensation(checkout['id'],provider)
    assert flow.reconcile_internal()==[]


def test_admin_review_release_preserves_other_financial_holds(db):
    from services.admin_flow_service import hold_order,release_order_review
    exe,fill,_=funded(db)
    c=db(); c.execute("INSERT INTO holds VALUES ('risk',?,'CHARGEBACK','review','ACTIVE','dp',?,NULL)",(fill,datetime.now(timezone.utc).isoformat())); c.commit(); c.close()
    assert hold_order(exe['legacy_order_id'],9,'Review')
    assert hold_order(exe['legacy_order_id'],9,'Review repeated')
    assert release_order_review(exe['legacy_order_id'],9)
    c=db(); assert c.execute("SELECT state FROM holds WHERE id='risk'").fetchone()[0]=='ACTIVE'
    assert c.execute("SELECT COUNT(*) FROM holds WHERE hold_type='ADMIN_REVIEW'").fetchone()[0]==1; c.close()


def test_frozen_seller_cannot_reserve_inventory(db):
    c=db(); c.execute('ALTER TABLE users ADD COLUMN is_frozen INTEGER DEFAULT 0')
    c.execute('UPDATE users SET is_frozen=1 WHERE id=2'); c.commit(); c.close()
    with pytest.raises(flow.FlowError) as exc: prep(db)
    assert exc.value.code=='SELLER_UNAVAILABLE'
    c=db(); assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==20; c.close()


def test_bid_address_parses_form_format_without_guessing():
    from services.shipping_address_service import bid_shipping
    bid={'delivery_address':'1 Main • Apt 2 • Boston, MA 02110','recipient_first_name':'A','recipient_last_name':'B'}
    address=bid_shipping(bid)
    assert address['line1']=='1 Main' and address['line2']=='Apt 2' and address['city']=='Boston'
    bid['delivery_address']='MA 02110'
    with pytest.raises(ValueError): bid_shipping(bid)


def release_ready(db):
    exe,fill,snap=funded(db)
    c=db(); approve(c,'ups_coverage_and_claim_policy'); ship=c.execute('SELECT id FROM shipments').fetchone()[0]; payable=c.execute('SELECT id FROM seller_payables').fetchone()[0]; c.close()
    flow.record_insurance(ship,9,'covered-policy',10000,100,{'covered':True})
    flow.authorize_shipment(ship,9)
    evidence={'reference':'carrier observation','carrier_confirmed':True,'destination_matches':True}
    flow.record_tracking(ship,2,'UPS','1Z999AA10123456784',evidence)
    flow.record_shipment_event(ship,'DELIVERED',evidence)
    c=db(); c.execute('UPDATE shipments SET delivered_at=?',((datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),)); c.commit(); c.close()
    return exe,fill,payable


def test_transfer_replay_and_hold_before_dispatch(db):
    from services.admin_flow_service import hold_order
    exe,fill,payable=release_ready(db)
    transfer,new=flow.claim_seller_transfer(payable,'transfer-stable')
    assert new and transfer['amount_cents']==9500
    assert not flow.claim_seller_transfer(payable,'transfer-stable')[1]
    with pytest.raises(flow.FlowError): flow.claim_seller_transfer(payable,'another-key')
    hold_order(exe['legacy_order_id'],9,'Review before dispatch')
    with pytest.raises(flow.FlowError): flow.begin_seller_transfer(transfer['id'])
    c=db(); assert c.execute('SELECT released_cents FROM seller_payables').fetchone()[0]==0; c.close()


def test_confirmed_transfer_cannot_double_release_or_change_provider_id(db):
    _,_,payable=release_ready(db)
    transfer,_=flow.claim_seller_transfer(payable,'transfer-stable')
    flow.begin_seller_transfer(transfer['id'])
    flow.complete_seller_transfer(transfer['id'],'tr_bound')
    flow.complete_seller_transfer(transfer['id'],'tr_bound')
    with pytest.raises(flow.FlowError): flow.complete_seller_transfer(transfer['id'],'tr_other')
    c=db(); assert c.execute('SELECT released_cents FROM seller_payables').fetchone()[0]==9500; c.close()
    assert flow.reconcile_internal()==[]


def test_reviewed_tax_uses_complete_address_and_listing_specific_code(db,monkeypatch):
    from services.tax_service import calculate_items
    import stripe
    c=db(); c.execute("INSERT INTO categories VALUES (1,'Silver','Coin')"); c.commit()
    shipping={'line1':'1 Main','city':'Boston','state':'MA','postal_code':'02110','country':'US'}
    with pytest.raises(flow.FlowError): calculate_items(c,[{'listing_id':10,'quantity':2,'price_each':100}],shipping)
    monkeypatch.setenv('TAX_CONFIGURATION_APPROVED','true')
    monkeypatch.setenv('TAX_PRODUCT_CODES_JSON','{"Silver|Coin":"txcd_reviewed"}')
    monkeypatch.setenv('TAX_SELLER_ORIGINS_JSON','{"2":{"line1":"2 Seller","city":"Boston","state":"MA","postal_code":"02110","country":"US"}}')
    calls=[]
    def calculate(**kw): calls.append(kw); return SimpleNamespace(id='taxcalc',tax_amount_exclusive=1250)
    monkeypatch.setattr(stripe.tax.Calculation,'create',calculate)
    tax,records=calculate_items(c,[{'listing_id':10,'quantity':2,'price_each':100}],shipping)
    assert tax==1250 and records[0]['amount_cents']==20000
    assert calls[0]['customer_details']['address']==shipping
    assert calls[0]['line_items'][0]['tax_code']=='txcd_reviewed'
    with pytest.raises(flow.FlowError): calculate_items(c,[{'listing_id':10,'quantity':2,'price_each':100}],dict(shipping,city=''))
    assert len(calls)==1; c.close()


def test_recovery_reversal_exact_amount_binding_and_replay(db):
    from services.recovery_service import approve_recovery,claim_reversal,complete_reversal
    exe,fill,payable=release_ready(db)
    tr,_=flow.claim_seller_transfer(payable,'release'); flow.begin_seller_transfer(tr['id']); flow.complete_seller_transfer(tr['id'],'tr_original')
    refund,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','refund_after_transfer')
    flow.record_refund_provider_result(refund['id'],{'id':'re_confirmed','status':'succeeded'})
    c=db(); approve(c,'chargeback_loss_liability'); c.close()
    rec=approve_recovery(fill,'REFUND',refund['id'],'WRONG_ITEM',{'reference':'reviewed seller evidence'},9)
    assert rec['amount_cents']==9500
    assert approve_recovery(fill,'REFUND',refund['id'],'WRONG_ITEM',{'reference':'same'},9)['id']==rec['id']
    op,provider_transfer=claim_reversal(rec['id']); assert provider_transfer=='tr_original' and op['amount_cents']==9500
    wrong=SimpleNamespace(id='trr',amount=9500,transfer='tr_wrong')
    with pytest.raises(flow.FlowError): complete_reversal(op['id'],wrong)
    wrong.transfer='tr_original'; wrong.amount=9501
    with pytest.raises(flow.FlowError): complete_reversal(op['id'],wrong)
    wrong.amount=9500
    assert complete_reversal(op['id'],wrong)
    assert not complete_reversal(op['id'],wrong)
    c=db(); assert c.execute('SELECT recovered_cents FROM recovery_obligations').fetchone()[0]==9500; c.close()
    assert flow.reconcile_internal()==[]


def test_lost_chargeback_before_transfer_voids_entitlement_without_seller_debt(db):
    from services.recovery_service import approve_recovery
    exe,fill,_=funded(db)
    obj={'id':'dp_before','payment_intent':'pi_1','amount':10308,'status':'lost'}
    event(db,'charge.dispute.closed',obj)
    c=db(); approve(c,'chargeback_loss_liability'); c.close()
    result=approve_recovery(fill,'CHARGEBACK','dp_before','WRONG_ITEM',{'reference':'adjudicated wrong item'},9)
    assert result['state']=='NO_RELEASED_DEBT'
    c=db(); assert c.execute('SELECT amount_cents FROM seller_payables').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM recovery_obligations').fetchone()[0]==0; c.close()
    assert flow.reconcile_internal()==[]


def test_financial_notices_aggregate_same_seller_and_replay_once(db,monkeypatch):
    import database
    from services.delivery_service import dispatch_financial_notifications
    monkeypatch.setattr(database,'get_db_connection',db)
    c=db(); c.execute('CREATE TABLE notifications(id INTEGER PRIMARY KEY,user_id INTEGER,type TEXT,title TEXT,message TEXT,related_order_id INTEGER,metadata TEXT)')
    c.execute('UPDATE listings SET seller_id=2 WHERE id=11'); c.commit(); c.close()
    checkout,snap=prep(db,[{'listing_id':10,'quantity':1,'price_each':100},{'listing_id':11,'quantity':1,'price_each':200}])
    flow.finalize_payment(checkout['id'],payment(checkout,snap))
    assert dispatch_financial_notifications()==1
    assert dispatch_financial_notifications()==0
    c=db(); rows=c.execute('SELECT user_id,message FROM notifications ORDER BY user_id').fetchall()
    assert len(rows)==2 and '$285.00' in rows[1]['message']
    assert 'do not ship before authorization' in rows[1]['message']; c.close()


def test_email_switch_does_not_send_without_explicit_enable(monkeypatch):
    from services.delivery_service import dispatch_email_queue
    import smtplib
    monkeypatch.delenv('EMAIL_DELIVERY_ENABLED',raising=False)
    def forbidden(*a,**kw): raise AssertionError('Real SMTP must not be contacted')
    monkeypatch.setattr(smtplib,'SMTP_SSL',forbidden)
    assert dispatch_email_queue()==0


def test_partial_ach_refund_is_gated_without_changing_allocation(db):
    exe,fill,snap=funded(db,rail='us_bank_account',quantity=2)
    with pytest.raises(flow.FlowError) as exc: flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','partial-ach')
    assert exc.value.code=='ACH_PARTIAL_REFUND_UNSUPPORTED'
    c=db(); assert c.execute('SELECT refunded_quantity FROM seller_fills').fetchone()[0]==0
    assert c.execute('SELECT COUNT(*) FROM flow_refunds').fetchone()[0]==0; c.close()
    refund,_=flow.create_refund(exe['id'],{fill:2},'SELLER_FAULT','full-ach')
    assert refund['total_cents']==snap['buyer_total_cents']


def test_confirmed_partial_refund_does_not_mark_other_pending_units_refunded(db):
    exe,fill,_=funded(db,quantity=2)
    first,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','confirmed-part')
    second,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','pending-part')
    flow.record_refund_provider_result(first['id'],{'id':'re_first','status':'succeeded'})
    c=db(); assert c.execute('SELECT state FROM seller_fills').fetchone()[0]=='REFUND_PENDING'
    assert c.execute('SELECT status FROM orders').fetchone()[0]=='Partially Refunded'; c.close()
    flow.record_refund_provider_result(second['id'],{'id':'re_second','status':'failed'})
    c=db(); assert c.execute('SELECT state FROM seller_fills').fetchone()[0]=='PARTIALLY_REFUNDED'; c.close()
    assert flow.reconcile_internal()==[]


def test_future_proceeds_offset_is_capped_and_replay_safe(db):
    from services.recovery_service import approve_recovery,offset_future_proceeds
    exe,fill,payable=release_ready(db)
    tr,_=flow.claim_seller_transfer(payable,'release'); flow.begin_seller_transfer(tr['id']); flow.complete_seller_transfer(tr['id'],'tr_original')
    refund,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','old-refund')
    flow.record_refund_provider_result(refund['id'],{'id':'re_old','status':'succeeded'})
    c=db(); approve(c,'chargeback_loss_liability'); c.execute('UPDATE listings SET quantity=10,active=1'); c.commit(); c.close()
    # Proceeds reserved before the debt was adjudicated can later satisfy it.
    second,snap,_=flow.prepare_checkout(1,[{'listing_id':10,'quantity':1,'price_each':100}],'card',0,{'shipping_address':'1 Main','recipient_first':'A','recipient_last':'B'},'future')
    c=db(); op,_=flow.claim_operation(c,'PAYMENT','future-payment','checkout',second['id'],snap['buyer_total_cents'],{})
    flow.bind_provider_payment(second['id'],'pi_future',op['id'],conn=c); c.commit(); c.close()
    pi=payment(second,snap); pi['id']='pi_future'
    next_exe,_=flow.finalize_payment(second['id'],pi)
    rec=approve_recovery(fill,'REFUND',refund['id'],'WRONG_ITEM',{'reference':'seller fault'},9)
    c=db(); future=c.execute('SELECT p.id FROM seller_payables p JOIN seller_fills f ON f.id=p.seller_fill_id WHERE f.execution_id=?',(next_exe['id'],)).fetchone()[0]; c.close()
    result=offset_future_proceeds(future,9,{'reference':'offset review'})
    assert result['offset_cents']==9500 and result['remaining_proceeds_cents']==0
    assert offset_future_proceeds(future,9,{'reference':'retry'})['offset_cents']==0
    c=db(); assert c.execute('SELECT recovered_cents FROM recovery_obligations WHERE id=?',(rec['id'],)).fetchone()[0]==9500; c.close()
    assert flow.reconcile_internal()==[]


def test_repeated_identical_checkouts_and_rail_round_trip_have_distinct_snapshots(db):
    first,snap,_=flow.prepare_checkout(1,[{'listing_id':10,'quantity':1,'price_each':100}],'card',0,{},'first')
    second,next_snap,_=flow.prepare_checkout(1,[{'listing_id':10,'quantity':1,'price_each':100}],'card',0,{},'second')
    assert first['id']!=second['id'] and snap['snapshot_hash']!=next_snap['snapshot_hash']
    ach,_=flow.revise_payment_rail(first['id'],'us_bank_account')
    card,_=flow.revise_payment_rail(first['id'],'card')
    assert len({snap['snapshot_hash'],ach['snapshot_hash'],card['snapshot_hash']})==3
    assert card['buyer_total_cents']==snap['buyer_total_cents']
    c=db(); c.execute("UPDATE checkout_attempts SET state='PAYMENT_PROCESSING' WHERE id=?",(first['id'],)); c.commit(); c.close()
    with pytest.raises(flow.FlowError): flow.revise_payment_rail(first['id'],'us_bank_account')


def test_provider_transfer_timeout_retries_original_operation_and_source(db,monkeypatch):
    from services import payout_service
    import stripe
    _,_,payable=release_ready(db)
    monkeypatch.setattr(payout_service,'refresh_seller',lambda conn,seller:True)
    monkeypatch.setattr(stripe.PaymentIntent,'retrieve',lambda _:SimpleNamespace(status='succeeded',currency='usd',latest_charge='ch_funding'))
    calls=[]
    def create(**kw):
        calls.append(kw)
        if len(calls)==1: raise TimeoutError('unknown transfer outcome')
        return SimpleNamespace(id='tr_provider',amount=kw['amount'],currency=kw['currency'],destination=kw['destination'])
    monkeypatch.setattr(stripe.Transfer,'create',create)
    with pytest.raises(TimeoutError): payout_service.release_payable(payable)
    assert payout_service.release_payable(payable)=='tr_provider'
    assert payout_service.release_payable(payable)=='tr_provider'
    assert len(calls)==2 and calls[0]==calls[1]
    assert calls[0]['source_transaction']=='ch_funding' and calls[0]['amount']==9500
    assert flow.reconcile_internal()==[]


def test_unknown_transfer_retry_after_refund_does_not_create_transfer(db,monkeypatch):
    from services import payout_service
    import stripe
    exe,fill,payable=release_ready(db)
    monkeypatch.setattr(payout_service,'refresh_seller',lambda conn,seller:True)
    monkeypatch.setattr(stripe.PaymentIntent,'retrieve',lambda _:SimpleNamespace(status='succeeded',currency='usd',latest_charge='ch_funding'))
    calls=[]
    def create(**kw): calls.append(kw); raise TimeoutError('unknown')
    monkeypatch.setattr(stripe.Transfer,'create',create)
    with pytest.raises(TimeoutError): payout_service.release_payable(payable)
    refund,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','after-unknown')
    flow.record_refund_provider_result(refund['id'],{'id':'re_after','status':'succeeded'})
    with pytest.raises(flow.FlowError): payout_service.release_payable(payable)
    assert len(calls)==1
    assert flow.reconcile_internal()==[]


def test_daily_release_controls_and_date_are_enforced(db,monkeypatch):
    from services import payout_service
    _,_,payable=release_ready(db)
    calls=[]; monkeypatch.setattr(payout_service,'release_payable',lambda p:calls.append(p))
    assert payout_service.run_daily_releases()==0 and calls==[]
    c=db(); c.execute("INSERT INTO system_settings(key,value) VALUES ('auto_payouts_enabled','1')"); c.commit(); c.close()
    assert payout_service.run_daily_releases()==1 and calls==[payable]
    assert payout_service.run_daily_releases()==0


def test_browser_payment_setup_unknown_retry_reuses_snapshot_tax_and_provider_key(db,monkeypatch):
    from flask import Flask
    import database, stripe
    import core.blueprints.checkout.routes as routes
    import utils.auth_utils as auth
    import services.tax_service as tax
    import core.blueprints.account.payment_methods as methods
    monkeypatch.setattr(database,'get_db_connection',db)
    monkeypatch.setattr(routes,'get_db_connection',db)
    monkeypatch.setattr(auth,'get_db_connection',db)
    monkeypatch.setattr(methods,'_ensure_stripe_customer',lambda *a:'cus_buyer')
    calculations=[]
    def calculate(conn,items,shipping):
        calculations.append(shipping.copy())
        return 0,[{'listing_id':10,'calculation_id':'calc_first','amount_cents':10000,'tax_cents':0}]
    monkeypatch.setattr(tax,'calculate_items',calculate)
    calls=[]
    def create(**kw):
        calls.append(kw)
        if len(calls)==1: raise TimeoutError('ambiguous request')
        return SimpleNamespace(id='pi_retry',client_secret='test_secret')
    monkeypatch.setattr(stripe.PaymentIntent,'create',create)
    c=db(); approve(c,'ups_coverage_and_claim_policy'); c.execute('ALTER TABLE users ADD COLUMN is_frozen INTEGER DEFAULT 0'); c.execute('UPDATE listings SET quantity=1 WHERE id=10'); c.commit(); c.close()
    app=Flask(__name__); app.config.update(TESTING=True,SECRET_KEY='disposable-test-key')
    app.register_blueprint(routes.checkout_bp)
    client=app.test_client()
    with client.session_transaction() as session:
        session['user_id']=1; session['checkout_nonce']='retry-nonce'
        session['checkout_items']=[{'listing_id':10,'quantity':1,'price_each':100}]
    body={'shipping_address':'1 Main • Boston, MA 02110','address_line1':'1 Main','city':'Boston','state':'MA','zip_code':'02110','country':'US'}
    assert client.post('/create-payment-intent',json=body).status_code==500
    response=client.post('/create-payment-intent',json=body)
    assert response.status_code==200
    assert len(calculations)==1 and calculations[0]['line1']=='1 Main'
    assert len(calls)==2 and calls[0]==calls[1]
    c=db(); assert c.execute('SELECT COUNT(*) FROM checkout_attempts').fetchone()[0]==1
    assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==0; c.close()
    changed=client.post('/create-payment-intent',json=dict(body,address_line1='2 Other'))
    assert changed.status_code==409 and len(calls)==2


def test_tax_sale_and_refund_queue_retry_preserves_original_allocations(db,monkeypatch):
    import database,stripe
    from services.tax_service import sync_tax_records
    monkeypatch.setattr(database,'get_db_connection',db)
    shipping={'tax_calculations':[{'listing_id':10,'calculation_id':'calc','amount_cents':20000,'tax_cents':1250}]}
    checkout,snap,_=flow.prepare_checkout(1,[{'listing_id':10,'quantity':2,'price_each':100}],'card',1250,shipping,'tax-order')
    c=db(); op,_=flow.claim_operation(c,'PAYMENT','tax-payment','checkout',checkout['id'],snap['buyer_total_cents'],{})
    flow.bind_provider_payment(checkout['id'],'pi_1',op['id'],conn=c); c.commit(); c.close()
    exe,_=flow.finalize_payment(checkout['id'],payment(checkout,snap))
    calls=[]
    def sale(**kw):
        calls.append(kw)
        if len(calls)==1: raise TimeoutError('ambiguous tax recording')
        return {'id':'tax_tx','reference':kw['reference'],'line_items':{'data':[{'id':'tax_line','reference':'10','amount':20000,'amount_tax':1250}],'has_more':False}}
    monkeypatch.setattr(stripe.tax.Transaction,'create_from_calculation',sale)
    sync_tax_records(); sync_tax_records(); sync_tax_records()
    assert len(calls)==2 and calls[0]==calls[1]
    c=db(); fill=c.execute('SELECT id FROM seller_fills').fetchone()[0]; c.close()
    refund,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','tax-refund')
    reversals=[]
    def reversal(**kw):
        reversals.append(kw)
        if len(reversals)==1: raise TimeoutError('ambiguous reversal')
        return SimpleNamespace(id='tax_reverse')
    monkeypatch.setattr(stripe.tax.Transaction,'create_reversal',reversal)
    sync_tax_records(); assert reversals==[]
    flow.record_refund_provider_result(refund['id'],{'id':'re_tax','status':'succeeded'})
    sync_tax_records(); sync_tax_records(); sync_tax_records()
    assert len(reversals)==2 and reversals[0]==reversals[1]
    assert reversals[0]['line_items'][0]['amount']==-10000
    assert reversals[0]['line_items'][0]['amount_tax']==-625
    assert reversals[0]['original_transaction']=='tax_tx'
    assert flow.reconcile_internal()==[]


def test_customer_projection_excludes_other_seller_proceeds_and_tracks_pending(db):
    from services.order_state_service import order_state
    checkout,snap=prep(db,[{'listing_id':10,'quantity':1,'price_each':100},{'listing_id':11,'quantity':1,'price_each':200}],rail='card')
    exe,_=flow.finalize_payment(checkout['id'],payment(checkout,snap))
    c=db(); buyer=order_state(c,exe['legacy_order_id']); seller=order_state(c,exe['legacy_order_id'],2)
    assert 'entitlement_cents' not in buyer and seller['entitlement_cents']==9500
    fill=c.execute('SELECT id FROM seller_fills WHERE seller_id=2').fetchone()[0]; c.close()
    refund,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','projected')
    c=db(); assert order_state(c,exe['legacy_order_id'],2)['status']=='Refund Pending'; c.close()
    flow.record_refund_provider_result(refund['id'],{'id':'re_projected','status':'succeeded'})
    c=db(); assert order_state(c,exe['legacy_order_id'],2)['status']=='Refunded'
    assert order_state(c,exe['legacy_order_id'],3)['status']=='Processing'; c.close()


def test_admin_mutation_requires_recent_auth_and_denies_frozen_admin(db,monkeypatch):
    import time
    from flask import Flask,Blueprint
    import utils.auth_utils as auth
    monkeypatch.setattr(auth,'get_db_connection',db)
    c=db(); c.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')
    c.execute('ALTER TABLE users ADD COLUMN is_frozen INTEGER DEFAULT 0'); c.execute('UPDATE users SET is_admin=1 WHERE id=1'); c.commit(); c.close()
    app=Flask(__name__); app.config.update(TESTING=True,SECRET_KEY='disposable',REQUIRE_ADMIN_REAUTH=True)
    bp=Blueprint('admin',__name__)
    @bp.route('/reauthenticate',endpoint='reauthenticate')
    def auth_route(): return 'test'
    @bp.route('/protected',methods=['POST'])
    @auth.admin_required
    def protected(): return 'authorized'
    app.register_blueprint(bp)
    app.jinja_loader=__import__('jinja2').DictLoader({'403.html':'Denied'})
    client=app.test_client()
    with client.session_transaction() as session: session['user_id']=1
    response=client.post('/protected'); assert response.status_code==403 and response.json['error_code']=='ADMIN_REAUTH_REQUIRED'
    with client.session_transaction() as session: session['authenticated_at']=time.time()
    assert client.post('/protected').status_code==200
    c=db(); c.execute('UPDATE users SET is_frozen=1 WHERE id=1'); c.commit(); c.close()
    assert client.post('/protected').status_code==403


def test_financial_health_reports_stale_worker_and_recent_success(db,monkeypatch):
    import database
    from services.flow_health_service import health
    monkeypatch.setattr(database,'get_db_connection',db)
    assert health()['worker_recent'] is False
    c=db(); c.execute('CREATE TABLE flow_worker_lease(id INTEGER PRIMARY KEY,last_success TEXT)')
    c.execute('INSERT INTO flow_worker_lease VALUES (1,?)',(datetime.now(timezone.utc).isoformat(),)); c.commit(); c.close()
    assert health()['worker_recent'] is True


def test_cart_refill_cannot_substitute_a_different_specification_in_mixed_bucket(db):
    from utils.cart_utils import validate_and_refill_cart
    c=db(); c.execute('ALTER TABLE categories ADD COLUMN bucket_id INTEGER')
    c.execute("INSERT INTO categories VALUES (1,'Silver','Coin',1),(2,'Silver','Coin',1)")
    c.execute('UPDATE listings SET quantity=0,active=0 WHERE id=10')
    c.execute('UPDATE listings SET category_id=2,price_per_coin=1 WHERE id=11')
    c.execute('INSERT INTO listings VALUES (12,3,1,2,1,200)')
    c.execute('INSERT INTO cart VALUES (1,1,10,1)'); c.commit()
    result=validate_and_refill_cart(c,1)
    assert result[1]['refilled']==1
    assert c.execute('SELECT listing_id FROM cart WHERE user_id=1').fetchone()[0]==12; c.close()


def test_incompatible_legacy_bucket_cannot_sell_wrong_grade(db):
    from services.catalog_identity_service import mixed_buckets
    c=db(); c.execute('ALTER TABLE categories ADD COLUMN bucket_id INTEGER')
    c.execute('ALTER TABLE categories ADD COLUMN grade TEXT')
    c.execute("INSERT INTO categories VALUES (1,'Silver','Coin',1,'MS70'),(2,'Silver','Coin',1,'Raw')"); c.commit()
    assert mixed_buckets(c)=={1:[[1],[2]]}; c.close()
    with pytest.raises(flow.FlowError) as exc: prep(db)
    assert exc.value.code=='CATALOG_REVIEW_REQUIRED'
    c=db(); assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==20; c.close()


def test_email_failure_retains_notice_and_retry_keeps_message_identity(db,monkeypatch):
    import database,config,smtplib
    from services.delivery_service import dispatch_financial_notifications,dispatch_email_queue
    monkeypatch.setattr(database,'get_db_connection',db)
    c=db(); c.execute('CREATE TABLE notifications(id INTEGER PRIMARY KEY,user_id INTEGER,type TEXT,title TEXT,message TEXT,related_order_id INTEGER,metadata TEXT)'); c.commit(); c.close()
    funded(db); dispatch_financial_notifications()
    c=db(); c.execute("UPDATE financial_notice_deliveries SET state='SENT' WHERE user_id=2"); c.commit(); c.close()
    monkeypatch.setenv('EMAIL_DELIVERY_ENABLED','true')
    monkeypatch.setattr(config,'EMAIL_ADDRESS','sender@example.invalid'); monkeypatch.setattr(config,'EMAIL_PASSWORD','disposable-mock')
    messages=[]
    class FakeSMTP:
        def __init__(self,*args,**kwargs): assert kwargs['timeout']==20
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def login(self,address,password): assert address=='sender@example.invalid' and password=='disposable-mock'
        def send_message(self,message):
            messages.append(message['Message-ID'])
            if len(messages)==1: raise TimeoutError('ambiguous delivery')
    monkeypatch.setattr(smtplib,'SMTP_SSL',FakeSMTP)
    assert dispatch_email_queue()==0
    c=db(); row=c.execute('SELECT state,attempts FROM financial_notice_deliveries WHERE user_id=1').fetchone(); assert tuple(row)==('RETRY',1)
    c.execute("UPDATE financial_notice_deliveries SET lease_until='2000-01-01' WHERE user_id=1"); c.commit(); c.close()
    assert dispatch_email_queue()==1 and dispatch_email_queue()==0
    assert len(messages)==2 and messages[0]==messages[1]


def test_worker_crash_releases_lease_and_does_not_claim_success(db,monkeypatch):
    import database
    from flask import Flask
    from services import flow_worker
    monkeypatch.setattr(database,'get_db_connection',db)
    monkeypatch.setattr(flow_worker,'_provider_reconciliation',lambda:None)
    def crash(): raise RuntimeError('controlled worker failure')
    monkeypatch.setattr(flow,'replay_retry_webhooks',crash)
    app=Flask(__name__)
    with pytest.raises(RuntimeError): flow_worker.run_once(app)
    c=db(); row=c.execute('SELECT expires_at,last_success FROM flow_worker_lease').fetchone()
    assert row['expires_at'] is None and row['last_success'] is None; c.close()
    monkeypatch.setattr(flow,'replay_retry_webhooks',lambda:0)
    assert flow_worker.run_once(app)
    c=db(); assert c.execute('SELECT last_success FROM flow_worker_lease').fetchone()[0]; c.close()


def test_invalid_money_and_fractional_quantity_fail_without_reserving(db):
    for invalid in ('NaN','Infinity','not-money'):
        with pytest.raises(flow.FlowError): flow.money_to_cents(invalid)
    for quantity in (1.5,True,'1.5'):
        with pytest.raises(flow.FlowError): flow.prepare_checkout(1,[{'listing_id':10,'quantity':quantity,'price_each':100}],'card',0,{},'invalid-'+str(quantity))
    c=db(); assert c.execute('SELECT quantity FROM listings WHERE id=10').fetchone()[0]==20; c.close()


def test_insurance_replay_cannot_change_posted_cost(db):
    funded(db)
    c=db(); approve(c,'ups_coverage_and_claim_policy'); ship=c.execute('SELECT id FROM shipments').fetchone()[0]; c.close()
    flow.record_insurance(ship,9,'policy',10000,100,{'covered':True,'reference':'receipt'})
    flow.record_insurance(ship,9,'policy',10000,100,{'covered':True,'reference':'receipt'})
    with pytest.raises(flow.FlowError): flow.record_insurance(ship,9,'policy',10000,200,{'covered':True,'reference':'changed'})
    c=db(); assert c.execute('SELECT premium_cents FROM insurance_policies').fetchone()[0]==100
    assert c.execute("SELECT COUNT(*) FROM ledger_journals WHERE event_type='INSURANCE_PURCHASED'").fetchone()[0]==1; c.close()
    assert flow.reconcile_internal()==[]


def test_admin_launch_controls_are_atomic_audited_and_enforced(db,monkeypatch):
    from flask import Flask
    import time,database
    import utils.auth_utils as auth
    from core.blueprints.admin import admin_bp
    monkeypatch.setattr(database,'get_db_connection',db)
    monkeypatch.setattr(auth,'get_db_connection',db)
    c=db(); c.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0'); c.execute('UPDATE users SET is_admin=1 WHERE id=1'); c.commit();c.close()
    app=Flask(__name__);app.config.update(TESTING=True,SECRET_KEY='disposable',REQUIRE_ADMIN_REAUTH=True)
    app.register_blueprint(admin_bp,url_prefix='/admin'); client=app.test_client()
    with client.session_transaction() as session: session['user_id']=1;session['authenticated_at']=time.time()
    response=client.put('/admin/api/flow-controls',json={'checkout_enabled':False,'manual_payouts_enabled':False})
    assert response.status_code==200 and response.json['controls']['checkout_enabled'] is False
    assert client.put('/admin/api/flow-controls',json={'checkout_enabled':1}).status_code==400
    c=db(); assert c.execute("SELECT COUNT(*) FROM flow_audit_events WHERE event_type='LAUNCH_CONTROLS_CHANGED'").fetchone()[0]==1; c.close()
    with pytest.raises(flow.FlowError) as exc: prep(db)
    assert exc.value.code=='OPERATIONS_PAUSED'


def test_internal_dispute_confirmation_releases_only_matching_hold(db):
    from services.admin_flow_service import close_internal_dispute
    exe,fill,_=funded(db)
    c=db()
    c.execute('CREATE TABLE disputes (id INTEGER PRIMARY KEY,status TEXT,resolved_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS dispute_fill_links (dispute_id INTEGER,seller_fill_id TEXT,created_at TEXT)')
    c.execute("INSERT INTO disputes VALUES (9,'under_review',NULL)")
    c.execute('INSERT INTO dispute_fill_links VALUES (9,?,?)',(fill,flow._now()))
    for hid,kind,source in [('internal','INTERNAL_DISPUTE','9'),('other','SHIPPING_FAILURE','9')]:
        c.execute('INSERT INTO holds VALUES (?,?,?,?,?,?,?,NULL)',(hid,fill,kind,'review','ACTIVE',source,flow._now()))
    c.commit();c.close()
    refund,_=flow.create_refund(exe['id'],{fill:1},'SELLER_FAULT','dispute-refund-9')
    flow.record_refund_provider_result(refund['id'],{'id':'re_dispute','status':'pending'})
    c=db();assert c.execute('SELECT status FROM disputes').fetchone()[0]=='under_review';assert c.execute("SELECT state FROM holds WHERE id='internal'").fetchone()[0]=='ACTIVE';c.close()
    flow.record_refund_provider_result(refund['id'],{'id':'re_dispute','status':'succeeded'})
    flow.record_refund_provider_result(refund['id'],{'id':'re_dispute','status':'succeeded'})
    c=db();assert c.execute('SELECT status FROM disputes').fetchone()[0]=='resolved_refund';assert c.execute("SELECT state FROM holds WHERE id='internal'").fetchone()[0]=='RELEASED';assert c.execute("SELECT state FROM holds WHERE id='other'").fetchone()[0]=='ACTIVE';c.close()
    assert flow.reconcile_internal()==[]


def test_legacy_payout_hold_release_preserves_other_holds(db):
    from services.admin_flow_service import hold_legacy_payout
    exe,fill,_=funded(db)
    c=db();order=c.execute('SELECT legacy_order_id FROM executions').fetchone()[0];seller=c.execute('SELECT seller_id FROM seller_fills').fetchone()[0]
    c.execute('CREATE TABLE order_payouts (id INTEGER PRIMARY KEY,order_id INTEGER,seller_id INTEGER)')
    c.execute('INSERT INTO order_payouts VALUES (5,?,?)',(order,seller))
    c.execute('INSERT INTO holds VALUES (?,?,?,?,?,?,?,NULL)',('another',fill,'INTERNAL_DISPUTE','review','ACTIVE','5',flow._now()));c.commit();c.close()
    assert hold_legacy_payout(5,1,'review')
    assert hold_legacy_payout(5,1,'review',release=True)
    c=db();assert c.execute("SELECT state FROM holds WHERE hold_type='ADMIN_PAYOUT'").fetchone()[0]=='RELEASED';assert c.execute("SELECT state FROM holds WHERE id='another'").fetchone()[0]=='ACTIVE';c.close()


def test_unverified_recovery_recording_is_retired(db):
    with pytest.raises(flow.FlowError) as exc: flow.record_recovery_attempt('fake','PROVIDER_REVERSAL',100,'SUCCEEDED','tr_fake')
    assert exc.value.code=='REVIEWED_RECOVERY_REQUIRED'


def test_admin_dispute_pending_refund_retries_original_operation(db,monkeypatch):
    from services import dispute_service as dispute
    exe,fill,_=funded(db)
    monkeypatch.setattr(dispute,'_get_conn',db)
    c=db();order=c.execute('SELECT legacy_order_id FROM executions').fetchone()[0]
    c.execute('CREATE TABLE disputes (id INTEGER PRIMARY KEY,status TEXT,buyer_id INTEGER,seller_id INTEGER,order_id INTEGER,resolved_at TEXT,resolved_by_admin_id INTEGER,resolution_note TEXT,stripe_refund_id TEXT,refund_amount REAL)')
    c.execute('CREATE TABLE dispute_timeline (dispute_id INTEGER,actor_type TEXT,actor_id INTEGER,event_type TEXT,note TEXT,created_at TEXT)')
    c.execute("INSERT INTO disputes VALUES (8,'open',1,2,?,NULL,NULL,NULL,NULL,NULL)",(order,))
    c.execute('INSERT INTO dispute_fill_links VALUES (8,?,?)',(fill,flow._now()))
    c.execute('INSERT INTO holds VALUES (?,?,?,?,?,?,?,NULL)',('internal8',fill,'INTERNAL_DISPUTE','review','ACTIVE','8',flow._now()));c.commit();c.close()
    calls=[]
    def pending(rid):
        calls.append(rid)
        flow.record_refund_provider_result(rid,{'id':'re_pending8','status':'pending'})
        return SimpleNamespace(id='re_pending8',status='pending')
    monkeypatch.setattr(flow,'submit_refund',pending)
    monkeypatch.setattr('services.risk_service.recompute_risk_profile',lambda *a:None)
    assert not dispute.admin_resolve(8,1,'resolved_refund','approved')['success']
    assert not dispute.admin_resolve(8,1,'resolved_refund','retry')['success']
    assert len(calls)==2 and calls[0]==calls[1]
    c=db();row=c.execute('SELECT status,resolved_at FROM disputes').fetchone();assert row['status']=='under_review' and row['resolved_at'] is None;assert c.execute("SELECT state FROM holds WHERE id='internal8'").fetchone()[0]=='ACTIVE';c.close()
    flow.record_refund_provider_result(calls[0],{'id':'re_pending8','status':'succeeded'})
    c=db();assert c.execute('SELECT status FROM disputes').fetchone()[0]=='resolved_refund';c.close()


def test_production_session_validation_fails_closed_on_database_error(monkeypatch):
    import database
    from app import app
    def unavailable(): raise RuntimeError('database unavailable')
    monkeypatch.setattr(database,'get_db_connection',unavailable)
    monkeypatch.setitem(app.config,'TESTING',False)
    with app.test_client() as client:
        with client.session_transaction() as session: session['user_id']=1
        response=client.get('/account/api/payment-methods')
    assert response.status_code==503
    assert response.get_json()=={'error':'Account verification is temporarily unavailable'}


def test_dispute_and_failed_payment_notices_are_durable_and_scoped(db,monkeypatch):
    import database
    monkeypatch.setattr(database,"get_db_connection",db)
    from services.delivery_service import dispatch_financial_notifications
    checkout,snap=prep(db,[{'listing_id':10,'quantity':1,'price_each':100},{'listing_id':11,'quantity':1,'price_each':200}],rail='card')
    exe,_=flow.finalize_payment(checkout['id'],payment(checkout,snap))
    c=db();c.execute('CREATE TABLE notifications(id INTEGER PRIMARY KEY,user_id INTEGER,type TEXT,title TEXT,message TEXT,related_order_id INTEGER,metadata TEXT)')
    c.execute("UPDATE outbox_events SET state='SENT'")
    flow._emit(c,'INTERNAL_DISPUTE_OPENED','execution',exe['id'],{'seller_ids':[2],'dispute_id':9},identity='9')
    flow._emit(c,'PAYMENT_FAILED','checkout',checkout['id'],{},identity='evt_failure')
    c.commit();c.close()
    assert dispatch_financial_notifications()==2
    assert dispatch_financial_notifications()==0
    c=db();recipients=c.execute('SELECT user_id,subject FROM financial_notice_deliveries ORDER BY subject,user_id').fetchall()
    assert [(r['user_id'],r['subject']) for r in recipients]==[(1,'Internal dispute opened'),(2,'Internal dispute opened'),(1,'Payment failed')]
    assert c.execute('SELECT COUNT(*) FROM notifications').fetchone()[0]==3;c.close()


@pytest.mark.parametrize('amount',[True,1.5,'NaN',None,'100.0'])
def test_insurance_rejects_invalid_cents_without_ledger_write(db,amount):
    exe,fill,_=funded(db)
    c=db();shipment=c.execute('SELECT id FROM shipments').fetchone()[0];before=c.execute('SELECT COUNT(*) FROM ledger_journals').fetchone()[0];c.close()
    with pytest.raises(flow.FlowError) as exc: flow.record_insurance(shipment,1,'policy',20000,amount,{'covered':True})
    assert exc.value.code=='INVALID_AMOUNT'
    c=db();assert c.execute('SELECT COUNT(*) FROM insurance_policies').fetchone()[0]==0;assert c.execute('SELECT COUNT(*) FROM ledger_journals').fetchone()[0]==before;c.close()
