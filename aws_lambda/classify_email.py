"""
AWS Lambda function for email classification
- Receives encrypted email content
- Calls Moonshot API (OpenAI-compatible, with logging disabled)
- Returns encrypted classification result
- Only logs metadata (no email content, no API requests/responses)
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
    """Retrieve API key from AWS Secrets Manager (supports OpenAI or Moonshot)"""
    try:
        secret_name = os.getenv('OPENAI_SECRET_NAME', 'openai-api-key')
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        return secret.get('api_key') or secret.get('OPENAI_API_KEY') or secret.get('MOONSHOT_API_KEY')
    except Exception as e:
        logger.error(f"Failed to retrieve API key: {type(e).__name__}")
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
    
    # Build condensed classification prompt (85-90% token reduction)
    prompt = f"""You are a zero-hallucination email classifier for a VC partner.

Classify into ONE of: dealflow, hiring, networking, spam, general.

Output ONLY this JSON:
{{"label":"...","confidence":0.0-1.0,"rationale":"...","signals":{{"intent":"...","keywords":[...],"entities":[...],"attachments":[...]}}}}

Rules:
- Ignore: sigs, quotes, legal, unsub, old threads.
- Spam overrides all. Triggers: phishing, fake invoices, crypto scams, mismatched From/Reply-To, malicious TLDs (.tk/.ml/.ga/.cf) + urgency.
- **Legitimate domains (google.com, microsoft.com, apple.com, etc.) = ALWAYS general, never spam.**
- Dealflow: fundraising, deck, SAFE, valuation, **warm intro about SPECIFIC startup/team**.
- Hiring: resume, CV, job app, recruiter, JD.
- Networking: coffee, intro, event, podcast, **no money ask AND no specific startup mentioned**.
- General: newsletters, receipts, vendor demos, Google/Microsoft security alerts.
- **Short body + deck/resume attachment = classify by attachment type.**

Tie-breaker: spam > dealflow > hiring > networking > general.

Examples:
1. "Intro: Founder raising pre-seed, deck attached" → dealflow
2. "Analyst role — resume attached" → hiring
3. "Coffee next week?" → networking
4. "URGENT: verify email" + unknown sender → spam
5. "Gmail security alert" → general

Input email:
{json.dumps(input_json, indent=2)}

Deterministic classification (reference): {deterministic_category.lower()}
(Override if email's PRIMARY INTENT suggests otherwise)

Return ONLY the JSON object. No additional text."""

    # Get API key from Secrets Manager
    api_key = get_openai_api_key()
    
    # Create OpenAI-compatible client for Moonshot API (NO logging will occur because we disabled it above)
    # Moonshot uses OpenAI-compatible API, so we can use the OpenAI client with custom base_url
    # Set timeout at client level (110 seconds to allow for Lambda timeout of 120s)
    import httpx
    client = OpenAI(
        base_url="https://api.moonshot.ai/v1",
        api_key=api_key,
        timeout=httpx.Timeout(110.0, connect=10.0)  # 110s total, 10s connect (Lambda timeout is 120s)
    )
    
    # Call Moonshot API with retry logic for rate limits
    # Using kimi-k2-turbo-preview model (faster than kimi-k2-thinking)
    import time
    max_retries = 3
    retry_delay = 2  # Start with 2 seconds
    
    response = None
    last_error = None
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="kimi-k2-turbo-preview",  # Faster model for better performance
                messages=[
                    {"role": "system", "content": "You are a deterministic email classifier for a venture capital firm. Return ONLY valid JSON. No markdown, no explanation, no additional text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                top_p=0.0,
                max_tokens=1000  # Increased from 300 to prevent finish_reason=length (response cutoff)
            )
            # Success - break out of retry loop
            break
        except Exception as api_error:
            last_error = api_error
            error_type = type(api_error).__name__
            error_msg = str(api_error)
            
            # Check if it's a rate limit error
            is_rate_limit = (
                error_type == 'RateLimitError' or 
                '429' in error_msg or 
                'overloaded' in error_msg.lower() or
                'rate limit' in error_msg.lower()
            )
            
            if is_rate_limit and attempt < max_retries - 1:
                # Exponential backoff for rate limits
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries}), waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                continue
            else:
                # Not a rate limit or out of retries - log and raise
                logger.error(f"API call failed: {error_type}: {error_msg[:200]}")
                raise
    
    # If we exhausted retries, raise the last error
    if response is None and last_error:
        raise last_error
    
    # Extract response with detailed error handling
    result = None  # Initialize EARLY to avoid UnboundLocalError
    
    try:
        if not response.choices or len(response.choices) == 0:
            raise ValueError("No choices in API response")
        
        message_content = response.choices[0].message.content
        if not message_content:
            # Log the full response structure for debugging
            finish_reason = response.choices[0].finish_reason if response.choices else 'N/A'
            logger.error(f"Empty message content. Response structure: choices={len(response.choices) if response.choices else 0}, finish_reason={finish_reason}")
            raise ValueError("Empty message content in API response - model may have been cut off or failed")
        
        ai_response = message_content.strip()
        
        # If response is still empty after strip, raise error
        if not ai_response:
            raise ValueError("Empty response after stripping whitespace")
        
        # Parse JSON response
        if ai_response.startswith('```'):
            ai_response = ai_response.split('```')[1]
            if ai_response.startswith('json'):
                ai_response = ai_response[4:]
            ai_response = ai_response.strip()
        
        # Try to parse JSON with better error handling
        try:
            result = json.loads(ai_response)
        except json.JSONDecodeError as e:
            # Log the problematic response (first 1000 chars for debugging)
            response_preview = ai_response[:1000] if ai_response else "(empty response)"
            logger.error(f"JSON decode error. Response length: {len(ai_response) if ai_response else 0}, Preview: {response_preview}")
            # Try to extract JSON from the response if it's embedded in text
            import re
            # More flexible regex to find JSON object
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*"label"[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', ai_response, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group(0))
                    logger.info("Successfully extracted JSON from response")
                except Exception as extract_error:
                    logger.error(f"Failed to parse extracted JSON: {str(extract_error)}")
                    raise ValueError(f"Failed to parse OpenAI response as JSON: {str(e)}")
            else:
                raise ValueError(f"Failed to parse OpenAI response as JSON: {str(e)}. Response preview: {response_preview[:200]}")
        
        # Verify result was assigned
        if result is None:
            raise ValueError("Failed to parse OpenAI response - result is None")
        
        # Store result in a local variable before cleanup to avoid UnboundLocalError
        final_result = result
            
    except Exception as parse_error:
        # Log the full error with traceback for debugging
        import traceback
        error_trace = traceback.format_exc()
        error_type = type(parse_error).__name__
        error_msg = str(parse_error)
        logger.error(f"Error parsing API response: {error_type}: {error_msg}")
        logger.error(f"Traceback: {error_trace}")
        # Check if result exists in this scope
        try:
            logger.error(f"Result variable state: result={result}, type={type(result)}")
        except NameError:
            logger.error("Result variable does not exist in this scope (UnboundLocalError)")
        # Re-raise the error
        raise
    
    # Clear sensitive data from memory (safely)
    try:
        del email_data
    except NameError:
        pass
    try:
        del prompt
    except NameError:
        pass
    try:
        del ai_response
    except NameError:
        pass
    try:
        del openai_key
    except NameError:
        pass
    
    # Return the stored result
    return final_result


def generate_email_with_kimi(email_data: Dict[str, Any]) -> str:
    """
    Generate scheduled email using Kimi AI
    This function does NOT log email content or API requests/responses
    """
    # Extract email components
    subject = email_data.get('subject', '')
    body = email_data.get('body', '')
    sender = email_data.get('sender', '')
    founder_name = email_data.get('founder_name', '')
    
    # Build email generation prompt
    prompt = f"""Generate a professional follow-up email for a deal flow opportunity.

Original Email:
Subject: {subject}
From: {sender}
Founder: {founder_name}
Body: {body[:1000]}...

Generate a warm, professional email that:
- Acknowledges receiving their email
- Shows genuine interest in learning more about their startup
- Asks relevant questions about their venture (team, traction, market, etc.)
- Maintains a friendly but professional tone
- Is concise but engaging (2-3 paragraphs)
- Ends with a clear call to action

Return ONLY the email body in HTML format. Use <p> tags for paragraphs. Do not include subject line or signature."""

    # Get API key from Secrets Manager
    api_key = get_openai_api_key()
    
    # Create OpenAI-compatible client for Moonshot API
    import httpx
    client = OpenAI(
        base_url="https://api.moonshot.ai/v1",
        api_key=api_key,
        timeout=httpx.Timeout(110.0, connect=10.0)
    )
    
    # Call Kimi API with retry logic
    import time
    max_retries = 3
    retry_delay = 2
    
    response = None
    last_error = None
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="kimi-k2-turbo-preview",
                messages=[
                    {"role": "system", "content": "You are a professional email writer for a venture capital firm. Return ONLY the email body in HTML format. No markdown, no explanation, no additional text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            # Success - break out of retry loop
            break
        except Exception as api_error:
            last_error = api_error
            error_type = type(api_error).__name__
            error_msg = str(api_error)
            
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Kimi API error (attempt {attempt + 1}/{max_retries}): {error_type}")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"Kimi API failed after {max_retries} attempts: {error_type}")
                raise Exception(f"Kimi API error: {error_msg}")
    
    if not response:
        raise Exception(f"Failed to generate email: {last_error}")
    
    # Extract generated email body
    generated_email = response.choices[0].message.content.strip()
    
    # Ensure it's HTML format (wrap in <p> tags if plain text)
    if not generated_email.startswith('<'):
        # Convert plain text to HTML
        paragraphs = generated_email.split('\n\n')
        generated_email = ''.join([f'<p>{p.strip()}</p>' for p in paragraphs if p.strip()])
    
    return generated_email


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler function
    - Receives encrypted email content
    - Supports two actions: 'classify' (default) and 'generate_email'
    - Decrypts email
    - Processes using OpenAI/Kimi (no logging)
    - Encrypts result
    - Returns encrypted result
    """
    try:
        # Extract metadata for logging (NO email content)
        thread_id = event.get('thread_id', 'unknown')
        user_id = event.get('user_id', 'unknown')
        request_id = getattr(context, "aws_request_id", None)
        action = event.get('action', 'classify')  # Default to classify for backward compatibility
        
        # ✅ Structured audit log: request (metadata only)
        logger.info(json.dumps({
            "event": f"{action}_request",
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
        
        # Handle different actions
        if action == 'generate_email':
            # Generate email using Kimi AI (NO logging of content - disabled above)
            generated_email = generate_email_with_kimi(email_data)
            
            # Encrypt result (NO logging)
            encrypted_result = encrypt_result(generated_email, user_encryption_key)
            
            # ✅ Structured audit log: email generation result (metadata only)
            try:
                logger.info(json.dumps({
                    "event": "email_generated",
                    "thread_id": thread_id,
                    "user_id": user_id,
                    "request_id": request_id
                }))
            except Exception:
                # Never fail the function because of logging
                pass
            
            # Clear sensitive data from memory
            del email_content
            del email_data
            del generated_email
            
            # ✅ OK - Log success (metadata only)
            logger.info(f"Email generation completed - Thread: {thread_id}")
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'success': True,
                    'encrypted_email_body': encrypted_result
                })
            }
        else:
            # Default: Classify email using OpenAI (NO logging of content - disabled above)
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

