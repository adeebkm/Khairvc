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

# Moonshot API for better PDF extraction (with OCR support)
try:
    from openai import OpenAI as MoonshotClient
    from pathlib import Path
    import tempfile
    MOONSHOT_AVAILABLE = True
except ImportError:
    MOONSHOT_AVAILABLE = False
    print("Note: OpenAI SDK not available. Moonshot PDF extraction won't work.")


# Gmail API scopes
# Note: Google automatically adds 'openid' scope when requesting userinfo scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.settings.basic',  # For fetching signatures
    'https://www.googleapis.com/auth/pubsub',  # For Pub/Sub push notifications (test environment)
    'openid',  # Explicitly include openid (Google adds it automatically anyway)
    'https://www.googleapis.com/auth/userinfo.profile',  # For user profile (name, picture)
    'https://www.googleapis.com/auth/userinfo.email'  # For user email
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
            
            # Get scopes from token if available, otherwise use current SCOPES
            # This prevents 'invalid_scope' errors when tokens were created with different scopes
            token_scopes = token_data.get('scopes')
            
            # If token has scopes stored, use them (handles old tokens without 'openid')
            # Otherwise, try with current SCOPES (for new tokens)
            if token_scopes and isinstance(token_scopes, list) and len(token_scopes) > 0:
                # Use token's original scopes to avoid scope mismatch errors
                creds = Credentials.from_authorized_user_info(token_data, token_scopes)
            else:
                # Token doesn't have scopes - try with current SCOPES
                # If that fails, try without scopes parameter (let token use its own)
                try:
                    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                except Exception as scope_error:
                    if 'scope' in str(scope_error).lower() or 'invalid_scope' in str(scope_error).lower():
                        print(f"⚠️  Scope mismatch detected, using token's original scopes...")
                        # Don't specify scopes - let Google use the token's stored scopes
                        creds = Credentials.from_authorized_user_info(token_data)
                    else:
                        raise
            
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
            max_results: Max emails to fetch in full sync (ignored for incremental sync)
            unread_only: Only fetch unread emails
            start_history_id: If provided, use incremental sync (fetch ALL changes since this ID, ignores max_results)
        
        Returns:
            tuple: (emails_list, new_history_id)
        """
        if not self.service:
            return [], None
        
        try:
            # INCREMENTAL SYNC: Use History API if we have a history_id
            # This fetches ALL new emails since history_id (ignores max_results limit)
            if start_history_id:
                print(f"🔄 Using incremental sync from history ID: {start_history_id} (fetching ALL new emails, no limit)")
                result = self._get_emails_incremental(start_history_id, unread_only)
                # Return in old format for backward compatibility (emails, history_id)
                # Note: deleted_ids are available in result but not returned here
                # They should be accessed separately via the full result dict
                return result['new_emails'], result['history_id']
            
            # FULL SYNC: Use messages.list() for first time or full refresh
            query = 'in:inbox'
            if unread_only:
                query = 'is:unread in:inbox'
            
            print(f"📧 Full sync: Fetching up to {max_results} emails...")
            
            # Gmail API pagination: messages().list() may return fewer than maxResults
            # We need to paginate to get all requested emails
            all_message_ids = []
            page_token = None
            history_id = None
            
            while len(all_message_ids) < max_results:
                # Build request parameters
                request_params = {
                    'userId': 'me',
                    'q': query,
                    'maxResults': min(max_results - len(all_message_ids), 500)  # Gmail max is 500 per page
                }
                if page_token:
                    request_params['pageToken'] = page_token
                
                # Get list of message IDs (with pagination)
                results = self.service.users().messages().list(**request_params).execute()
                
                page_messages = results.get('messages', [])
                if not history_id:
                    history_id = results.get('historyId')  # Store this for next incremental sync!
                
                if not page_messages:
                    break  # No more messages
                
                all_message_ids.extend([msg['id'] for msg in page_messages])
                
                # Check if there are more pages
                page_token = results.get('nextPageToken')
                if not page_token:
                    break  # No more pages
                
                print(f"📄 Fetched {len(page_messages)} message IDs (total: {len(all_message_ids)}/{max_results})")
            
            messages = [{'id': msg_id} for msg_id in all_message_ids[:max_results]]  # Limit to max_results
            
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
                    
                    # Extract attachments for classification
                    email_data = self._extract_message_data(response, extract_attachments=True)
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
    
    def get_older_emails(self, max_results=200, start_page_token=None, progress_callback=None, skip_existing_ids=None):
        """
        Fetch older emails using pagination (for emails before the initial 60).
        Fetches slowly with delays to avoid rate limits.
        
        Args:
            max_results: Maximum total emails to fetch (default 200)
            start_page_token: Optional pageToken to start from (for resuming)
            progress_callback: Optional callback function(emails_fetched, total_target) for progress updates
            skip_existing_ids: Optional set of message IDs to skip (already in database)
        
        Returns:
            tuple: (emails_list, next_page_token, total_fetched)
        """
        if not self.service:
            return [], None, 0
        
        try:
            query = 'in:inbox'
            emails = []
            page_token = start_page_token
            total_fetched = 0
            existing_ids = skip_existing_ids or set()
            
            # Fetch in smaller pages to avoid rate limits (super slow for background fetching)
            PAGE_SIZE = 20  # Fetch 20 emails per page
            DELAY_BETWEEN_PAGES = 5.0  # 5 second delay between pages (very conservative for background)
            DELAY_BETWEEN_BATCHES = 1.0  # 1 second delay between batches within a page
            
            from googleapiclient.http import BatchHttpRequest
            import time
            
            while total_fetched < max_results:
                # Calculate how many to fetch in this page
                remaining = max_results - total_fetched
                page_max = min(PAGE_SIZE, remaining)
                
                print(f"📧 Fetching older emails: page {len(emails) // PAGE_SIZE + 1}, requesting {page_max} emails...")
                
                # Get list of message IDs for this page
                request_params = {
                    'userId': 'me',
                    'q': query,
                    'maxResults': page_max
                }
                
                if page_token:
                    request_params['pageToken'] = page_token
                
                try:
                    results = self.service.users().messages().list(**request_params).execute()
                except Exception as e:
                    error_str = str(e)
                    if '429' in error_str or 'rateLimitExceeded' in error_str:
                        print(f"⚠️ Rate limit hit. Waiting 5 seconds before retry...")
                        time.sleep(5)
                        continue  # Retry this page
                    else:
                        raise
                
                messages = results.get('messages', [])
                next_page_token = results.get('nextPageToken')
                
                if not messages:
                    print(f"✅ No more emails to fetch")
                    break
                
                # Filter out messages we already have (if skip_existing_ids provided)
                messages_to_fetch = messages
                if existing_ids:
                    messages_to_fetch = [msg for msg in messages if msg.get('id') not in existing_ids]
                    skipped = len(messages) - len(messages_to_fetch)
                    if skipped > 0:
                        print(f"⏭️  Skipping {skipped} emails that are already in database")
                
                if not messages_to_fetch:
                    # All messages in this page are duplicates, move to next page
                    if next_page_token:
                        page_token = next_page_token
                        time.sleep(DELAY_BETWEEN_PAGES)
                        continue
                    else:
                        break
                
                # Batch fetch email details for this page
                BATCH_SIZE = 10
                page_emails = []
                errors = []
                
                def callback(request_id, response, exception):
                    if exception:
                        error_str = str(exception)
                        if '429' not in error_str and 'rateLimitExceeded' not in error_str:
                            print(f"⚠️  Error in batch request: {exception}")
                        errors.append(exception)
                    else:
                        # Extract attachments for classification
                        email_data = self._extract_message_data(response, extract_attachments=True)
                        if email_data:
                            page_emails.append(email_data)
                
                # Process messages in batches
                for i in range(0, len(messages_to_fetch), BATCH_SIZE):
                    batch_chunk = messages_to_fetch[i:i + BATCH_SIZE]
                    
                    batch = self.service.new_batch_http_request(callback=callback)
                    for message in batch_chunk:
                        batch.add(self.service.users().messages().get(
                            userId='me',
                            id=message['id'],
                            format='full'
                        ))
                    
                    try:
                        batch.execute()
                    except Exception as batch_error:
                        error_str = str(batch_error)
                        if '429' in error_str or 'rateLimitExceeded' in error_str:
                            print(f"⚠️ Rate limit hit on batch. Waiting 3 seconds...")
                            time.sleep(3)
                            # Retry this batch once
                            try:
                                batch.execute()
                            except Exception as retry_error:
                                print(f"⚠️ Retry failed: {retry_error}")
                        else:
                            print(f"⚠️ Batch error: {batch_error}")
                    
                    # Delay between batches (except for the last batch of the page)
                    if i + BATCH_SIZE < len(messages_to_fetch):
                        time.sleep(DELAY_BETWEEN_BATCHES)
                
                emails.extend(page_emails)
                total_fetched = len(emails)
                
                # Call progress callback if provided
                if progress_callback:
                    try:
                        progress_callback(total_fetched, max_results)
                    except Exception as e:
                        print(f"⚠️ Progress callback error: {e}")
                
                print(f"✅ Fetched {len(page_emails)} emails in this page. Total: {total_fetched}/{max_results}")
                
                # Check if we've reached the target or there's no next page
                if total_fetched >= max_results or not next_page_token:
                    break
                
                # Delay before fetching next page (to avoid rate limits)
                if next_page_token:
                    print(f"⏳ Waiting {DELAY_BETWEEN_PAGES}s before fetching next page...")
                    time.sleep(DELAY_BETWEEN_PAGES)
                    page_token = next_page_token
            
            print(f"✅ Older emails fetch complete: {total_fetched} emails fetched")
            return emails, page_token, total_fetched
        
        except Exception as e:
            error_str = str(e)
            if '429' in error_str or 'rateLimitExceeded' in error_str:
                print(f"⚠️ Gmail API rate limit exceeded: {error_str}")
                raise
            else:
                print(f"Error fetching older emails: {error_str}")
                return emails, page_token, len(emails)
    
    def _get_emails_incremental(self, start_history_id, unread_only=False):
        """
        Fetch only changes since start_history_id using Gmail History API.
        This is MUCH faster and uses far fewer API calls than full sync.
        Returns dict with new_emails, deleted_ids, and history_id.
        """
        try:
            # Single API call to get all changes since last sync (additions AND deletions)
            history_response = self.service.users().history().list(
                userId='me',
                startHistoryId=start_history_id,
                historyTypes=['messageAdded', 'messageDeleted'],  # Track both additions and deletions
                labelId='INBOX'  # Only inbox messages
            ).execute()
            
            changes = history_response.get('history', [])
            new_history_id = history_response.get('historyId')
            
            if not changes:
                print(f"✅ Incremental sync: No changes since last sync. historyId: {new_history_id}")
                return {
                    'new_emails': [],
                    'deleted_ids': [],
                    'history_id': new_history_id
                }
            
            # Extract message IDs from history changes (both additions and deletions)
            message_ids = set()
            deleted_message_ids = set()
            
            for change in changes:
                # Track deletions
                if 'messagesDeleted' in change:
                    for msg_deleted in change['messagesDeleted']:
                        message = msg_deleted.get('message', {})
                        deleted_message_ids.add(message['id'])
                        print(f"🗑️  Detected deleted message: {message['id'][:16]}...")
                
                # Track additions
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
            
            if not message_ids and not deleted_message_ids:
                print(f"✅ Incremental sync: {len(changes)} changes but no new inbox messages or deletions. historyId: {new_history_id}")
                return {
                    'new_emails': [],
                    'deleted_ids': [],
                    'history_id': new_history_id
                }
            
            if deleted_message_ids:
                print(f"🗑️  Found {len(deleted_message_ids)} deleted message(s)")
            
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
                    # Extract attachments for classification
                    email_data = self._extract_message_data(response, extract_attachments=True)
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
            print(f"✅ Incremental sync: Fetched {len(emails)} new emails, {len(deleted_message_ids)} deleted with {total_api_calls} API calls. historyId: {new_history_id}")
            if errors:
                print(f"⚠️  {len(errors)} errors encountered (some emails may be missing)")
            
            return {
                'new_emails': emails,
                'deleted_ids': list(deleted_message_ids),
                'history_id': new_history_id
            }
            
        except Exception as e:
            error_str = str(e)
            # If history is too old or invalid, fall back to full sync
            if 'historyId' in error_str or '404' in error_str or 'invalid' in error_str.lower():
                print(f"⚠️  History ID expired or invalid, falling back to full sync: {error_str}")
                emails, history_id = self.get_emails(max_results=10, unread_only=unread_only, start_history_id=None)
                return {
                    'new_emails': emails,
                    'deleted_ids': [],
                    'history_id': history_id
                }
            else:
                print(f"Error in incremental sync: {error_str}")
                raise
    
    def get_thread_messages(self, thread_id, extract_attachments=False):
        """Get all messages in a thread - optimized to avoid extra API calls
        
        Args:
            thread_id: Gmail thread ID
            extract_attachments: If False (default), skip PDF/attachment extraction for faster loading.
                                Only set to True when classifying emails for the first time.
        """
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
                email_data = self._extract_message_data(message, extract_attachments=extract_attachments)
                if email_data:
                    thread_emails.append(email_data)
            
            # Sort by date (oldest first)
            thread_emails.sort(key=lambda x: int(x.get('date', 0)))
            
            print(f"✅ Fetched {len(thread_emails)} messages from thread with 1 API call (no extra calls)")
            return thread_emails
        
        except Exception as e:
            print(f"Error fetching thread messages: {str(e)}")
            return []
    
    def _extract_message_data(self, message, extract_attachments=False):
        """
        Extract email data from a message object (no API call).
        This can be used when we already have the message data from threads.get() or messages.get()
        
        Args:
            message: Gmail message object
            extract_attachments: If False (default), only list attachment filenames without extracting content.
                                If True, download and extract PDF/document text content.
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
            
            # Extract and parse attachments (conditionally)
            if extract_attachments:
                attachments_data = self._extract_attachments(message['payload'], message_id)
            else:
                # Just list attachment filenames without extracting content (much faster!)
                attachments_data = self._list_attachments_only(message['payload'])
            attachment_texts = []
            pdf_attachments = []
            
            # Limit total attachment text to 1500 characters
            total_attachment_chars = 0
            MAX_ATTACHMENT_CHARS = 1500
            
            for att in attachments_data:
                if att.get('text'):
                    att_text = att['text']
                    # Calculate remaining characters available
                    remaining_chars = MAX_ATTACHMENT_CHARS - total_attachment_chars
                    if remaining_chars > 0:
                        # Truncate if needed
                        if len(att_text) > remaining_chars:
                            att_text = att_text[:remaining_chars] + "... [truncated]"
                        attachment_texts.append(att_text)
                        total_attachment_chars += len(att_text)
                    else:
                        # No more space for attachments
                        break
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
    
    def _list_attachments_only(self, payload):
        """
        List attachments without downloading or extracting content (much faster!)
        Used when viewing emails to avoid expensive PDF extraction.
        """
        attachments = []
        
        def walk_parts(parts):
            """Recursively walk through email parts to find attachments"""
            for part in parts:
                mime_type = part.get('mimeType', '')
                filename = part.get('filename', '')
                body = part.get('body', {})
                attachment_id = body.get('attachmentId')
                size = body.get('size', 0)
                
                # Skip if not an attachment or no filename
                if not attachment_id or not filename:
                    # Check nested parts
                    if 'parts' in part:
                        walk_parts(part['parts'])
                    continue
                
                # Just add metadata without downloading
                attachments.append({
                    'filename': filename,
                    'mime_type': mime_type,
                    'size': size,
                    'text': None,  # No text extraction
                    'has_text': False
                })
        
        # Start walking from payload
        if 'parts' in payload:
            walk_parts(payload['parts'])
        
        return attachments
    
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
    
    def _get_moonshot_api_key(self):
        """Get Moonshot API key from AWS Secrets Manager (if available) or environment variables"""
        # First try AWS Secrets Manager (like Lambda does)
        try:
            aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
            aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
            aws_region = os.getenv('AWS_REGION', 'us-east-1')
            
            if aws_access_key and aws_secret_key:
                import boto3
                secrets_client = boto3.client(
                    'secretsmanager',
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                    region_name=aws_region
                )
                
                secret_name = os.getenv('OPENAI_SECRET_NAME', 'openai-api-key-test')
                try:
                    response = secrets_client.get_secret_value(SecretId=secret_name)
                    secret = json.loads(response['SecretString'])
                    api_key = secret.get('api_key') or secret.get('MOONSHOT_API_KEY') or secret.get('OPENAI_API_KEY')
                    if api_key:
                        print(f"   🔑 Retrieved Moonshot API key from AWS Secrets Manager")
                        return api_key
                except Exception as secrets_error:
                    print(f"   ⚠️  Could not retrieve from Secrets Manager: {str(secrets_error)[:100]}")
        except Exception as e:
            # AWS not available or not configured, fall through to environment variables
            pass
        
        # Fallback to environment variables (Railway)
        moonshot_key = os.getenv('MOONSHOT_API_KEY') or os.getenv('OPENAI_API_KEY')
        if moonshot_key:
            # Log first few characters for debugging (don't log full key for security)
            key_preview = moonshot_key[:10] + "..." if len(moonshot_key) > 10 else moonshot_key[:len(moonshot_key)]
            print(f"   🔑 Using Moonshot API key from environment variables (key starts with: {key_preview})")
            # Validate key format
            if not moonshot_key.startswith('sk-'):
                print(f"   ⚠️  WARNING: API key doesn't start with 'sk-' - may be invalid")
        else:
            print(f"   ❌ No Moonshot API key found in environment variables (checked MOONSHOT_API_KEY and OPENAI_API_KEY)")
        return moonshot_key
    
    def _extract_pdf_text(self, file_data, filename):
        """Extract text from PDF file using Moonshot (if enabled) or PyPDF2 (fallback)"""
        use_moonshot = os.getenv('USE_MOONSHOT', 'false').lower() == 'true'
        
        # Try Moonshot first if enabled (better extraction with OCR)
        if use_moonshot and MOONSHOT_AVAILABLE:
            try:
                moonshot_key = self._get_moonshot_api_key()
                if moonshot_key:
                    # Check if key looks valid (starts with 'sk-')
                    if moonshot_key.startswith('sk-'):
                        print(f"📄 Using Moonshot to extract PDF content: {filename}")
                        result = self._extract_pdf_with_moonshot(file_data, filename, moonshot_key)
                        if result:
                            return result
                        # If Moonshot failed, fall through to PyPDF2
                        print(f"⚠️  Moonshot extraction returned None, falling back to PyPDF2")
                    else:
                        print(f"⚠️  Moonshot API key format invalid (should start with 'sk-'), falling back to PyPDF2")
                else:
                    print(f"⚠️  Moonshot enabled but API key not found (checked Secrets Manager and environment), falling back to PyPDF2")
            except Exception as e:
                print(f"⚠️  Moonshot PDF extraction failed: {str(e)}, falling back to PyPDF2")
                import traceback
                traceback.print_exc()
        
        # Fallback to PyPDF2 (production or if Moonshot fails)
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
    
    def _extract_pdf_with_moonshot(self, file_data, filename, api_key):
        """Extract text from PDF using Moonshot's file upload API (with OCR support)"""
        tmp_path = None
        try:
            # Create Moonshot client
            client = MoonshotClient(
                api_key=api_key,
                base_url="https://api.moonshot.ai/v1"
            )
            
            # Save PDF to temporary file (Moonshot API requires a file path)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(file_data)
                tmp_path = tmp_file.name
            
            try:
                # Upload PDF to Moonshot
                print(f"   📤 Uploading PDF to Moonshot...")
                file_object = client.files.create(
                    file=Path(tmp_path),
                    purpose="file-extract"
                )
                
                # Extract content from uploaded file
                print(f"   📥 Extracting content from Moonshot...")
                file_content = client.files.content(file_id=file_object.id).text
                
                print(f"   ✅ Successfully extracted {len(file_content)} characters from PDF using Moonshot")
                return file_content
                
            finally:
                # Clean up temporary file
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
                    
        except Exception as e:
            error_msg = str(e)
            # Check if it's an authentication error
            if '401' in error_msg or 'incorrect_api_key' in error_msg.lower() or 'unauthorized' in error_msg.lower():
                print(f"❌ Moonshot API key authentication failed. Please check MOONSHOT_API_KEY in worker environment variables.")
            else:
                print(f"❌ Moonshot PDF extraction error: {error_msg}")
            
            # Clean up temp file if it exists
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            
            # Return None to trigger PyPDF2 fallback
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
    
    def send_reply_with_attachments(self, to_email, subject, body, thread_id=None, attachments=None, send_as_email=None, cc=None, bcc=None):
        """
        Send a reply email with attachments
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body
            thread_id: Optional Gmail thread ID for threading
            attachments: List of dicts with 'filename' and 'data' (base64 encoded)
            send_as_email: Optional email address of send-as alias to use for signature
            cc: Optional CC recipients
            bcc: Optional BCC recipients
        """
        if not self.service:
            return False
        
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.base import MIMEBase
            from email import encoders
            
            # Create message container
            message = MIMEMultipart()
            message['to'] = to_email
            message['subject'] = f"Re: {subject}" if not subject.startswith('Re:') else subject
            
            if cc:
                message['cc'] = cc
            if bcc:
                message['bcc'] = bcc
            
            # Fetch and append signature
            signature = self.get_signature(send_as_email=send_as_email)
            if signature:
                body = f"{body}\n\n{signature}"
            
            # Add body
            body_part = MIMEText(body, 'plain')
            message.attach(body_part)
            
            # Add attachments
            if attachments:
                for attachment in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    # Decode base64 data
                    file_data = base64.b64decode(attachment['data'])
                    part.set_payload(file_data)
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename="{attachment["filename"]}"')
                    message.attach(part)
            
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
            print(f"Error sending reply with attachments: {str(e)}")
            return False
    
    def forward_email(self, to_email, subject, body, original_message_id, include_attachments=False, send_as_email=None):
        """
        Forward an email
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body (your message)
            original_message_id: Gmail message ID of original email
            include_attachments: Whether to include original attachments
            send_as_email: Optional email address of send-as alias to use for signature
        """
        if not self.service:
            return False
        
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.base import MIMEBase
            from email import encoders
            
            # Fetch original message
            original = self.service.users().messages().get(
                userId='me',
                id=original_message_id,
                format='full'
            ).execute()
            
            # Create message container
            message = MIMEMultipart()
            message['to'] = to_email
            message['subject'] = f"Fwd: {subject}" if not subject.startswith('Fwd:') else subject
            
            # Fetch and append signature
            signature = self.get_signature(send_as_email=send_as_email)
            
            # Build forwarded message body
            original_data = self._extract_message_data(original)
            forwarded_body = f"{body}\n\n"
            forwarded_body += "---------- Forwarded message ---------\n"
            forwarded_body += f"From: {original_data.get('from', 'Unknown')}\n"
            forwarded_body += f"Date: {original_data.get('date', '')}\n"
            forwarded_body += f"Subject: {original_data.get('subject', 'No Subject')}\n"
            forwarded_body += f"To: {original_data.get('to', '')}\n\n"
            forwarded_body += original_data.get('body', '')
            
            if signature:
                forwarded_body = f"{forwarded_body}\n\n{signature}"
            
            body_part = MIMEText(forwarded_body, 'plain')
            message.attach(body_part)
            
            # Include attachments if requested
            if include_attachments and original_data.get('attachments'):
                for att in original_data['attachments']:
                    # Fetch attachment data
                    if att.get('attachmentId'):
                        att_data = self.service.users().messages().attachments().get(
                            userId='me',
                            messageId=original_message_id,
                            id=att['attachmentId']
                        ).execute()
                        
                        file_data = base64.urlsafe_b64decode(att_data['data'])
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(file_data)
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', f'attachment; filename="{att.get("filename", "attachment")}"')
                        message.attach(part)
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            result = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            return True
        
        except Exception as e:
            print(f"Error forwarding email: {str(e)}")
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
    
    def setup_pubsub_watch(self, topic_name, user_id=None):
        """
        Set up Gmail Watch with Pub/Sub for push notifications (test environment).
        This reduces API calls by receiving real-time notifications instead of polling.
        
        Args:
            topic_name: Full Pub/Sub topic name (e.g., 'projects/PROJECT_ID/topics/gmail-notifications')
            user_id: Optional user ID for logging
        
        Returns:
            dict: Watch response with expiration timestamp, or None if failed
        """
        if not self.service:
            print("❌ Gmail service not initialized")
            return None
        
        try:
            # Gmail Watch API - sets up push notifications via Pub/Sub
            # Watch expires after 7 days (604800 seconds), must be renewed
            watch_request = {
                'topicName': topic_name,
                'labelIds': ['INBOX'],  # Only watch inbox
                'labelFilterAction': 'include'  # Include only inbox messages
            }
            
            print(f"📡 Setting up Gmail Watch with Pub/Sub topic: {topic_name}")
            if user_id:
                print(f"   User ID: {user_id}")
            
            watch_response = self.service.users().watch(
                userId='me',
                body=watch_request
            ).execute()
            
            expiration = watch_response.get('expiration')
            history_id = watch_response.get('historyId')
            
            print(f"✅ Gmail Watch established successfully")
            print(f"   Expiration: {expiration} (Unix timestamp)")
            print(f"   History ID: {history_id}")
            
            return {
                'expiration': expiration,
                'history_id': history_id
            }
            
        except Exception as e:
            error_str = str(e)
            print(f"❌ Error setting up Gmail Watch: {error_str}")
            
            # Common errors:
            if '403' in error_str or 'permission' in error_str.lower():
                print("   → Make sure Pub/Sub API is enabled in Google Cloud Console")
                print("   → Verify the topic exists and the service account has publish permissions")
            elif '404' in error_str:
                print("   → Topic not found. Create it in Google Cloud Console first")
            
            return None
    
    def stop_watch(self):
        """
        Stop Gmail Watch (cleanup when disconnecting or switching to polling)
        
        Returns:
            bool: True if successful
        """
        if not self.service:
            return False
        
        try:
            self.service.users().stop(userId='me').execute()
            print("✅ Gmail Watch stopped")
            return True
        except Exception as e:
            print(f"⚠️  Error stopping Gmail Watch: {str(e)}")
            return False
