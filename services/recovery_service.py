"""Evidence-reviewed seller recovery and exact provider reversal identities."""
import stripe
from services.flow_safety import serialized


@serialized
def approve_recovery(fill_id, source_type, source_id, liability_reason, evidence, admin_id, conn=None):
    from services import flow_of_funds as flow
    flow.require_approved_policy(conn,'chargeback_loss_liability')
    allowed={'COUNTERFEIT','WRONG_ITEM','MISDESCRIPTION','FAILURE_TO_FULFILL'}
    if liability_reason not in allowed or not isinstance(evidence,dict) or not evidence.get('reference'):
        raise flow.FlowError('Recovery requires an approved seller-fault reason and evidence','LIABILITY_REVIEW_REQUIRED',409)
    fill=conn.execute('SELECT * FROM seller_fills WHERE id=?',(fill_id,)).fetchone()
    payable=conn.execute('SELECT * FROM seller_payables WHERE seller_fill_id=?',(fill_id,)).fetchone()
    if not fill or not payable: raise flow.FlowError('Fill not found','FILL_NOT_FOUND',404)
    old=conn.execute('SELECT * FROM recovery_obligations WHERE source_type=? AND source_id=? AND seller_fill_id=?',(source_type,source_id,fill_id)).fetchone()
    if old: return dict(old)
    if source_type=='REFUND':
        refund=conn.execute('''SELECT a.* FROM refund_allocations a JOIN flow_refunds r ON r.id=a.refund_id
          WHERE a.refund_id=? AND a.seller_fill_id=? AND r.state='SUCCEEDED' ''',(source_id,fill_id)).fetchone()
        if not refund: raise flow.FlowError('Recovery needs a confirmed allocated refund','RECOVERY_SOURCE_INVALID',409)
        amount=min(refund['seller_net_cents'],max(0,payable['released_cents']-payable['amount_cents']))
        credit='SELLER_PAYABLE'
    elif source_type=='CHARGEBACK':
        dispute=conn.execute("SELECT * FROM processor_disputes WHERE provider_dispute_id=? AND execution_id=? AND state='LOST'",(source_id,fill['execution_id'])).fetchone()
        if not dispute: raise flow.FlowError('Recovery needs a final lost dispute','RECOVERY_SOURCE_INVALID',409)
        # Refund overlap and multi-seller attribution require explicit review.
        if conn.execute("SELECT id FROM flow_refunds WHERE execution_id=? AND state<>'FAILED'",(fill['execution_id'],)).fetchone():
            raise flow.FlowError('Refund/dispute overlap must be reconciled first','RECOVERY_OVERLAP_REVIEW',409)
        snap=conn.execute('SELECT * FROM snapshot_lines WHERE id=?',(fill['snapshot_line_id'],)).fetchone()
        total=conn.execute('SELECT buyer_total_cents FROM execution_snapshots WHERE id=(SELECT snapshot_id FROM executions WHERE id=?)',(fill['execution_id'],)).fetchone()[0]
        if dispute['amount_cents']!=total: raise flow.FlowError('Partial disputed amount needs attribution review','RECOVERY_OVERLAP_REVIEW',409)
        amount=payable['released_cents']
        unpaid=max(0,payable['amount_cents']-amount)
        conn.execute("UPDATE seller_payables SET amount_cents=0,state='RECOVERY_PENDING',block_reason='CHARGEBACK_LOSS' WHERE id=?",(payable['id'],))
        entries=[]
        if unpaid: entries.append({'account':'SELLER_PAYABLE','debit':unpaid,'component':'chargeback_entitlement'})
        for account,value in [('MARKETPLACE_FEE_REVENUE',fill['seller_fee_cents']),('SPREAD_REVENUE',fill['spread_cents']),('TAX_PAYABLE',snap['tax_cents']),('CARD_SURCHARGE',snap['card_surcharge_cents'])]:
            if value: entries.append({'account':account,'debit':value,'component':'chargeback_component'})
        if entries:
            entries.append({'account':'DISPUTE_LOSS_EXPENSE','credit':sum(e['debit'] for e in entries),'component':'chargeback_attribution'})
            flow._journal(conn,'processor_dispute',source_id,'SELLER_FAULT_ATTRIBUTION',f'chargeback-attribution:{source_id}:{fill_id}',entries)
        credit='DISPUTE_LOSS_EXPENSE'
    else: raise flow.FlowError('Unknown recovery source','RECOVERY_SOURCE_INVALID',409)
    existing_debt=conn.execute("SELECT COALESCE(SUM(amount_cents),0) FROM recovery_obligations WHERE seller_fill_id=?",(fill_id,)).fetchone()[0]
    amount=min(amount,max(0,fill['seller_net_cents']-existing_debt))
    if amount<=0:
        if source_type!='CHARGEBACK':
            raise flow.FlowError('No released seller net remains to recover','RECOVERY_EMPTY',409)
        flow._audit(conn,'processor_dispute',source_id,'UNPAID_ENTITLEMENT_VOIDED','admin',admin_id,metadata=evidence)
        return {'state':'NO_RELEASED_DEBT','amount_cents':0,'seller_fill_id':fill_id}
    rid=flow._id('rec'); now=flow._now()
    conn.execute('INSERT INTO recovery_obligations VALUES (?,?,?,?,?,?,?,?,?,?,?)',(rid,fill['seller_id'],fill_id,source_type,source_id,amount,0,'OPEN',liability_reason,now,now))
    flow._journal(conn,'recovery',rid,'RECOVERY_APPROVED',f'recovery-approved:{rid}',[
      {'account':'SELLER_RECOVERY_RECEIVABLE','debit':amount,'component':'seller_recovery'},
      {'account':credit,'credit':amount,'component':'seller_recovery'}])
    flow._audit(conn,'recovery',rid,'LIABILITY_APPROVED','admin',admin_id,metadata=evidence)
    return dict(conn.execute('SELECT * FROM recovery_obligations WHERE id=?',(rid,)).fetchone())


@serialized
def claim_reversal(recovery_id, conn=None):
    from services import flow_of_funds as flow
    rec=conn.execute('SELECT * FROM recovery_obligations WHERE id=?',(recovery_id,)).fetchone()
    if not rec: raise flow.FlowError('Recovery not found','RECOVERY_NOT_FOUND',404)
    transfer=conn.execute('''SELECT t.* FROM transfers t JOIN seller_payables p ON p.id=t.seller_payable_id
      WHERE p.seller_fill_id=? AND t.state='TRANSFER_CONFIRMED' ''',(rec['seller_fill_id'],)).fetchone()
    if not transfer: raise flow.FlowError('Confirmed provider transfer is required','RECOVERY_TRANSFER_REQUIRED',409)
    key=f'recovery-reversal:{recovery_id}'
    old=conn.execute('SELECT * FROM financial_operations WHERE idempotency_key=?',(key,)).fetchone()
    if old: return dict(old),transfer['provider_transfer_id']
    amount=rec['amount_cents']-rec['recovered_cents']
    if amount<=0: raise flow.FlowError('Recovery already satisfied','RECOVERY_EMPTY',409)
    op,_=flow.claim_operation(conn,'TRANSFER_REVERSAL',key,'recovery',recovery_id,amount,{'transfer':transfer['provider_transfer_id'],'amount':amount})
    return op,transfer['provider_transfer_id']


@serialized
def complete_reversal(operation_id, provider, conn=None):
    from services import flow_of_funds as flow
    op=conn.execute('SELECT * FROM financial_operations WHERE id=?',(operation_id,)).fetchone()
    if not op: raise flow.FlowError('Reversal operation missing','RECOVERY_NOT_FOUND',404)
    if op['state']=='SUCCEEDED':
        if op['provider_object_id']!=provider.id: raise flow.FlowError('Reversal identity changed','RECOVERY_BINDING_MISMATCH',409)
        return False
    rec=conn.execute('SELECT * FROM recovery_obligations WHERE id=?',(op['aggregate_id'],)).fetchone()
    original=conn.execute('SELECT t.provider_transfer_id FROM transfers t JOIN seller_payables p ON p.id=t.seller_payable_id WHERE p.seller_fill_id=? AND t.state=\'TRANSFER_CONFIRMED\'',(rec['seller_fill_id'],)).fetchone()
    expected_transfer=original['provider_transfer_id'] if original else None
    if provider.transfer!=expected_transfer:
        raise flow.FlowError('Reversal transfer identity changed','RECOVERY_BINDING_MISMATCH',409)
    if provider.amount!=op['amount_cents'] or rec['recovered_cents']+provider.amount>rec['amount_cents']:
        raise flow.FlowError('Reversal amount exceeds debt','RECOVERY_BINDING_MISMATCH',409)
    now=flow._now(); total=rec['recovered_cents']+provider.amount
    conn.execute('UPDATE recovery_obligations SET recovered_cents=?,state=?,updated_at=? WHERE id=?',(total,'RECOVERED' if total==rec['amount_cents'] else 'PARTIAL',now,rec['id']))
    conn.execute("UPDATE financial_operations SET state='SUCCEEDED',provider_object_id=?,updated_at=? WHERE id=?",(provider.id,now,operation_id))
    flow._journal(conn,'recovery',rec['id'],'REVERSAL_CONFIRMED',f'reversal:{provider.id}',[
      {'account':'PROCESSOR_CASH','debit':provider.amount,'component':'seller_recovery'},
      {'account':'SELLER_RECOVERY_RECEIVABLE','credit':provider.amount,'component':'seller_recovery'}])
    return True


def reverse_transfer(recovery_id):
    op,transfer=claim_reversal(recovery_id)
    if op['state']=='SUCCEEDED': return op['provider_object_id']
    reversal=stripe.Transfer.create_reversal(transfer,amount=op['amount_cents'],idempotency_key=op['idempotency_key'],metadata={'recovery_id':recovery_id})
    complete_reversal(op['id'],reversal)
    return reversal.id


@serialized
def offset_future_proceeds(payable_id,admin_id,evidence,conn=None):
    """Apply only reviewed seller debt against untransferred canonical proceeds."""
    from services import flow_of_funds as flow
    flow.require_approved_policy(conn,'chargeback_loss_liability')
    if not isinstance(evidence,dict) or not evidence.get('reference'):
        raise flow.FlowError('Offset requires review evidence','LIABILITY_REVIEW_REQUIRED',409)
    payable=conn.execute('SELECT * FROM seller_payables WHERE id=?',(payable_id,)).fetchone()
    if not payable: raise flow.FlowError('Payable not found','PAYABLE_NOT_FOUND',404)
    if conn.execute('SELECT id FROM transfers WHERE seller_payable_id=?',(payable_id,)).fetchone():
        raise flow.FlowError('Claimed transfer must be reconciled before offset','OFFSET_TRANSFER_CLAIMED',409)
    fill=conn.execute('SELECT * FROM seller_fills WHERE id=?',(payable['seller_fill_id'],)).fetchone()
    if conn.execute("SELECT a.id FROM refund_allocations a JOIN flow_refunds r ON r.id=a.refund_id WHERE a.seller_fill_id=? AND r.state NOT IN ('FAILED','SUCCEEDED')",(fill['id'],)).fetchone():
        raise flow.FlowError('Pending refund blocks offset','REFUND_PENDING',409)
    available=max(0,payable['amount_cents']-payable['released_cents'])
    debts=conn.execute("SELECT * FROM recovery_obligations WHERE seller_id=? AND state IN ('OPEN','PARTIAL') ORDER BY created_at,id",(payable['seller_id'],)).fetchall()
    total=0
    for debt in debts:
        key=f"offset:{payable_id}:{debt['id']}"
        if conn.execute('SELECT id FROM ledger_journals WHERE idempotency_key=?',(key,)).fetchone(): continue
        amount=min(available,debt['amount_cents']-debt['recovered_cents'])
        if amount<=0: continue
        recovered=debt['recovered_cents']+amount
        conn.execute('UPDATE recovery_obligations SET recovered_cents=?,state=?,updated_at=? WHERE id=?',(recovered,'RECOVERED' if recovered==debt['amount_cents'] else 'PARTIAL',flow._now(),debt['id']))
        conn.execute('UPDATE seller_payables SET amount_cents=amount_cents-? WHERE id=?',(amount,payable_id))
        flow._journal(conn,'recovery',debt['id'],'FUTURE_PROCEEDS_OFFSET',key,[
          {'account':'SELLER_PAYABLE','debit':amount,'component':'future_offset','fill_id':fill['id']},
          {'account':'SELLER_RECOVERY_RECEIVABLE','credit':amount,'component':'future_offset'}])
        flow._audit(conn,'recovery',debt['id'],'FUTURE_PROCEEDS_OFFSET','admin',admin_id,metadata=dict(evidence,payable_id=payable_id,amount_cents=amount))
        total+=amount; available-=amount
    return {'offset_cents':total,'remaining_proceeds_cents':available}
