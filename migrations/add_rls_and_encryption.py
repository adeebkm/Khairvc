"""
Migration: Add Row-Level Security (RLS) and Field Encryption
Priority 1: Database-level security
Priority 2: Encrypt sensitive fields (subject, snippet)

Run this migration on PostgreSQL:
    python migrations/add_rls_and_encryption.py

For Railway, run via Railway CLI or connect to database directly.
"""
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def run_migration():
    """Add RLS and encryption columns"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in environment")
        print("   Set DATABASE_URL in .env or Railway variables")
        sys.exit(1)
    
    # Handle both SQLite (local) and PostgreSQL (Railway)
    if 'sqlite' in database_url.lower():
        print("⚠️  SQLite detected. RLS is PostgreSQL-only.")
        print("   Skipping RLS migration (will work in production with PostgreSQL)")
        print("   Adding encryption columns only...")
        return add_encryption_columns_sqlite(database_url)
    else:
        print("✅ PostgreSQL detected. Running full migration...")
        return add_rls_and_encryption_postgres(database_url)

def add_rls_and_encryption_postgres(database_url):
    """Add RLS and encryption for PostgreSQL"""
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()
        
        try:
            print("\n📋 Step 1: Adding encryption columns...")
            
            # Add encrypted columns (nullable initially for migration)
            conn.execute(text("""
                ALTER TABLE email_classifications 
                ADD COLUMN IF NOT EXISTS subject_encrypted TEXT;
            """))
            
            conn.execute(text("""
                ALTER TABLE email_classifications 
                ADD COLUMN IF NOT EXISTS snippet_encrypted TEXT;
            """))
            
            print("   ✅ Added subject_encrypted column")
            print("   ✅ Added snippet_encrypted column")
            
            print("\n📋 Step 2: Migrating existing data...")
            # Copy existing plain text to encrypted columns (will be encrypted by app)
            # For now, just copy - app will encrypt on next write
            conn.execute(text("""
                UPDATE email_classifications 
                SET subject_encrypted = subject 
                WHERE subject_encrypted IS NULL AND subject IS NOT NULL;
            """))
            
            conn.execute(text("""
                UPDATE email_classifications 
                SET snippet_encrypted = snippet 
                WHERE snippet_encrypted IS NULL AND snippet IS NOT NULL;
            """))
            
            print("   ✅ Migrated existing data")
            
            print("\n📋 Step 3: Enabling Row-Level Security...")
            
            # Enable RLS
            conn.execute(text("""
                ALTER TABLE email_classifications ENABLE ROW LEVEL SECURITY;
            """))
            
            print("   ✅ Enabled RLS on email_classifications")
            
            print("\n📋 Step 4: Creating RLS policy...")
            
            # Drop policy if exists (for re-running migration)
            conn.execute(text("""
                DROP POLICY IF EXISTS user_isolation ON email_classifications;
            """))
            
            # Create policy
            conn.execute(text("""
                CREATE POLICY user_isolation ON email_classifications
                    FOR ALL
                    USING (user_id = current_setting('app.current_user_id', true)::int);
            """))
            
            print("   ✅ Created RLS policy: user_isolation")
            
            print("\n📋 Step 5: Creating helper function for user context...")
            
            # Create function to set user context (for use in Flask)
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION set_user_context(user_id_param INTEGER)
                RETURNS VOID AS $$
                BEGIN
                    PERFORM set_config('app.current_user_id', user_id_param::text, false);
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            print("   ✅ Created set_user_context function")
            
            # Commit transaction
            trans.commit()
            
            print("\n✅ Migration completed successfully!")
            print("\n📝 Next steps:")
            print("   1. Update Flask app to set user context (see app.py changes)")
            print("   2. Update models.py to use encrypted fields")
            print("   3. Restart application")
            
            return True
            
        except Exception as e:
            trans.rollback()
            print(f"\n❌ Migration failed: {e}")
            print("   Transaction rolled back")
            return False

def add_encryption_columns_sqlite(database_url):
    """Add encryption columns for SQLite (RLS not supported)"""
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        trans = conn.begin()
        
        try:
            print("\n📋 Adding encryption columns to SQLite...")
            
            # SQLite doesn't support IF NOT EXISTS in ALTER TABLE
            # Check if columns exist first
            result = conn.execute(text("""
                PRAGMA table_info(email_classifications);
            """))
            
            existing_columns = [row[1] for row in result]
            
            if 'subject_encrypted' not in existing_columns:
                conn.execute(text("""
                    ALTER TABLE email_classifications 
                    ADD COLUMN subject_encrypted TEXT;
                """))
                print("   ✅ Added subject_encrypted column")
            else:
                print("   ⚠️  subject_encrypted column already exists")
            
            if 'snippet_encrypted' not in existing_columns:
                conn.execute(text("""
                    ALTER TABLE email_classifications 
                    ADD COLUMN snippet_encrypted TEXT;
                """))
                print("   ✅ Added snippet_encrypted column")
            else:
                print("   ⚠️  snippet_encrypted column already exists")
            
            # Migrate existing data
            conn.execute(text("""
                UPDATE email_classifications 
                SET subject_encrypted = subject 
                WHERE subject_encrypted IS NULL AND subject IS NOT NULL;
            """))
            
            conn.execute(text("""
                UPDATE email_classifications 
                SET snippet_encrypted = snippet 
                WHERE snippet_encrypted IS NULL AND snippet IS NOT NULL;
            """))
            
            print("   ✅ Migrated existing data")
            
            trans.commit()
            
            print("\n✅ SQLite migration completed!")
            print("   ⚠️  Note: RLS is PostgreSQL-only. Will be enabled in production.")
            
            return True
            
        except Exception as e:
            trans.rollback()
            print(f"\n❌ Migration failed: {e}")
            return False

if __name__ == '__main__':
    print("🚀 Starting migration: RLS + Field Encryption")
    print("=" * 60)
    success = run_migration()
    sys.exit(0 if success else 1)

