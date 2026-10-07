"""Seed explicitly simulated evidence only in a marked temporary preview database.

Run from the repository: python -m scripts.seed_smart_pricing_demo --database PATH
The preview root must contain ISOLATED_METEX_PREVIEW. Never touches providers.
"""
import argparse
import hashlib
import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from services import smart_pricing_service as smart
from services.flow_of_funds import seller_fee_cents


def seed(path):
    path = Path(path).resolve()
    if not path.is_relative_to(Path('/private/tmp')) or not (path.parent.parent / 'ISOLATED_METEX_PREVIEW').is_file():
        raise ValueError('Requires a marked, isolated preview database under /private/tmp.')
    if not path.is_file():
        raise ValueError('Preview database must already exist.')
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            conn.execute('CREATE TABLE IF NOT EXISTS smart_demo_manifest (id INTEGER PRIMARY KEY, data_json TEXT NOT NULL)')
            existing = conn.execute('SELECT data_json FROM smart_demo_manifest WHERE id=1').fetchone()
            if existing:
                return json.loads(existing['data_json'])
            owner = conn.execute("SELECT id FROM users WHERE username='testuser'").fetchone()
            if not owner:
                raise ValueError('Requires the existing local testuser account.')
            cached = conn.execute("SELECT price_usd_per_oz FROM spot_prices WHERE metal='gold'").fetchone()
            if not cached or cached[0] <= 0:
                raise ValueError('Requires a feed-derived gold quote; no synthetic current spot price is created.')
            basis_cents = smart.cents(cached[0])
            now = smart.now_utc()
            def insert(table, values):
                columns = ','.join(values)
                marks = ','.join('?' for _ in values)
                return conn.execute(f'INSERT INTO {table} ({columns}) VALUES ({marks})',tuple(values.values())).lastrowid
            bucket = conn.execute('SELECT COALESCE(MAX(bucket_id),0)+1 FROM categories').fetchone()[0]
            category = insert('categories', dict(name='SIMULATION — 1 oz Gold Bar',bucket_id=bucket,metal='Gold',product_type='Bar',product_line='PAMP Suisse',mint='PAMP Suisse',year='2026',weight='1 oz',purity='.9999',finish='BU',condition_category='BU',series_variant='None',is_isolated=0,graded=0))
            ids = []
            premiums = [50,55,60,65,70,75,80,85]
            for index, premium in enumerate([70]+premiums):
                seller = owner['id'] if index==0 else insert('users',dict(username=f'smart_demo_seller_{index}',email=f'smart-demo-{index}@example.invalid',password='DISABLED_SIMULATION_ACCOUNT',password_hash='DISABLED_SIMULATION_ACCOUNT',is_admin=0))
                lid = insert('listings',dict(seller_id=seller,category_id=category,quantity=1,price_per_coin=(basis_cents+premium*100)/100,active=1,name=f'SIMULATION — Gold Bar {index+1}',description='Simulated inventory for local Smart Pricing testing. Not a real offer or transaction.',pricing_mode='premium_to_spot',spot_premium=premium,floor_price=.01,pricing_metal='Gold',is_isolated=0,graded=0,packaging_type='Capsule',actual_year='2026'))
                ids.append(lid)
                if index==0:
                    continue
                stamp = (now-timedelta(days=9-index)).isoformat()
                # Historical metal values are simulated and frozen independently of today's quote.
                historical_metal = basis_cents+(index-4)*1000
                gross = historical_metal+premium*100
                fee = seller_fee_cents(gross)
                key = f'smart-demo-{bucket}-{index}'
                product = smart.signature(smart.product(conn,lid))
                snapshot = json.dumps({'simulation':True,'lines':[{'listing_id':lid,'smart_pricing_basis':{'product':product,'metal_value_cents':historical_metal}}]},sort_keys=True)
                insert('execution_snapshots',dict(id=key,checkout_id=key,version=1,snapshot_hash=hashlib.sha256(snapshot.encode()).hexdigest(),currency='usd',payment_rail='card',buyer_id=owner['id'],merchandise_cents=gross,tax_cents=0,grading_cents=0,other_buyer_charges_cents=0,card_surcharge_cents=0,buyer_total_cents=gross,shipping_json='{}',snapshot_json=snapshot,created_at=stamp))
                insert('executions',dict(id=key,checkout_id=key,snapshot_id=key,payment_operation_id=key,provider_payment_id='SIMULATED_NO_PROVIDER_'+key,buyer_id=owner['id'],state='ACTIVE',payment_state='APPROVED',payment_approved_at=stamp,created_at=stamp,updated_at=stamp))
                insert('snapshot_lines',dict(id=key,snapshot_id=key,listing_id=lid,seller_id=seller,quantity=1,buyer_unit_cents=gross,seller_unit_cents=gross,buyer_gross_cents=gross,seller_gross_cents=gross,seller_fee_cents=fee,seller_net_cents=gross-fee,spread_cents=0))
                insert('seller_fills',dict(id=key,execution_id=key,snapshot_line_id=key,seller_id=seller,quantity=1,state='FUNDED',seller_gross_cents=gross,seller_fee_cents=fee,seller_net_cents=gross-fee,spread_cents=0,created_at=stamp,updated_at=stamp))
                insert('shipments',dict(id=key,seller_fill_id=key,leg_type='SELLER_TO_BUYER',state='DELIVERED',destination_type='BUYER',delivered_at=stamp,created_at=stamp,updated_at=stamp))
                insert('bucket_price_history',dict(bucket_id=bucket,best_ask_price=gross/100,timestamp=stamp))
            source, evidence = smart.evidence(conn,ids[0],smart.product(conn,ids[0]),now)
            if source!='sales_exact' or len(evidence)!=8:
                raise ValueError('Simulated sales failed exact-match evidence validation.')
            result=dict(bucket_id=bucket,category_id=category,listing_ids=ids,edit_listing_id=ids[0],simulated_sales=8,premiums_dollars=premiums,source=source)
            insert('smart_demo_manifest',dict(id=1,data_json=json.dumps(result)))
            return result
    finally:
        conn.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True)
    print(json.dumps(seed(parser.parse_args().database),indent=2))
