"""Refund a late successful payment whose inventory was already released."""
import stripe
from services.flow_safety import serialized


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS payment_compensations (
      checkout_id TEXT PRIMARY KEY,payment_id TEXT NOT NULL UNIQUE,amount_cents INTEGER NOT NULL,
      state TEXT NOT NULL,provider_refund_id TEXT,last_error TEXT)''')


def record_late_payment(conn, checkout, snapshot, payment):
    from services import flow_of_funds as flow
    ensure_schema(conn)
    conn.execute("INSERT INTO payment_compensations VALUES (?,?,?,'PENDING',NULL,NULL) ON CONFLICT(checkout_id) DO NOTHING",(checkout['id'],payment['id'],snapshot['buyer_total_cents']))
    flow._journal(conn,'checkout',checkout['id'],'LATE_PAYMENT',f"late-payment:{payment['id']}",[
      {'account':'PROCESSOR_CASH','debit':snapshot['buyer_total_cents'],'component':'late_payment'},
      {'account':'BUYER_REFUND_PAYABLE','credit':snapshot['buyer_total_cents'],'component':'late_payment'}])
    conn.execute("UPDATE checkout_attempts SET state='COMPENSATION_REQUIRED' WHERE id=?",(checkout['id'],))
    flow._emit(conn,'LATE_PAYMENT_REFUND_PENDING','checkout',checkout['id'],{'amount_cents':snapshot['buyer_total_cents']})


@serialized
def finish_compensation(checkout_id, provider, conn=None):
    from services import flow_of_funds as flow
    ensure_schema(conn)
    row=conn.execute('SELECT * FROM payment_compensations WHERE checkout_id=?',(checkout_id,)).fetchone()
    if not row or provider.amount!=row['amount_cents'] or provider.payment_intent!=row['payment_id']:
        raise flow.FlowError('Compensation binding mismatch','REFUND_BINDING_MISMATCH',409)
    if row['provider_refund_id'] and row['provider_refund_id']!=provider.id:
        raise flow.FlowError('Compensation refund identity changed','REFUND_BINDING_MISMATCH',409)
    if row['state']=='SUCCEEDED': return False
    if provider.status=='succeeded':
        flow._journal(conn,'checkout',checkout_id,'LATE_PAYMENT_REFUNDED',f'late-refund:{provider.id}',[
          {'account':'BUYER_REFUND_PAYABLE','debit':row['amount_cents'],'component':'late_refund'},
          {'account':'PROCESSOR_CASH','credit':row['amount_cents'],'component':'late_refund'}])
        state='SUCCEEDED'
    elif provider.status in ('failed','canceled'): state='FAILED'
    else: state='PROCESSING'
    conn.execute('UPDATE payment_compensations SET state=?,provider_refund_id=? WHERE checkout_id=?',(state,provider.id,checkout_id))
    if state=='FAILED':
        conn.execute("INSERT INTO flow_reviews VALUES (?,?,?,?,?,?,?) ON CONFLICT(scope_type,scope_id,reason) DO NOTHING",(flow._id('review'),'checkout',checkout_id,'LATE_REFUND_FAILURE','OPEN',flow._canonical({'refund_id':provider.id}),flow._now()))
    if state in ('SUCCEEDED','FAILED'):
        flow._emit(conn,'LATE_PAYMENT_REFUND_'+state,'checkout',checkout_id,{'amount_cents':row['amount_cents']},identity=provider.id)
    return state=='SUCCEEDED'


def retry_compensations():
    from services import flow_of_funds as flow
    conn=flow.get_db_connection(); ensure_schema(conn)
    rows=conn.execute("SELECT * FROM payment_compensations WHERE state IN ('PENDING','PROCESSING') LIMIT 25").fetchall()
    conn.commit(); conn.close()
    for row in rows:
        try:
            if row['provider_refund_id']: provider=stripe.Refund.retrieve(row['provider_refund_id'])
            else: provider=stripe.Refund.create(payment_intent=row['payment_id'],amount=row['amount_cents'],
                metadata={'compensation_checkout_id':row['checkout_id']},idempotency_key=f"late-refund:{row['checkout_id']}")
            finish_compensation(row['checkout_id'],provider)
        except Exception as exc:
            conn=flow.get_db_connection()
            conn.execute('UPDATE payment_compensations SET last_error=? WHERE checkout_id=?',(type(exc).__name__,row['checkout_id']))
            conn.commit(); conn.close()
