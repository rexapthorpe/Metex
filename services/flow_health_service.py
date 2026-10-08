"""Read-only operational signals; no provider calls or customer data."""
from datetime import datetime,timezone
import database


def health():
    conn=database.get_db_connection()
    try:
        columns=database.get_table_columns(conn,'flow_worker_lease')
        worker=conn.execute('SELECT last_success FROM flow_worker_lease WHERE id=1').fetchone() if columns else None
        recent=False
        if worker and worker['last_success']:
            timestamp=datetime.fromisoformat(str(worker['last_success']).replace('Z','+00:00'))
            if timestamp.tzinfo is None: timestamp=timestamp.replace(tzinfo=timezone.utc)
            recent=0<=(datetime.now(timezone.utc)-timestamp).total_seconds()<1800
        counts={}
        for table,state in [('webhook_inbox','RETRY'),('outbox_events','RETRY'),('flow_reviews','OPEN'),('reconciliation_cases','OPEN')]:
            counts[table]=conn.execute(f'SELECT COUNT(*) FROM {table} WHERE state=?',(state,)).fetchone()[0] if database.get_table_columns(conn,table) else 0
        imbalance=conn.execute('SELECT COUNT(*) FROM (SELECT j.id FROM ledger_journals j JOIN ledger_entries e ON e.journal_id=j.id GROUP BY j.id HAVING SUM(e.debit_cents)<>SUM(e.credit_cents)) problems').fetchone()[0] if database.get_table_columns(conn,'ledger_journals') else 0
        return {'worker_recent':recent,'pending_reviews':counts,'unbalanced_journals':imbalance,'healthy':recent and imbalance==0 and counts['reconciliation_cases']==0}
    finally: conn.close()
