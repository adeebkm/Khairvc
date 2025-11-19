"""
Clear all email classifications from Railway database
This forces Lambda to re-classify all emails on next fetch
"""
import os
from sqlalchemy import create_engine, text

# Get Railway database URL
database_url = os.getenv('DATABASE_URL')
if not database_url:
    print("❌ DATABASE_URL not found. Run with: railway run --service web python3 clear_classifications.py")
    exit(1)

# Fix postgres:// -> postgresql://
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

print(f"📊 Connecting to database...")
engine = create_engine(database_url)

with engine.connect() as conn:
    # Count existing classifications
    result = conn.execute(text("SELECT COUNT(*) FROM email_classification"))
    count = result.scalar()
    print(f"📧 Found {count} classified emails")
    
    if count > 0:
        print("🗑️  Deleting all classifications...")
        conn.execute(text("DELETE FROM email_classification"))
        conn.commit()
        print("✅ All classifications deleted!")
        print("\n🚀 Next time you fetch emails on Railway, Lambda will classify them!")
    else:
        print("✅ No classifications to delete")

print("\n📝 Note: The emails themselves are still in the database,")
print("   only their classifications have been cleared.")

