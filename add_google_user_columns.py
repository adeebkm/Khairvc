"""
Migration script to add Google OAuth user columns to users table
"""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set.")

# Ensure the URL is compatible with psycopg2
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def run_migration():
    print("Connecting to database...")
    try:
        with engine.connect() as connection:
            print("Running migration...")
            
            # Check if columns already exist
            result = connection.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' 
                AND column_name IN ('google_id', 'full_name', 'profile_picture')
            """))
            existing_columns = [row[0] for row in result]
            
            # Add google_id column if it doesn't exist
            if 'google_id' not in existing_columns:
                connection.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN google_id VARCHAR(255) UNIQUE
                """))
                print("✅ Successfully added 'google_id' column to users table")
            else:
                print("ℹ️  'google_id' column already exists. Skipping.")
            
            # Add full_name column if it doesn't exist
            if 'full_name' not in existing_columns:
                connection.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN full_name VARCHAR(200)
                """))
                print("✅ Successfully added 'full_name' column to users table")
            else:
                print("ℹ️  'full_name' column already exists. Skipping.")
            
            # Add profile_picture column if it doesn't exist
            if 'profile_picture' not in existing_columns:
                connection.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN profile_picture VARCHAR(500)
                """))
                print("✅ Successfully added 'profile_picture' column to users table")
            else:
                print("ℹ️  'profile_picture' column already exists. Skipping.")
            
            # Make password_hash nullable (for Google OAuth users)
            # Check current nullability
            result = connection.execute(text("""
                SELECT is_nullable 
                FROM information_schema.columns 
                WHERE table_name='users' 
                AND column_name='password_hash'
            """))
            password_nullable = result.scalar()
            
            if password_nullable == 'NO':
                connection.execute(text("""
                    ALTER TABLE users 
                    ALTER COLUMN password_hash DROP NOT NULL
                """))
                print("✅ Made 'password_hash' column nullable (for Google OAuth users)")
            else:
                print("ℹ️  'password_hash' column is already nullable. Skipping.")
            
            connection.commit()
            print("\n✅ Migration successful!")
            print("   Columns added:")
            print("   - google_id (VARCHAR(255), UNIQUE)")
            print("   - full_name (VARCHAR(200))")
            print("   - profile_picture (VARCHAR(500))")
            print("   - password_hash (now nullable)")

    except Exception as e:
        print(f"❌ An error occurred during migration: {e}")
        import traceback
        traceback.print_exc()
        # Rollback in case of error
        with engine.connect() as connection:
            connection.rollback()
        raise

if __name__ == "__main__":
    run_migration()

