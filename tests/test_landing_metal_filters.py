"""Real buy-route SQL filtering across standard, individual and set inventory."""
import importlib
import pytest


@pytest.mark.parametrize('requested,expected',[('Gold','Gold'),('Silver','Silver'),('Platinum','Platinum'),('Palladium','Palladium'),(' gold ','Gold')])
def test_metal_filter_excludes_other_metals_in_every_catalog_group(app,monkeypatch,requested,expected):
    import database
    page=importlib.import_module('core.blueprints.buy.buy_page')
    monkeypatch.setattr(page,'get_db_connection',database.get_db_connection)
    monkeypatch.setattr(page,'render_template',lambda template,**context:context)
    c=database.get_db_connection()
    for metal_index,metal in enumerate(['Gold','Silver','Platinum','Palladium']):
        for kind_index,kind in enumerate(['standard','one_of_a_kind','set']):
            bid=900000+metal_index*10+kind_index
            cur=c.execute('INSERT INTO categories(bucket_id,metal,product_type,weight,mint,year,is_isolated) VALUES (?,?,?,?,?,?,?)',(bid,metal.lower() if metal=='Gold' else metal,'Bar','1 oz','Filter fixture',2026,int(kind!='standard')))
            c.execute('INSERT INTO listings(seller_id,category_id,price_per_coin,quantity,active,pricing_mode,is_isolated,isolated_type,name) VALUES (?,?,?,?,?,?,?,?,?)',(999999,cur.lastrowid,100,1,1,'static',int(kind!='standard'),kind if kind!='standard' else None,'Filter fixture'))
    c.commit();c.close()
    with app.test_request_context('/buy',query_string={'metal':requested}):
        result=page.buy()
    assert result['metal_filter']==expected
    for group in ['standard_buckets','one_of_a_kind_buckets','set_buckets']:
        fixtures=[b for b in result[group] if 900000<=b['bucket_id']<900100]
        assert len(fixtures)==1
        assert fixtures[0]['metal'].lower()==expected.lower()
        assert fixtures[0]['lowest_price']==100
