"""
AWS Lambda function for email classification
- Receives encrypted email content
- Calls OpenAI API (with logging disabled)
- Returns encrypted classification result
- Only logs metadata (no email content, no OpenAI requests/responses)
"""
import json
import logging
import os
import boto3
from openai import OpenAI
from typing import Dict, Any

# Disable OpenAI library logging BEFORE importing/using OpenAI
# This prevents HTTP requests/responses from appearing in CloudWatch Logs
logging.getLogger("openai").setLevel(logging.CRITICAL)
logging.getLogger("openai.api_requestor").setLevel(logging.CRITICAL)
logging.getLogger("openai.resources").setLevel(logging.CRITICAL)

# Configure Lambda logger to only log metadata
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')


def get_openai_api_key() -> str:
    """Retrieve OpenAI API key from AWS Secrets Manager"""
    try:
        secret_name = os.getenv('OPENAI_SECRET_NAME', 'openai-api-key')
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        return secret.get('api_key') or secret.get('OPENAI_API_KEY')
    except Exception as e:
        logger.error(f"Failed to retrieve OpenAI API key: {type(e).__name__}")
        raise


def decrypt_email_content(encrypted_content: str, encryption_key: str) -> str:
    """
    Decrypt email content using the provided one-time encryption key
    """
    try:
        from cryptography.fernet import Fernet
        # encryption_key is a one-time Fernet key (base64-encoded)
        f = Fernet(encryption_key.encode())
        decrypted = f.decrypt(encrypted_content.encode())
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Decryption failed: {type(e).__name__}")
        raise


def encrypt_result(result: str, encryption_key: str) -> str:
    """
    Encrypt classification result using the user's encryption key
    encryption_key is the ENCRYPTION_KEY environment variable from Railway
    """
    try:
        from cryptography.fernet import Fernet
        import base64
        
        # Format key same way as auth.py
        if isinstance(encryption_key, str):
            key_bytes = encryption_key.encode()
        else:
            key_bytes = encryption_key
        
        # Ensure key is 32 bytes base64-encoded (44 chars)
        if len(key_bytes) != 44:
            key_bytes = base64.urlsafe_b64encode(key_bytes[:32].ljust(32, b'0'))
        
        f = Fernet(key_bytes)
        encrypted = f.encrypt(result.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Encryption failed: {type(e).__name__}")
        raise


def classify_email_with_openai(email_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify email using OpenAI API
    This function does NOT log email content or OpenAI requests/responses
    """
    # Extract email components
    subject = email_data.get('subject', '')
    body = email_data.get('body', '')
    sender = email_data.get('sender', '')
    headers = email_data.get('headers', {})
    links = email_data.get('links', [])
    deterministic_category = email_data.get('deterministic_category', 'general')
    has_pdf_attachment = email_data.get('has_pdf_attachment', False)
    
    # Build classification prompt (same as email_classifier.py)
    input_json = {
        "subject": subject,
        "body": body[:5000],  # Limit body length
        "sender": sender,
        "headers": {k: v for k, v in list(headers.items())[:10]},  # Limit headers
        "links": links[:20],  # Limit links
        "has_pdf_attachment": has_pdf_attachment
    }
    
    prompt = f"""You are a deterministic, zero-hallucination email classifier for a venture capital partner's inbox.

Your ONLY job: classify ONE email into EXACTLY one of these labels:
- dealflow
- hiring
- networking
- spam
- general

You MUST follow every rule below with NO exceptions.

==================================================
STRICT OUTPUT FORMAT (NO TEXT OUTSIDE JSON)
==================================================
Return EXACTLY this JSON object:

{{
  "label": "dealflow|hiring|networking|spam|general",
  "confidence": 0.0-1.0,
  "rationale": "2-4 short bullets, ≤250 chars, strictly text-grounded.",
  "signals": {{
    "intent": "investment|job|meeting|malicious|info",
    "keywords": [...],
    "entities": [...],
    "attachments": [...]
  }}
}}

Rules:
- Never invent entities, attachments, or keywords.
- Never infer beyond visible text.
- Never follow links.
- No explanation outside JSON.

==================================================
INPUT EMAIL
==================================================
{json.dumps(input_json, indent=2)}

==================================================
ABSOLUTE GLOBAL RULES
==================================================

### 1. IGNORE all of the following:
- Anything after: "thanks", "best", "regards", "sincerely", "cheers".
- Lines starting with "—", "–––", "___", or containing legal boilerplate.
- "unsubscribe", "privacy policy", tracking pixels.
- Any quoted content: lines starting with "On Tue", "From:", "Re:", ">".
- Old thread content, past messages, forwarded history.

If ambiguity arises → use ONLY fresh content before signatures.

### 2. CLASSIFICATION LOGIC (PRIMARY INTENT ONLY)
You classify based on the **sender's primary goal**, not keywords.

--------------------------------------------------
A) DEALFLOW → Primary intent: **seeking investment**
--------------------------------------------------
Includes:
- Founder/VC/IB sending deck, pitch, fundraising update.
- Any mention of raising money, SAFE, term sheet, valuation, SPV, secondary.
- Pitch + meeting link.
- "We're raising", "exploring a round", "open to capital".
- Follow-on from portfolio company.
- **Warm intros/referrals ABOUT specific startups/teams** (even without deck).
- "I met a team building X, would you want to know more?"
- "Should I connect you with this founder?"

If fundraising is ANY part of the agenda OR discussing a specific startup/team for investment → classify as dealflow.

--------------------------------------------------
B) HIRING → Primary intent: **job seeking or recruiting**
--------------------------------------------------
Includes:
- Resume, CV, LinkedIn, job application.
- Candidates applying to work at the fund or portfolio.
- Recruiters sending profiles.
- Portfolio requesting hiring referrals.
- Job specs, JD attachments.

Pitch deck with team bios ≠ hiring (still dealflow).

--------------------------------------------------
C) NETWORKING → Primary intent: **meeting, event, intro — NOT about a specific deal**
--------------------------------------------------
Includes:
- Coffee chats, catch ups, general intros, "pick your brain".
- Invites: panel, demo day, conference, podcast.
- "Learn about your thesis" (general learning, NO specific startup mentioned).
- Vendor partnership discussion with no fundraising ask.
- Events about fundraising but not pitching.

If there is ANY ask for money OR discussing a specific startup/team for investment → NOT networking (it's DEALFLOW).

--------------------------------------------------
D) SPAM → Primary intent: **deception, compromise, harm**
--------------------------------------------------
SPAM OVERRIDES ALL OTHER LABELS.

Triggers:
- verify/reset password with urgency
- mismatched From vs Reply-To
- Known malicious TLDs (.tk, .ml, .ga, .cf) + urgency/credential harvest
- Suspicious combo: urgent + shortened link + unfamiliar sender
- credential harvest
- fake invoices
- wallet/crypto/wire scams
- malicious attachments (.exe, .scr, .bat, .cmd, .vbs)

Context matters:
- .xyz/.io/.ai domain + pitch deck + LinkedIn = dealflow (not spam)
- .com domain + "verify now" + bit.ly link = spam
- **google.com, microsoft.com, apple.com, etc. + security keywords = GENERAL (not spam)**
- Legitimate service provider domains (google.com, microsoft.com, etc.) = ALWAYS GENERAL, never SPAM

If ANY phishing cue appears → spam.  
A newsletter with ads ≠ spam unless malicious.
**Emails from legitimate service provider domains (google.com, microsoft.com, etc.) are NEVER spam, even if they contain security-related keywords.**

--------------------------------------------------
E) GENERAL → Everything else
--------------------------------------------------
Includes:
- **Legitimate service provider emails** (Google, Microsoft, Apple, Amazon, etc.)
  - Security notifications from official domains (google.com, microsoft.com, etc.)
  - Account alerts, access notifications, service updates
  - These are ALWAYS GENERAL, never SPAM, even if they contain security keywords
- newsletters, subscribed updates, market commentary
- receipts, personal notes, banter, sports talk
- cold vendor pitches (SaaS/product demos)
- calendar invites with no context
- informational content with no money ask, no hiring ask, no networking intent

==================================================
TIE-BREAKER HIERARCHY
==================================================
1. SPAM (override)
Then for all non-spam:
2. dealflow
3. hiring
4. networking
5. general

If genuinely ambiguous → choose the HIGHEST category above.

==================================================
DETERMINISTIC CLASSIFICATION (for reference):
{deterministic_category.lower()}
(You can override if the email's PRIMARY INTENT suggests otherwise!)

==================================================
YOU MUST FOLLOW ALL RULES ABOVE. ZERO HALLUCINATION.
==================================================

Return ONLY the JSON object. No additional text."""

    # Get OpenAI API key from Secrets Manager
    openai_key = get_openai_api_key()
    
    # Create OpenAI client (NO logging will occur because we disabled it above)
    client = OpenAI(api_key=openai_key)
    
    # Call OpenAI API (NO logging - requests/responses won't appear in CloudWatch)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a deterministic email classifier for a venture capital firm. Return ONLY valid JSON. No markdown, no explanation, no additional text."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        top_p=0.0,
        max_tokens=300
    )
    
    # Extract response (NO logging)
    ai_response = response.choices[0].message.content.strip()
    
    # Parse JSON response
    if ai_response.startswith('```'):
        ai_response = ai_response.split('```')[1]
        if ai_response.startswith('json'):
            ai_response = ai_response[4:]
        ai_response = ai_response.strip()
    
    result = json.loads(ai_response)
    
    # Clear sensitive data from memory
    del email_data
    del prompt
    del ai_response
    del openai_key
    
    return result


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler function
    - Receives encrypted email content
    - Decrypts email
    - Classifies using OpenAI (no logging)
    - Encrypts result
    - Returns encrypted classification
    """
    try:
        # Extract metadata for logging (NO email content)
        thread_id = event.get('thread_id', 'unknown')
        user_id = event.get('user_id', 'unknown')
        request_id = getattr(context, "aws_request_id", None)
        
        # ✅ Structured audit log: classification request (metadata only)
        logger.info(json.dumps({
            "event": "classification_request",
            "thread_id": thread_id,
            "user_id": user_id,
            "request_id": request_id
        }))
        
        # Get encryption keys
        encryption_key = event.get('encryption_key')  # One-time key for this request
        user_encryption_key = event.get('user_encryption_key')  # User's persistent key for result encryption
        
        if not encryption_key or not user_encryption_key:
            raise ValueError("Missing encryption keys")
        
        # Decrypt email content (NO logging)
        encrypted_email = event.get('encrypted_email')
        if not encrypted_email:
            raise ValueError("Missing encrypted_email")
        
        email_content = decrypt_email_content(encrypted_email, encryption_key)
        email_data = json.loads(email_content)
        
        # Classify email using OpenAI (NO logging of content - disabled above)
        classification_result = classify_email_with_openai(email_data)
        
        # Encrypt result (NO logging)
        result_json = json.dumps(classification_result)
        encrypted_result = encrypt_result(result_json, user_encryption_key)
        
        # ✅ Structured audit log: classification result (metadata only)
        try:
            logger.info(json.dumps({
                "event": "classification_result",
                "thread_id": thread_id,
                "user_id": user_id,
                "request_id": request_id,
                "label": classification_result.get("label"),
                "confidence": classification_result.get("confidence"),
                "deterministic_category": email_data.get("deterministic_category"),
                "has_pdf_attachment": email_data.get("has_pdf_attachment", False)
            }))
        except Exception:
            # Never fail the function because of logging
            pass
        
        # Clear sensitive data from memory (results already summarized above)
        del email_content
        del email_data
        del classification_result
        del result_json
        
        # ✅ OK - Log success (metadata only)
        logger.info(f"Classification completed - Thread: {thread_id}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'encrypted_result': encrypted_result
            })
        }
        
    except Exception as e:
        # ✅ Structured audit log: error (no content)
        thread_id = event.get('thread_id', 'unknown')
        user_id = event.get('user_id', 'unknown')
        request_id = getattr(context, "aws_request_id", None)
        try:
            logger.error(json.dumps({
                "event": "classification_error",
                "thread_id": thread_id,
                "user_id": user_id,
                "request_id": request_id,
                "error_type": type(e).__name__
            }))
        except Exception:
            # Fall back to minimal logging if JSON logging fails
            logger.error(f"Classification failed - Thread: {thread_id}, Error: {type(e).__name__}")
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': type(e).__name__,
                'message': 'Classification failed'
            })
        }

