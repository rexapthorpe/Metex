"""Project confirmed canonical refunds; pending allocations are not returned money."""
from services import flow_of_funds as flow


def refresh_refunds(conn,execution_id):
    fills=conn.execute('SELECT id,quantity FROM seller_fills WHERE execution_id=?',(execution_id,)).fetchall()
    confirmed_total=0; quantity_total=0
    for fill in fills:
        confirmed=conn.execute("SELECT COALESCE(SUM(a.quantity),0) FROM refund_allocations a JOIN flow_refunds r ON r.id=a.refund_id WHERE a.seller_fill_id=? AND r.state='SUCCEEDED'",(fill['id'],)).fetchone()[0]
        pending=conn.execute("SELECT r.id FROM flow_refunds r JOIN refund_allocations a ON a.refund_id=r.id WHERE a.seller_fill_id=? AND r.state NOT IN ('FAILED','SUCCEEDED')",(fill['id'],)).fetchone()
        state='REFUND_PENDING' if pending else 'REFUNDED' if confirmed==fill['quantity'] else 'PARTIALLY_REFUNDED' if confirmed else 'FUNDED'
        conn.execute('UPDATE seller_fills SET state=? WHERE id=?',(state,fill['id']))
        confirmed_total+=confirmed; quantity_total+=fill['quantity']
    if confirmed_total:
        status='Refunded' if confirmed_total==quantity_total else 'Partially Refunded'
        conn.execute('UPDATE orders SET status=? WHERE id=(SELECT legacy_order_id FROM executions WHERE id=?)',(status,execution_id))
        order=conn.execute('SELECT o.* FROM orders o JOIN executions e ON e.legacy_order_id=o.id WHERE e.id=?',(execution_id,)).fetchone()
        if order and 'refund_amount' in order.keys():
            amount=conn.execute("SELECT COALESCE(SUM(total_cents),0) FROM flow_refunds WHERE execution_id=? AND state='SUCCEEDED'",(execution_id,)).fetchone()[0]
            conn.execute('UPDATE orders SET refund_amount=? WHERE id=?',(amount/100,order['id']))
