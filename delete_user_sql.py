#!/usr/bin/env python3
"""
Delete user 'adeebkm' and all associated data using SQL queries
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()

# Use provided PostgreSQL connection string
database_url = 'postgresql://postgres:aYckAdnBSNIpbpivCldCqHPreVmmiSgq@switchyard.proxy.rlwy.net:16682/railway'

# Create engine
engine = create_engine(database_url)

username = 'amaantrial'

print(f"🔍 Deleting user '{username}' and all associated data...\n")

with engine.connect() as conn:
    # Start transaction
    trans = conn.begin()
    
    try:
        # Step 1: Find the user_id
        result = conn.execute(text("SELECT id, username, email FROM users WHERE username = :username"), {"username": username})
        user_row = result.fetchone()
        
        if not user_row:
            print(f"❌ User '{username}' not found")
            trans.rollback()
            sys.exit(1)
        
        user_id = user_row[0]
        print(f"✅ Found user: {user_row[1]} (ID: {user_id}, Email: {user_row[2]})")
        
        # Step 2: Count associated data
        email_count = conn.execute(text("SELECT COUNT(*) FROM email_classifications WHERE user_id = :user_id"), {"user_id": user_id}).scalar()
        deal_count = conn.execute(text("SELECT COUNT(*) FROM deals WHERE user_id = :user_id"), {"user_id": user_id}).scalar()
        token_count = conn.execute(text("SELECT COUNT(*) FROM gmail_tokens WHERE user_id = :user_id"), {"user_id": user_id}).scalar()
        
        print(f"\n📊 Associated data:")
        print(f"   - Email Classifications: {email_count}")
        print(f"   - Deals: {deal_count}")
        print(f"   - Gmail Tokens: {token_count}")
        
        # Step 3: Delete deals first (they reference email_classifications)
        deleted_deals = conn.execute(text("DELETE FROM deals WHERE user_id = :user_id"), {"user_id": user_id}).rowcount
        print(f"\n🗑️  Deleted {deleted_deals} deals")
        
        # Step 4: Delete email classifications (after deals are deleted)
        deleted_emails = conn.execute(text("DELETE FROM email_classifications WHERE user_id = :user_id"), {"user_id": user_id}).rowcount
        print(f"🗑️  Deleted {deleted_emails} email classifications")
        
        # Step 5: Delete Gmail tokens
        deleted_tokens = conn.execute(text("DELETE FROM gmail_tokens WHERE user_id = :user_id"), {"user_id": user_id}).rowcount
        print(f"🗑️  Deleted {deleted_tokens} Gmail tokens")
        
        # Step 6: Delete the user
        deleted_user = conn.execute(text("DELETE FROM users WHERE username = :username"), {"username": username}).rowcount
        print(f"🗑️  Deleted {deleted_user} user")
        
        # Commit transaction
        trans.commit()
        
        print(f"\n✅ Successfully deleted user '{username}' and all associated data")
        
        # Verify deletion
        verify_user = conn.execute(text("SELECT COUNT(*) FROM users WHERE username = :username"), {"username": username}).scalar()
        verify_emails = conn.execute(text("SELECT COUNT(*) FROM email_classifications WHERE user_id = :user_id"), {"user_id": user_id}).scalar()
        verify_deals = conn.execute(text("SELECT COUNT(*) FROM deals WHERE user_id = :user_id"), {"user_id": user_id}).scalar()
        verify_tokens = conn.execute(text("SELECT COUNT(*) FROM gmail_tokens WHERE user_id = :user_id"), {"user_id": user_id}).scalar()
        
        print(f"\n✅ Verification:")
        print(f"   - Users remaining: {verify_user}")
        print(f"   - Email classifications remaining: {verify_emails}")
        print(f"   - Deals remaining: {verify_deals}")
        print(f"   - Gmail tokens remaining: {verify_tokens}")
        
    except Exception as e:
        trans.rollback()
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

