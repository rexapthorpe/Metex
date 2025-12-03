# Photo Migration Guide

## Overview

This migration moves listing photo data from the old `listings.photo_filename` field to the new `listing_photos` table, establishing a proper relational structure for photo management.

## Problem Statement

**Before Migration:**
- Photos stored as filename strings in `listings.photo_filename` field
- No proper foreign key relationships
- Difficult to support multiple photos per listing
- Order items modal showed "No Image" placeholder

**After Migration:**
- Photos stored in dedicated `listing_photos` table
- Proper foreign key relationships (`listing_id`, `uploader_id`)
- Foundation for multiple photos per listing (future feature)
- Order items modal displays actual product photos

## Files Modified

### 1. Migration Script
**`migrations/migrate_photos_to_listing_photos.py`**
- Reads existing `listings.photo_filename` data
- Creates corresponding entries in `listing_photos` table
- Preserves all relationships
- Includes validation and rollback capability

### 2. Updated Routes
**`routes/sell_routes.py`** (lines 137-171)
- Changed to insert photos into `listing_photos` table
- Stores `file_path` as `"uploads/listings/{filename}"`
- Links photo to listing via `listing_id` foreign key

### 3. Verification Script
**`migrations/verify_photo_migration.py`**
- Validates migration completed successfully
- Tests order_items API query
- Checks file system for actual photos
- Provides diagnostic information

## Database Schema

### listing_photos Table
```sql
CREATE TABLE listing_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    uploader_id INTEGER,
    file_path TEXT NOT NULL,
    FOREIGN KEY (listing_id) REFERENCES listings(id),
    FOREIGN KEY (uploader_id) REFERENCES users(id)
)
```

### Path Format
- **Old format:** `IMG_0554.jpeg` (just filename)
- **New format:** `uploads/listings/IMG_0554.jpeg` (relative to static folder)
- **Rendered as:** `/static/uploads/listings/IMG_0554.jpeg` (in HTML)

## Step-by-Step Migration Instructions

### Step 1: Backup Database
```bash
cd "C:\Users\rex.apthorpe\OneDrive - West Point\Desktop\MetalsExchangeApp\Metex"
python -c "import shutil; from datetime import datetime; shutil.copy('database.db', f'database_backup_{datetime.now().strftime(\"%Y%m%d_%H%M%S\")}.db')"
```

### Step 2: Run Migration Script
```bash
python migrations/migrate_photos_to_listing_photos.py
```

**What this does:**
1. Validates prerequisites (checks tables exist)
2. Shows preview of what will be migrated
3. Asks for confirmation
4. Creates backup SQL dump
5. Runs dry run first
6. Performs actual migration
7. Validates results

**Expected Output:**
```
===================================================================================
PHOTO MIGRATION SCRIPT
Migrating listings.photo_filename → listing_photos table
===================================================================================

VALIDATING MIGRATION PREREQUISITES
✓ listing_photos table exists
✓ Current rows in listing_photos: 0
✓ Listings with photo_filename: 3

MIGRATION PREVIEW
Will migrate 3 photo records:

1. Listing ID: 34
   Uploader ID: 1
   Photo Filename: IMG_0554.jpeg
   Full Path: uploads/listings/IMG_0554.jpeg

...

Ready to migrate 3 records. Continue? (yes/no): yes

✅ Migration completed successfully!
   - Migrated: 3
   - Skipped (already migrated): 0
```

### Step 3: Verify Migration
```bash
python migrations/verify_photo_migration.py
```

**What this checks:**
- Migration status (records moved correctly)
- Order items API query returns image_url
- Photo files exist on disk
- No data consistency issues
- Sample test data report

**Expected Output:**
```
MIGRATION STATUS CHECK
✓ Records in listing_photos table: 3
✓ Listings still using old photo_filename field: 3
✓ Unique listings with photos: 3

✅ Migration appears complete!

ORDER ITEMS API QUERY TEST
Testing with Order ID: 33
Query returned 1 items:

1. Order Item 22:
   Listing ID: 35
   Seller: john_doe
   Raw file_path: uploads/listings/IMG_0554_1.jpeg
   Computed image_url: /static/uploads/listings/IMG_0554_1.jpeg
   ✅ Image URL generated successfully

✅ ALL VERIFICATIONS PASSED!
```

### Step 4: Test in Application
1. Start Flask application:
   ```bash
   python app.py
   ```

2. Navigate to **Account > Orders** tab

3. Click **"Items"** button on any order with photos

4. Verify photos appear in the modal (not "No Image" placeholder)

5. Test creating a new listing:
   - Go to **Sell** page
   - Fill out form and upload a photo
   - Submit listing
   - Verify listing was created successfully

6. Make a test purchase and verify photo appears in orders modal

## Troubleshooting

### Issue: Migration shows "Nothing to migrate"
**Cause:** No listings have `photo_filename` values
**Solution:** This is normal if you haven't created listings with photos yet. The migration is ready for when you do.

### Issue: Photos show as "No Image" after migration
**Check:**
```bash
python migrations/verify_photo_migration.py
```

Look for:
- Missing files on disk
- Orphaned photo records
- Path format issues

### Issue: New listings don't save photos
**Check:**
1. Is `static/uploads/listings/` directory writable?
2. Check Flask logs for errors
3. Verify `listing_photos` table accepts inserts:
   ```bash
   python -c "from database import get_db_connection; conn = get_db_connection(); print(conn.execute('SELECT * FROM listing_photos').fetchall())"
   ```

### Issue: Photos appear broken in browser
**Check network tab:**
- Look for 404 errors on image requests
- Verify URL format: `/static/uploads/listings/filename.jpg`
- Check that files exist in correct location

**Fix path issues:**
```bash
python -c "
from database import get_db_connection
conn = get_db_connection()
# Show all current paths
for row in conn.execute('SELECT id, listing_id, file_path FROM listing_photos').fetchall():
    print(f'ID {row[0]}, Listing {row[1]}: {row[2]}')
conn.close()
"
```

## Rollback Instructions

### If migration fails mid-process:
1. Restore from automatic backup:
   ```bash
   # The migration script creates backup_before_migration_YYYYMMDD_HHMMSS.sql
   # Restore it manually or re-run migration after fixing issues
   ```

2. Clear listing_photos table:
   ```bash
   python -c "from database import get_db_connection; conn = get_db_connection(); conn.execute('DELETE FROM listing_photos'); conn.commit()"
   ```

3. Re-run migration after fixing issues

### If you need to completely undo changes:
1. Restore full database backup from Step 1
2. Revert `routes/sell_routes.py` changes using git:
   ```bash
   git checkout routes/sell_routes.py
   ```

## Future Enhancements

Once migration is stable, consider:

1. **Remove old field:** Drop `listings.photo_filename` column (after confirming all listings migrated)
2. **Multiple photos:** Extend UI to support multiple photos per listing
3. **Photo gallery:** Add carousel/gallery view in order items modal
4. **Image optimization:** Add thumbnail generation for faster loading
5. **Cloud storage:** Move to S3/CloudFront for better scalability

## Support

If you encounter issues:
1. Check this README troubleshooting section
2. Review migration script output for specific error messages
3. Run verification script for diagnostic information
4. Check `CLAUDE.md` for project architecture overview
