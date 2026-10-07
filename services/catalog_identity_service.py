"""Fail closed on legacy buckets containing incompatible product specifications."""
import database
FIELDS=('metal','product_line','product_type','weight','purity','mint','year','finish','grade','condition_category','series_variant','graded','grading_service','coin_series')


def mixed_buckets(conn):
    columns=database.get_table_columns(conn,'categories')
    if 'bucket_id' not in columns: return {}
    fields=[field for field in FIELDS if field in columns]
    rows=conn.execute('SELECT * FROM categories WHERE bucket_id IS NOT NULL ORDER BY bucket_id,id').fetchall()
    groups={}
    for row in rows:
        data=dict(row)
        if data.get('is_isolated'): continue
        groups.setdefault(data['bucket_id'],{}).setdefault(tuple(data.get(f) for f in fields),[]).append(data['id'])
    return {key:list(specs.values()) for key,specs in groups.items() if len(specs)>1}


def require_consistent_listing(conn,listing_id):
    columns=database.get_table_columns(conn,'categories')
    if 'bucket_id' not in columns: return
    row=conn.execute('SELECT c.* FROM categories c JOIN listings l ON l.category_id=c.id WHERE l.id=?',(listing_id,)).fetchone()
    if not row: return
    row=dict(row)
    if row.get('is_isolated') or row.get('bucket_id') is None: return
    fields=[field for field in FIELDS if field in columns]
    siblings=conn.execute('SELECT * FROM categories WHERE bucket_id=?',(row['bucket_id'],)).fetchall()
    if any(tuple(dict(other).get(f) for f in fields)!=tuple(row.get(f) for f in fields) for other in siblings if not dict(other).get('is_isolated')):
        from services.flow_of_funds import FlowError
        raise FlowError('This product group needs catalog review before purchase','CATALOG_REVIEW_REQUIRED',409)
