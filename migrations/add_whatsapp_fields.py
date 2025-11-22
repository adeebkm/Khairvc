"""
Migration: Add WhatsApp integration fields to User and Deal models
Run this after deploying the updated models
"""
import os
import sys
from sqlalchemy import text

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db

def run_migration():
    """Add WhatsApp fields to database"""
    with app.app_context():
        try:
            print("🔄 Starting WhatsApp fields migration...")
            
            # Check if columns already exist
            with db.engine.connect() as conn:
                # Check users table
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' 
                    AND column_name IN ('whatsapp_number', 'whatsapp_enabled')
                """))
                existing_user_columns = [row[0] for row in result]
                
                # Check deals table
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'deals' 
                    AND column_name IN ('whatsapp_alert_sent', 'whatsapp_alert_sent_at', 
                                       'whatsapp_followup_count', 'whatsapp_last_followup_at', 'whatsapp_stopped')
                """))
                existing_deal_columns = [row[0] for row in result]
            
            # Add User fields
            if 'whatsapp_number' not in existing_user_columns:
                print("  ➕ Adding whatsapp_number to users table...")
                db.session.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN whatsapp_number VARCHAR(20)
                """))
            
            if 'whatsapp_enabled' not in existing_user_columns:
                print("  ➕ Adding whatsapp_enabled to users table...")
                db.session.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN whatsapp_enabled BOOLEAN DEFAULT FALSE
                """))
            
            # Add Deal fields
            if 'whatsapp_alert_sent' not in existing_deal_columns:
                print("  ➕ Adding whatsapp_alert_sent to deals table...")
                db.session.execute(text("""
                    ALTER TABLE deals 
                    ADD COLUMN whatsapp_alert_sent BOOLEAN DEFAULT FALSE
                """))
            
            if 'whatsapp_alert_sent_at' not in existing_deal_columns:
                print("  ➕ Adding whatsapp_alert_sent_at to deals table...")
                db.session.execute(text("""
                    ALTER TABLE deals 
                    ADD COLUMN whatsapp_alert_sent_at TIMESTAMP
                """))
            
            if 'whatsapp_followup_count' not in existing_deal_columns:
                print("  ➕ Adding whatsapp_followup_count to deals table...")
                db.session.execute(text("""
                    ALTER TABLE deals 
                    ADD COLUMN whatsapp_followup_count INTEGER DEFAULT 0
                """))
            
            if 'whatsapp_last_followup_at' not in existing_deal_columns:
                print("  ➕ Adding whatsapp_last_followup_at to deals table...")
                db.session.execute(text("""
                    ALTER TABLE deals 
                    ADD COLUMN whatsapp_last_followup_at TIMESTAMP
                """))
            
            if 'whatsapp_stopped' not in existing_deal_columns:
                print("  ➕ Adding whatsapp_stopped to deals table...")
                db.session.execute(text("""
                    ALTER TABLE deals 
                    ADD COLUMN whatsapp_stopped BOOLEAN DEFAULT FALSE
                """))
            
            db.session.commit()
            print("✅ Migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Migration failed: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

if __name__ == '__main__':
    run_migration()

