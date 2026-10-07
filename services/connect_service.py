"""Connect readiness uses transfers capability, not direct-charge capability."""
import stripe


def seller_for_account(conn, account_id):
    if not account_id:
        return None
    row = conn.execute('SELECT id FROM users WHERE stripe_account_id=?', (account_id,)).fetchone()
    return row['id'] if row else None


def apply_account_status(conn, account):
    data = account.to_dict() if hasattr(account, 'to_dict') else dict(account)
    seller = seller_for_account(conn, data['id'])
    if seller is None:
        return False
    transfer_ready = (data.get('capabilities') or {}).get('transfers') == 'active'
    conn.execute('''UPDATE users SET stripe_onboarding_complete=?,
        stripe_charges_enabled=?,stripe_payouts_enabled=? WHERE id=?''',
        (int(bool(data.get('details_submitted'))), int(transfer_ready),
         int(bool(data.get('payouts_enabled'))), seller))
    return True


def refresh_seller(conn, seller_id):
    row = conn.execute('SELECT stripe_account_id FROM users WHERE id=?', (seller_id,)).fetchone()
    if not row or not row['stripe_account_id']:
        return False
    account = stripe.Account.retrieve(row['stripe_account_id'])
    apply_account_status(conn, account)
    data = account.to_dict() if hasattr(account, 'to_dict') else dict(account)
    return (bool(data.get('details_submitted')) and bool(data.get('payouts_enabled'))
            and (data.get('capabilities') or {}).get('transfers') == 'active')
