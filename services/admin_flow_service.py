"""Canonical admin holds cannot be bypassed by legacy order projections."""
from services.flow_safety import serialized
from services import flow_of_funds as flow


@serialized
def hold_order(order_id, admin_id, reason, conn=None):
    exe=conn.execute('SELECT id FROM executions WHERE legacy_order_id=?',(order_id,)).fetchone()
    if not exe: return False
    for fill in conn.execute('SELECT id FROM seller_fills WHERE execution_id=?',(exe['id'],)).fetchall():
        conn.execute("INSERT INTO holds VALUES (?,?,?,?,?,?,?,NULL) ON CONFLICT(seller_fill_id,hold_type,source_id) DO UPDATE SET state='ACTIVE',reason=excluded.reason,released_at=NULL",(flow._id('hold'),fill['id'],'ADMIN_REVIEW',reason,'ACTIVE',str(order_id),flow._now()))
    flow._audit(conn,'execution',exe['id'],'ADMIN_HOLD','admin',admin_id,metadata={'reason':reason})
    return True


@serialized
def release_order_review(order_id, admin_id, conn=None):
    exe=conn.execute('SELECT id FROM executions WHERE legacy_order_id=?',(order_id,)).fetchone()
    if not exe: return False
    conn.execute("UPDATE holds SET state='RELEASED',released_at=? WHERE hold_type='ADMIN_REVIEW' AND source_id=? AND seller_fill_id IN (SELECT id FROM seller_fills WHERE execution_id=?)",(flow._now(),str(order_id),exe['id']))
    flow._audit(conn,'execution',exe['id'],'ADMIN_REVIEW_RELEASED','admin',admin_id)
    return True


@serialized
def deliver_order(order_id, seller_id, admin_id, evidence, conn=None):
    exe=conn.execute('SELECT id FROM executions WHERE legacy_order_id=?',(order_id,)).fetchone()
    if not exe: return False
    if not isinstance(evidence,dict):
        raise flow.FlowError('Carrier delivery evidence is required','CARRIER_EVIDENCE_REQUIRED',409)
    shipments=conn.execute('SELECT s.id FROM shipments s JOIN seller_fills f ON f.id=s.seller_fill_id WHERE f.execution_id=? AND f.seller_id=?',(exe['id'],seller_id)).fetchall()
    if not shipments: raise flow.FlowError('Shipment not found','SHIPMENT_NOT_FOUND',404)
    for ship in shipments:
        flow.record_shipment_event(ship['id'],'DELIVERED',dict(evidence,reviewed_by=admin_id),conn=conn)
    return True


@serialized
def hold_legacy_payout(payout_id,admin_id,reason,release=False,conn=None):
    import database
    if not database.get_table_columns(conn,'order_payouts'): return False
    payout=conn.execute('SELECT order_id,seller_id FROM order_payouts WHERE id=?',(payout_id,)).fetchone()
    if not payout: return False
    fills=conn.execute('SELECT f.id FROM seller_fills f JOIN executions e ON e.id=f.execution_id WHERE e.legacy_order_id=? AND f.seller_id=?',(payout['order_id'],payout['seller_id'])).fetchall()
    if not fills: return False
    for fill in fills:
        if release:
            conn.execute("UPDATE holds SET state='RELEASED',released_at=? WHERE seller_fill_id=? AND hold_type='ADMIN_PAYOUT' AND source_id=?",(flow._now(),fill['id'],str(payout_id)))
        else:
            conn.execute("INSERT INTO holds VALUES (?,?,?,?,?,?,?,NULL) ON CONFLICT(seller_fill_id,hold_type,source_id) DO UPDATE SET state='ACTIVE',reason=excluded.reason,released_at=NULL",(flow._id('hold'),fill['id'],'ADMIN_PAYOUT',reason,'ACTIVE',str(payout_id),flow._now()))
    flow._audit(conn,'legacy_payout',str(payout_id),'ADMIN_PAYOUT_HOLD_RELEASED' if release else 'ADMIN_PAYOUT_HELD','admin',admin_id,metadata={'reason':reason})
    return True


@serialized
def close_internal_dispute(dispute_id,admin_id,conn=None):
    conn.execute("UPDATE holds SET state='RELEASED',released_at=? WHERE hold_type='INTERNAL_DISPUTE' AND source_id=?",(flow._now(),str(dispute_id)))
    flow._audit(conn,'dispute',str(dispute_id),'INTERNAL_HOLD_RELEASED','admin',admin_id)


def confirm_dispute_refund(conn,refund):
    import database
    key=conn.execute('SELECT idempotency_key FROM financial_operations WHERE id=?',(refund['financial_operation_id'],)).fetchone()[0]
    prefix='dispute-refund-'
    if not key.startswith(prefix) or not key[len(prefix):].isdigit() or not database.get_table_columns(conn,'disputes'): return
    did=int(key[len(prefix):])
    links=conn.execute('SELECT f.* FROM seller_fills f JOIN dispute_fill_links d ON d.seller_fill_id=f.id WHERE d.dispute_id=?',(did,)).fetchall()
    if not links or any(f['execution_id']!=refund['execution_id'] for f in links): return
    for fill in links:
        confirmed=conn.execute("SELECT COALESCE(SUM(a.quantity),0) FROM refund_allocations a JOIN flow_refunds r ON r.id=a.refund_id WHERE a.seller_fill_id=? AND r.state='SUCCEEDED'",(fill['id'],)).fetchone()[0]
        if confirmed!=fill['quantity']: return
    conn.execute("UPDATE disputes SET status='resolved_refund',resolved_at=? WHERE id=?",(flow._now(),did))
    close_internal_dispute(did,0,conn=conn)
    sellers=list({f['seller_id'] for f in links})
    flow._emit(conn,'INTERNAL_DISPUTE_RESOLVED','execution',refund['execution_id'],{'dispute_id':did,'seller_ids':sellers,'status':'resolved_refund'},identity=str(did))
