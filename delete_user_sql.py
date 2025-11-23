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

# Users to delete
usernames = ['amaantrial', 'adeebkm']

print(f"🔍 Deleting {len(usernames)} user(s) and all associated data...\n")

for username in usernames:
    print(f"\n{'='*60}")
    print(f"Processing user: {username}")
    print(f"{'='*60}\n")
    
    # Check if user exists first
    with engine.connect() as check_conn:
        result = check_conn.execute(text("SELECT id, username, email FROM users WHERE username = :username"), {"username": username})
        user_row = result.fetchone()
        
        if not user_row:
            print(f"⚠️  User '{username}' not found, skipping...")
            continue
    
    # User exists, proceed with deletion
    with engine.begin() as conn:  # Use begin() context manager for automatic transaction handling
        try:
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
            
            # Transaction auto-commits when exiting 'with' block
            print(f"\n✅ Successfully deleted user '{username}' and all associated data")
            
            # Verify deletion (after commit)
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
            print(f"\n❌ Error deleting user '{username}': {e}")
            import traceback
            traceback.print_exc()
            # Transaction auto-rolls back on exception

print(f"\n{'='*60}")
print(f"✅ Finished processing {len(usernames)} user(s)")
print(f"{'='*60}")

