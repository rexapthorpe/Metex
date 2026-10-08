"""Read canonical order status for customer views without exposing other seller funds."""
from services import flow_of_funds as flow


def order_state(conn,order_id,seller_id=None):
    exe=conn.execute('SELECT * FROM executions WHERE legacy_order_id=?',(order_id,)).fetchone()
    if not exe: return None
    query='SELECT * FROM seller_fills WHERE execution_id=?'; args=[exe['id']]
    if seller_id is not None: query+=' AND seller_id=?'; args.append(seller_id)
    fills=conn.execute(query,args).fetchall()
    if not fills: return None
    shipments=[]; total=0; refunded=0; pending=False; released=0; entitlement=0; holds=False
    for fill in fills:
        total+=fill['quantity']
        refunded+=conn.execute("SELECT COALESCE(SUM(a.quantity),0) FROM refund_allocations a JOIN flow_refunds r ON r.id=a.refund_id WHERE a.seller_fill_id=? AND r.state='SUCCEEDED'",(fill['id'],)).fetchone()[0]
        pending=pending or bool(conn.execute("SELECT a.id FROM refund_allocations a JOIN flow_refunds r ON r.id=a.refund_id WHERE a.seller_fill_id=? AND r.state NOT IN ('FAILED','SUCCEEDED')",(fill['id'],)).fetchone())
        holds=holds or bool(conn.execute("SELECT id FROM holds WHERE seller_fill_id=? AND state='ACTIVE'",(fill['id'],)).fetchone())
        for ship in conn.execute('SELECT state,carrier,tracking_number,delivered_at,tracking_due_at FROM shipments WHERE seller_fill_id=?',(fill['id'],)).fetchall(): shipments.append(dict(ship))
        payable=conn.execute('SELECT amount_cents,released_cents FROM seller_payables WHERE seller_fill_id=?',(fill['id'],)).fetchone()
        if payable: entitlement+=payable['amount_cents']; released+=payable['released_cents']
    if exe['payment_state']!='APPROVED': status='Payment Review'
    elif pending: status='Refund Pending'
    elif refunded==total: status='Refunded'
    elif refunded: status='Partially Refunded'
    elif shipments and all(s['state']=='DELIVERED' for s in shipments): status='Delivered'
    elif any(s['state']=='IN_TRANSIT' for s in shipments): status='Awaiting Delivery'
    elif any(s['state'] in ('AWAITING_TRACKING','TRACKING_VERIFICATION_PENDING') for s in shipments): status='Awaiting Shipment'
    else: status='Processing'
    payout='Connected account transfer confirmed' if released and released>=entitlement else 'Held for review' if holds or pending or exe['payment_state']!='APPROVED' else 'Awaiting eligibility review'
    result={'status':status,'payment_state':exe['payment_state'],'shipments':shipments,'refund_pending':pending}
    if seller_id is not None: result.update(payout_label=payout,released_cents=released,entitlement_cents=entitlement)
    return result


def attach_account_states(conn,orders,sales,user_id):
    flow.ensure_flow_schema(conn)
    for order in orders:
        state=order_state(conn,order['id'])
        if state: order['canonical_state']=state; order['status']=state['status']
    for sale in sales:
        state=order_state(conn,sale['order_id'],user_id)
        if state:
            sale['canonical_state']=state; sale['status']=state['status']
            sale['payout_user_state']='hold'
            sale['payout_user_label']=state['payout_label']
            for field in ('payout_tracking_uploaded_str','payout_delivered_str','payout_eligible_at_str'): sale[field]=None
