"""Canonical provider transfer dispatch shared by manual and daily releases."""
import stripe
from services import flow_of_funds as flow
from services.connect_service import refresh_seller


def release_payable(payable_id,key=None):
    key=key or f'seller-transfer:{payable_id}'
    transfer,_=flow.claim_seller_transfer(payable_id,key)
    if transfer.get('state')=='TRANSFER_CONFIRMED': return transfer['provider_transfer_id']
    conn=flow.get_db_connection()
    try:
        row=conn.execute('''SELECT p.seller_id,u.stripe_account_id,e.provider_payment_id
          FROM seller_payables p JOIN seller_fills f ON f.id=p.seller_fill_id
          JOIN executions e ON e.id=f.execution_id JOIN users u ON u.id=p.seller_id WHERE p.id=?''',(payable_id,)).fetchone()
        ready=refresh_seller(conn,row['seller_id']) if row else False
        conn.commit()
    finally: conn.close()
    if not ready or not row or not row['stripe_account_id']:
        raise flow.FlowError('Seller account is not ready','SELLER_ACCOUNT_NOT_READY',409)
    payment=stripe.PaymentIntent.retrieve(row['provider_payment_id'])
    if payment.status!='succeeded' or payment.currency!='usd' or not payment.latest_charge:
        raise flow.FlowError('Funding source needs reconciliation','TRANSFER_SOURCE_INVALID',409)
    flow.begin_seller_transfer(transfer['id'])
    provider=stripe.Transfer.create(amount=transfer['amount_cents'],currency='usd',destination=row['stripe_account_id'],
      source_transaction=payment.latest_charge,metadata={'seller_payable_id':payable_id,'seller_id':str(row['seller_id'])},idempotency_key=key)
    if provider.amount!=transfer['amount_cents'] or provider.currency!='usd' or provider.destination!=row['stripe_account_id']:
        raise flow.FlowError('Transfer provider binding mismatch','TRANSFER_BINDING_MISMATCH',409)
    flow.complete_seller_transfer(transfer['id'],provider.id)
    return provider.id


def run_daily_releases():
    """Daily UTC evaluation; errors retain original identities for later review."""
    from datetime import datetime,timezone
    conn=flow.get_db_connection(); flow.ensure_flow_schema(conn)
    try:
        flow.require_operation_enabled(conn,'auto_payouts_enabled')
        flow.require_operation_enabled(conn,'manual_payouts_enabled')
        day=datetime.now(timezone.utc).date().isoformat()
        conn.execute('UPDATE flow_mutex SET revision=revision+1 WHERE id=1')
        last=conn.execute("SELECT value FROM system_settings WHERE key='last_auto_payout_day'").fetchone()
        if last and last['value']==day: conn.rollback(); return 0
        rows=conn.execute('SELECT id FROM seller_payables WHERE amount_cents>released_cents').fetchall()
        conn.execute("INSERT INTO system_settings(key,value) VALUES ('last_auto_payout_day',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(day,))
        conn.commit()
    except flow.FlowError:
        conn.rollback(); return 0
    finally: conn.close()
    released=0
    for row in rows:
        if not flow.evaluate_payout(row['id'])[0]: continue
        try: release_payable(row['id']); released+=1
        except Exception as exc:
            conn=flow.get_db_connection()
            conn.execute("INSERT INTO flow_reviews VALUES (?,?,?,?,?,?,?) ON CONFLICT(scope_type,scope_id,reason) DO NOTHING",(flow._id('review'),'payable',row['id'],'TRANSFER_RECONCILIATION','OPEN',flow._canonical({'failure_type':type(exc).__name__}),flow._now()))
            conn.commit(); conn.close()
    return released
