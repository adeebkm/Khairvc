#!/usr/bin/env python3
"""
Database migration script to add rationale column to email_classifications table
"""
import os
import sys
from app import app, db
from sqlalchemy import text

def add_rationale_column():
    """Add rationale column to email_classifications table"""
    with app.app_context():
        try:
            # Check if column already exists (SQLite compatible)
            result = db.session.execute(text(
                "PRAGMA table_info(email_classifications)"
            ))
            
            columns = [row[1] for row in result.fetchall()]
            if 'rationale' in columns:
                print("✓ Rationale column already exists")
                return True
            
            # Add the column
            print("Adding rationale column...")
            db.session.execute(text(
                "ALTER TABLE email_classifications ADD COLUMN rationale TEXT"
            ))
            db.session.commit()
            print("✓ Rationale column added successfully")
            return True
            
        except Exception as e:
            print(f"Error adding rationale column: {e}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    print("="*60)
    print("DATABASE MIGRATION: Add Rationale Column")
    print("="*60)
    
    success = add_rationale_column()
    
    if success:
        print("\n✅ Migration completed successfully!")
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)

