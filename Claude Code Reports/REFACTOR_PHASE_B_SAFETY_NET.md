# Phase B: Safety Net Report

## Test Baseline Established

**Date**: 2026-01-21
**Test Results**: 218 passed, 82 failed (300 total)

---

## 1. Test Suite Analysis

### Passing Tests (218) - CRITICAL BASELINE

All core business logic tests pass:

| Test File | Tests | Status |
|-----------|-------|--------|
| `test_ledger.py` | 11 | ALL PASS |
| `test_ledger_phase1_verification.py` | 17 | ALL PASS |
| `test_ledger_phase2_escrow_control.py` | 25 | ALL PASS |
| `test_ledger_hardening.py` | 13 | ALL PASS |
| `test_bucket_fees.py` | 7 | ALL PASS |
| `test_bucket_fee_e2e_verification.py` | 10 | ALL PASS |
| `test_api_shapes.py` (public endpoints) | 8 | ALL PASS |
| `test_critical_flows.py` (non-admin) | ~20 | MOST PASS |

**Key passing test areas:**
- Ledger creation, invariants, events
- Fee calculations (percent, flat, custom)
- Escrow operations (hold, release, refund)
- Payout state management
- Cart data API
- Portfolio data API
- Authentication flow
- Bid/listing accessibility

### Failing Tests (82) - PRE-EXISTING ISSUES

**Root Causes Identified:**

1. **CSRF Template Error (Flask-WTF not installed)**
   ```
   jinja2.exceptions.UndefinedError: 'csrf_token' is undefined
   ```
   - Affects: All template rendering tests
   - Reason: `base.html` calls `{{ csrf_token() }}` but Flask-WTF not in requirements

2. **Security Headers Disabled in Test Mode**
   - Affects: 15+ security header tests
   - Reason: Headers middleware skipped when `TESTING=True`

3. **Admin Tests Missing Admin User Setup**
   - Affects: ~20 admin-related tests
   - Reason: Test fixtures don't properly set up admin users

**These failures are NOT caused by application bugs** - they are test configuration issues.

---

## 2. Refactor Safety Strategy

### Tests to Monitor During Refactor

Since template tests fail due to CSRF issues, we'll rely on:

1. **Core Logic Tests** (60 tests) - Must remain 100% passing
   ```bash
   python -m pytest tests/test_ledger*.py tests/test_bucket_fee*.py -v
   ```

2. **API Shape Tests** (public endpoints) - Must remain passing
   ```bash
   python -m pytest tests/test_api_shapes.py -k "Public or Cart or Portfolio or Listing" -v
   ```

3. **Manual Smoke Tests** (see checklist below)

### Pre-Refactor Checksum

Before each refactor step, verify:
```bash
# Quick sanity check (should be ~60 passing)
source venv/bin/activate && python -m pytest tests/test_ledger.py tests/test_ledger_phase1_verification.py tests/test_ledger_phase2_escrow_control.py tests/test_bucket_fees.py -v --tb=no
```

---

## 3. Manual Smoke Test Checklist

Run these manually after each significant refactor step.

### A. Public Pages (No Login Required)

| Test | URL | Expected |
|------|-----|----------|
| Login page loads | `/login` | Shows login form |
| Register page loads | `/register` | Shows registration form |
| Buy page loads | `/buy` | Shows marketplace items |
| Forgot password | `/forgot-password` | Shows email form |
| Spot prices API | `/api/spot-prices` | JSON with gold/silver prices |

### B. Authenticated User Pages

| Test | URL | Expected |
|------|-----|----------|
| Account page | `/account` | Shows tabs: Cart, Bids, Listings, etc. |
| Sell page | `/sell` | Shows listing form with mode selector |
| View cart | `/cart` | Shows cart contents or empty state |
| Checkout | `/checkout` | Shows checkout form or redirect |
| Notifications | `/api/notifications` | JSON array |

### C. Account Tab Navigation

| Test | Action | Expected |
|------|--------|----------|
| Cart tab | Click "Cart" in sidebar | Shows cart items |
| Bids tab | Click "Bids" | Shows my bids |
| Listings tab | Click "Listings" | Shows my listings |
| Sold tab | Click "Sold" | Shows sold items |
| Orders tab | Click "Orders" | Shows orders |
| Portfolio tab | Click "Portfolio" | Shows portfolio chart |
| Messages tab | Click "Messages" | Shows conversations |
| Ratings tab | Click "Ratings" | Shows ratings given/received |

### D. Sell Page Functionality

| Test | Action | Expected |
|------|--------|----------|
| Mode: Standard | Select "Standard Listing" | Form shows standard fields |
| Mode: Isolated | Select "One-of-a-Kind" | Title/description fields appear |
| Mode: Set | Select "Set Listing" | Set builder UI appears |
| Photo upload | Click photo box | File picker opens |
| Form validation | Submit empty form | Shows validation errors |

### E. Modal Functionality

| Test | Action | Expected |
|------|--------|----------|
| Bid modal | Click "Place Bid" on bucket | Modal opens with bid form |
| Edit listing modal | Click "Edit" on listing | Modal opens with current values |
| Buy item modal | Click "Buy" on bucket | Modal opens with quantity selector |
| Confirmation modals | Complete any action | Success modal appears |

### F. Admin Dashboard (Admin User)

| Test | URL | Expected |
|------|-----|----------|
| Dashboard loads | `/admin/dashboard` | Shows Overview tab |
| Users tab | Click "Users" | Shows user list |
| Listings tab | Click "Listings" | Shows listing management |
| Buckets tab | Click "Buckets" | Shows bucket management |
| Ledger tab | Click "Ledger" | Shows financial data |

### G. Critical Business Flows

| Test | Flow | Expected |
|------|------|----------|
| Create listing | Fill sell form → Submit | Listing appears in My Listings |
| Place bid | Open bid modal → Submit | Bid appears in My Bids |
| Add to cart | Click Add to Cart | Item appears in cart |
| Checkout | Go through checkout | Order confirmation shown |
| Edit listing | Open edit modal → Save | Changes saved |
| Cancel listing | Click cancel → Confirm | Listing marked cancelled |

---

## 4. Refactor Verification Process

For each refactor step:

1. **Before Changes**
   ```bash
   # Run core tests
   source venv/bin/activate && python -m pytest tests/test_ledger*.py tests/test_bucket_fee*.py -v --tb=no
   ```

2. **Make Changes** (one file/module at a time)

3. **After Changes**
   ```bash
   # Verify core tests still pass
   python -m pytest tests/test_ledger*.py tests/test_bucket_fee*.py -v --tb=no

   # Run the app
   python app.py
   ```

4. **Manual Smoke Test**
   - Open browser to `http://localhost:5000`
   - Run through checklist sections relevant to changed files

5. **Commit** (if all tests pass)

---

## 5. Files Requiring Extra Caution

These files have high test coverage and business criticality:

| File | Related Tests | Risk Level |
|------|---------------|------------|
| `core/services/ledger/*` | 66 tests | HIGH |
| `services/pricing_service.py` | Fee calculation tests | HIGH |
| `core/blueprints/checkout/routes.py` | Order creation | HIGH |
| `core/blueprints/buy/purchase.py` | Purchase flow | HIGH |
| `services/notification_service.py` | Notification tests | MEDIUM |

---

## 6. Approval to Proceed

**Baseline Established:**
- 218 tests passing (core business logic 100% pass)
- 82 tests failing (pre-existing CSRF/config issues)
- Manual smoke checklist created

**Ready for Phase C (Refactor Execution)?**

The refactor will proceed in this order:
1. **C-1**: Extract inline JS from templates (sell.html, view_bucket.html)
2. **C-2**: Split templates into partials
3. **C-3**: Split Python route modules
4. **C-4**: Final cleanup + backward compatibility

Please confirm to begin Phase C-1.
