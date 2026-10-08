"""Evidence-backed manual carrier workflow, sharing the canonical state machine."""
from flask import jsonify, request, session
import database
from utils.auth_utils import admin_required
from services import flow_of_funds as flow
from . import admin_bp
from utils.rate_limit import rate_limit


@admin_bp.route('/api/flow-operations', methods=['GET'])
@admin_required
def flow_operations():
    conn=database.get_db_connection()
    try:
        flow.ensure_flow_schema(conn)
        shipments=[dict(r) for r in conn.execute('SELECT s.*,l.buyer_gross_cents AS insured_value_required_cents FROM shipments s JOIN seller_fills f ON f.id=s.seller_fill_id JOIN snapshot_lines l ON l.id=f.snapshot_line_id ORDER BY s.created_at DESC LIMIT 100').fetchall()]
        reviews=[dict(r) for r in conn.execute("SELECT * FROM flow_reviews WHERE state='OPEN' ORDER BY created_at LIMIT 100").fetchall()]
        conn.commit()
        return jsonify(shipments=shipments,reviews=reviews)
    finally: conn.close()


@admin_bp.route('/api/flow-shipments/<shipment_id>/carrier-confirmation',methods=['POST'])
@admin_required
def confirm_carrier(shipment_id):
    body=request.get_json(silent=True) or {}
    evidence=body.get('evidence') or {}
    if not isinstance(evidence,dict): return jsonify(error='Evidence must be an object'),400
    evidence=dict(evidence,reviewed_by=session['user_id'])
    conn=database.get_db_connection()
    try:
        row=conn.execute('''SELECT s.*,f.seller_id FROM shipments s JOIN seller_fills f
          ON f.id=s.seller_fill_id WHERE s.id=?''',(shipment_id,)).fetchone()
        if not row: return jsonify(error='Shipment not found'),404
    finally: conn.close()
    try:
        flow.record_tracking(shipment_id,row['seller_id'],row['carrier'] or '',row['tracking_number'] or '',evidence)
        return jsonify(success=True,state='IN_TRANSIT')
    except flow.FlowError as exc:
        return jsonify(error=str(exc),error_code=exc.code),exc.status


@admin_bp.route('/api/flow-shipments/<shipment_id>/carrier-event',methods=['POST'])
@admin_required
def carrier_event(shipment_id):
    body=request.get_json(silent=True) or {}
    evidence=body.get('evidence') or {}
    if not isinstance(evidence,dict): return jsonify(error='Evidence must be an object'),400
    try:
        flow.record_shipment_event(shipment_id,body.get('state'),dict(evidence,reviewed_by=session['user_id']))
        return jsonify(success=True)
    except flow.FlowError as exc:
        return jsonify(error=str(exc),error_code=exc.code),exc.status


@admin_bp.route('/api/flow-controls',methods=['GET','PUT'])
@admin_required
def flow_controls():
    from services.system_settings_service import get_setting,set_setting
    keys=('checkout_enabled','manual_payouts_enabled','auto_payouts_enabled','shipments_enabled')
    if request.method=='PUT':
        body=request.get_json(silent=True) or {}
        if any(key not in keys or not isinstance(value,bool) for key,value in body.items()):
            return jsonify(error='Unknown control or non-boolean value'),400
        conn=database.get_db_connection()
        try:
            flow.ensure_flow_schema(conn)
            conn.execute('UPDATE flow_mutex SET revision=revision+1 WHERE id=1')
            before={key:get_setting(key,'0')=='1' for key in body}
            for key,value in body.items():
                conn.execute("INSERT INTO system_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",(key,'1' if value else '0'))
            flow._audit(conn,'controls','launch','LAUNCH_CONTROLS_CHANGED','admin',session['user_id'],before=before,after=body)
            conn.commit()
        except Exception:
            conn.rollback(); raise
        finally: conn.close()
    return jsonify(controls={key:get_setting(key,'0')=='1' for key in keys})


@admin_bp.route('/api/flow-recovery/approve',methods=['POST'])
@admin_required
def approve_seller_recovery():
    from services.recovery_service import approve_recovery
    body=request.get_json(silent=True) or {}
    try:
        result=approve_recovery(body.get('fill_id'),body.get('source_type'),body.get('source_id'),
          body.get('liability_reason'),body.get('evidence'),session['user_id'])
        return jsonify(success=True,recovery=result)
    except flow.FlowError as exc:
        return jsonify(error=str(exc),error_code=exc.code),exc.status


@admin_bp.route('/api/flow-recovery/<recovery_id>/reverse-transfer',methods=['POST'])
@admin_required
def reverse_seller_transfer(recovery_id):
    from services.recovery_service import reverse_transfer
    try: return jsonify(success=True,reversal_id=reverse_transfer(recovery_id))
    except flow.FlowError as exc:
        return jsonify(error=str(exc),error_code=exc.code),exc.status


@admin_bp.route('/api/flow-payables/<payable_id>/review',methods=['POST'])
@admin_required
def review_high_value_release(payable_id):
    body=request.get_json(silent=True) or {}
    reference=body.get('reference')
    if not isinstance(reference,str) or not reference.strip(): return jsonify(error='Review evidence reference required'),400
    conn=database.get_db_connection()
    try:
        flow.ensure_flow_schema(conn)
        if not conn.execute('SELECT id FROM seller_payables WHERE id=?',(payable_id,)).fetchone(): return jsonify(error='Payable not found'),404
        conn.execute("INSERT INTO flow_reviews VALUES (?,?,?,?,?,?,?) ON CONFLICT(scope_type,scope_id,reason) DO UPDATE SET state='APPROVED',evidence_json=excluded.evidence_json",(flow._id('review'),'payable',payable_id,'HIGH_VALUE_RELEASE','APPROVED',flow._canonical({'reference':reference,'admin_id':session['user_id']}),flow._now()))
        flow._audit(conn,'payable',payable_id,'HIGH_VALUE_REVIEW','admin',session['user_id'],metadata={'reference':reference})
        conn.commit(); return jsonify(success=True)
    finally: conn.close()


@admin_bp.route('/operations',methods=['GET'])
@admin_required
def operations_page():
    from flask import render_template
    return render_template('admin/operations.html')


@admin_bp.route('/api/flow-payables/<payable_id>/offset-recovery',methods=['POST'])
@admin_required
def offset_seller_recovery(payable_id):
    from services.recovery_service import offset_future_proceeds
    body=request.get_json(silent=True) or {}
    try:
        return jsonify(success=True,offset=offset_future_proceeds(payable_id,session['user_id'],body.get('evidence')))
    except flow.FlowError as exc:
        return jsonify(error=str(exc),error_code=exc.code),exc.status


@admin_bp.route('/reauthenticate',methods=['GET','POST'])
@admin_required
@rate_limit('5 per minute;20 per hour')
def reauthenticate():
    from flask import render_template
    from werkzeug.security import check_password_hash
    import time
    if request.method=='GET': return render_template('admin/reauthenticate.html')
    body=request.get_json(silent=True) or request.form
    conn=database.get_db_connection()
    try:
        user=conn.execute('SELECT password FROM users WHERE id=?',(session['user_id'],)).fetchone()
        valid=bool(user and user['password'] and check_password_hash(user['password'],body.get('password','')))
    finally: conn.close()
    if not valid: return jsonify(error='Password verification failed'),403
    session['authenticated_at']=time.time()
    conn=database.get_db_connection()
    try:
        flow.ensure_flow_schema(conn)
        flow._audit(conn,'user',str(session['user_id']),'ADMIN_REAUTHENTICATED','admin',session['user_id'])
        conn.commit()
    finally: conn.close()
    return jsonify(success=True)


@admin_bp.route('/api/flow-health',methods=['GET'])
@admin_required
def flow_health():
    from services.flow_health_service import health
    try: return jsonify(health())
    except Exception: return jsonify(healthy=False,error='Operational health could not be read'),503
