#!/usr/bin/env python3
"""
Setup helper script for Gmail Auto-Reply
Helps create .env file interactively
"""
import os


def create_env_file():
    """Interactive setup to create .env file"""
    print("=" * 60)
    print("Gmail Auto-Reply Setup")
    print("=" * 60)
    print()
    
    # Check if .env already exists
    if os.path.exists('.env'):
        response = input(".env file already exists. Overwrite? (y/n): ").lower()
        if response != 'y':
            print("Setup cancelled.")
            return
    
    print("Let's set up your configuration.\n")
    
    # Get OpenAI API key
    print("1. OpenAI API Key")
    print("   Get your key from: https://platform.openai.com/api-keys")
    openai_key = input("   Enter your OpenAI API key: ").strip()
    
    if not openai_key:
        print("✗ OpenAI API key is required!")
        return
    
    # Get send emails preference
    print("\n2. Email Sending Mode")
    print("   'false' = Test mode (preview replies, don't send)")
    print("   'true' = Production mode (actually send replies)")
    send_emails = input("   Send emails? (false/true) [false]: ").strip().lower() or 'false'
    
    if send_emails not in ['true', 'false']:
        send_emails = 'false'
    
    # Get max emails
    print("\n3. Maximum Emails to Process")
    print("   How many emails to process per run")
    max_emails = input("   Max emails [5]: ").strip() or '5'
    
    try:
        int(max_emails)
    except ValueError:
        max_emails = '5'
    
    # Get unread only preference
    print("\n4. Unread Only")
    print("   Only process unread emails?")
    unread_only = input("   Unread only? (true/false) [true]: ").strip().lower() or 'true'
    
    if unread_only not in ['true', 'false']:
        unread_only = 'true'
    
    # Create .env content
    env_content = f"""# Gmail OpenAI Auto-Reply Configuration

# OpenAI API Key
OPENAI_API_KEY={openai_key}

# Email Sending Mode
# Set to 'true' to actually send emails
# Set to 'false' to test without sending
SEND_EMAILS={send_emails}

# Maximum number of emails to process per run
MAX_EMAILS={max_emails}

# Only process unread emails
UNREAD_ONLY={unread_only}
"""
    
    # Write .env file
    try:
        with open('.env', 'w') as f:
            f.write(env_content)
        
        print("\n" + "=" * 60)
        print("✓ Configuration saved to .env")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Download credentials.json from Google Cloud Console")
        print("2. Run: python auto_reply.py")
        print()
        print("See setup_guide.md for detailed instructions!")
        
    except Exception as e:
        print(f"\n✗ Error creating .env file: {str(e)}")


def main():
    create_env_file()


if __name__ == "__main__":
    main()

