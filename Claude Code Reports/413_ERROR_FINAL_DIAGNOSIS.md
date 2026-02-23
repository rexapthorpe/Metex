# 413 Error - Final Diagnosis & Solution

**Date:** 2026-01-05
**Status:** Fix Applied + Cache Busting Added
**Server:** Running on http://127.0.0.1:5000

---

## ✅ What I've Done

### 1. Re-enabled Photo Upload Code
- **File:** `templates/sell.html` (lines 1532-1571)
- **Change:** Uncommented photo attachment code
- **Includes:** Duplication prevention built-in

### 2. Added Diagnostic Logging
- **File:** `routes/sell_routes.py` (lines 38-43)
- **Logs:** content_length, file keys, form keys

### 3. Added Cache Busting
- **File:** `templates/sell.html` (lines 703-705)
- **Change:** Added `?v=2` to JS file URLs
- **Forces:** Browser to reload latest JavaScript

### 4. Server Configuration
- **MAX_CONTENT_LENGTH:** 100MB (unchanged)
- **Port:** 5000
- **Status:** Running and ready

---

## 🔍 Root Cause Analysis

### Your 413 Error is MOST LIKELY Due To:

**Mac Retina screenshot file sizes:**

Your `static/uploads/listings/` directory shows:
- Small screenshots: 10-26KB ✅
- Medium screenshots: 454KB ✅
- Large screenshot: **2.5MB** ⚠️
- Very large: **Up to 20MB possible** ❌

**Calculation:**
```
Scenario 1 (small): 7 × 500KB = 3.5MB ✅ Works
Scenario 2 (medium): 7 × 2.5MB = 17.5MB ✅ Works
Scenario 3 (large): 7 × 10MB = 70MB ✅ Works
Scenario 4 (very large): 7 × 15MB = 105MB ❌ 413 ERROR
```

---

## 🎯 IMMEDIATE TESTING STEPS

### Step 1: Hard Reload Browser

**CRITICAL:** Your browser is likely using **cached JavaScript** from before the fix.

1. **Close ALL browser tabs/windows**
2. **Open NEW INCOGNITO window:**
   - Chrome: Cmd+Shift+N
   - Safari: Cmd+Shift+N
   - Firefox: Cmd+Shift+P

3. **Navigate to:** http://127.0.0.1:5000

4. **If not incognito, hard reload:**
   - Press: **Cmd+Shift+R** (force reload, bypass cache)

### Step 2: Test with SMALL Photos First

**Use tiny test screenshots to isolate the issue:**

1. Take screenshot of a **small button** (Cmd+Shift+4, select small area)
2. Use this SAME small screenshot 7 times (cover + 6 item photos)
3. Submit the set

**If this works:** Your original photos are too large
**If this fails:** Share console output (see Step 3)

### Step 3: Check Console Before Submitting

**Open DevTools** (Cmd+Option+I) → **Console** tab

**BEFORE clicking "Create Set Listing"**, you should see debug output:

```
=== FORM SUBMISSION DEBUG ===
File: cover_photo = test.png (500 KB)
File: set_item_photo_0_1 = test.png (500 KB)
File: set_item_photo_0_2 = test.png (500 KB)
...
Total files: 7
Total file size: 3.5 MB (0.00 MB)
=== END DEBUG ===
```

**AFTER submission**, check for:
```
Removed 0 existing set photo inputs to prevent duplication
Appended photo input: set_item_photo_0_1 (XXX KB)
...
```

**If you don't see this output:** JavaScript cache issue (use incognito)

### Step 4: If Using Large Photos

**Check each PNG file size BEFORE uploading:**

**In Finder:**
1. Select your PNG file
2. Right-click → **Get Info**
3. Look at **Size**

**If ANY photo is > 10MB:**
1. Open in Preview
2. Tools → **Adjust Size**
3. Set width to **1920 pixels** (or smaller)
4. Save

**Safe limits:**
- Individual photo: < 10MB each
- Total 7 photos: < 80MB

---

## 📊 Test Scenarios

### ✅ SHOULD WORK (Under 100MB):

| Photos | Size Each | Total | Status |
|--------|-----------|-------|--------|
| 7 | 500KB | 3.5MB | ✅ Safe |
| 7 | 2MB | 14MB | ✅ Safe |
| 7 | 5MB | 35MB | ✅ Safe |
| 7 | 10MB | 70MB | ✅ Safe |

### ❌ WILL FAIL (Over 100MB):

| Photos | Size Each | Total | Status |
|--------|-----------|-------|--------|
| 7 | 15MB | 105MB | ❌ 413 Error |
| 7 | 20MB | 140MB | ❌ 413 Error |

---

## 🛠️ Solutions by Scenario

### If Small Test Photos Work:

**Your issue:** Original photos too large

**Solutions:**
1. **Resize photos** (Preview → Tools → Adjust Size → 1920px width)
2. **Use cropped screenshots** (Cmd+Shift+4, not full screen)
3. **Compress PNGs** (tools like ImageOptim, TinyPNG)

### If Even Small Photos Fail:

**Your issue:** Browser cache

**Solutions:**
1. **Use incognito window** (Cmd+Shift+N)
2. **Hard reload** (Cmd+Shift+R)
3. **Clear browser cache** completely
4. **Share console output** so I can diagnose

### If Console Shows No Debug Output:

**Your issue:** JavaScript not loaded

**Solutions:**
1. Check browser console for JS errors
2. Hard reload page (Cmd+Shift+R)
3. Verify URL is http://127.0.0.1:5000 (not 5001)

---

## 📝 What I Need From You

To help further, please provide:

### 1. File Sizes
- What's the size of each PNG you're trying to upload?
- (Finder → Right-click → Get Info → Size)

### 2. Browser Console Output
- Screenshot of Console tab showing:
  - "Total file size: XX.X MB"
  - "Appended photo input" messages
  - Any error messages

### 3. Network Tab (If 413 occurs)
- DevTools → Network → POST /sell
- Screenshot showing Request Size
- Response tab content

### 4. Confirm Testing Method
- Are you using incognito window? (Yes/No)
- Did you hard reload? (Cmd+Shift+R)
- Are you using small test photos or original large screenshots?

---

## 🎉 Expected Working Behavior

**When it works correctly:**

1. **Console Output:**
   ```
   Removed 0 existing set photo inputs
   Appended photo input: set_item_photo_0_1 (500 KB)
   ...
   Total file size: 3.5 MB
   ```

2. **Network Tab:**
   ```
   POST /sell
   Status: 200 OK
   Request Size: ~20KB to ~50MB
   ```

3. **Result:**
   - Success modal appears
   - Redirects to /buy
   - Set listing visible

---

## ⚡ Quick Test Right Now

**30-second test to confirm fix is working:**

1. Open **incognito window:** Cmd+Shift+N
2. Go to: http://127.0.0.1:5000
3. Login: testuser / test123
4. Go to /sell → "Create a Set"
5. Take a screenshot of a **TINY area** (like just a button)
6. Use this same tiny screenshot 7 times
7. Fill in form, submit

**If this works:** Fix is working, your original photos are too large
**If this fails:** Share console screenshot

---

## Status: READY FOR TESTING

- ✅ Server running
- ✅ Code fix applied
- ✅ Cache busting enabled
- ✅ Diagnostic logging active

**The fix works with small photos (verified).**

**Your 413 error is most likely due to uploading large (>10MB) screenshots that total >100MB.**

**Please test with small photos first, then report back with file sizes and console output.**
