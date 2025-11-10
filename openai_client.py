"""
OpenAI Client for generating email replies
"""
import os
from openai import OpenAI


class OpenAIClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY environment variable.")
        
        self.client = OpenAI(api_key=self.api_key)
        print("✓ OpenAI client initialized")
    
    def generate_reply(self, email_subject, email_body, sender):
        """
        Generate a professional email reply using OpenAI
        """
        try:
            prompt = f"""You are a professional email assistant. Generate a thoughtful, professional, and concise email reply.

Original Email Details:
From: {sender}
Subject: {email_subject}

Email Body:
{email_body}

Instructions:
1. Generate a professional and appropriate response
2. Be concise and clear
3. Match the tone of the original email
4. Address the main points from the original email
5. If the email seems like spam or doesn't require a response, respond with "NO_REPLY_NEEDED"

Generate only the email reply body (no subject line, no greetings like "Dear [Name]" unless appropriate based on original):
"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful email assistant that generates professional email replies."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            reply_text = response.choices[0].message.content.strip()
            
            # Check if OpenAI determined no reply is needed
            if "NO_REPLY_NEEDED" in reply_text:
                return None
            
            return reply_text
        
        except Exception as e:
            print(f"✗ Error generating reply with OpenAI: {str(e)}")
            return None
    
    def should_reply_to_email(self, email_subject, email_body):
        """
        Determine if an email should receive an automated reply
        """
        try:
            prompt = f"""Analyze this email and determine if it should receive an automated reply.

Subject: {email_subject}
Body: {email_body[:500]}

Respond with ONLY "YES" or "NO".

Reply "NO" if the email is:
- Spam
- Newsletter
- Automated notification
- Marketing email
- No-reply email

Reply "YES" if the email is:
- Personal message
- Business inquiry
- Request for information
- Legitimate question or discussion
"""
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an email classification assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=10
            )
            
            decision = response.choices[0].message.content.strip().upper()
            return "YES" in decision
        
        except Exception as e:
            print(f"Error checking if should reply: {str(e)}")
            # Default to not replying if there's an error
            return False

