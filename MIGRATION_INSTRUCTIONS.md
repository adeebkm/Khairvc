# Database Migration Instructions

## Problem
The `processed` column was added to the `EmailClassification` model but doesn't exist in the production database yet, causing the error:
```
column email_classifications.processed does not exist
```

## Solution
Run the migration script to add the `processed` column to the database.

## Option 1: Run Migration on Railway (Recommended)

### Step 1: Push the migration script to GitHub
The migration script `add_processed_column.py` is already in your repo.

### Step 2: Run migration via Railway CLI or Dashboard

**Using Railway CLI:**
```bash
# Install Railway CLI if not already installed
npm i -g @railway/cli

# Login to Railway
railway login

# Link to your project
railway link

# Run the migration
railway run python add_processed_column.py
```

**Using Railway Dashboard (Web Terminal):**
1. Go to your Railway project
2. Click on your web service
3. Go to the "Settings" tab
4. Scroll down to "Service" section
5. Click "Open Terminal" or use the "Deployments" tab
6. In the terminal, run:
   ```bash
   python add_processed_column.py
   ```

## Option 2: Run Migration via Direct Database Connection

If you have direct access to the PostgreSQL database:

```bash
# Get your DATABASE_URL from Railway dashboard
export DATABASE_URL="postgresql://user:pass@host:port/dbname"

# Run the migration locally
python add_processed_column.py
```

## Option 3: Manual SQL (Direct Database Access)

If you prefer to run SQL directly:

```sql
-- Add the processed column
ALTER TABLE email_classifications 
ADD COLUMN processed BOOLEAN DEFAULT FALSE;

-- Set existing rows to processed=true
UPDATE email_classifications 
SET processed = TRUE 
WHERE processed IS NULL OR processed = FALSE;
```

## Verification

After running the migration, verify it worked:

```sql
-- Check the column exists
SELECT column_name, data_type, column_default
FROM information_schema.columns 
WHERE table_name = 'email_classifications' 
AND column_name = 'processed';

-- Check some rows
SELECT id, user_id, message_id, processed 
FROM email_classifications 
LIMIT 5;
```

## What the Migration Does

1. Adds a `processed` BOOLEAN column to `email_classifications` table
2. Sets default value to `FALSE` for new rows
3. Sets all existing rows to `processed = TRUE` (since they're already classified)

This prevents re-processing of existing emails while allowing new emails to be marked as processed after classification.

## After Migration

Once the migration is complete:
1. Restart your Railway services (web and workers)
2. The application should work normally
3. Monitor logs to ensure no more "processed does not exist" errors

## Rollback (if needed)

If something goes wrong, you can remove the column:

```sql
ALTER TABLE email_classifications DROP COLUMN processed;
```

Then remove the `processed` field from `models.py` and redeploy.

