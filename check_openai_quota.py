#!/usr/bin/env python3
"""
Check OpenAI API quota and usage
"""
import os
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime

# Load environment variables
load_dotenv()

def check_openai_quota():
    """Check OpenAI API quota and usage"""
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment variables")
        print("   Make sure you have a .env file with OPENAI_API_KEY=your_key")
        return
    
    print("🔍 Checking OpenAI API quota and usage...")
    print(f"   API Key: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else ''}")
    print()
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Try a simple API call to check quota
        print("📊 Testing API access...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'OK' if you can read this."}
            ],
            max_tokens=10
        )
        
        print("✅ API is working! OpenAI quota is available.")
        print(f"   Response: {response.choices[0].message.content}")
        print()
        print("💡 Note: OpenAI doesn't provide a direct quota API endpoint.")
        print("   To check detailed usage and billing:")
        print("   1. Visit: https://platform.openai.com/usage")
        print("   2. Check your billing: https://platform.openai.com/account/billing")
        print("   3. View your limits: https://platform.openai.com/account/limits")
        
    except Exception as e:
        error_str = str(e)
        
        if '429' in error_str or 'rate_limit' in error_str.lower():
            print("⚠️  Rate limit error (429)")
            print("   You're making too many requests too quickly.")
            print("   This is NOT a quota issue - your account has credits, but you're hitting rate limits.")
            print()
            print("   Solutions:")
            print("   1. Wait 1-2 minutes and try again")
            print("   2. Reduce the number of emails being classified at once")
            print("   3. Check your rate limits: https://platform.openai.com/account/limits")
            print("   4. Consider upgrading to a higher tier for higher rate limits")
            
        elif 'quota' in error_str.lower() or 'insufficient_quota' in error_str.lower():
            print("❌ Quota exceeded!")
            print("   Your OpenAI account has exceeded its quota.")
            print()
            print("   Possible reasons:")
            print("   - Free tier limit reached")
            print("   - Billing limit reached")
            print("   - Payment method issue")
            print()
            print("   To fix:")
            print("   1. Check usage: https://platform.openai.com/usage")
            print("   2. Check billing: https://platform.openai.com/account/billing")
            print("   3. Add payment method if needed")
            print("   4. Upgrade your plan if on free tier")
            
        elif '401' in error_str or 'unauthorized' in error_str.lower():
            print("❌ Authentication error (401)")
            print("   Your API key is invalid or expired.")
            print("   Check your .env file and regenerate your API key at:")
            print("   https://platform.openai.com/api-keys")
            
        else:
            print(f"❌ Error: {error_str}")
            print()
            print("   Check your OpenAI account status at:")
            print("   https://platform.openai.com/account")

if __name__ == "__main__":
    check_openai_quota()

