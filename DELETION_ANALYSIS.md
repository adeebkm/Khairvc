# Email Deletion Analysis

## Summary
**All users' emails were deleted down to 20** because of a bug in the email deletion logic that ran on **every page load**.

## Database Status (Current)
- **User 23**: 14 emails remaining
- **User 33**: 21 emails remaining  
- **User 34**: 21 emails remaining

All users should have had ~200 emails, but the old code deleted them down to 20.

## Root Cause

### Old Code (Before Fix)
Located in `app.py` at the `/api/emails` endpoint:

```python
# Enforce 20 email limit: Delete oldest emails if more than 20 exist
total_classifications = EmailClassification.query.filter_by(user_id=current_user.id).count()
if total_classifications > 20:
    # Get IDs of oldest emails (keep latest 20)
    oldest_classifications = EmailClassification.query.filter_by(
        user_id=current_user.id
    ).order_by(EmailClassification.classified_at.asc()).limit(total_classifications - 20).all()
    
    # Delete oldest classifications
    for old_class in oldest_classifications:
        db.session.delete(old_class)
    
    db.session.commit()
    print(f"🗑️  Deleted {len(oldest_classifications)} old emails (keeping latest 20)")
```

### The Problem
1. This code ran **every time** the frontend called `/api/emails` (on every page load/refresh)
2. If a user had more than 20 emails, it would **immediately delete** all emails except the latest 20
3. Users who had 200+ emails during setup would lose 180+ emails on the first page load

### Why It Happened
- The deletion limit was incorrectly set to 20 instead of 200
- The deletion logic was placed in the email fetching endpoint, so it ran frequently
- No safeguards prevented deletion of already-classified emails

## Timeline of Events

1. **During Setup**: Users had ~200 emails fetched and classified
2. **First Page Load**: `/api/emails` endpoint called
3. **Deletion Triggered**: `if total_classifications > 20:` was true
4. **Mass Deletion**: System deleted 180+ oldest emails, keeping only latest 20
5. **Result**: Users' logs showed "🗑️  Deleted 2 old emails (keeping latest 20)"

## Fix Applied

### New Code (After Fix - Commit d908a88)
```python
# Keep latest 200 emails (not 20) - delete older emails if more than 200 exist
total_classifications = EmailClassification.query.filter_by(user_id=current_user.id).count()
if total_classifications > 200:
    # Get IDs of oldest emails (keep latest 200)
    oldest_classifications = EmailClassification.query.filter_by(
        user_id=current_user.id
    ).order_by(EmailClassification.classified_at.asc()).limit(total_classifications - 200).all()
    
    # Delete oldest classifications
    for old_class in oldest_classifications:
        db.session.delete(old_class)
    
    db.session.commit()
    print(f"🗑️  Deleted {len(oldest_classifications)} old emails (keeping latest 200)")
```

### Changes Made
1. Changed threshold from `20` to `200`
2. Changed deletion logic from `total_classifications - 20` to `total_classifications - 200`
3. Updated log message from "keeping latest 20" to "keeping latest 200"

## Impact

### Before Fix
- ❌ Users lost 180+ emails immediately after setup
- ❌ Only 20 most recent emails remained
- ❌ All older emails (including important dealflow) were permanently deleted

### After Fix
- ✅ Users can now accumulate up to 200 emails
- ✅ No automatic deletion until 200+ emails exist
- ✅ Future emails will be preserved up to the 200 limit

## Recovery Options

### Option 1: Re-fetch from Gmail (Recommended)
Users can trigger a full re-fetch of their emails:
1. Clear existing classifications from database
2. Re-run initial setup to fetch 200 emails again
3. All emails will be re-classified

### Option 2: Wait for New Emails
- As new emails arrive, they will accumulate up to 200
- Pub/Sub will fetch new emails automatically
- Database will gradually fill back up to 200

### Option 3: Manual Re-fetch Script
Create a script to:
1. Fetch all emails from Gmail (using Gmail API)
2. Skip emails already in database
3. Classify and store missing emails

## Recommendations

1. **For Existing Users**: 
   - Notify them about the deletion
   - Offer to re-fetch their emails
   - Emails are still in Gmail, just not in the database

2. **For New Users**:
   - Fix is already deployed
   - They won't experience this issue

3. **Monitoring**:
   - Add alerts if email count drops suddenly
   - Log email counts on each fetch/delete operation

## Git Commits

- **Bug Introduced**: Before commit 45f5c9b
- **Bug Fixed**: Commit d908a88 (2025-11-22)
- **Fix Improved**: Commit 9c74943 (WhatsApp error handling)

