from database import get_db_connection

conn = get_db_connection()

# Find remaining NULL
remaining = conn.execute('SELECT id FROM categories WHERE bucket_id IS NULL').fetchone()

if remaining:
    cat_id = remaining[0]
    max_bucket = conn.execute('SELECT COALESCE(MAX(bucket_id), 0) + 1 AS next_id FROM categories').fetchone()
    next_id = max_bucket[0]

    conn.execute('UPDATE categories SET bucket_id = ? WHERE id = ?', (next_id, cat_id))
    conn.commit()
    print(f'Fixed category {cat_id} with bucket_id {next_id}')
else:
    print('No NULL bucket_ids found!')

conn.close()
