#!/usr/bin/env python3
"""
Helper script to generate keys and format credentials for Railway deployment
"""
import os
import json
import base64
from cryptography.fernet import Fernet

def generate_secret_key():
    """Generate a random secret key"""
    return os.urandom(32).hex()

def generate_encryption_key():
    """Generate a Fernet encryption key"""
    return Fernet.generate_key().decode()

def format_credentials_json():
    """Format credentials.json for Railway environment variable"""
    if not os.path.exists('credentials.json'):
        print("❌ credentials.json not found!")
        return None
    
    with open('credentials.json', 'r') as f:
        credentials = json.load(f)
    
    # Return as compact JSON string
    return json.dumps(credentials, separators=(',', ':'))

def main():
    print("=" * 60)
    print("Railway Deployment Setup Helper")
    print("=" * 60)
    print()
    
    # Generate keys
    print("1. Generating SECRET_KEY...")
    secret_key = generate_secret_key()
    print(f"   SECRET_KEY={secret_key}")
    print()
    
    print("2. Generating ENCRYPTION_KEY...")
    encryption_key = generate_encryption_key()
    print(f"   ENCRYPTION_KEY={encryption_key}")
    print()
    
    # Format credentials
    print("3. Formatting credentials.json...")
    credentials_json = format_credentials_json()
    if credentials_json:
        print("   GOOGLE_CREDENTIALS_JSON (first 50 chars):", credentials_json[:50] + "...")
        print()
        print("   Full value (copy this to Railway):")
        print("   " + "-" * 56)
        print("   " + credentials_json)
        print("   " + "-" * 56)
        print()
        
        # Also show base64 version
        credentials_b64 = base64.b64encode(credentials_json.encode()).decode()
        print("   Or as Base64 (alternative):")
        print("   " + "-" * 56)
        print("   " + credentials_b64)
        print("   " + "-" * 56)
    else:
        print("   ⚠️  Skipped (credentials.json not found)")
    print()
    
    print("=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("1. Copy the SECRET_KEY and ENCRYPTION_KEY to Railway environment variables")
    print("2. Copy the GOOGLE_CREDENTIALS_JSON to Railway environment variables")
    print("3. Set OAUTH_REDIRECT_URI to: https://your-app.railway.app/oauth2callback")
    print("4. Update Google Cloud Console with the redirect URI")
    print("5. Deploy to Railway!")
    print()

if __name__ == '__main__':
    main()

