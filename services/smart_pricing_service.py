"""Deterministic dollar-premium management; legacy listing premium remains authoritative.
All mutations serialize with canonical inventory operations using flow_mutex.
No provider calls or browser timers. Unknown evidence means hold, never guess.
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import database

VERSION = 'premium-v1-classified-preview'
log = logging.getLogger(__name__)
STRATEGIES = {
    'fast': {'quantile': Decimal('.25'), 'hours': 24, 'step': Decimal('.25'),
             'age_grace_days': 2, 'age_ramp_days': 14, 'age_max_spread': Decimal('.50')},
    'balanced': {'quantile': Decimal('.50'), 'hours': 48, 'step': Decimal('.15'),
                 'age_grace_days': 7, 'age_ramp_days': 30, 'age_max_spread': Decimal('.25')},
    'big': {'quantile': Decimal('.75'), 'hours': 72, 'step': Decimal('.08'),
            'age_grace_days': 21, 'age_ramp_days': 60, 'age_max_spread': Decimal('.10')},
}
EVIDENCE_WEIGHTS = {'sales_exact': 8, 'sales_year': 6, 'sales_grade': 2, 'sales_family': 3,
                    'asks_exact': 2, 'asks_year': Decimal('1.5'), 'asks_grade': Decimal('.5'), 'asks_family': Decimal('.75')}
MATCH_QUALITY = {'exact': Decimal(1), 'year': Decimal('.8'), 'grade': Decimal('.3'), 'family': Decimal('.45')}
CONFIDENCE = {'minimum_effective': Decimal('1.8'), 'high': Decimal('.75'),
              'medium': Decimal('.45'), 'minimum_score': Decimal('.15'),
              'dispersion_limit': Decimal('.5'), 'dispersion_penalty': Decimal('.85'),
              'outlier_penalty': Decimal('.9')}
STANDARD_FAMILIES = ('eagle', 'buffalo', 'maple', 'britannia', 'krugerrand', 'philharmonic', 'kangaroo', 'panda')
RARE_WORDS = re.compile(r'\b(rare|key[ -]?date|commemorative|limited|proof|specimen|error|variety|pedigree|numismatic)\b', re.I)
RECENCY_HALF_DAYS = Decimal(30)
GRADE_WEIGHT_CAP = Decimal('.5')  # Total corroborating grade weight <= half exact-grade weight.
MAX_SPOT_AGE = 900
MIN_CHANGE_CENTS = 100
MAX_STEP_CENTS = 5000
ATTRIBUTES = ('metal', 'product_type', 'weight', 'purity', 'mint', 'year',
              'product_line', 'coin_series', 'finish', 'grade', 'condition_category',
              'series_variant', 'special_designation', 'graded', 'grading_service',
              'packaging_type', 'actual_year', 'denomination', 'condition_notes',
              'issue_total', 'edition_total', 'set_configuration', 'rare_identity', 'collector_flags')


class SpotUnavailable(ValueError):
    pass

class PreviewChanged(ValueError):
    pass

SPOT_MESSAGE = 'METEX needs a current metal price before Smart Pricing can calculate your initial listing price. Please try again shortly or use manual pricing.'

def seller_error(exc):
    if isinstance(exc,SpotUnavailable):
        return {'success':False,'code':'SMART_SPOT_UNAVAILABLE','title':'Current metal pricing is temporarily unavailable','message':SPOT_MESSAGE}
    if isinstance(exc,PreviewChanged):
        return {'success':False,'code':'SMART_PREVIEW_CHANGED','title':'Price updated','message':'Your Smart Pricing preview changed or expired. Review the updated listing price before continuing.'}
    return {'success':False,'message':str(exc)}


def cents(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) > Decimal('10000000'):
            raise ValueError()
        return int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except Exception as exc:
        raise ValueError('Enter a finite dollar amount, up to $10,000,000.') from exc


def now_utc():
    return datetime.now(timezone.utc)


def timestamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def ensure_schema(conn, create_indexes=False):
    conn.execute('''CREATE TABLE IF NOT EXISTS smart_pricing_settings (
      listing_id INTEGER PRIMARY KEY REFERENCES listings(id), enabled INTEGER NOT NULL DEFAULT 0,
      strategy TEXT NOT NULL CHECK(strategy IN ('fast','balanced','big')),
      minimum_cents INTEGER NOT NULL CHECK(minimum_cents>=0), revision INTEGER NOT NULL DEFAULT 1,
      enabled_at TEXT NOT NULL, last_review TEXT, last_adjustment TEXT,
      estimate_cents INTEGER, review_json TEXT NOT NULL DEFAULT '{}')''')
    # CREATE INDEX takes a PostgreSQL table lock: only deployment bootstrap may
    # acquire it, never a request/job competing for the canonical flow mutex.
    if create_indexes:
        conn.execute('CREATE INDEX IF NOT EXISTS smart_pricing_due_idx ON smart_pricing_settings(enabled,last_review)')
    conn.execute('''CREATE TABLE IF NOT EXISTS smart_pricing_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER NOT NULL REFERENCES listings(id),
      revision INTEGER NOT NULL, reviewed_at TEXT NOT NULL, previous_cents INTEGER NOT NULL,
      new_cents INTEGER NOT NULL, strategy TEXT NOT NULL, estimate_cents INTEGER,
      reason_json TEXT NOT NULL, engine_version TEXT NOT NULL,
      UNIQUE(listing_id,revision))''')


def lock(conn):
    # Same lock and ordering as prepare_checkout / execute_bid_fill.
    conn.execute('UPDATE flow_mutex SET revision=revision+1 WHERE id=1')


def parse_form(form):
    enabled = form.get('smart_pricing_enabled', '0') == '1'
    if not enabled:
        return None
    strategy = form.get('smart_pricing_strategy', 'balanced')
    if strategy not in STRATEGIES:
        raise ValueError('Choose Sell Fast, Balanced or Sell Big.')
    raw = str(form.get('smart_minimum', '')).strip()
    minimum = cents(raw)
    if minimum < 0 or Decimal(raw) != Decimal(minimum) / 100:
        raise ValueError('Minimum premium must be nonnegative with at most two decimal places.')
    return strategy, minimum


def configure(conn, listing_id, settings, initial=False, approval=None):
    """Caller owns transaction and mutex. Enforce authorization floor on enable/edit."""
    ensure_schema(conn)
    if not settings:
        conn.execute('UPDATE smart_pricing_settings SET enabled=0,revision=revision+1 WHERE listing_id=?', (listing_id,))
        return
    strategy, minimum = settings
    listing = conn.execute('SELECT * FROM listings WHERE id=?', (listing_id,)).fetchone()
    listing = dict(listing)
    if listing['pricing_mode'] != 'premium_to_spot':
        raise ValueError('Smart Pricing requires premium-to-spot pricing.')
    premium = max(cents(listing.get('spot_premium') or 0), minimum)
    item = product(conn, listing_id)
    metal_value, snapshots = metal_basis(conn, item, now_utc())
    starting_premium = premium
    initial_estimate = None
    initial_details = None
    if approval:
        premium = approval['initial_premium_cents']
        initial_estimate = approval['market']['p50_cents'] if approval['market'] else None
        initial_details = dict(approval, reason='seller-selected starting premium; held until defensible evidence' if approval['seeded'] else 'seller-confirmed evidence-based starting premium')
        initial_details.pop('product',None)
    elif initial:
        # Internal callers still need an explicit seed when evidence is absent.
        quote = initial_quote(conn,item,strategy,minimum,str(Decimal(premium)/100))
        premium = quote['initial_premium_cents']
        initial_estimate = quote['market']['p50_cents'] if quote['market'] else None
        initial_details = dict(quote, reason='seller-selected starting premium; held until defensible evidence' if quote['seeded'] else 'initial evidence-based premium before publication')
    total = metal_value + premium
    if total <= 0:
        raise ValueError('A positive current spot-based price is required.')
    conn.execute('UPDATE listings SET spot_premium=?,price_per_coin=? WHERE id=?', (str(Decimal(premium)/100), str(Decimal(total)/100), listing_id))
    conn.execute('''INSERT INTO smart_pricing_settings
      (listing_id,enabled,strategy,minimum_cents,enabled_at) VALUES (?,1,?,?,?)
      ON CONFLICT(listing_id) DO UPDATE SET enabled=1,strategy=excluded.strategy,
      minimum_cents=excluded.minimum_cents,revision=smart_pricing_settings.revision+1,
      last_review=NULL,estimate_cents=NULL,review_json='{}' ''',
      (listing_id, strategy, minimum, now_utc().isoformat()))
    if initial_details:
        initial_details['strategy_config'] = {k:str(v) for k,v in STRATEGIES[strategy].items()}
        reviewed = now_utc().isoformat()
        conn.execute('UPDATE smart_pricing_settings SET estimate_cents=?,last_review=?,review_json=? WHERE listing_id=?',
                     (initial_estimate, reviewed, json.dumps(initial_details, sort_keys=True), listing_id))
        if premium != starting_premium:
            conn.execute('UPDATE smart_pricing_settings SET last_adjustment=? WHERE listing_id=?', (reviewed, listing_id))
        conn.execute('''INSERT INTO smart_pricing_history (listing_id,revision,reviewed_at,previous_cents,new_cents,strategy,estimate_cents,reason_json,engine_version)
                VALUES (?,?,?,?,?,?,?,?,?)''', (listing_id,conn.execute('SELECT revision FROM smart_pricing_settings WHERE listing_id=?',(listing_id,)).fetchone()['revision'],reviewed,starting_premium,premium,strategy,initial_estimate,json.dumps(initial_details,sort_keys=True),VERSION))


def product(conn, listing_id):
    row = conn.execute('SELECT l.*,c.*,l.id AS listing_id FROM categories c JOIN listings l ON l.category_id=c.id WHERE l.id=?', (listing_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    if item.get('isolated_type') == 'set':
        item['set_items'] = [dict(part) for part in conn.execute('SELECT * FROM listing_set_items WHERE listing_id=? ORDER BY position_index', (listing_id,))]
    return item


def signature(item):
    result = {key: str(item.get(key) or '').strip().lower() for key in ATTRIBUTES}
    classification=classify_smart_pricing_item(item)
    if classification['classification']=='STANDARDIZED': result['condition_notes']=''
    result['collector_flags']='|'.join(classification['reasons']) if classification['classification']=='RARE_OR_SPECIAL' else ''
    result['weight'] = str(weight_ounces(item.get('weight'))) if item.get('weight') else ''
    for key in ('series_variant','special_designation','condition_category','grade'):
        if result[key]=='none': result[key]=''
    result['grade'] = result['grade'].replace(' ', '')
    result['graded']='1' if result['graded'] in ('1','yes','true') else ''
    if item.get('set_items'):
        parts = []
        for part in item['set_items']:
            part_sig = signature(dict(part, isolated_type='one_of_a_kind'))
            part_sig['quantity'] = str(part.get('quantity') or 1)
            parts.append(part_sig)
        result['set_configuration'] = json.dumps(sorted(parts,key=lambda p:json.dumps(p,sort_keys=True)),sort_keys=True)
    if item.get('isolated_type')=='set':
        result = {key:'' for key in ATTRIBUTES} | {key:result[key] for key in ('set_configuration','issue_total','edition_total')}
    if nonstandard(item):
        result['rare_identity'] = str(item.get('isolated_type') or 'collector') + ':' + str(item.get('name') or item.get('listing_title') or '').strip().lower()
    return result


def weight_ounces(weight):
    match = re.fullmatch(r'(\d+(?:\.\d+)?|\d+/\d+)\s*(oz|g|kg|lb)?', str(weight or '').strip(), re.I)
    if not match:
        raise ValueError('Unsupported weight; a reliable metal value is unavailable.')
    number, unit = match.groups()
    if '/' in number:
        numerator, denominator = number.split('/')
        value = Decimal(numerator)/Decimal(denominator)
    else:
        value = Decimal(number)
    value *= {'oz':Decimal(1),'g':Decimal('.0321507'),'kg':Decimal('32.1507'),'lb':Decimal('14.5833')}[(unit or 'oz').lower()]
    if value<=0:
        raise ValueError('Weight must be positive.')
    return value.normalize()


def metal_value_cents(item, price):
    """Strict legacy weight convention (weight is contained metal in troy oz).
    Do not reinterpret nominal purity as another weight multiplier.
    """
    return cents(weight_ounces(item.get('weight')) * Decimal(str(price)))


def refresh_preview_spot_prices(conn, item):
    """Use normal sell-page spot refresh/cache, bridging verified cache timestamps
    into canonical snapshots. No financial rematching or invented freshness.
    Provider calls stay outside checkout/worker price calculations.
    """
    if not database.get_table_columns(conn,'spot_prices'):
        return
    parts=item.get('set_items') if item.get('isolated_type')=='set' else [item]
    metals={str(part.get('metal') or '').lower() for part in (parts or [])}
    now=now_utc()
    def cached(metal):
        row=conn.execute('SELECT metal,price_usd_per_oz,updated_at,source FROM spot_prices WHERE LOWER(metal)=?',(metal,)).fetchone()
        try:
            if row and 0<=(now-timestamp(row['updated_at'])).total_seconds()<=MAX_SPOT_AGE and cents(row['price_usd_per_oz'])>0:return row
        except (ValueError,TypeError):pass
        return None
    needs_refresh=False
    for metal in metals:
        if cached(metal):continue
        try:fresh_spot(conn,{'metal':metal},now)
        except SpotUnavailable:needs_refresh=True
    if needs_refresh:
        from services.spot_price_service import get_current_spot_prices
        try:get_current_spot_prices()  # Same refresh + cache used by /api/spot-prices.
        except Exception:log.exception('Sell preview spot refresh failed')
        now=now_utc()  # Provider/cache updates occur after the request's initial clock read.
    for metal in metals:
        row=cached(metal)
        if not row:continue
        latest=conn.execute('SELECT as_of FROM spot_price_snapshots WHERE metal=? ORDER BY as_of DESC LIMIT 1',(metal,)).fetchone()
        try:newer=not latest or timestamp(row['updated_at'])>timestamp(latest['as_of'])
        except (ValueError,TypeError):newer=True
        if newer:
            conn.execute('INSERT INTO spot_price_snapshots(metal,price_usd,as_of,source) VALUES(?,?,?,?)',
                         (metal,row['price_usd_per_oz'],timestamp(row['updated_at']).isoformat(),row['source'] or 'spot-cache'))
    conn.commit()  # Market-data cache only, before signed preview calculation.


def fresh_spot(conn, item, now):
    metal = str(item.get('pricing_metal') or item.get('metal') or '').lower()
    if metal != str(item.get('metal') or '').lower():
        raise ValueError('Pricing metal must match the item metal.')
    row = conn.execute('SELECT * FROM spot_price_snapshots WHERE metal=? ORDER BY as_of DESC LIMIT 1', (metal,)).fetchone()
    try:
        usable=row and 0 <= (now-timestamp(row['as_of'])).total_seconds() <= MAX_SPOT_AGE and cents(row['price_usd'])>0
    except (ValueError,TypeError):
        usable=False
    if not usable:
        raise SpotUnavailable('Fresh spot data unavailable; premium held.')
    return row


def metal_basis(conn, item, now):
    if item.get('isolated_type') == 'set':
        parts = item.get('set_items') or []
        if len(parts)<2:
            raise ValueError('Complete the set contents before previewing Smart Pricing.')
        total, snapshots = 0, []
        for part in parts:
            quantity = int(part.get('quantity') or 1)
            if not 1<=quantity<=100000:
                raise ValueError('Set item quantities must be positive.')
            spot = fresh_spot(conn,part,now)
            total += metal_value_cents(part,spot['price_usd'])*quantity
            snapshots.append({'metal':str(part['metal']).lower(),'as_of':str(spot['as_of']),'source':spot['source']})
        return total, snapshots
    spot = fresh_spot(conn,item,now)
    return metal_value_cents(item,spot['price_usd']), [{'metal':str(item['metal']).lower(),'as_of':str(spot['as_of']),'source':spot['source']}]


def capture_sale_basis(conn, listing_id):
    """Freeze trustworthy product/spot basis in canonical execution JSON.
    Missing old evidence is never inferred from today's spot or mutable listing.
    """
    try:
        if "category_id" not in database.get_table_columns(conn, "listings"):
            return None
        item = product(conn, listing_id)
        if not item:
            return None
        value, snapshots = metal_basis(conn,item,now_utc())
        return {'product':signature(item),'metal_value_cents':value,
                'spot_snapshots':snapshots,'version':VERSION}
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def present(value):
    return str(value or '').strip().lower() not in ('','none','no','0')


def classify_smart_pricing_item(item):
    """Structured identity drives pricing; seller prose is diagnostic only."""
    reasons=[]
    flags=str(item.get('collector_flags') or '').upper().split('|')
    if item.get('isolated_type')=='set' or present(item.get('is_set')) or item.get('set_configuration') or len(item.get('set_items') or [])>1:
        kind='SET'; reasons=['MULTI_ITEM_CONFIGURATION']
    elif item.get('isolated_type')=='one_of_a_kind' or present(item.get('is_isolated')) or present(item.get('is_unique')):
        kind='ONE_OF_A_KIND'; reasons=['EXPLICIT_UNIQUE_ITEM_FLAG']
    else:
        structured=' '.join(str(item.get(k) or '').lower() for k in ('finish','strike_type','product_line','coin_series','series_variant','special_designation','condition_category'))
        for expression,code in ((r'reverse[ -]?proof','REVERSE_PROOF'),(r'\bproof\b','PROOF'),(r'burnished|specimen|special[ -]?strike|matte','SPECIAL_STRIKE'),(r'commemorative|anniversary','COMMEMORATIVE'),(r'limited|special[ -]?release|first[ -]?(strike|release)|early[ -]?release','LIMITED_EDITION'),(r'key[ -]?date|rare[ -]?date','KEY_DATE'),(r'error|variety|pedigree|numismatic','RARE_VARIANT')):
            if re.search(expression,structured): reasons.append(code)
        for field,code in (('key_date','KEY_DATE'),('rare_date','KEY_DATE'),('is_rare','RARE_VARIANT'),('low_mintage','LOW_MINTAGE'),('limited_mintage','LOW_MINTAGE'),('is_commemorative','COMMEMORATIVE'),('is_error','RARE_VARIANT'),('is_variety','RARE_VARIANT')):
            if present(item.get(field)) or code in flags: reasons.append(code)
        if any(present(item.get(k)) for k in ('issue_number','issue_total','edition_number','edition_total')) or 'NUMBERED_ITEM' in flags: reasons.append('NUMBERED_ITEM')
        if present(item.get('series_variant')) or present(item.get('special_designation')): reasons.append('RARE_VARIANT')
        if reasons: kind='RARE_OR_SPECIAL'
        else:
            identity=str(item.get('product_line') or item.get('coin_series') or '').strip().lower()
            ordinary_finish=str(item.get('finish') or '').strip().lower() in ('bu','brilliant uncirculated','business strike','uncirculated','mint state')
            known_family=any(re.search(r'\b'+re.escape(family)+r's?\b',identity) for family in STANDARD_FAMILIES)
            ordinary_type=str(item.get('product_type') or '').lower() in ('coin','bar','round')
            if identity and ordinary_finish and ordinary_type and (known_family or str(item.get('product_type') or '').lower() in ('bar','round')):
                kind='STANDARDIZED'; reasons=['STANDARD_BULLION_PRODUCT']
            else: kind='UNKNOWN_NONSTANDARD'; reasons=['UNKNOWN_PRODUCT_CLASS']
    prose=' '.join(str(item.get(k) or '') for k in ('name','listing_title','description','listing_description','condition_notes'))
    secondary=['POSSIBLE_SPECIAL_ITEM_UNCONFIRMED'] if RARE_WORDS.search(prose) or re.search(r'one of a kind|\bset\b',prose,re.I) else []
    return {'classification':kind,'reasons':sorted(set(reasons)),'secondary_signals':secondary}


def classify_year_comparability(item):
    result=classify_smart_pricing_item(item)
    return {'classification':'YEAR_RELAXABLE' if result['classification']=='STANDARDIZED' else 'YEAR_SENSITIVE','reasons':result['reasons']}


def nonstandard(item):
    return classify_smart_pricing_item(item)['classification']!='STANDARDIZED'


def standardized(sig):
    return classify_year_comparability(sig)['classification']=='YEAR_RELAXABLE'


def normalized_signature(value):
    result={key:str(value.get(key) or '').strip().lower() for key in ATTRIBUTES}
    if result['weight']:
        result['weight']=str(weight_ounces(result['weight']))
    result['grade']=result['grade'].replace(' ','')
    result['graded']='1' if result['graded'] in ('1','yes','true') else ''
    for key in ('series_variant','special_designation','condition_category','grade'):
        if result[key]=='none':result[key]=''
    # Preserve opaque, canonical JSON case instead of lowercasing the whole set.
    result['set_configuration']=value.get('set_configuration') or ''
    if classify_smart_pricing_item(result)['classification']=='STANDARDIZED': result['condition_notes']=''
    return result


def comparable_tier(left, right):
    left,right=normalized_signature(left),normalized_signature(right)
    if any(sig.get('rare_identity','').startswith('set:') and not sig.get('set_configuration') for sig in (left,right)):
        return None
    if left == right:
        return 'exact'
    if left.get('set_configuration') or right.get('set_configuration') or left.get('rare_identity') or right.get('rare_identity'):
        return None
    if not standardized(left) or not standardized(right):
        return None
    year_keys = ('year','actual_year')
    same_except_year = all(left.get(k,'')==right.get(k,'') for k in ATTRIBUTES if k not in year_keys)
    years=[left.get('actual_year') or left.get('year'),right.get('actual_year') or right.get('year')]
    safe_years=standardized(left) and standardized(right)
    if same_except_year and safe_years:
        return 'year'
    left_grade = re.fullmatch(r'ms(\d{2})', left.get('grade','').replace(' ',''))
    right_grade = re.fullmatch(r'ms(\d{2})', right.get('grade','').replace(' ',''))
    # Adjacent certified ordinary bullion grades only; distribution requires
    # corroborating exact-grade evidence and caps their aggregate influence.
    if safe_years and left_grade and right_grade and left.get('graded')=='1' and right.get('graded')=='1' and left.get('grading_service') and left.get('grading_service')==right.get('grading_service'):
        lg, rg = int(left_grade[1]), int(right_grade[1])
        if 68<=lg<=70 and 68<=rg<=70 and abs(lg-rg)==1 and all(left.get(k,'')==right.get(k,'') for k in ATTRIBUTES if k not in (*year_keys,'grade')):
            return 'grade'
    # Same branded family, mint, finish/condition/grade/content. Only
    # non-value-bearing loose/capsule packaging may differ at this last level.
    safe_packaging = ('','loose','capsule')
    if safe_years and left.get('packaging_type','') in safe_packaging and right.get('packaging_type','') in safe_packaging:
        if all(left.get(k,'')==right.get(k,'') for k in ATTRIBUTES if k not in (*year_keys,'packaging_type')):
            return 'family'
    return None


def evidence(conn, listing_id, item, now):
    target = signature(item)
    pools = {kind+'_'+tier: [] for kind in ('sales','asks') for tier in ('exact','year','grade','family')}
    rows = conn.execute('''SELECT es.snapshot_json,e.created_at,sl.id AS observation_id,sl.listing_id,sl.seller_id,sl.seller_unit_cents
      FROM executions e JOIN execution_snapshots es ON es.id=e.snapshot_id
      JOIN snapshot_lines sl ON sl.snapshot_id=es.id JOIN seller_fills sf ON sf.snapshot_line_id=sl.id
      WHERE e.payment_state='APPROVED' AND sf.refunded_quantity=0
      AND EXISTS (SELECT 1 FROM shipments sh WHERE sh.seller_fill_id=sf.id AND sh.state='DELIVERED' AND sh.destination_type='BUYER')
      AND NOT EXISTS (SELECT 1 FROM holds h WHERE h.seller_fill_id=sf.id AND h.state='ACTIVE')
      AND NOT EXISTS (SELECT 1 FROM flow_refunds fr JOIN refund_allocations ra ON ra.refund_id=fr.id WHERE ra.seller_fill_id=sf.id AND fr.state<>'FAILED')
      AND e.created_at>=? AND sl.seller_id<>? ORDER BY e.created_at DESC LIMIT 500''',
      ((now-timedelta(days=90)).isoformat(), item['seller_id'])).fetchall()
    for row in rows:
        data = json.loads(row['snapshot_json'])
        line = next((line for line in data.get('lines', []) if line['listing_id'] == row['listing_id']), {})
        basis = line.get('smart_pricing_basis')
        if not basis:
            continue
        try:
            tier = comparable_tier(target, basis['product'])
        except (ValueError,ZeroDivisionError):
            continue
        if tier:
            pools['sales_'+tier].append({'premium': row['seller_unit_cents']-basis['metal_value_cents'], 'id': row['listing_id'], 'time': str(row['created_at']), 'observation_id': row['observation_id']})
    # One best-tier ask per competing seller; later tiers cannot crowd out
    # that seller's exact product. Use the lowest ask within the same tier.
    rows = conn.execute('SELECT l.id FROM listings l WHERE l.active=1 AND l.quantity>0 AND l.seller_id<>? ORDER BY l.id DESC LIMIT 1000', (item['seller_id'],)).fetchall()
    candidates = []
    for row in rows:
        comp = product(conn,row['id'])
        try:
            tier = comparable_tier(target,signature(comp))
            if not tier:
                continue
            value, _ = metal_basis(conn,comp,now)
            premium = max(cents(comp.get('spot_premium') or 0),cents(comp.get('floor_price') or 0)-value) if comp['pricing_mode']=='premium_to_spot' else cents(comp['price_per_coin'])-value
            candidates.append((('exact','year','grade','family').index(tier),premium,comp,tier))
        except (ValueError,ZeroDivisionError):
            continue
    seen = set()
    for _,premium,comp,tier in sorted(candidates,key=lambda c:(c[0],c[1],c[2]['listing_id'])):
        if comp['seller_id'] in seen:
            continue
        seen.add(comp['seller_id'])
        pools['asks_'+tier].append({'premium':premium,'id':comp['listing_id']})
    for name, observations in pools.items():
        for observation in observations:
            age = max(Decimal(0), Decimal(str((now-timestamp(observation['time'])).total_seconds()/86400))) if observation.get('time') else Decimal(0)
            recency = RECENCY_HALF_DAYS / (RECENCY_HALF_DAYS + age)
            observation.update(source=name, weight=str(Decimal(EVIDENCE_WEIGHTS[name])*recency), recency=str(recency))
    values = []
    # Stop at the first defensible completed-sale level. Asks are added only
    # after all four completed-sale levels fail to yield a usable estimate.
    for kind in ('sales','asks'):
        for tier in ('exact','year','grade','family'):
            name = kind+'_'+tier
            values.extend(pools[name])
            if distribution(values):
                return name, values
    return 'insufficient', values


def weighted_quantile(values, q):
    """Interpolate weighted cumulative centers, clamping endpoint tails."""
    ordered = sorted(values, key=lambda v: v['premium'])
    centers, cumulative = [], Decimal(0)
    for value in ordered:
        weight = Decimal(value.get('weight', '1'))
        centers.append(cumulative + weight/2)
        cumulative += weight
    target = cumulative*q
    if target <= centers[0]:
        return ordered[0]['premium']
    for i in range(1, len(ordered)):
        if target <= centers[i]:
            fraction = (target-centers[i-1])/(centers[i]-centers[i-1])
            return int((Decimal(ordered[i-1]['premium'])*(1-fraction)+Decimal(ordered[i]['premium'])*fraction).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return ordered[-1]['premium']


def distribution(values):
    values=[dict(v) for v in values]
    if len(values) < 2:
        return None
    # Robust unweighted screening prevents one oversized evidence weight from
    # authorizing an otherwise unreasonable observation.
    plain = [{'premium':v['premium']} for v in values]
    low, median, high = [weighted_quantile(plain, Decimal(q)) for q in ('.25','.5','.75')]
    if len(values)==2 and Decimal(high-low)/max(abs(median),MIN_CHANGE_CENTS)>CONFIDENCE['dispersion_limit']:
        return None
    spread = max(high-low, MIN_CHANGE_CENTS)
    mad = max(MIN_CHANGE_CENTS, weighted_quantile([{'premium':abs(v['premium']-median)} for v in values], Decimal('.5')))
    qualified = [v for v in values if low-Decimal('1.5')*spread <= v['premium'] <= high+Decimal('1.5')*spread and abs(v['premium']-median) <= 6*mad]
    if len(qualified) < 2:
        return None
    if len(qualified)==2:
        pair=[{'premium':v['premium']} for v in qualified]
        pair_median=weighted_quantile(pair,Decimal('.5'))
        if Decimal(abs(pair[0]['premium']-pair[1]['premium']))/max(abs(pair_median),MIN_CHANGE_CENTS)>CONFIDENCE['dispersion_limit']:
            return None
    primary=[v for v in qualified if v.get('source','asks_exact').split('_',1)[-1] in ('exact','year','family')]
    adjacent=[v for v in qualified if v.get('source','asks_exact').endswith('_grade')]
    if adjacent:
        if not primary: return None
        anchor=weighted_quantile(primary,Decimal('.5'))
        adjacent=[v for v in adjacent if Decimal(abs(v['premium']-anchor))/max(abs(Decimal(anchor)),MIN_CHANGE_CENTS)<=CONFIDENCE['dispersion_limit']]
        qualified=primary+adjacent
        if not adjacent: return distribution(primary)
        primary_weight=sum(Decimal(v.get('weight','1')) for v in primary)
        grade_weight=sum(Decimal(v.get('weight','1')) for v in adjacent)
        scale=min(Decimal(1),primary_weight*GRADE_WEIGHT_CAP/grade_weight)
        for v in adjacent: v['weight']=str(Decimal(v.get('weight','1'))*scale)
    weights = [Decimal(v.get('weight','1')) for v in qualified]
    effective = sum(weights)**2/sum(w*w for w in weights)
    if effective < CONFIDENCE['minimum_effective']:
        return None
    def quality(v):
        kind, tier = v.get('source','asks_exact').split('_',1)
        return MATCH_QUALITY.get(tier,Decimal('.4'))*(Decimal(1) if kind=='sales' else Decimal('.65'))
    quality_score = sum(w*quality(v)*Decimal(v.get('recency','1')) for w,v in zip(weights,qualified))/sum(weights)
    dispersion = Decimal(high-low)/max(abs(median),MIN_CHANGE_CENTS)
    dispersion_scale = CONFIDENCE['dispersion_penalty'] if dispersion>CONFIDENCE['dispersion_limit'] else Decimal(1)
    outlier_scale = CONFIDENCE['outlier_penalty'] if len(qualified)<len(values) else Decimal(1)
    confidence = min(Decimal(1), effective/3)*quality_score*dispersion_scale*outlier_scale
    if adjacent: confidence=min(confidence,Decimal('.6'))
    if confidence < CONFIDENCE['minimum_score']:
        return None
    return {'p25_cents':weighted_quantile(qualified,Decimal('.25')),
            'p50_cents':weighted_quantile(qualified,Decimal('.50')),
            'p75_cents':weighted_quantile(qualified,Decimal('.75')),
            'confidence':str(confidence.quantize(Decimal('.001'))),
            'confidence_label':'high' if confidence>=CONFIDENCE['high'] else 'medium' if confidence>=CONFIDENCE['medium'] else 'low',
            'effective_comps':str(effective.quantize(Decimal('.01'))), 'dispersion_ratio':str(dispersion.quantize(Decimal('.001'))),
            'qualified_comps':qualified, 'rejected_comps':len(values)-len(qualified)}


def demand_adjustment(item, market):
    """Extension point: no reliable exposure/interest/conversion series exists yet."""
    return 0, 'unavailable; no reliable engagement data'


def target_details(values, strategy, minimum=0, age_days=0, item=None):
    market = distribution(values)
    if not market:
        return None
    config = STRATEGIES[strategy]
    base = market[{Decimal('.25'):'p25_cents',Decimal('.50'):'p50_cents',Decimal('.75'):'p75_cents'}[config['quantile']]]
    # Saturating pressure measured in observed IQR, never dollars per day.
    elapsed = max(Decimal(0), Decimal(str(age_days))-config['age_grace_days'])
    fraction = elapsed/(elapsed+config['age_ramp_days'])
    scale = Decimal('.5') if market['confidence_label']=='low' else Decimal(1)
    age = -int(Decimal(market['p75_cents']-market['p25_cents'])*config['age_max_spread']*fraction*scale)
    demand, demand_reason = demand_adjustment(item, market)
    lower = market['p25_cents']-int(Decimal(market['p75_cents']-market['p25_cents'])*Decimal('.5'))
    target = max(minimum, min(market['p75_cents'], max(lower, base+age+demand)))
    return dict(market, base_target_cents=base, age_adjustment_cents=age,
                age_days=str(age_days), demand_adjustment_cents=demand,
                demand_reason=demand_reason, market_lower_cents=lower,
                market_upper_cents=market['p75_cents'], target_cents=target)


def recommendation(values, strategy):
    details = target_details(values,strategy)
    return (details['p50_cents'], details['target_cents']) if details else None


def evaluate(listing_id, now=None):
    now = now or now_utc()
    conn = database.get_db_connection()
    try:
        ensure_schema(conn); lock(conn)
        settings = conn.execute('SELECT * FROM smart_pricing_settings WHERE listing_id=?', (listing_id,)).fetchone()
        item = product(conn, listing_id)
        if not settings or not settings['enabled'] or not item or not item['active'] or item['quantity'] <= 0 or item['pricing_mode'] != 'premium_to_spot' :
            return 'ineligible'
        seller = conn.execute('SELECT * FROM users WHERE id=?', (item['seller_id'],)).fetchone()
        if not seller or dict(seller).get('is_banned') or dict(seller).get('is_frozen'):
            return 'seller_unavailable'
        if conn.execute("SELECT id FROM inventory_reservations WHERE listing_id=? AND state='HELD'", (listing_id,)).fetchone():
            return 'reserved'
        hours = STRATEGIES[settings['strategy']]['hours']
        if settings['last_review'] and now-timestamp(settings['last_review']) < timedelta(hours=hours):
            return 'cooldown'
        old = cents(item.get('spot_premium') or 0)
        details = {'engine': VERSION, 'confidence_label':'insufficient', 'seeded':True, 'reason': 'Not enough comparable market data; seller premium held'}
        estimate = None
        new = old
        try:
            current_metal_value, _ = metal_basis(conn, item, now)
            source, values = evidence(conn, listing_id, item, now)
            if values:
                age_days = max(0, (now-timestamp(item.get('created_at') or settings['enabled_at'])).total_seconds()/86400)
                market = target_details(values, settings['strategy'], settings['minimum_cents'], age_days, item)
                result = (market['p50_cents'], market['target_cents']) if market else None
                if result:
                    estimate, target = result
                    target = max(target, settings['minimum_cents'])
                    confidence_scale = Decimal('.5') if market['confidence_label']=='low' else Decimal(1)
                    step = min(MAX_STEP_CENTS, max(MIN_CHANGE_CENTS, int(Decimal(max(abs(old), abs(estimate))) * STRATEGIES[settings['strategy']]['step'] * confidence_scale)))
                    new = max(settings['minimum_cents'], min(old+step, max(old-step, target)))
                    if abs(new-old) < MIN_CHANGE_CENTS:
                        new = old
                    if settings['last_adjustment'] and now-timestamp(settings['last_adjustment']) < timedelta(hours=hours):
                        new = old
                    details = {**market, 'age_basis': 'listing_created_at' if item.get('created_at') else 'smart_enabled_at_unknown_listing_age', 'engine': VERSION, 'source': source, 'comps': values, 'target_cents': target,
                               'reason': 'evidence-based premium target', 'step_limit_cents': step}
        except (ValueError, ZeroDivisionError) as exc:
            details['reason'] = str(exc)
        if details.get('confidence_label')=='insufficient' and 'values' in locals():
            details.update(source=source,comps=values)
        else:
            details['seeded']=False
        details['classification']=classify_smart_pricing_item(item)
        details['year_comparability']=classify_year_comparability(item)
        details['minimum_cents'] = settings['minimum_cents']
        details['strategy_config'] = {key:str(value) for key,value in STRATEGIES[settings['strategy']].items()}
        reviewed = now.isoformat()
        revision = settings['revision']+1
        conn.execute('''UPDATE smart_pricing_settings SET last_review=?,estimate_cents=?,review_json=?,revision=? WHERE listing_id=?''',
                     (reviewed, estimate, json.dumps(details, sort_keys=True), revision, listing_id))
        if new != old:
            conn.execute('UPDATE listings SET spot_premium=?,price_per_coin=? WHERE id=?', (str(Decimal(new)/100), str(Decimal(current_metal_value+new)/100), listing_id))
            conn.execute('UPDATE smart_pricing_settings SET last_adjustment=? WHERE listing_id=?', (reviewed, listing_id))
            conn.execute('''INSERT INTO smart_pricing_history (listing_id,revision,reviewed_at,previous_cents,new_cents,strategy,estimate_cents,reason_json,engine_version)
              VALUES (?,?,?,?,?,?,?,?,?)''', (listing_id, revision, reviewed, old, new, settings['strategy'], estimate, json.dumps(details, sort_keys=True), VERSION))
        conn.commit()
        return 'adjusted' if new != old else 'held'
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def run_due(limit=100):
    if os.getenv('SMART_REPRICING_ENABLED', 'true').lower() != 'true':
        return {'paused': 1}
    conn = database.get_db_connection()
    try:
        ensure_schema(conn)
        if not conn.execute('SELECT listing_id FROM smart_pricing_settings WHERE enabled=1 LIMIT 1').fetchone():
            conn.commit()
            return {}
        ids = [r['listing_id'] for r in conn.execute('''SELECT s.listing_id FROM smart_pricing_settings s JOIN listings l ON l.id=s.listing_id WHERE s.enabled=1 AND l.active=1 AND l.quantity>0 AND l.pricing_mode='premium_to_spot' 
          AND NOT EXISTS (SELECT 1 FROM inventory_reservations ir WHERE ir.listing_id=l.id AND ir.state='HELD')
          AND (s.last_review IS NULL OR
            (s.strategy='fast' AND s.last_review<=?) OR
            (s.strategy='balanced' AND s.last_review<=?) OR
            (s.strategy='big' AND s.last_review<=?))
          ORDER BY COALESCE(s.last_review,s.enabled_at) LIMIT ?''',
          tuple((now_utc()-timedelta(hours=STRATEGIES[key]['hours'])).isoformat() for key in ('fast','balanced','big')) + (limit,))]
        conn.commit()
    finally:
        conn.close()
    results = {}
    for listing_id in ids:
        try:
            result = evaluate(listing_id)
            results[result] = results.get(result, 0)+1
        except Exception:
            log.exception('Smart Pricing evaluation failed for listing %s', listing_id)
            results['error'] = results.get('error', 0)+1
    log.info('Smart Pricing cycle: %s', results)
    return results


def dashboard(conn, listing_id):
    ensure_schema(conn)
    row = conn.execute('SELECT * FROM smart_pricing_settings WHERE listing_id=?', (listing_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data['last_review_label'] = timestamp(data['last_review']).strftime('%b %d, %Y · %H:%M UTC') if data['last_review'] else None
    data['history'] = [dict(r) for r in conn.execute('SELECT * FROM smart_pricing_history WHERE listing_id=? ORDER BY id DESC LIMIT 20', (listing_id,))]
    for event in data['history']:
        event['time_label'] = timestamp(event['reviewed_at']).strftime('%b %d, %Y · %H:%M UTC')
    data['review'] = json.loads(data['review_json'])
    return data


def form_item(form, seller_id, base=None):
    """Normalize actual sell fields for a read-only preview, never market prices."""
    item = dict(base or {})
    for key in ATTRIBUTES:
        if key not in ('set_configuration','rare_identity','collector_flags'):
            item[key] = form.get(key, '')
    item.update(seller_id=seller_id, name=form.get('listing_title',''),
                description=form.get('listing_description',''),
                graded=1 if form.get('graded')=='yes' else 0,
                grading_service=form.get('grading_service','') if form.get('graded')=='yes' else '',
                pricing_metal=form.get('pricing_metal') or form.get('metal'),
                condition_notes=form.get('item_condition_notes') or form.get('condition_notes',''),
                packaging_type=form.get('item_packaging_type') or form.get('packaging_type',''))
    item['isolated_type'] = 'set' if form.get('is_set')=='1' else 'one_of_a_kind' if form.get('is_isolated')=='1' or form.get('issue_total') else (base or {}).get('isolated_type')
    if item['isolated_type']=='set':
        raw = form.get('set_items_json','')
        if raw:
            parts = json.loads(raw)
        else:
            indices = sorted({int(m[1]) for key in form for m in [re.match(r'set_items\[(\d+)\]\[',key)] if m})
            parts = [{key:form.get(f'set_items[{i}][{key}]','') for key in (*ATTRIBUTES,'quantity')} for i in indices]
        if not isinstance(parts,list) or len(parts)>100 or any(not isinstance(p,dict) for p in parts):
            raise ValueError('Provide a valid set configuration with at most 100 items.')
        item['set_items'] = parts or (base or {}).get('set_items',[])
    return item


def starting_cents(raw):
    if raw is None or str(raw).strip()=='':
        raise ValueError('Not enough comparable market data. Enter your starting premium over spot.')
    value = cents(raw)
    if value<0 or Decimal(str(raw))!=Decimal(value)/100:
        raise ValueError('Starting premium must be nonnegative with at most two decimal places.')
    return value


def initial_quote(conn, item, strategy, minimum, starting=None, now=None):
    now = now or now_utc()
    if item.get('isolated_type')!='set' and any(not item.get(k) for k in ('metal','product_type','weight','purity','mint','year')):
        raise ValueError('Complete the product specifications before previewing Smart Pricing.')
    value, spots = metal_basis(conn,item,now)
    source, observations = evidence(conn,item.get('listing_id'),item,now)
    market = target_details(observations,strategy,minimum) if observations else None
    premium = market['target_cents'] if market else max(minimum,starting_cents(starting))
    if value+premium<=0:
        raise ValueError('A positive listing price is required.')
    return {'engine':VERSION,'strategy':strategy,'minimum_cents':minimum,
            'initial_premium_cents':premium,'metal_value_cents':value,
            'initial_price_cents':value+premium,'seeded':market is None,
            'source':source,'confidence_label':market['confidence_label'] if market else 'insufficient',
            'market':market,'product':signature(item),'spot_snapshots':spots,
            'warning_required':nonstandard(item),'classification':classify_smart_pricing_item(item),'year_comparability':classify_year_comparability(item)}


def preview_quote(conn,item,strategy,minimum,starting=None,acknowledged=False,quantity=1):
    """One server calculation used for preview and atomic publication validation."""
    from flask import current_app
    from itsdangerous import URLSafeTimedSerializer
    if nonstandard(item) and not acknowledged:
        return {'warning_required':True}
    # Preview insufficient data without inventing or defaulting a seller seed.
    value, spots = metal_basis(conn,item,now_utc())
    source, observations = evidence(conn,item.get('listing_id'),item,now_utc())
    market = target_details(observations,strategy,minimum) if observations else None
    if not market and (starting is None or str(starting).strip()==''):
        return {'warning_required':nonstandard(item),'seeded':True,'confidence_label':'insufficient',
                'needs_starting':True,'metal_value_cents':value,'source':source}
    quote = initial_quote(conn,item,strategy,minimum,starting)
    authorization = {key:quote[key] for key in ('product','strategy','minimum_cents','initial_premium_cents','metal_value_cents','initial_price_cents','seeded')}
    authorization.update(seller_id=item['seller_id'],acknowledged=bool(acknowledged),starting=starting)
    quote['token'] = URLSafeTimedSerializer(current_app.secret_key,salt='metex-smart-preview-v1').dumps(authorization)
    # Raw comp IDs and technical percentile names remain server-side audit data.
    quote.pop('product')
    if market:
        quote['fair_premium_cents']=market['p50_cents']
        quote['range_lower_cents']=market['p25_cents']
        quote['range_upper_cents']=market['p75_cents']
    quote.pop('market')
    from services.flow_of_funds import seller_fee_cents
    quantity=int(quantity)
    if not 1<=quantity<=100000:raise ValueError('Choose a valid listing quantity.')
    fee=seller_fee_cents(quote['initial_price_cents'])
    gross=quote['initial_price_cents']*quantity
    quote.update(quantity=quantity,seller_fee_cents=fee,estimated_net_cents=quote['initial_price_cents']-fee,
                 estimated_total_net_cents=gross-seller_fee_cents(gross))
    return quote


def validate_preview(conn,item,settings,form):
    from flask import current_app
    from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
    try:
        approved = URLSafeTimedSerializer(current_app.secret_key,salt='metex-smart-preview-v1').loads(form.get('smart_preview_token',''),max_age=900)
    except (BadSignature,SignatureExpired):
        raise PreviewChanged('Review the current Smart Pricing preview and confirm it before publishing.')
    if approved['seller_id']!=item['seller_id'] or nonstandard(item) and not approved.get('acknowledged'):
        raise ValueError('Review and acknowledge the Smart Pricing accuracy warning.')
    strategy,minimum=settings
    quote = initial_quote(conn,item,strategy,minimum,form.get('smart_starting'))
    for key in ('product','strategy','minimum_cents','initial_premium_cents','metal_value_cents','initial_price_cents','seeded'):
        if approved.get(key)!=quote[key]:
            raise PreviewChanged('Smart Pricing inputs or market prices changed. Refresh the preview and confirm the new price.')
    quote['warning_acknowledged'] = approved.get('acknowledged',False)
    return quote
