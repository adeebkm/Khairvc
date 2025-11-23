"""
Migration script to add 'processed' column to email_classifications table
Run this on Railway or your production database
"""
import os
from sqlalchemy import create_engine, text

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ DATABASE_URL environment variable not set")
    exit(1)

# Fix postgres:// to postgresql:// for SQLAlchemy compatibility
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

print(f"Connecting to database...")
engine = create_engine(DATABASE_URL)

# Migration SQL
migration_sql = """
-- Add processed column to email_classifications table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'email_classifications' 
        AND column_name = 'processed'
    ) THEN
        ALTER TABLE email_classifications 
        ADD COLUMN processed BOOLEAN DEFAULT FALSE;
        
        PRINT '✅ Successfully added processed column to email_classifications table';
    ELSE
        PRINT 'ℹ️  Column processed already exists in email_classifications table';
    END IF;
END $$;

-- Set existing rows to processed=true (they're already classified)
UPDATE email_classifications 
SET processed = TRUE 
WHERE processed IS NULL;
"""

try:
    with engine.connect() as conn:
        # Execute migration
        print("Running migration...")
        
        # Check if column exists first
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'email_classifications' 
            AND column_name = 'processed'
        """))
        
        if result.fetchone():
            print("ℹ️  Column 'processed' already exists in email_classifications table")
        else:
            # Add the column
            conn.execute(text("""
                ALTER TABLE email_classifications 
                ADD COLUMN processed BOOLEAN DEFAULT FALSE
            """))
            conn.commit()
            print("✅ Successfully added 'processed' column to email_classifications table")
            
            # Set existing rows to processed=true
            conn.execute(text("""
                UPDATE email_classifications 
                SET processed = TRUE 
                WHERE processed IS NULL OR processed = FALSE
            """))
            conn.commit()
            print("✅ Set all existing email classifications to processed=true")
        
        # Verify the column exists
        result = conn.execute(text("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns 
            WHERE table_name = 'email_classifications' 
            AND column_name = 'processed'
        """))
        
        row = result.fetchone()
        if row:
            print(f"\n✅ Migration successful!")
            print(f"   Column: {row[0]}")
            print(f"   Type: {row[1]}")
            print(f"   Default: {row[2]}")
        else:
            print("\n❌ Migration may have failed - column not found after migration")
            
except Exception as e:
    print(f"\n❌ Migration failed: {str(e)}")
    import traceback
    traceback.print_exc()
finally:
    engine.dispose()

print("\n✅ Migration complete!")

