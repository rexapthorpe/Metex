"""Atomic in-app event fanout and a durable email queue.

SMTP cannot promise exactly-once delivery after an ambiguous connection failure.
Stable Message-ID supports recipient deduplication; the queue retains failures.
"""
import json
import os
import smtplib
from email.message import EmailMessage
from html import escape
from datetime import datetime, timedelta, timezone
import database


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS financial_notice_deliveries (
      notice_key TEXT PRIMARY KEY,outbox_id TEXT NOT NULL,user_id INTEGER NOT NULL,
      subject TEXT NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'PENDING',
      attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT,lease_until TIMESTAMP,sent_at TIMESTAMP)''')


def dispatch_financial_notifications(limit=100):
    from services.flow_of_funds import ensure_flow_schema
    conn=database.get_db_connection()
    try:
        ensure_flow_schema(conn); ensure_schema(conn)
        conn.execute('UPDATE flow_mutex SET revision=revision+1 WHERE id=1')
        rows=conn.execute("SELECT * FROM outbox_events WHERE state IN ('PENDING','RETRY') ORDER BY created_at LIMIT ?",(limit,)).fetchall()
        sent=0
        for row in rows:
            payload=json.loads(row['payload_json']); typ=row['event_type'].split(':')[0]
            exe=None
            if row['aggregate_type']=='execution':
                exe=conn.execute('SELECT * FROM executions WHERE id=?',(row['aggregate_id'],)).fetchone()
            elif row['aggregate_type']=='refund':
                exe=conn.execute('SELECT e.* FROM executions e JOIN flow_refunds r ON r.execution_id=e.id WHERE r.id=?',(row['aggregate_id'],)).fetchone()
            elif row['aggregate_type']=='shipment':
                exe=conn.execute('SELECT e.* FROM executions e JOIN seller_fills f ON f.execution_id=e.id JOIN shipments s ON s.seller_fill_id=f.id WHERE s.id=?',(row['aggregate_id'],)).fetchone()
            recipients=[]
            if exe:
                snap=conn.execute('SELECT * FROM execution_snapshots WHERE id=?',(exe['snapshot_id'],)).fetchone()
                body=f"Order #{exe['legacy_order_id']}: {typ.replace('_',' ').lower()}."
                if typ=='EXECUTION_FUNDED':
                    body+=f" Merchandise ${snap['merchandise_cents']/100:.2f}; tax ${snap['tax_cents']/100:.2f}; card surcharge ${snap['card_surcharge_cents']/100:.2f}; total ${snap['buyer_total_cents']/100:.2f}."
                recipients.append((exe['buyer_id'],body,exe['legacy_order_id']))
                sellers=conn.execute('SELECT seller_id,seller_net_cents,id FROM seller_fills WHERE execution_id=?',(exe['id'],)).fetchall()
                if payload.get('seller_ids') is not None:
                    sellers=[f for f in sellers if f['seller_id'] in payload['seller_ids']]
                if row['aggregate_type']=='shipment':
                    shipment=conn.execute('SELECT seller_fill_id FROM shipments WHERE id=?',(row['aggregate_id'],)).fetchone()
                    sellers=[f for f in sellers if f['id']==shipment['seller_fill_id']]
                if row['aggregate_type']=='refund':
                    affected={f['seller_fill_id'] for f in conn.execute('SELECT seller_fill_id FROM refund_allocations WHERE refund_id=?',(row['aggregate_id'],)).fetchall()}
                    sellers=[f for f in sellers if f['id'] in affected]
                seller_totals={}
                for seller in sellers:
                    seller_totals[seller['seller_id']]=seller_totals.get(seller['seller_id'],0)+seller['seller_net_cents']
                for seller_id,net in seller_totals.items():
                    message=f"Order #{exe['legacy_order_id']}: {typ.replace('_',' ').lower()}. Your original fill net: ${net/100:.2f}."
                    message+=' Shipping authorized; upload accepted UPS tracking by the order deadline.' if typ=='SHIPMENT_AUTHORIZED' else ' Follow the current order status; do not ship before authorization.'
                    recipients.append((seller_id,message,exe['legacy_order_id']))
            elif row['aggregate_type']=='checkout' and typ=='PAYMENT_FAILED':
                checkout=conn.execute('SELECT buyer_id FROM checkout_attempts WHERE id=?',(row['aggregate_id'],)).fetchone()
                if checkout: recipients=[(checkout['buyer_id'],'Your payment failed or was canceled. Check the current checkout status before retrying; shipping is not authorized.',None)]
            elif row['aggregate_type']=='checkout' and typ=='ACH_PROCESSING':
                order=conn.execute('SELECT o.* FROM orders o JOIN checkout_attempts c ON c.provider_payment_id=o.stripe_payment_intent_id WHERE c.id=?',(row['aggregate_id'],)).fetchone()
                if order: recipients=[(order['buyer_id'],f"Order #{order['id']}: bank payment is processing. Shipping waits for confirmed payment.",order['id'])]
            elif row['aggregate_type']=='checkout' and typ.startswith('LATE_PAYMENT_REFUND_'):
                checkout=conn.execute('SELECT buyer_id FROM checkout_attempts WHERE id=?',(row['aggregate_id'],)).fetchone()
                if checkout:
                    description={'LATE_PAYMENT_REFUND_PENDING':'Payment arrived after the reservation ended. A full refund is pending; no order will be shipped.',
                      'LATE_PAYMENT_REFUND_SUCCEEDED':'The provider confirmed your full refund for the expired reservation.',
                      'LATE_PAYMENT_REFUND_FAILED':'The refund for your expired reservation requires support review. The refund has not been confirmed.'}.get(typ)
                    if description: recipients=[(checkout['buyer_id'],description,None)]
            elif row['aggregate_type']=='seller' and typ=='BANK_PAYOUT':
                recipients=[(int(row['aggregate_id']),f"Bank payout {payload['payout_id']}: {payload.get('status','pending')}.",None)]
            if not recipients:
                conn.execute("UPDATE outbox_events SET state='RETRY',attempts=attempts+1 WHERE id=?",(row['id'],))
                continue
            for user,body,order in recipients:
                key=f"{row['id']}:{user}"
                if conn.execute('SELECT notice_key FROM financial_notice_deliveries WHERE notice_key=?',(key,)).fetchone(): continue
                title=typ.replace('_',' ').capitalize()
                conn.execute('INSERT INTO financial_notice_deliveries(notice_key,outbox_id,user_id,subject,body) VALUES (?,?,?,?,?)',(key,row['id'],user,title,body))
                # Financial notices are mandatory transaction records, not marketing.
                conn.execute('INSERT INTO notifications(user_id,type,title,message,related_order_id,metadata) VALUES (?,?,?,?,?,?)',(user,'financial_status',title,body,order,json.dumps({'notice_key':key})))
            conn.execute("UPDATE outbox_events SET state='SENT',sent_at=CURRENT_TIMESTAMP WHERE id=?",(row['id'],)); sent+=1
        conn.commit()
        return sent
    except Exception:
        conn.rollback(); raise
    finally: conn.close()


def dispatch_email_queue(limit=25):
    # Explicit delivery switch defaults off; tests and setup never send real mail.
    if os.getenv('EMAIL_DELIVERY_ENABLED')!='true': return 0
    import config
    if not config.EMAIL_ADDRESS or not config.EMAIL_PASSWORD:
        raise RuntimeError('Email credentials are required')
    conn=database.get_db_connection(); ensure_schema(conn)
    now=datetime.now(timezone.utc)
    rows=conn.execute("SELECT * FROM financial_notice_deliveries WHERE state<>'SENT' AND (lease_until IS NULL OR lease_until<?) ORDER BY notice_key LIMIT ?",(now.isoformat(),limit)).fetchall()
    conn.commit(); conn.close(); sent=0
    for row in rows:
        conn=database.get_db_connection()
        changed=conn.execute("UPDATE financial_notice_deliveries SET state='SENDING',attempts=attempts+1,lease_until=? WHERE notice_key=? AND state<>'SENT' AND (lease_until IS NULL OR lease_until<?)",((now+timedelta(minutes=5)).isoformat(),row['notice_key'],now.isoformat()))
        user=conn.execute('SELECT email FROM users WHERE id=?',(row['user_id'],)).fetchone()
        conn.commit(); conn.close()
        if changed.rowcount!=1: continue
        try:
            if not user or not user['email']: raise ValueError('Recipient email unavailable')
            message=EmailMessage(); message['From']=config.EMAIL_ADDRESS; message['To']=user['email']
            message['Subject']=row['subject']; message['Message-ID']=f"<metex-{row['notice_key']}@{config.EMAIL_ADDRESS.split('@')[-1]}>"
            message.set_content(row['body'])
            with smtplib.SMTP_SSL('smtp.gmail.com',465,timeout=20) as smtp:
                smtp.login(config.EMAIL_ADDRESS,config.EMAIL_PASSWORD); smtp.send_message(message)
            state='SENT'; error=None; sent+=1
        except Exception as exc: state='RETRY'; error=type(exc).__name__
        conn=database.get_db_connection()
        conn.execute('UPDATE financial_notice_deliveries SET state=?,last_error=?,lease_until=?,sent_at=? WHERE notice_key=?',(state,error,None if state=='SENT' else (now+timedelta(minutes=5)).isoformat(),now.isoformat() if state=='SENT' else None,row['notice_key']))
        conn.commit(); conn.close()
    return sent
