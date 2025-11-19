"""
Gmail Client for reading and sending emails - Multi-user version
"""
import os
import json
import base64
import re
import io
from email.mime.text import MIMEText
from email.header import decode_header
import html
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# PDF and document parsing
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("Note: PyPDF2 not installed. PDF attachments won't be parsed.")

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("Note: python-docx not installed. Word documents won't be parsed.")


# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.settings.basic'  # For fetching signatures
]


class GmailClient:
    def __init__(self, token_json=None):
        """
        Initialize Gmail client with token data
        
        Args:
            token_json: JSON string of token data (from database)
                       If None, will try to authenticate via OAuth flow
        """
        self.service = None
        if token_json:
            self.authenticate_from_token(token_json)
        else:
            self.authenticate()
    
    def authenticate_from_token(self, token_json):
        """Authenticate using stored token JSON"""
        try:
            token_data = json.loads(token_json)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            
            # Refresh if expired
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            
            self.service = build('gmail', 'v1', credentials=creds)
            return True
        except Exception as e:
            print(f"Error authenticating from token: {str(e)}")
            return False
    
    def authenticate(self):
        """Authenticate with Gmail API via OAuth flow (for first-time setup)"""
        if not os.path.exists('credentials.json'):
            raise FileNotFoundError(
                "credentials.json not found. Please download it from Google Cloud Console."
            )
        
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        
        self.service = build('gmail', 'v1', credentials=creds)
        return creds.to_json()  # Return token JSON for storage
    
    def get_unread_emails(self, max_results=10, start_history_id=None):
        """Get unread emails from inbox"""
        return self.get_emails(max_results=max_results, unread_only=True, start_history_id=start_history_id)
    
    def get_starred_emails(self, max_results=20):
        """
        Get starred emails from Gmail
        
        Args:
            max_results: Max emails to fetch
        
        Returns:
            list: List of starred email dictionaries
        """
        if not self.service:
            return []
        
        try:
            query = 'is:starred'
            print(f"⭐ Fetching up to {max_results} starred emails...")
            
            # Get list of message IDs
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            if not messages:
                print("⭐ No starred emails found")
                return []
            
            print(f"⭐ Found {len(messages)} starred emails, fetching details...")
            
            # Batch fetch email details
            starred_emails = []
            for msg in messages:
                try:
                    email_data = self.get_email_details(msg['id'])
                    if email_data:
                        starred_emails.append(email_data)
                except Exception as e:
                    print(f"⚠️  Error fetching starred email {msg['id']}: {str(e)}")
                    continue
            
            print(f"✅ Fetched {len(starred_emails)} starred emails")
            return starred_emails
            
        except Exception as e:
            print(f"❌ Error fetching starred emails: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_sent_emails(self, max_results=20):
        """
        Get sent emails from Gmail
        
        Args:
            max_results: Max emails to fetch
        
        Returns:
            list: List of sent email dictionaries
        """
        if not self.service:
            return []
        
        try:
            query = 'in:sent'
            print(f"📤 Fetching up to {max_results} sent emails...")
            
            # Get list of message IDs
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            if not messages:
                print("📤 No sent emails found")
                return []
            
            print(f"📤 Found {len(messages)} sent emails, fetching details...")
            
            # Batch fetch email details
            sent_emails = []
            for msg in messages:
                try:
                    email_data = self.get_email_details(msg['id'])
                    if email_data:
                        sent_emails.append(email_data)
                except Exception as e:
                    print(f"⚠️  Error fetching sent email {msg['id']}: {str(e)}")
                    continue
            
            print(f"✅ Fetched {len(sent_emails)} sent emails")
            return sent_emails
            
        except Exception as e:
            print(f"❌ Error fetching sent emails: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_drafts(self, max_results=20):
        """
        Get draft emails from Gmail
        
        Args:
            max_results: Max drafts to fetch
        
        Returns:
            list: List of draft email dictionaries
        """
        if not self.service:
            return []
        
        try:
            query = 'in:drafts'
            print(f"📝 Fetching up to {max_results} drafts...")
            
            # Get list of message IDs
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            if not messages:
                print("📝 No drafts found")
                return []
            
            print(f"📝 Found {len(messages)} drafts, fetching details...")
            
            # Batch fetch email details
            drafts = []
            for msg in messages:
                try:
                    email_data = self.get_email_details(msg['id'])
                    if email_data:
                        drafts.append(email_data)
                except Exception as e:
                    print(f"⚠️  Error fetching draft {msg['id']}: {str(e)}")
                    continue
            
            print(f"✅ Fetched {len(drafts)} drafts")
            return drafts
            
        except Exception as e:
            print(f"❌ Error fetching drafts: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_emails(self, max_results=10, unread_only=False, start_history_id=None):
        """
        Get emails from inbox using batch requests (optimized to reduce API calls).
        Supports incremental sync via Gmail History API.
        
        Args:
            max_results: Max emails to fetch in full sync
            unread_only: Only fetch unread emails
            start_history_id: If provided, use incremental sync (fetch only changes since this ID)
        
        Returns:
            tuple: (emails_list, new_history_id)
        """
        if not self.service:
            return [], None
        
        try:
            # INCREMENTAL SYNC: Use History API if we have a history_id
            if start_history_id:
                print(f"🔄 Using incremental sync from history ID: {start_history_id}")
                return self._get_emails_incremental(start_history_id, unread_only)
            
            # FULL SYNC: Use messages.list() for first time or full refresh
            query = 'in:inbox'
            if unread_only:
                query = 'is:unread in:inbox'
            
            print(f"📧 Full sync: Fetching up to {max_results} emails...")
            
            # First API call: Get list of message IDs
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            history_id = results.get('historyId')  # Store this for next incremental sync!
            
            if not messages:
                return [], history_id
            
            # Use batch request to fetch all message details
            # Process in smaller chunks to avoid Gmail API rate limits
            from googleapiclient.http import BatchHttpRequest
            import time
            
            emails = []
            errors = []
            latest_history_id = None
            
            # Gmail API allows max 100 requests per batch, but concurrent requests are limited
            # Process in chunks of 10 to avoid "Too many concurrent requests" errors
            BATCH_SIZE = 10
            DELAY_BETWEEN_BATCHES = 0.5  # 500ms delay between batches
            
            def callback(request_id, response, exception):
                nonlocal latest_history_id
                if exception:
                    error_str = str(exception)
                    # Don't log every rate limit error (too noisy)
                    if '429' not in error_str and 'rateLimitExceeded' not in error_str:
                        print(f"⚠️  Error in batch request: {exception}")
                    errors.append(exception)
                else:
                    # Extract historyId from message for incremental sync
                    if not latest_history_id and 'historyId' in response:
                        latest_history_id = response['historyId']
                    
                    email_data = self._extract_message_data(response)
                    if email_data:
                        emails.append(email_data)
            
            # Process messages in smaller batches to avoid rate limits
            total_messages = len(messages)
            for i in range(0, total_messages, BATCH_SIZE):
                batch_chunk = messages[i:i + BATCH_SIZE]
                
                # Create batch request for this chunk
                batch = self.service.new_batch_http_request(callback=callback)
                
                for message in batch_chunk:
                    batch.add(self.service.users().messages().get(
                        userId='me',
                        id=message['id'],
                        format='full'
                    ))
                
                # Execute this batch
                try:
                    batch.execute()
                except Exception as batch_error:
                    error_str = str(batch_error)
                    if '429' in error_str or 'rateLimitExceeded' in error_str:
                        print(f"⚠️  Rate limit hit on batch {i//BATCH_SIZE + 1}. Waiting 2 seconds...")
                        time.sleep(2)  # Wait longer on rate limit
                        # Retry this batch once
                        try:
                            batch.execute()
                        except Exception as retry_error:
                            print(f"⚠️  Retry failed: {retry_error}")
                    else:
                        print(f"⚠️  Batch error: {batch_error}")
                
                # Add delay between batches (except for the last one)
                if i + BATCH_SIZE < total_messages:
                    time.sleep(DELAY_BETWEEN_BATCHES)
            
            # Use historyId from the fetched messages (for incremental sync next time)
            if latest_history_id:
                history_id = latest_history_id
            
            # Calculate actual API calls: 1 for list + batches (each batch = 1 API call)
            num_batches = (len(messages) + BATCH_SIZE - 1) // BATCH_SIZE
            total_api_calls = 1 + num_batches  # 1 for list, rest for batches
            print(f"✅ Full sync: Fetched {len(emails)} emails with {total_api_calls} API calls. historyId: {history_id}")
            if errors:
                print(f"⚠️  {len(errors)} errors encountered (some emails may be missing)")
            
            return emails, history_id
        
        except Exception as e:
            error_str = str(e)
            # Re-raise rate limit errors so they can be handled properly by app.py
            if '429' in error_str or 'rateLimitExceeded' in error_str or 'rate limit' in error_str.lower():
                print(f"⚠️ Gmail API rate limit exceeded: {error_str}")
                raise  # Re-raise to let app.py handle it with proper error response
            else:
                print(f"Error fetching emails: {error_str}")
                return [], None
    
    def _get_emails_incremental(self, start_history_id, unread_only=False):
        """
        Fetch only changes since start_history_id using Gmail History API.
        This is MUCH faster and uses far fewer API calls than full sync.
        """
        try:
            # Single API call to get all changes since last sync
            history_response = self.service.users().history().list(
                userId='me',
                startHistoryId=start_history_id,
                historyTypes=['messageAdded'],  # Only get new messages
                labelId='INBOX'  # Only inbox messages
            ).execute()
            
            changes = history_response.get('history', [])
            new_history_id = history_response.get('historyId')
            
            if not changes:
                print(f"✅ Incremental sync: No new emails since last sync. historyId: {new_history_id}")
                return [], new_history_id
            
            # Extract message IDs from history changes
            message_ids = set()
            for change in changes:
                if 'messagesAdded' in change:
                    for msg_added in change['messagesAdded']:
                        message = msg_added.get('message', {})
                        # Filter by unread if requested
                        if unread_only:
                            label_ids = message.get('labelIds', [])
                            if 'UNREAD' in label_ids and 'INBOX' in label_ids:
                                message_ids.add(message['id'])
                        else:
                            if 'INBOX' in message.get('labelIds', []):
                                message_ids.add(message['id'])
            
            if not message_ids:
                print(f"✅ Incremental sync: {len(changes)} changes but no new inbox messages. historyId: {new_history_id}")
                return [], new_history_id
            
            print(f"🔄 Incremental sync: Found {len(message_ids)} new messages. Fetching details...")
            
            # Batch fetch the new messages (in chunks to avoid rate limits)
            from googleapiclient.http import BatchHttpRequest
            import time
            
            emails = []
            errors = []
            
            # Process in chunks of 10 to avoid "Too many concurrent requests" errors
            BATCH_SIZE = 10
            DELAY_BETWEEN_BATCHES = 0.5  # 500ms delay between batches
            
            def callback(request_id, response, exception):
                if exception:
                    error_str = str(exception)
                    # Don't log every rate limit error (too noisy)
                    if '429' not in error_str and 'rateLimitExceeded' not in error_str:
                        print(f"⚠️  Error in batch request: {exception}")
                    errors.append(exception)
                else:
                    email_data = self._extract_message_data(response)
                    if email_data:
                        emails.append(email_data)
            
            # Process message IDs in smaller batches
            message_ids_list = list(message_ids)
            total_messages = len(message_ids_list)
            
            for i in range(0, total_messages, BATCH_SIZE):
                batch_chunk = message_ids_list[i:i + BATCH_SIZE]
                
                batch = self.service.new_batch_http_request(callback=callback)
                
                for message_id in batch_chunk:
                    batch.add(self.service.users().messages().get(
                        userId='me',
                        id=message_id,
                        format='full'
                    ))
                
                # Execute this batch
                try:
                    batch.execute()
                except Exception as batch_error:
                    error_str = str(batch_error)
                    if '429' in error_str or 'rateLimitExceeded' in error_str:
                        print(f"⚠️  Rate limit hit on incremental batch {i//BATCH_SIZE + 1}. Waiting 2 seconds...")
                        time.sleep(2)  # Wait longer on rate limit
                        # Retry this batch once
                        try:
                            batch.execute()
                        except Exception as retry_error:
                            print(f"⚠️  Retry failed: {retry_error}")
                    else:
                        print(f"⚠️  Batch error: {batch_error}")
                
                # Add delay between batches (except for the last one)
                if i + BATCH_SIZE < total_messages:
                    time.sleep(DELAY_BETWEEN_BATCHES)
            
            # Calculate actual API calls: 1 for history + batches
            num_batches = (len(message_ids_list) + BATCH_SIZE - 1) // BATCH_SIZE if message_ids_list else 0
            total_api_calls = 1 + num_batches  # 1 for history, rest for batches
            print(f"✅ Incremental sync: Fetched {len(emails)} new emails with {total_api_calls} API calls. historyId: {new_history_id}")
            if errors:
                print(f"⚠️  {len(errors)} errors encountered (some emails may be missing)")
            
            return emails, new_history_id
            
        except Exception as e:
            error_str = str(e)
            # If history is too old or invalid, fall back to full sync
            if 'historyId' in error_str or '404' in error_str or 'invalid' in error_str.lower():
                print(f"⚠️  History ID expired or invalid, falling back to full sync: {error_str}")
                return self.get_emails(max_results=10, unread_only=unread_only, start_history_id=None)
            else:
                print(f"Error in incremental sync: {error_str}")
                raise
    
    def get_thread_messages(self, thread_id):
        """Get all messages in a thread - optimized to avoid extra API calls"""
        if not self.service:
            return []
        
        try:
            # Single API call to get entire thread with all messages
            thread = self.service.users().threads().get(
                userId='me',
                id=thread_id,
                format='full'
            ).execute()
            
            messages = thread.get('messages', [])
            thread_emails = []
            
            # Extract data directly from thread response (no additional API calls!)
            for message in messages:
                email_data = self._extract_message_data(message)
                if email_data:
                    thread_emails.append(email_data)
            
            # Sort by date (oldest first)
            thread_emails.sort(key=lambda x: int(x.get('date', 0)))
            
            print(f"✅ Fetched {len(thread_emails)} messages from thread with 1 API call (no extra calls)")
            return thread_emails
        
        except Exception as e:
            print(f"Error fetching thread messages: {str(e)}")
            return []
    
    def _extract_message_data(self, message):
        """
        Extract email data from a message object (no API call).
        This can be used when we already have the message data from threads.get() or messages.get()
        """
        try:
            message_id = message['id']
            headers_list = message['payload']['headers']
            subject_raw = next((h['value'] for h in headers_list if h['name'] == 'Subject'), None)
            sender_raw = next((h['value'] for h in headers_list if h['name'] == 'From'), 'Unknown')
            to_raw = next((h['value'] for h in headers_list if h['name'] == 'To'), None)
            
            # Decode RFC 2047 encoded headers (like =?UTF-8?B?...?=)
            def decode_header_value(value):
                if not value or not value.strip():
                    return None
                try:
                    # Decode RFC 2047 encoding
                    decoded_parts = decode_header(value)
                    decoded_str = ''.join([
                        part[0].decode(part[1] or 'utf-8') if isinstance(part[0], bytes) else part[0]
                        for part in decoded_parts
                    ])
                    # Decode HTML entities (like &#39; -> ')
                    result = html.unescape(decoded_str)
                    # Return None if result is empty or just whitespace
                    return result.strip() if result.strip() else None
                except Exception as e:
                    print(f"Error decoding header value: {str(e)}")
                    return value.strip() if value and value.strip() else None
            
            subject = decode_header_value(subject_raw) if subject_raw else None
            if not subject:
                subject = 'No Subject'
            sender = decode_header_value(sender_raw)
            recipient = decode_header_value(to_raw) if to_raw else None
            
            # Convert headers to dictionary for classification
            headers_dict = {h['name']: h['value'] for h in headers_list}
            
            # Extract both plain text and HTML bodies
            body_plain, body_html = self._get_email_bodies(message['payload'])
            # For classification and snippet we prefer plain text, fall back to HTML if needed
            body = body_plain or body_html or ''
            
            # Extract and parse attachments
            attachments_data = self._extract_attachments(message['payload'], message_id)
            attachment_texts = []
            pdf_attachments = []
            
            for att in attachments_data:
                if att.get('text'):
                    attachment_texts.append(att['text'])
                if att.get('mime_type') == 'application/pdf':
                    pdf_attachments.append(att)
            
            # Combine body with attachment text (for classification)
            combined_text = body
            if attachment_texts:
                combined_text = f"{body}\n\n--- Attachment Content ---\n\n" + "\n\n".join(attachment_texts)
            
            # Decode HTML entities in body and snippet (classification uses plain text)
            if body:
                body = html.unescape(body)
            if combined_text:
                combined_text = html.unescape(combined_text)
            snippet_raw = message.get('snippet', '')
            snippet = html.unescape(snippet_raw) if snippet_raw else ''
            
            # Check if email is starred
            try:
                label_ids = message.get('labelIds', [])
                if not isinstance(label_ids, list):
                    label_ids = []
            except (AttributeError, KeyError):
                label_ids = []
            is_starred = 'STARRED' in label_ids
            
            return {
                'id': message_id,
                'thread_id': message['threadId'],
                'subject': subject,
                'from': sender,
                'to': recipient,  # Add 'to' field for sent emails
                'body': body,
                'body_html': body_html,  # Raw HTML body (for rich rendering in UI)
                'combined_text': combined_text,  # Body + attachment text
                'snippet': snippet,
                'date': message.get('internalDate'),  # Gmail timestamp in milliseconds
                'headers': headers_dict,  # For classification
                'attachments': attachments_data,  # List of attachments with extracted text
                'is_starred': is_starred,  # Star status
                'label_ids': label_ids  # All labels for reference
            }
        
        except Exception as e:
            print(f"Error extracting message data: {str(e)}")
            return None
    
    def get_email_details(self, message_id):
        """Get details of a specific email (makes 1 API call)"""
        if not self.service:
            return None
        
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            return self._extract_message_data(message)
        except Exception as e:
            print(f"Error fetching email details for {message_id}: {str(e)}")
            return None
    
    def _get_email_bodies(self, payload):
        """
        Extract both plain text and HTML bodies from payload.
        Returns: (body_plain, body_html)
        """
        body_plain = ""
        body_html = ""
        
        def decode_part(part_body):
            try:
                return base64.urlsafe_b64decode(part_body['data']).decode('utf-8')
            except Exception:
                try:
                    return base64.urlsafe_b64decode(part_body['data']).decode('latin-1', errors='ignore')
                except Exception:
                    return ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')
                part_body = part.get('body', {})
                
                # Nested multi-part (e.g., alternative)
                if 'parts' in part:
                    p_plain, p_html = self._get_email_bodies(part)
                    if p_plain and not body_plain:
                        body_plain = p_plain
                    if p_html and not body_html:
                        body_html = p_html
                    continue
                
                if 'data' not in part_body:
                    continue
                
                if mime_type == 'text/plain' and not body_plain:
                    body_plain = decode_part(part_body)
                elif mime_type == 'text/html' and not body_html:
                    body_html = decode_part(part_body)
        else:
            # Single-part message
            mime_type = payload.get('mimeType', '')
            body = payload.get('body', {})
            if 'data' in body:
                decoded = decode_part(body)
                if mime_type == 'text/plain':
                    body_plain = decoded
                elif mime_type == 'text/html':
                    body_html = decoded
                else:
                    # Unknown type - treat as plain text fallback
                    body_plain = decoded
        
        return body_plain, body_html
    
    def _get_email_body(self, payload):
        """
        Backwards-compatible helper: return a single body string.
        Prefer plain text, fall back to HTML.
        """
        body_plain, body_html = self._get_email_bodies(payload)
        return body_plain or body_html or ""
    
    def _extract_attachments(self, payload, message_id):
        """Extract attachments from email payload and parse text content"""
        attachments = []
        
        def walk_parts(parts):
            """Recursively walk through email parts to find attachments"""
            for part in parts:
                mime_type = part.get('mimeType', '')
                filename = part.get('filename', '')
                body = part.get('body', {})
                attachment_id = body.get('attachmentId')
                
                # Skip if not an attachment or no filename
                if not attachment_id or not filename:
                    # Check nested parts
                    if 'parts' in part:
                        walk_parts(part['parts'])
                    continue
                
                # Download attachment
                try:
                    attachment = self.service.users().messages().attachments().get(
                        userId='me',
                        messageId=message_id,
                        id=attachment_id
                    ).execute()
                    
                    # Decode attachment data
                    file_data = base64.urlsafe_b64decode(attachment['data'])
                    
                    # Extract text based on file type
                    extracted_text = None
                    
                    if mime_type == 'application/pdf':
                        extracted_text = self._extract_pdf_text(file_data, filename)
                    elif mime_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
                                       'application/msword']:
                        extracted_text = self._extract_docx_text(file_data, filename)
                    elif mime_type.startswith('text/'):
                        try:
                            extracted_text = file_data.decode('utf-8')
                        except:
                            extracted_text = file_data.decode('latin-1', errors='ignore')
                    
                    attachments.append({
                        'filename': filename,
                        'mime_type': mime_type,
                        'size': len(file_data),
                        'text': extracted_text,
                        'has_text': bool(extracted_text)
                    })
                except Exception as e:
                    print(f"Note: Could not extract attachment {filename}: {str(e)}")
                    attachments.append({
                        'filename': filename,
                        'mime_type': mime_type,
                        'size': 0,
                        'text': None,
                        'has_text': False
                    })
        
        # Start walking from payload
        if 'parts' in payload:
            walk_parts(payload['parts'])
        
        return attachments
    
    def _extract_pdf_text(self, file_data, filename):
        """Extract text from PDF file"""
        if not PDF_AVAILABLE:
            return None
        
        try:
            pdf_file = io.BytesIO(file_data)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text_parts = []
            
            for page in pdf_reader.pages:
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                except:
                    continue
            
            if text_parts:
                return '\n\n'.join(text_parts)
        except Exception as e:
            print(f"Note: Could not parse PDF {filename}: {str(e)}")
        
        return None
    
    def _extract_docx_text(self, file_data, filename):
        """Extract text from Word document"""
        if not DOCX_AVAILABLE:
            return None
        
        try:
            doc_file = io.BytesIO(file_data)
            doc = Document(doc_file)
            text_parts = []
            
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_parts.append(paragraph.text)
            
            if text_parts:
                return '\n\n'.join(text_parts)
        except Exception as e:
            print(f"Note: Could not parse Word document {filename}: {str(e)}")
        
        return None
    
    def send_reply(self, to_email, subject, body, thread_id=None, send_as_email=None):
        """
        Send a reply email with signature automatically appended
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body (signature will be appended if not already present)
            thread_id: Optional Gmail thread ID for threading
            send_as_email: Optional email address of send-as alias to use for signature
        """
        if not self.service:
            return False
        
        try:
            # Fetch and append signature if available and not already in body
            signature = self.get_signature(send_as_email=send_as_email)
            if signature:
                # Check if signature is already in the body (simple check)
                # If body already ends with signature (or contains it), don't append again
                signature_clean = signature.strip()
                body_clean = body.strip()
                
                # Only append if signature is not already at the end of the body
                if not body_clean.endswith(signature_clean):
                    # Append signature with proper spacing
                    body = f"{body}\n\n{signature}"
            
            message = MIMEText(body)
            message['to'] = to_email
            message['subject'] = f"Re: {subject}" if not subject.startswith('Re:') else subject
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            send_message = {'raw': raw_message}
            if thread_id:
                send_message['threadId'] = thread_id
            
            result = self.service.users().messages().send(
                userId='me',
                body=send_message
            ).execute()
            
            return True
        
        except Exception as e:
            print(f"Error sending reply: {str(e)}")
            return False
    
    def send_email(self, to_email, subject, body, send_as_email=None, cc=None, bcc=None):
        """
        Send a new email (not a reply) with signature automatically appended
        
        Args:
            to_email: Recipient email address(es) - can be string or list
            subject: Email subject
            body: Email body (signature will be appended if not already present)
            send_as_email: Optional email address of send-as alias to use for signature
            cc: Optional CC email address(es) - can be string or list
            bcc: Optional BCC email address(es) - can be string or list
        """
        if not self.service:
            return False
        
        try:
            # Fetch and append signature if available and not already in body
            signature = self.get_signature(send_as_email=send_as_email)
            if signature:
                signature_clean = signature.strip()
                body_clean = body.strip()
                
                # Only append if signature is not already at the end of the body
                if not body_clean.endswith(signature_clean):
                    body = f"{body}\n\n{signature}"
            
            message = MIMEText(body)
            message['subject'] = subject
            
            # Handle multiple recipients
            if isinstance(to_email, list):
                message['to'] = ', '.join(to_email)
            else:
                message['to'] = to_email
            
            if cc:
                if isinstance(cc, list):
                    message['cc'] = ', '.join(cc)
                else:
                    message['cc'] = cc
            
            if bcc:
                if isinstance(bcc, list):
                    message['bcc'] = ', '.join(bcc)
                else:
                    message['bcc'] = bcc
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            send_message = {'raw': raw_message}
            
            result = self.service.users().messages().send(
                userId='me',
                body=send_message
            ).execute()
            
            return True
        
        except Exception as e:
            print(f"Error sending email: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_signature(self, send_as_email=None):
        """
        Get the user's email signature from a specific or primary send-as alias
        
        Args:
            send_as_email: Optional email address of the send-as alias to use.
                          If None, uses primary alias.
        
        Returns:
            str: The signature text (HTML tags stripped for plain text emails)
        """
        if not self.service:
            return None
        
        try:
            # Get all send-as aliases
            aliases = self.service.users().settings().sendAs().list(
                userId='me'
            ).execute()
            
            send_as_list = aliases.get('sendAs', [])
            selected_alias = None
            
            # Find the requested alias by email
            if send_as_email:
                for alias in send_as_list:
                    if alias.get('sendAsEmail', '').lower() == send_as_email.lower():
                        selected_alias = alias
                        break
            
            # If not found or not specified, use primary alias
            if not selected_alias:
                for alias in send_as_list:
                    if alias.get('isPrimary', False):
                        selected_alias = alias
                        break
            
            # Fallback to first alias if no primary found
            if not selected_alias and send_as_list:
                selected_alias = send_as_list[0]
            
            if not selected_alias:
                return None
            
            signature = selected_alias.get('signature', '')
            
            # Strip HTML tags for plain text emails
            if signature:
                # Convert HTML breaks and paragraphs to newlines FIRST (before removing tags)
                signature = re.sub(r'<br\s*/?>', '\n', signature, flags=re.IGNORECASE)
                signature = re.sub(r'</p>', '\n\n', signature, flags=re.IGNORECASE)
                signature = re.sub(r'<p[^>]*>', '\n', signature, flags=re.IGNORECASE)
                signature = re.sub(r'</div>', '\n', signature, flags=re.IGNORECASE)
                signature = re.sub(r'<div[^>]*>', '', signature, flags=re.IGNORECASE)
                # Remove all other HTML tags
                signature = re.sub(r'<[^>]+>', '', signature)
                # Clean up HTML entities
                signature = signature.replace('&nbsp;', ' ')
                signature = signature.replace('&amp;', '&')
                signature = signature.replace('&lt;', '<')
                signature = signature.replace('&gt;', '>')
                signature = signature.replace('&quot;', '"')
                signature = signature.replace('&#39;', "'")
                # Replace multiple spaces with single space (but preserve intentional line breaks)
                signature = re.sub(r'[ \t]+', ' ', signature)  # Multiple spaces/tabs to single space
                # Clean up multiple newlines (but keep single newlines)
                signature = re.sub(r'\n{3,}', '\n\n', signature)
                # Remove leading/trailing whitespace from each line
                lines = [line.strip() for line in signature.split('\n')]
                signature = '\n'.join(lines)
                signature = signature.strip()
            
            # Debug logging
            if signature:
                print(f"✓ Signature fetched: {len(signature)} characters")
            else:
                print("Note: No signature found in Gmail settings")
            
            return signature if signature else None
            
        except Exception as e:
            # If settings API is not available (user hasn't re-authenticated with new scope),
            # silently fail and return None
            print(f"Note: Could not fetch signature (may need re-authentication): {str(e)}")
            return None
    
    def mark_as_read(self, message_id):
        """Mark an email as read"""
        if not self.service:
            return False
        
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            return True
        except Exception as e:
            print(f"Error marking email as read: {str(e)}")
            return False
    
    def toggle_star(self, message_id, star=True):
        """
        Star or unstar an email
        
        Args:
            message_id: Gmail message ID
            star: True to star, False to unstar
        
        Returns:
            bool: True if successful
        """
        if not self.service:
            return False
        
        try:
            if star:
                # Add STARRED label
                self.service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body={'addLabelIds': ['STARRED']}
                ).execute()
                print(f"⭐ Starred email {message_id}")
            else:
                # Remove STARRED label
                self.service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body={'removeLabelIds': ['STARRED']}
                ).execute()
                print(f"⭐ Unstarred email {message_id}")
            return True
        except Exception as e:
            print(f"Error toggling star for email {message_id}: {str(e)}")
            return False
    
    def get_profile(self):
        """
        Get Gmail profile information including email address
        
        Returns:
            dict: Profile information with 'emailAddress' key, or None if error
        """
        if not self.service:
            return None
        
        try:
            profile = self.service.users().getProfile(userId='me').execute()
            return profile
        except Exception as e:
            print(f"Error getting Gmail profile: {str(e)}")
            return None
