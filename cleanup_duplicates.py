#!/usr/bin/env python3
"""
Cleanup script to remove duplicate emails from the database.
Keeps the oldest record (based on classified_at) and removes newer duplicates.
"""
import os
import sys
import psycopg2
from datetime import datetime

def cleanup_duplicates(database_url=None):
    """Remove duplicate emails, keeping the oldest one for each (user_id, message_id) pair"""
    
    if not database_url:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("⚠️  DATABASE_URL not found in environment variables.")
            print("Please provide your PostgreSQL connection string:")
            database_url = input("DATABASE_URL: ").strip()
            
            if not database_url:
                print("❌ No database URL provided. Exiting.")
                sys.exit(1)
    
    # Convert postgres:// to postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        print("🔍 Finding duplicate emails...")
        
        # Find all duplicates
        cur.execute('''
            SELECT message_id, user_id, COUNT(*) as count
            FROM email_classifications
            WHERE message_id IS NOT NULL
            GROUP BY message_id, user_id
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        ''')
        duplicates = cur.fetchall()
        
        if not duplicates:
            print("✅ No duplicates found!")
            cur.close()
            conn.close()
            return
        
        print(f"📊 Found {len(duplicates)} duplicate (user_id, message_id) pairs")
        
        total_duplicates_to_remove = 0
        
        # For each duplicate pair, keep the oldest and remove the rest
        for msg_id, user_id, count in duplicates:
            print(f"\n🔍 Processing: message_id={msg_id}, user_id={user_id}, duplicates={count}")
            
            # Get all records for this (user_id, message_id) pair, ordered by classified_at
            cur.execute('''
                SELECT id, classified_at
                FROM email_classifications
                WHERE message_id = %s AND user_id = %s
                ORDER BY classified_at ASC, id ASC
            ''', (msg_id, user_id))
            
            records = cur.fetchall()
            
            if len(records) <= 1:
                continue
            
            # Keep the first (oldest) record
            keep_id = records[0][0]
            remove_ids = [r[0] for r in records[1:]]
            
            print(f"  ✓ Keeping ID {keep_id} (oldest)")
            print(f"  🗑️  Removing IDs: {remove_ids}")
            
            # Check if any of the records to remove have associated deals
            cur.execute('''
                SELECT id FROM deals
                WHERE classification_id = ANY(%s)
            ''', (remove_ids,))
            deals_to_update = cur.fetchall()
            
            if deals_to_update:
                deal_ids = [d[0] for d in deals_to_update]
                print(f"  ⚠️  Found {len(deal_ids)} deal(s) associated with records to be removed")
                print(f"  🔄 Updating deals to point to kept record (ID {keep_id})...")
                
                # Update deals to point to the kept classification
                cur.execute('''
                    UPDATE deals
                    SET classification_id = %s
                    WHERE classification_id = ANY(%s)
                ''', (keep_id, remove_ids))
                print(f"  ✅ Updated {cur.rowcount} deal(s)")
            
            # Delete the duplicate email classifications
            cur.execute('''
                DELETE FROM email_classifications
                WHERE id = ANY(%s)
            ''', (remove_ids,))
            
            removed_count = cur.rowcount
            total_duplicates_to_remove += removed_count
            print(f"  ✅ Removed {removed_count} duplicate record(s)")
        
        # Commit all changes
        conn.commit()
        
        print(f"\n✅ Cleanup complete!")
        print(f"📊 Total duplicates removed: {total_duplicates_to_remove}")
        
        # Verify no duplicates remain
        cur.execute('''
            SELECT COUNT(*) FROM (
                SELECT message_id, user_id, COUNT(*) as count
                FROM email_classifications
                WHERE message_id IS NOT NULL
                GROUP BY message_id, user_id
                HAVING COUNT(*) > 1
            ) as dupes
        ''')
        remaining_duplicates = cur.fetchone()[0]
        
        if remaining_duplicates == 0:
            print("✅ Verification: No duplicates remain in the database")
        else:
            print(f"⚠️  Warning: {remaining_duplicates} duplicate pairs still remain")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        database_url = sys.argv[1]
    else:
        database_url = None
    
    cleanup_duplicates(database_url)

