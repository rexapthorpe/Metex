"""Read-only pre-migration report; no bucket IDs or historical records are changed."""
import json
import database
from services.catalog_identity_service import mixed_buckets


def main():
    conn=database.get_db_connection()
    try: print(json.dumps({'mixed_buckets':mixed_buckets(conn)},indent=2))
    finally: conn.close()


if __name__=='__main__': main()
