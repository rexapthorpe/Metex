"""Per-listing Tax calculations and durable transaction/reversal recording.

No tax classifications or collection obligations are guessed. Missing reviewed
configuration stops payment setup, including zero-tax orders.
"""
import json
import os
import stripe
import database


def calculate_items(conn, items, shipping):
    from services.flow_of_funds import FlowError, money_to_cents
    if os.getenv('TAX_CONFIGURATION_APPROVED')!='true':
        raise FlowError('Reviewed tax configuration is required','TAX_CONFIGURATION_REQUIRED',503)
    codes=json.loads(os.getenv('TAX_PRODUCT_CODES_JSON','{}'))
    origins=json.loads(os.getenv('TAX_SELLER_ORIGINS_JSON','{}'))
    address={key:str(shipping.get(key,'')).strip() for key in ('line1','city','state','postal_code','country')}
    if any(not value for value in address.values()) or address['country']!='US':
        raise FlowError('Complete US shipping address is required','TAX_ADDRESS_REQUIRED',400)
    if shipping.get('line2'): address['line2']=str(shipping['line2']).strip()
    records=[]
    for item in items:
        listing=conn.execute('''SELECT l.seller_id,c.product_type,c.metal FROM listings l
          JOIN categories c ON c.id=l.category_id WHERE l.id=?''',(item['listing_id'],)).fetchone()
        if not listing: raise FlowError('Listing not found','INVENTORY_UNAVAILABLE',409)
        code=codes.get(f"{listing['metal']}|{listing['product_type']}")
        origin=origins.get(str(listing['seller_id']))
        if not code or not origin:
            raise FlowError('Reviewed product tax code and seller origin are required','TAX_CONFIGURATION_REQUIRED',503)
        amount=money_to_cents(item['price_each'])*int(item['quantity'])
        calc=stripe.tax.Calculation.create(currency='usd',
          customer_details={'address':address,'address_source':'shipping'},ship_from_details={'address':origin},
          line_items=[{'amount':amount,'reference':str(item['listing_id']),'tax_code':code,'tax_behavior':'exclusive'}])
        records.append({'listing_id':int(item['listing_id']),'calculation_id':calc.id,
                        'amount_cents':amount,'tax_cents':int(calc.tax_amount_exclusive)})
    return sum(r['tax_cents'] for r in records),records


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS flow_tax_records (
      operation_key TEXT PRIMARY KEY,execution_id TEXT NOT NULL,listing_id INTEGER NOT NULL,
      refund_id TEXT,calculation_id TEXT,provider_id TEXT,state TEXT NOT NULL,
      provider_line_id TEXT,last_error TEXT,updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')


def sync_tax_records(limit=50):
    """Provider idempotency keys survive DB failures and worker restarts."""
    from services.flow_of_funds import _canonical
    conn=database.get_db_connection(); ensure_schema(conn)
    rows=conn.execute('''SELECT e.id,e.snapshot_id,s.shipping_json FROM executions e
      JOIN execution_snapshots s ON s.id=e.snapshot_id ORDER BY e.created_at''').fetchall()
    tasks=[]
    for row in rows:
        for calc in json.loads(row['shipping_json']).get('tax_calculations',[]):
            key=f"tax-sale:{row['id']}:{calc['listing_id']}"
            conn.execute('''INSERT INTO flow_tax_records(operation_key,execution_id,listing_id,calculation_id,state)
              VALUES (?,?,?,?,'PENDING') ON CONFLICT(operation_key) DO NOTHING''',
              (key,row['id'],calc['listing_id'],calc['calculation_id']))
    pending=conn.execute("SELECT * FROM flow_tax_records WHERE state='PENDING' AND refund_id IS NULL LIMIT ?",(limit,)).fetchall()
    conn.commit(); conn.close()
    for row in pending:
        try:
            transaction=stripe.tax.Transaction.create_from_calculation(calculation=row['calculation_id'],
              reference=row['operation_key'],expand=['line_items'],idempotency_key=row['operation_key'])
            data=transaction.to_dict() if hasattr(transaction,'to_dict') else dict(transaction)
            lines=data['line_items']['data']
            if len(lines)!=1 or data['line_items'].get('has_more'):
                raise ValueError('Tax transaction must contain exactly its original listing')
            conn=database.get_db_connection()
            expected=conn.execute('SELECT l.buyer_gross_cents,l.tax_cents FROM snapshot_lines l JOIN executions e ON e.snapshot_id=l.snapshot_id WHERE e.id=? AND l.listing_id=?',(row['execution_id'],row['listing_id'])).fetchone()
            conn.close()
            if not expected or data.get('reference')!=row['operation_key'] or lines[0].get('reference')!=str(row['listing_id']) or lines[0].get('amount')!=expected['buyer_gross_cents'] or lines[0].get('amount_tax')!=expected['tax_cents']:
                raise ValueError('Tax transaction snapshot binding mismatch')
            conn=database.get_db_connection()
            conn.execute("UPDATE flow_tax_records SET provider_id=?,provider_line_id=?,state='SUCCEEDED',last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE operation_key=?",(data['id'],lines[0]['id'],row['operation_key']))
            conn.commit(); conn.close()
        except Exception as exc:
            _record_error(row['operation_key'],type(exc).__name__)
    conn=database.get_db_connection()
    refunds=conn.execute('''SELECT r.id,r.execution_id,a.*,l.listing_id,t.provider_id,t.provider_line_id
      FROM flow_refunds r JOIN refund_allocations a ON a.refund_id=r.id
      JOIN seller_fills f ON f.id=a.seller_fill_id JOIN snapshot_lines l ON l.id=f.snapshot_line_id
      JOIN flow_tax_records t ON t.execution_id=r.execution_id AND t.listing_id=l.listing_id AND t.refund_id IS NULL
      WHERE r.state='SUCCEEDED' AND t.state='SUCCEEDED' ''').fetchall()
    for row in refunds:
        key=f"tax-refund:{row['refund_id']}:{row['listing_id']}"
        conn.execute('''INSERT INTO flow_tax_records(operation_key,execution_id,listing_id,refund_id,state)
          VALUES (?,?,?,?,'PENDING') ON CONFLICT(operation_key) DO NOTHING''',(key,row['execution_id'],row['listing_id'],row['refund_id']))
        existing=conn.execute('SELECT state FROM flow_tax_records WHERE operation_key=?',(key,)).fetchone()
        if existing['state']=='PENDING': tasks.append((key,dict(row)))
    conn.commit(); conn.close()
    for key,row in tasks[:limit]:
        try:
            original_amount=row['seller_net_cents']+row['seller_fee_cents']+row['spread_cents']
            reversal=stripe.tax.Transaction.create_reversal(mode='partial',original_transaction=row['provider_id'],
              reference=key,line_items=[{'original_line_item':row['provider_line_id'],'amount':-original_amount,
              'amount_tax':-row['tax_cents'],'reference':key}],idempotency_key=key)
            conn=database.get_db_connection()
            conn.execute("UPDATE flow_tax_records SET provider_id=?,state='SUCCEEDED',last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE operation_key=?",(reversal.id,key))
            conn.commit(); conn.close()
        except Exception as exc: _record_error(key,type(exc).__name__)


def _record_error(key, message):
    conn=database.get_db_connection()
    conn.execute('UPDATE flow_tax_records SET last_error=?,updated_at=CURRENT_TIMESTAMP WHERE operation_key=?',(message,key))
    conn.commit(); conn.close()
