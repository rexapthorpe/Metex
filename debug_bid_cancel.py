#!/usr/bin/env python3
"""
Debug why bid cancellation is failing with 400 error.
"""

import sqlite3

conn = sqlite3.connect('database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("\n" + "="*70)
print("BID CANCELLATION DEBUG")
print("="*70)

# Check all bids
print("\n[ALL BIDS]")
bids = cursor.execute("""
    SELECT id, buyer_id, category_id, status, active,
           quantity_requested, remaining_quantity, created_at
    FROM bids
    ORDER BY id DESC
    LIMIT 10
""").fetchall()

if not bids:
    print("  No bids found in database!")
else:
    for bid in bids:
        print(f"\n  Bid #{bid['id']}:")
        print(f"    buyer_id: {bid['buyer_id']}")
        print(f"    category_id: {bid['category_id']}")
        print(f"    status: '{bid['status']}'")
        print(f"    active: {bid['active']} ({'Yes' if bid['active'] else 'No'})")
        print(f"    quantity_requested: {bid['quantity_requested']}")
        print(f"    remaining_quantity: {bid['remaining_quantity']}")
        print(f"    created_at: {bid['created_at']}")

        # Check if this bid would pass the cancel validation
        can_cancel = bid['active'] and bid['status'] == 'Open'
        print(f"    Can cancel: {'YES' if can_cancel else 'NO'}")

        if not can_cancel:
            reasons = []
            if not bid['active']:
                reasons.append("active=0 (bid is inactive)")
            if bid['status'] != 'Open':
                reasons.append(f"status='{bid['status']}' (must be 'Open')")
            print(f"    Reason: {', '.join(reasons)}")

print("\n" + "="*70)
print("CANCEL ROUTE VALIDATION")
print("="*70)

# Simulate what the cancel route checks
print("\nThe /bids/cancel/<bid_id> route checks:")
print("1. Bid exists")
print("2. Bid belongs to current user (buyer_id matches session)")
print("3. active = 1 (truthy)")
print("4. status = 'Open'")
print("\nIf ANY of these fail, returns 400 Bad Request")

print("\n" + "="*70 + "\n")

conn.close()
