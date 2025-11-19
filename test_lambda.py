#!/usr/bin/env python3
"""Quick test to verify AWS Lambda connection"""

import os
from lambda_client import LambdaClient

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

print("🧪 Testing Lambda Connection...\n")

# Check environment variables
print("📋 Environment Variables:")
print(f"   LAMBDA_FUNCTION_ARN: {os.getenv('LAMBDA_FUNCTION_ARN', 'NOT SET')[:50]}...")
print(f"   AWS_REGION: {os.getenv('AWS_REGION', 'NOT SET')}")
print(f"   AWS_ACCESS_KEY_ID: {os.getenv('AWS_ACCESS_KEY_ID', 'NOT SET')[:10]}...")
print()

try:
    # Initialize Lambda client
    print("⚡ Initializing Lambda client...")
    lambda_client = LambdaClient()
    print("✅ Lambda client initialized successfully!\n")
    
    # Test classification with a simple email
    print("📧 Testing email classification...")
    result = lambda_client.classify_email(
        subject="Investment Opportunity - AI Startup",
        body="Hi, we're building an AI company and looking for seed funding. We have a deck attached.",
        headers={},
        sender="founder@startup.com",
        links=["https://docsend.com/view/deck"],
        deterministic_category="DEAL_FLOW",
        has_pdf_attachment=True,
        thread_id="test-thread-123",
        user_id="test-user-1"
    )
    
    print(f"✅ Classification succeeded!")
    print(f"   Category: {result[0]}")
    print(f"   Confidence: {result[1]}")
    print("\n🎉 Lambda integration is working perfectly!")
    
except Exception as e:
    print(f"❌ Lambda test failed: {str(e)}")
    print("\n💡 This means the app will fall back to direct OpenAI calls.")
    import traceback
    traceback.print_exc()

