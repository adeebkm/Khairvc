#!/usr/bin/env python3
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import EmailClassification

print("🔄 Clearing email classifications cache...")

with app.app_context():
    try:
        count = EmailClassification.query.count()
        print(f"📊 Found {count} classified emails in database")
        
        if count > 0:
            print("🗑️  Deleting all classifications...")
            EmailClassification.query.delete()
            db.session.commit()
            print(f"✅ Successfully deleted {count} classifications!")
            print("\n🚀 Next fetch will trigger Lambda classification for all emails!")
        else:
            print("✅ No classifications found in database")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

