#!/usr/bin/env python3
"""
Reset Railway PostgreSQL database by dropping and recreating all tables
Run this with Railway's DATABASE_URL
"""
import os
import sys

def reset_database():
    """Drop and recreate all tables"""
    try:
        # Get Railway DATABASE_URL
        database_url = input("Enter Railway DATABASE_URL (from Railway Variables): ").strip()
        
        if not database_url:
            print("❌ No DATABASE_URL provided")
            return
        
        # Confirm action
        confirm = input("⚠️  This will DELETE ALL DATA in the database. Type 'YES' to confirm: ")
        if confirm != 'YES':
            print("❌ Cancelled")
            return
        
        # Set DATABASE_URL temporarily
        os.environ['DATABASE_URL'] = database_url
        
        # Import after setting DATABASE_URL
        from models import db
        from flask import Flask
        
        # Create minimal Flask app
        app = Flask(__name__)
        
        # Convert postgres:// to postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # Initialize db
        db.init_app(app)
        
        with app.app_context():
            print("🗑️  Dropping all tables...")
            db.drop_all()
            print("✅ All tables dropped")
            
            print("📋 Creating fresh tables...")
            db.create_all()
            print("✅ Database reset complete!")
            
            print("\n✅ Railway database has been reset.")
            print("   All users, emails, and classifications have been deleted.")
            print("   Database schema is fresh and ready.")
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    reset_database()

