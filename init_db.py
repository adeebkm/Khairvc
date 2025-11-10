#!/usr/bin/env python3
"""
Initialize database with new schema
Run this after adding new models to recreate the database
"""
from app import app, db
from models import User, GmailToken, EmailClassification, Deal

with app.app_context():
    # Drop all tables and recreate
    db.drop_all()
    db.create_all()
    print("✓ Database recreated with new schema")
    print("✓ Tables created: users, gmail_tokens, email_classifications, deals")

