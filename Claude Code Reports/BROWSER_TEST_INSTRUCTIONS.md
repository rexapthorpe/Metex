# Browser Test Instructions - Diagnose 413 Error

## STEP 1: Clear Browser Cache & Open Fresh Window

1. **Open INCOGNITO/PRIVATE window** (critical - avoids cached JavaScript)
   - Chrome/Edge: Cmd+Shift+N
   - Firefox: Cmd+Shift+P
   - Safari: Cmd+Shift+N

2. **Open DevTools BEFORE navigating to site**
   - Press: Cmd+Option+I
   - Go to **Console** tab
   - Go to **Network** tab

## STEP 2: Login and Navigate

1. Navigate to: **http://127.0.0.1:5000**
2. Login with:
   - Username: `testuser`
   - Password: `test123`
3. Go to **/sell** page
4. Switch to **"Create a Set"** mode

## STEP 3: Add Items (Use SMALL Photos First)

**IMPORTANT: Start with SMALL test photos (< 1MB each) to isolate the issue**

### Add Item #1:
- Fill all product specs (metal, product_line, product_type, weight, purity, mint, year, finish, grade)
- Upload **1-3 SMALL photos** (PNG, < 1MB each)
  - Use screenshot tool to capture a small area
  - Or use existing small images
- Click "+ Add Item to Set"
- ✅ Verify item appears in sidebar

### Add Item #2:
- Fill product specs (different values)
- Upload **1-3 SMALL photos**
- Click "+ Add Item to Set"
- ✅ Verify 2 items now in sidebar

## STEP 4: Complete Set-Level Fields

- **Listing Title:** "Test Small Photos"
- **Cover Photo:** Upload 1 SMALL photo
- **Quantity:** 1
- **Pricing:** Static mode, $100.00

## STEP 5: BEFORE Clicking "Create Set Listing"

**Check Console Tab in DevTools:**

Look for debug output like:
```
=== FORM SUBMISSION DEBUG ===
File: cover_photo = xxx.png (XXX KB)
File: set_item_photo_0_1 = xxx.png (XXX KB)
...
Total files: X
Total file size: XX.X KB (XX.XX MB)
```

**ACTION: Take a screenshot of this console output and share it**

## STEP 6: Submit

1. Click **"Create Set Listing"**
2. Click **"Confirm"** in modal

## STEP 7: Capture Error Details

### If you get 413 error:

**A) Check Console Tab:**
- What does it say for "Total file size"?
- Copy the entire console output

**B) Check Network Tab:**
- Find the failed **POST /sell** request
- Click on it
- Go to **Headers** section
- Look for **Request Size** or **Content-Length**
- Take screenshot

**C) Check Response:**
- In Network tab, click the failed POST /sell
- Go to **Response** tab
- Copy the response text

### If you get 500 error:

- Check Console output
- Check Network tab POST /sell → Response
- Share terminal output from server

## STEP 8: Share Results

Please share:
1. Screenshot of **Console tab** showing file sizes
2. Screenshot of **Network tab** showing request details
3. What error message you saw in the popup
4. Terminal output from server (if accessible)

---

## Expected Behavior (Working)

**Console should show:**
```
Removed 0 existing set photo inputs to prevent duplication
Appended photo input: set_item_photo_0_1 (XXX KB)
Appended photo input: set_item_photo_0_2 (XXX KB)
...
Total files: 7
Total file size: XX.X KB (0.XX MB)
```

**Network tab should show:**
```
Status: 200 OK
Request Size: ~20KB to ~50KB (for small test photos)
```

**Result:**
- Success modal appears
- Redirects to /buy page
- Set listing visible

---

## Troubleshooting

### If Total File Size > 100MB:
- Your photos are too large
- Resize photos before uploading
- Or use smaller test images first

### If Console shows duplicate file inputs:
- JavaScript cache issue
- Hard reload: Cmd+Shift+R
- Or use incognito window

### If No console output at all:
- JavaScript not loaded
- Hard reload page
- Check browser console for JS errors

---

## Quick Test with Tiny Photos

If you want to test immediately with guaranteed small files:

1. Take a screenshot of a TINY area (like just a button)
2. Use that same tiny screenshot 7 times (cover + 6 item photos)
3. This will be < 50KB total
4. Should work instantly

Then gradually increase photo sizes to find the limit.
