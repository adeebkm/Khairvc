"""
Configuration settings for Gmail Auto-Reply
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Gmail Configuration
SEND_EMAILS = os.getenv('SEND_EMAILS', 'false').lower() == 'true'
MAX_EMAILS = int(os.getenv('MAX_EMAILS', '5'))
UNREAD_ONLY = os.getenv('UNREAD_ONLY', 'true').lower() == 'true'

# Validation
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not set in .env file")

