# Portfolio Chart Diagnosis and Fix

## Current Status

You reported:
- ✅ Portfolio tab loads without errors
- ✅ Current Holdings section populated correctly
- ✅ Asset Allocation pie chart renders
- ✅ Exclusion and listing actions work
- ❌ Portfolio value line chart NOT rendering
- ❌ Time-range buttons (1D, 1W, 1M, 3M, 1Y) do nothing

## Diagnosis Process

### 1. Verified Components

| Component | Status | Location |
|-----------|--------|----------|
| Chart.js Library | ✅ Loaded | account.html:116 |
| Canvas Element | ✅ Exists | portfolio_tab.html:45 |
| Time Buttons | ✅ Configured | portfolio_tab.html:36-40 |
| CSS Height | ✅ Set (400px) | portfolio_tab.css:158-161 |
| JavaScript Functions | ✅ Implemented | portfolio_tab.js |
| API Endpoint | ✅ Working | /portfolio/history |
| Historical Data | ✅ Available | portfolio_snapshots table |

### 2. Potential Issues

Based on the symptoms, the likely issue is:

**The portfolio_tab.js is not being loaded or initialized properly.**

Possible causes:
1. Script not loaded in account.html
2. Script loads but init function never runs
3. JavaScript errors preventing execution
4. Timing issue - chart renders before DOM is ready

## Test Procedure

### Step 1: Check Browser Console

1. Open browser: http://127.0.0.1:5000
2. Login as `rexb` (or user with orders)
3. Press F12 to open DevTools
4. Go to Console tab
5. Click Account → Portfolio

**Expected console output:**
```
[Portfolio] Initializing portfolio tab
```

**If you see:**
- `Uncaught ReferenceError: initPortfolioTab is not defined`
  → portfolio_tab.js not loaded

- `Chart is not defined`
  → Chart.js not loaded

- No output at all
  → init function never called

### Step 2: Verify Script Loading

In DevTools Console, type:
```javascript
typeof initPortfolioTab
typeof Chart
```

**Expected:**
```
"function"
"function"
```

### Step 3: Manual Test

In DevTools Console, run:
```javascript
loadPortfolioHistory('1m')
```

Watch the Network tab for:
- Request to `/portfolio/history?range=1m`
- Response should be 200 with JSON

### Step 4: Test Chart Rendering

In DevTools Console, run:
```javascript
renderValueChart([{
  date: '2025-11-27',
  value: 100000,
  cost_basis: 95000
}, {
  date: '2025-11-28',
  value: 104971,
  cost_basis: 95911
}])
```

**Expected:** Chart appears in canvas

## Likely Fix Needed

Check if `static/js/tabs/portfolio_tab.js` is loaded in `templates/account.html`.

The file should be included AFTER Chart.js but BEFORE closing `</body>` tag.

### Verification

Run this in browser console when on Portfolio tab:
```javascript
document.querySelector('#portfolio-value-chart')  // Should return canvas element
typeof renderValueChart  // Should return "function"
```

## Test File Created

I created `test_portfolio_chart.html` to test the chart in isolation.

**To test:**
1. Start Flask: `python app.py`
2. Login as any user
3. Navigate to: http://127.0.0.1:5000/test_portfolio_chart.html
4. Check if chart renders
5. Check if time buttons work

This will help isolate whether it's a chart/JavaScript issue or an integration issue.

## Expected Behavior After Fix

When viewing Portfolio tab:
1. Line chart appears showing portfolio value over time
2. Chart has two lines:
   - Blue solid line: Portfolio Value
   - Gray dashed line: Cost Basis
3. Clicking time buttons (1D, 1W, 1M, 3M, 1Y):
   - Button becomes highlighted
   - Chart updates with new data range
   - No page reload

## Next Steps

1. Check browser console for errors
2. Verify portfolio_tab.js is loaded
3. Run manual test commands above
4. Share any error messages you see

The chart rendering code itself is correct - the issue is likely in the loading/initialization sequence.
