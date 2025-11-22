#!/usr/bin/env python3
"""
Delete a user and all their associated data from the database
"""
from app import app, db
from models import User, GmailToken, EmailClassification, Deal

def delete_user(username):
    """Delete a user and all their associated data"""
    with app.app_context():
        # Find the user
        user = User.query.filter_by(username=username).first()
        
        if not user:
            print(f"❌ User '{username}' not found")
            return False
        
        user_id = user.id
        print(f"🔍 Found user: {user.username} (ID: {user_id}, Email: {user.email})")
        
        # Count associated data
        email_count = EmailClassification.query.filter_by(user_id=user_id).count()
        deal_count = Deal.query.filter_by(user_id=user_id).count()
        token_count = GmailToken.query.filter_by(user_id=user_id).count()
        
        print(f"📊 Associated data:")
        print(f"   - Email Classifications: {email_count}")
        print(f"   - Deals: {deal_count}")
        print(f"   - Gmail Tokens: {token_count}")
        
        # Delete all associated data
        print(f"\n🗑️  Deleting all data for user '{username}'...")
        
        # Delete email classifications
        deleted_emails = EmailClassification.query.filter_by(user_id=user_id).delete()
        print(f"   ✅ Deleted {deleted_emails} email classifications")
        
        # Delete deals
        deleted_deals = Deal.query.filter_by(user_id=user_id).delete()
        print(f"   ✅ Deleted {deleted_deals} deals")
        
        # Delete Gmail token (should cascade, but being explicit)
        deleted_tokens = GmailToken.query.filter_by(user_id=user_id).delete()
        print(f"   ✅ Deleted {deleted_tokens} Gmail tokens")
        
        # Delete the user
        db.session.delete(user)
        
        # Commit all deletions
        db.session.commit()
        
        print(f"\n✅ Successfully deleted user '{username}' and all associated data")
        return True

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python delete_user.py <username>")
        print("Example: python delete_user.py adeebkm")
        sys.exit(1)
    
    username = sys.argv[1]
    delete_user(username)

