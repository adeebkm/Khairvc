#!/usr/bin/env python3
"""
Test script to verify your setup before running the main application
"""
import os
import sys


def test_dependencies():
    """Test if all required dependencies are installed"""
    print("Testing dependencies...")
    
    required_packages = [
        'google.auth',
        'google_auth_oauthlib',
        'googleapiclient',
        'openai',
        'dotenv'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ✗ {package} - NOT INSTALLED")
            missing.append(package)
    
    if missing:
        print(f"\n✗ Missing packages: {', '.join(missing)}")
        print("Run: pip install -r requirements.txt")
        return False
    
    print("✓ All dependencies installed\n")
    return True


def test_env_file():
    """Test if .env file exists and has required variables"""
    print("Testing .env file...")
    
    if not os.path.exists('.env'):
        print("  ✗ .env file not found")
        print("  Run: python setup.py")
        return False
    
    print("  ✓ .env file exists")
    
    # Load .env
    from dotenv import load_dotenv
    load_dotenv()
    
    # Check OpenAI key
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key or openai_key == 'your_openai_api_key_here':
        print("  ✗ OPENAI_API_KEY not set properly")
        print("  Edit .env and add your OpenAI API key")
        return False
    
    print(f"  ✓ OPENAI_API_KEY set (starts with: {openai_key[:7]}...)")
    
    # Check other variables
    send_emails = os.getenv('SEND_EMAILS', 'false')
    print(f"  ✓ SEND_EMAILS = {send_emails}")
    
    max_emails = os.getenv('MAX_EMAILS', '5')
    print(f"  ✓ MAX_EMAILS = {max_emails}")
    
    print("✓ .env file configured correctly\n")
    return True


def test_credentials():
    """Test if Gmail credentials.json exists"""
    print("Testing Gmail credentials...")
    
    if not os.path.exists('credentials.json'):
        print("  ✗ credentials.json not found")
        print("  Download from Google Cloud Console")
        print("  See setup_guide.md for instructions")
        return False
    
    print("  ✓ credentials.json exists")
    print("✓ Gmail credentials found\n")
    return True


def main():
    print("=" * 60)
    print("Gmail Auto-Reply Setup Test")
    print("=" * 60)
    print()
    
    all_good = True
    
    # Test dependencies
    if not test_dependencies():
        all_good = False
    
    # Test .env file
    if not test_env_file():
        all_good = False
    
    # Test credentials
    if not test_credentials():
        all_good = False
    
    print("=" * 60)
    if all_good:
        print("✓ All checks passed! Ready to run.")
        print("=" * 60)
        print()
        print("Next step: python auto_reply.py")
    else:
        print("✗ Some checks failed. Please fix the issues above.")
        print("=" * 60)
        print()
        print("See setup_guide.md for help")
        sys.exit(1)


if __name__ == "__main__":
    main()

