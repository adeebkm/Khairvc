#!/usr/bin/env python3
"""Manually clear classifications via Railway"""
import os
import sys

# This script is designed to run WITH Railway environment variables
if 'DATABASE_URL' not in os.environ:
    print("❌ This script must be run with Railway environment:")
    print("   railway run python3 manual_clear.py")
    sys.exit(1)

import psycopg2

db_url = os.environ['DATABASE_URL']
print("🔗 Connecting to Railway database...")

conn = psycopg2.connect(db_url)
cur = conn.cursor()

try:
    # Step 1: Nullify foreign key references
    print("🔄 Removing foreign key references...")
    cur.execute("UPDATE deals SET classification_id = NULL WHERE classification_id IS NOT NULL;")
    print(f"✅ Updated {cur.rowcount} deals")
    
    # Step 2: Delete classifications
    print("🗑️  Deleting classifications...")
    cur.execute("DELETE FROM email_classifications;")
    deleted = cur.rowcount
    print(f"✅ Deleted {deleted} classifications")
    
    # Commit
    conn.commit()
    
    # Verify
    cur.execute("SELECT COUNT(*) FROM email_classifications;")
    remaining = cur.fetchone()[0]
    print(f"\n✅ Success! {remaining} classifications remaining (should be 0)")
    print("\n🚀 Next fetch will use Lambda to classify emails!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    conn.rollback()
    sys.exit(1)
finally:
    cur.close()
    conn.close()

