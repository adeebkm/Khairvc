#!/usr/bin/env python3
"""
Test script to send WhatsApp message with new credentials
"""
import os
import sys
import requests
import json

# Set credentials
PHONE_NUMBER_ID = "937687349418916"
ACCESS_TOKEN = "EAAabU6CFZC3gBQIYnxNDYHC6BNBHnlVbwwlZCU313W2Gxc6PyN7HCN8UkS20W0dSHZBiVwdhLLLB2lPBLQxBPwv0bXiuZA7YItOziXjomOIbEirKJSuHTJ4fZBiCTtZBIm4Eh3cgEifMkiXZC9REZABHXrTON1ruJtRbc1ZCc4ZCM0ZCkQp3UQaVZCHWOAZCKv0ZCGRIemGZBHyOiLbJXEbkp3lUO5Fke8TEwSz6utRZCX3QQ4SUhmoOwY4riSbCwguuPE9y03F290kM5ZBcbYKSayTWCVxVZCpLZCUCwZDZD"
API_VERSION = "v23.0"
TEMPLATE_NAME = "hello_world"  # Try hello_world first to test connection
TO_NUMBER = "+15716638104"

def test_template_message():
    """Test sending a template message"""
    url = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages"
    
    headers = {
        'Authorization': f'Bearer {ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    # Test template message
    if TEMPLATE_NAME == "hello_world":
        # hello_world template has no parameters
        payload = {
            'messaging_product': 'whatsapp',
            'to': TO_NUMBER,
            'type': 'template',
            'template': {
                'name': TEMPLATE_NAME,
                'language': {
                    'code': 'en_US'
                }
            }
        }
    else:
        # deal_flow_alert template with 3 variables: subject, sender, details
        payload = {
            'messaging_product': 'whatsapp',
            'to': TO_NUMBER,
            'type': 'template',
            'template': {
                'name': TEMPLATE_NAME,
                'language': {
                    'code': 'en_US'
                },
                'components': [
                    {
                        'type': 'body',
                        'parameters': [
                            {'type': 'text', 'text': 'Test Deal Flow Alert'},  # subject
                            {'type': 'text', 'text': 'test@example.com'},      # sender
                            {'type': 'text', 'text': 'This is a test message from Khair VC platform'}  # details
                        ]
                    }
                ]
            }
        }
    
    print(f"📱 Testing WhatsApp message to {TO_NUMBER}")
    print(f"   Template: {TEMPLATE_NAME}")
    print(f"   API Version: {API_VERSION}")
    print(f"   Phone Number ID: {PHONE_NUMBER_ID}")
    print()
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        print("✅ Message sent successfully!")
        print(f"   Response: {json.dumps(result, indent=2)}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error sending message: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
                print(f"   Error details: {json.dumps(error_detail, indent=2)}")
            except:
                print(f"   Status code: {e.response.status_code}")
                print(f"   Response: {e.response.text}")
        return False

if __name__ == "__main__":
    success = test_template_message()
    sys.exit(0 if success else 1)

