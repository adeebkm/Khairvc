#!/usr/bin/env python3
"""
Quick migration script to add encryption columns
Run this on Railway: railway run python run_migration.py
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def main():
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ ERROR: DATABASE_URL not found")
        print("   Set DATABASE_URL environment variable")
        sys.exit(1)
    
    if 'sqlite' in database_url.lower():
        print("⚠️  SQLite detected - columns will be added automatically")
        sys.exit(0)
    
    print("🚀 Running migration: Adding encryption columns...")
    print(f"   Database: {database_url.split('@')[-1] if '@' in database_url else 'local'}")
    
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        trans = conn.begin()
        
        try:
            # Check if columns exist
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'email_classifications' 
                AND column_name IN ('subject_encrypted', 'snippet_encrypted')
            """))
            existing = [row[0] for row in result]
            
            if 'subject_encrypted' in existing and 'snippet_encrypted' in existing:
                print("✅ Columns already exist - nothing to do!")
                trans.commit()
                return
            
            # Add columns
            if 'subject_encrypted' not in existing:
                conn.execute(text("""
                    ALTER TABLE email_classifications 
                    ADD COLUMN subject_encrypted TEXT;
                """))
                print("   ✅ Added subject_encrypted")
            
            if 'snippet_encrypted' not in existing:
                conn.execute(text("""
                    ALTER TABLE email_classifications 
                    ADD COLUMN snippet_encrypted TEXT;
                """))
                print("   ✅ Added snippet_encrypted")
            
            # Migrate data
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
            
            trans.commit()
            print("\n✅ Migration completed successfully!")
            
        except Exception as e:
            trans.rollback()
            print(f"\n❌ Migration failed: {e}")
            sys.exit(1)

if __name__ == '__main__':
    main()

