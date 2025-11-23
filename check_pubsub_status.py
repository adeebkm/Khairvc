#!/usr/bin/env python3
"""
Check Gmail Pub/Sub watch status and re-enable if needed
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Set up Flask app context
from app import app, db, User, GmailToken
from gmail_client import GmailClient
import datetime

def check_and_fix_pubsub():
    with app.app_context():
        print("=" * 60)
        print("🔍 Checking Gmail Pub/Sub Watch Status")
        print("=" * 60)
        
        users = User.query.join(GmailToken).all()
        
        if not users:
            print("❌ No users with Gmail tokens found")
            return
        
        for user in users:
            print(f"\n📧 User {user.id}: {user.email}")
            
            token = user.gmail_token
            if not token or not token.token_json:
                print(f"   ❌ No Gmail token")
                continue
            
            # Check watch expiration
            if token.watch_expiration:
                exp_dt = datetime.datetime.fromtimestamp(token.watch_expiration / 1000)
                now = datetime.datetime.now()
                time_left = exp_dt - now
                
                if exp_dt > now:
                    print(f"   ✅ Watch is ACTIVE")
                    print(f"   ⏰ Expires: {exp_dt}")
                    print(f"   ⏳ Time left: {time_left}")
                    print(f"   📊 History ID: {token.history_id}")
                else:
                    print(f"   ❌ Watch EXPIRED at {exp_dt}")
                    print(f"   🔄 Attempting to renew...")
                    
                    # Try to renew watch
                    try:
                        gmail = GmailClient(token.token_json)
                        topic = os.getenv('PUBSUB_TOPIC_NAME', 'projects/innate-gizmo-477223-f4/topics/gmail-notifications')
                        
                        result = gmail.service.users().watch(
                            userId='me',
                            body={
                                'topicName': topic,
                                'labelIds': ['INBOX']
                            }
                        ).execute()
                        
                        new_expiration = result.get('expiration')
                        new_history_id = result.get('historyId')
                        
                        token.watch_expiration = int(new_expiration)
                        token.history_id = new_history_id
                        db.session.commit()
                        
                        exp_dt = datetime.datetime.fromtimestamp(int(new_expiration) / 1000)
                        print(f"   ✅ Watch renewed! New expiration: {exp_dt}")
                        print(f"   📊 New history ID: {new_history_id}")
                        
                    except Exception as e:
                        print(f"   ❌ Failed to renew: {str(e)}")
            else:
                print(f"   ❌ No watch set up")
                print(f"   🔄 Setting up watch...")
                
                # Set up watch
                try:
                    gmail = GmailClient(token.token_json)
                    topic = os.getenv('PUBSUB_TOPIC_NAME', 'projects/innate-gizmo-477223-f4/topics/gmail-notifications')
                    
                    result = gmail.service.users().watch(
                        userId='me',
                        body={
                            'topicName': topic,
                            'labelIds': ['INBOX']
                        }
                    ).execute()
                    
                    expiration = result.get('expiration')
                    history_id = result.get('historyId')
                    
                    token.watch_expiration = int(expiration)
                    token.history_id = history_id
                    db.session.commit()
                    
                    exp_dt = datetime.datetime.fromtimestamp(int(expiration) / 1000)
                    print(f"   ✅ Watch set up! Expiration: {exp_dt}")
                    print(f"   📊 History ID: {history_id}")
                    
                except Exception as e:
                    print(f"   ❌ Failed to set up: {str(e)}")
        
        print("\n" + "=" * 60)
        print("🔍 Pub/Sub Configuration")
        print("=" * 60)
        print(f"Topic: {os.getenv('PUBSUB_TOPIC_NAME', 'NOT SET')}")
        print(f"Webhook URL should be: https://your-domain.railway.app/api/pubsub/gmail-notifications")
        print("\n⚠️  Make sure:")
        print("   1. Pub/Sub topic exists in Google Cloud")
        print("   2. Gmail API has permission to publish to the topic")
        print("   3. Webhook URL is publicly accessible")
        print("   4. Pub/Sub subscription pushes to your webhook URL")

if __name__ == '__main__':
    check_and_fix_pubsub()

