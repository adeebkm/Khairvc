"""
Background tasks for email processing
"""
import os
import sys
import json
from datetime import datetime, timedelta
from celery import current_task
from celery_config import celery

# Ensure the app directory is in Python path (for Railway worker)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

# Import models and clients inside functions to avoid circular imports


@celery.task(bind=True, name='tasks.sync_user_emails', time_limit=1800, soft_time_limit=1700)  # 30 min hard, 28.3 min soft
def sync_user_emails(self, user_id, max_emails=50, force_full_sync=False):
    """
    Background task to sync and classify emails for a user
    
    Args:
        user_id: User ID to sync emails for
        max_emails: Maximum number of emails to fetch
        force_full_sync: Force full sync (ignore history_id)
    
    Returns:
        dict: Status and results
    """
    # Import inside function to avoid circular imports
    # Try multiple import strategies for Railway worker
    # Note: os is imported at module level, but ensure it's available here
    import os  # Ensure os is available in function scope
    
    try:
        from app import app, db
    except ImportError:
        # Fallback: add current directory to path and try again
        import sys
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        if '/app' not in sys.path:
            sys.path.insert(0, '/app')
        from app import app, db
    
    from models import User, GmailToken, EmailClassification, Deal
    from gmail_client import GmailClient
    from email_classifier import EmailClassifier, CATEGORY_DEAL_FLOW
    from openai_client import OpenAIClient
    from lambda_client import LambdaClient
    from auth import decrypt_token
    from threading import Semaphore
    
    # Rate limiting semaphore (shared across all workers)
    # Increased to 20 for faster processing (Lambda can handle more concurrent requests)
    CLASSIFICATION_SEMAPHORE = Semaphore(20)
    
    with app.app_context():
        try:
            # Update task state
            self.update_state(
                state='PROGRESS',
                meta={'status': 'initializing', 'progress': 0, 'total': max_emails}
            )
            
            # Get user with retry on connection errors
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    user = User.query.get(user_id)
                    break
                except Exception as db_error:
                    if 'EOF' in str(db_error) or 'SSL SYSCALL' in str(db_error) or 'connection' in str(db_error).lower():
                        if attempt < max_retries - 1:
                            print(f"⚠️  Database connection error (attempt {attempt + 1}/{max_retries}), retrying...")
                            db.session.rollback()
                            import time
                            time.sleep(1)  # Wait 1 second before retry
                            continue
                        else:
                            raise
                    else:
                        raise
            
            if not user:
                return {'status': 'error', 'error': 'User not found'}
            
            if not user.gmail_token:
                return {'status': 'error', 'error': 'Gmail not connected'}
            
            # Get Gmail client
            token_json = decrypt_token(user.gmail_token.encrypted_token)
            gmail = GmailClient(token_json=token_json)
            
            if not gmail.service:
                return {'status': 'error', 'error': 'Failed to connect to Gmail'}
            
            # Get history_id for incremental sync
            gmail_token = GmailToken.query.filter_by(user_id=user_id).first()
            start_history_id = None if force_full_sync else (gmail_token.history_id if gmail_token else None)
            
            # Update task state
            self.update_state(
                state='PROGRESS',
                meta={'status': 'fetching', 'progress': 0, 'total': max_emails}
            )
            
            # Fetch emails from Gmail
            # For incremental sync, don't limit results - fetch ALL new emails
            # For full sync, respect max_emails limit
            if start_history_id:
                # Incremental sync: fetch ALL new emails (no limit)
                print(f"📧 [TASK] Incremental sync: Fetching ALL new emails since history_id={start_history_id}")
                emails, new_history_id = gmail.get_emails(
                    max_results=None,  # No limit for incremental sync
                    unread_only=False,
                    start_history_id=start_history_id
                )
            else:
                # Full sync: respect max_emails limit
                print(f"📧 [TASK] Full sync: Fetching up to {max_emails} emails...")
                emails, new_history_id = gmail.get_emails(
                    max_results=max_emails,
                    unread_only=False,
                    start_history_id=None
                )
            if start_history_id:
                print(f"📧 [TASK] Incremental sync: Fetched {len(emails)} new emails (no limit)")
            else:
                print(f"📧 [TASK] Full sync: Fetched {len(emails)} emails from Gmail (target: {max_emails})")
            
            # Deduplicate emails by message_id to prevent processing the same email multiple times
            original_count = len(emails) if emails else 0
            if emails:
                seen_message_ids = set()
                deduplicated_emails = []
                duplicates_in_batch = 0
                for email in emails:
                    message_id = email.get('id', '')
                    if message_id and message_id not in seen_message_ids:
                        seen_message_ids.add(message_id)
                        deduplicated_emails.append(email)
                    else:
                        duplicates_in_batch += 1
                        if duplicates_in_batch <= 5:  # Log first 5 duplicates
                            print(f"⏭️  Skipping duplicate email in batch: {message_id[:16]}...")
                emails = deduplicated_emails
                if duplicates_in_batch > 0:
                    print(f"📊 [TASK] Deduplicated emails: {len(emails)} unique out of {original_count} total (removed {duplicates_in_batch} duplicates)")
            
            print(f"📦 [TASK] Emails ready for processing: {len(emails)} emails (stored in memory, not yet in database)")
            
            if not emails:
                # Update history_id even if no new emails
                if new_history_id and gmail_token:
                    gmail_token.history_id = new_history_id
                    # Commit with retry on connection errors
                    max_commit_retries = 3
                    for commit_attempt in range(max_commit_retries):
                        try:
                            db.session.commit()
                            break
                        except Exception as commit_error:
                            if 'EOF' in str(commit_error) or 'SSL SYSCALL' in str(commit_error) or 'connection' in str(commit_error).lower():
                                if commit_attempt < max_commit_retries - 1:
                                    db.session.rollback()
                                    import time
                                    time.sleep(0.5)
                                    gmail_token.history_id = new_history_id
                                    continue
                                else:
                                    raise
                            else:
                                raise
                
                return {
                    'status': 'complete',
                    'emails_processed': 0,
                    'emails_classified': 0,
                    'message': 'No new emails'
                }
            
            # Update task state
            self.update_state(
                state='PROGRESS',
                meta={'status': 'classifying', 'progress': 0, 'total': len(emails)}
            )
            
            # Initialize classifier (with error handling for missing API key)
            try:
                openai_client = OpenAIClient()
            except Exception as openai_error:
                error_msg = str(openai_error)
                # Check if using Moonshot or OpenAI
                use_moonshot = os.getenv('USE_MOONSHOT', 'false').lower() == 'true'
                api_key_name = 'MOONSHOT_API_KEY' if use_moonshot else 'OPENAI_API_KEY'
                
                if 'API key' in error_msg or 'OPENAI_API_KEY' in error_msg or 'MOONSHOT_API_KEY' in error_msg:
                    return {
                        'status': 'error',
                        'error': f'API key not configured in worker. Please set {api_key_name} (or OPENAI_API_KEY as fallback) and USE_MOONSHOT={str(use_moonshot).lower()} environment variables in the worker service. Error: {error_msg}'
                    }
                else:
                    return {
                        'status': 'error',
                        'error': f'Failed to initialize AI client: {error_msg}'
                    }
            
            # EmailClassifier initializes LambdaClient internally, don't pass it
            classifier = EmailClassifier(openai_client)
            
            # Process emails
            emails_processed = 0
            emails_classified = 0
            emails_skipped_duplicate = 0
            emails_failed_classification = 0
            emails_failed_commit = 0
            errors = []
            
            import time  # For rate limiting delays
            
            print(f"📧 [TASK] Starting classification loop: {len(emails)} emails to process")
            print(f"📊 [TASK] Initial state: emails_fetched={len(emails)}, target={max_emails}")
            
            # Track message_ids we've already processed in this task run to prevent duplicates
            processed_message_ids = set()
            
            for idx, email in enumerate(emails):
                message_id = email.get('id', '')
                
                # Skip if we've already processed this message_id in this task run
                if message_id in processed_message_ids:
                    emails_skipped_duplicate += 1
                    print(f"⏭️  [TASK] Email {idx + 1}/{len(emails)}: Skipped (already processed in this task run: {message_id[:16]}...)")
                    continue
                
                processed_message_ids.add(message_id)
                try:
                    # Update progress every 10 emails
                    if (idx + 1) % 10 == 0 or idx == 0:
                        self.update_state(
                            state='PROGRESS',
                            meta={
                                'status': 'classifying',
                                'progress': idx + 1,
                                'total': len(emails),
                                'fetched': len(emails),
                                'classified': emails_classified,
                                'current_email': email.get('subject', 'No Subject')[:50]
                            }
                        )
                        print(f"📧 [TASK] Progress: {idx + 1}/{len(emails)} emails processed, {emails_classified} classified, {emails_skipped_duplicate} skipped (duplicate)")
                    
                    # Extract email data
                    headers = email.get('headers', {})
                    email_body = email.get('body', '')
                    
                    # Extract attachments if any
                    attachment_text = None
                    pdf_attachments = []
                    if email.get('attachments'):
                        for att in email['attachments']:
                            if att.get('mimeType', '').startswith('application/pdf'):
                                pdf_attachments.append(att)
                    
                    # Check if email already exists FIRST (before classification to save API calls)
                    # Use a fresh query after any potential rollback
                    try:
                        existing_classification = EmailClassification.query.filter_by(
                            user_id=user_id,
                            message_id=email.get('id', '')
                        ).first()
                    except Exception as query_error:
                        # If query fails (e.g., session rolled back), rollback and retry
                        db.session.rollback()
                        existing_classification = EmailClassification.query.filter_by(
                            user_id=user_id,
                            message_id=email.get('id', '')
                        ).first()
                    
                    if existing_classification:
                        emails_processed += 1
                        emails_skipped_duplicate += 1
                        if (idx + 1) % 10 == 0 or emails_skipped_duplicate <= 5:  # Log first 5 and every 10th
                            print(f"⏭️  [TASK] Email {idx + 1}/{len(emails)}: Skipped (duplicate by message_id: {email.get('id', 'unknown')[:16]}...) - Total skipped: {emails_skipped_duplicate}")
                        continue  # Skip this email entirely
                    
                    # Classify email (with rate limiting)
                    try:
                        with CLASSIFICATION_SEMAPHORE:
                            print(f"🤖 [TASK] Email {idx + 1}/{len(emails)}: Classifying (message_id: {email.get('id', 'unknown')[:16]}...)")
                            classification_result = classifier.classify_email(
                                subject=email.get('subject', ''),
                                body=email_body,
                                headers=headers,
                                sender=email.get('from', ''),
                                thread_id=email.get('thread_id', ''),
                                user_id=str(user_id)
                            )
                            print(f"✅ [TASK] Email {idx + 1}/{len(emails)}: Classified as {classification_result.get('category', 'UNKNOWN')}")
                    except Exception as classify_error:
                        emails_failed_classification += 1
                        error_msg = f"Error classifying email {idx + 1}: {str(classify_error)}"
                        errors.append(error_msg)
                        print(f"❌ [TASK] {error_msg}")
                        continue  # Skip this email if classification fails
                    
                    # No delay needed - semaphore already provides rate limiting (max 10 concurrent)
                    # Removing delay saves ~100 seconds for 200 emails
                    
                    # Create new classification
                    new_classification = EmailClassification(
                        user_id=user_id,
                        thread_id=email.get('thread_id', ''),
                        message_id=email.get('id', ''),
                        sender=email.get('from', 'Unknown'),
                        email_date=email.get('date'),
                        category=classification_result['category'],
                        tags=','.join(classification_result.get('tags', [])),
                        confidence=classification_result.get('confidence', 0.0),
                        extracted_links=json.dumps(classification_result.get('links', []))
                    )
                    # Use encrypted field setters
                    new_classification.set_subject_encrypted(email.get('subject', 'No Subject'))
                    new_classification.set_snippet_encrypted(email.get('snippet', ''))
                    db.session.add(new_classification)
                    
                    # Batch commits: Commit every 10 emails instead of each one (10x faster for DB operations)
                    # Only commit immediately if it's the last email or we've accumulated 10
                    should_commit_now = (idx + 1) % 10 == 0 or (idx + 1) == len(emails)
                    
                    if should_commit_now:
                        # Commit with retry on connection errors and handle duplicate key errors
                        max_commit_retries = 3
                        commit_success = False
                        duplicate_detected = False
                        
                        for commit_attempt in range(max_commit_retries):
                            try:
                                db.session.commit()
                                commit_success = True
                                break
                            except Exception as commit_error:
                                error_str = str(commit_error)
                                # Handle connection errors
                                if 'EOF' in error_str or 'SSL SYSCALL' in error_str or 'connection' in error_str.lower():
                                    if commit_attempt < max_commit_retries - 1:
                                        db.session.rollback()
                                        time.sleep(0.5)
                                        # Re-add the classification
                                        db.session.add(new_classification)
                                        continue
                                    else:
                                        raise
                                # Handle duplicate key errors (unique constraint violation)
                                elif 'UniqueViolation' in error_str or 'duplicate key' in error_str.lower() or 'uq_user_message' in error_str:
                                    db.session.rollback()
                                    # Expire the object to clear it from session
                                    try:
                                        db.session.expunge(new_classification)
                                    except:
                                        pass
                                    # Clear all pending changes to ensure clean state for next email
                                    db.session.expire_all()
                                    print(f"⏭️  [TASK] Email {idx + 1}/{len(emails)} (message_id: {email.get('id', 'unknown')[:16]}...): Duplicate key error - already exists, skipping")
                                    duplicate_detected = True
                                    break  # Skip this email, continue to next
                                else:
                                    db.session.rollback()
                                    # Expire the object to clear it from session
                                    try:
                                        db.session.expunge(new_classification)
                                    except:
                                        pass
                                    # Clear all pending changes
                                    db.session.expire_all()
                                    raise
                        
                        if duplicate_detected:
                            emails_processed += 1
                            emails_skipped_duplicate += 1
                            # Ensure session is clean before processing next email
                            try:
                                db.session.rollback()
                                db.session.expire_all()
                            except:
                                pass
                            continue  # Skip to next email
                        
                        if not commit_success:
                            # Commit failed for other reasons, skip this email
                            emails_processed += 1
                            emails_failed_commit += 1
                            print(f"❌ [TASK] Email {idx + 1}/{len(emails)}: Commit failed, skipped")
                            continue
                    else:
                        # Not committing yet - just add to session (will commit in batch)
                        commit_success = True
                        duplicate_detected = False
                    
                    emails_processed += 1
                    emails_classified += 1
                    if (idx + 1) % 10 == 0 or emails_classified <= 5:  # Log first 5 and every 10th
                        print(f"✅ [TASK] Email {idx + 1}/{len(emails)}: Successfully classified and saved - Total classified: {emails_classified}")
                    
                    # Deal Flow specific processing
                    if classification_result['category'] == CATEGORY_DEAL_FLOW:
                        deck_links = [l for l in classification_result.get('links', []) if any(
                            ind in l.lower() for ind in ['docsend', 'dataroom', 'deck', 'drive.google.com', 'dropbox.com', 'notion.so']
                        )]
                        
                        if pdf_attachments:
                            pdf_filename = pdf_attachments[0].get('filename', 'deck.pdf')
                            if not deck_links:
                                new_classification.deck_link = f"[PDF Attachment: {pdf_filename}]"
                        
                        if deck_links and not new_classification.deck_link:
                            new_classification.deck_link = deck_links[0]
                        
                        # Check four basics
                        basics = classifier.check_four_basics(
                            email.get('subject', ''),
                            email_body,
                            classification_result.get('links', []),
                            attachment_text=attachment_text
                        )
                        
                        # Extract founder info
                        founder_email = email.get('from', '').split('<')[1].split('>')[0] if '<' in email.get('from', '') else email.get('from', '')
                        founder_name = email.get('from', '').split('<')[0].strip() if '<' in email.get('from', '') else ''
                        
                        # Create Deal record
                        deal = Deal(
                            user_id=user_id,
                            thread_id=email.get('thread_id', ''),
                            classification_id=new_classification.id,
                            founder_name=founder_name,
                            founder_email=founder_email,
                            subject=email.get('subject', ''),
                            deck_link=new_classification.deck_link,
                            has_deck=basics.get('has_deck', False) or bool(new_classification.deck_link),
                            has_team_info=basics.get('has_team_info', False),
                            has_traction=basics.get('has_traction', False),
                            has_round_info=basics.get('has_round_info', False),
                            state='New'  # Default state
                        )
                        db.session.add(deal)
                        # Commit with retry on connection errors
                        max_commit_retries = 3
                        for commit_attempt in range(max_commit_retries):
                            try:
                                db.session.commit()
                                # Send WhatsApp alert if enabled
                                try:
                                    from whatsapp_service import WhatsAppService
                                    user = User.query.get(user_id)
                                    
                                    if user:
                                        print(f"📱 [TASK] Checking WhatsApp for deal {deal.id}: enabled={user.whatsapp_enabled}, number={user.whatsapp_number[:10] + '...' if user.whatsapp_number else 'None'}")
                                        
                                        if user.whatsapp_enabled and user.whatsapp_number:
                                            print(f"📱 [TASK] Sending WhatsApp alert for deal {deal.id} to {user.whatsapp_number}")
                                            whatsapp = WhatsAppService()
                                            whatsapp.send_deal_alert(deal, user.whatsapp_number)
                                            deal.whatsapp_alert_sent = True
                                            deal.whatsapp_alert_sent_at = datetime.utcnow()
                                            db.session.commit()
                                            print(f"✅ [TASK] WhatsApp alert sent for deal {deal.id}")
                                        else:
                                            print(f"⚠️  [TASK] WhatsApp not enabled or number not set for user {user.id}")
                                    else:
                                        print(f"⚠️  [TASK] User {user_id} not found for WhatsApp alert")
                                except Exception as whatsapp_error:
                                    error_msg = str(whatsapp_error)
                                    print(f"❌ [TASK] WhatsApp alert failed for deal {deal.id}: {error_msg}")
                                    import traceback
                                    traceback.print_exc()
                                    # Don't fail the whole task if WhatsApp fails
                                break
                            except Exception as commit_error:
                                if 'EOF' in str(commit_error) or 'SSL SYSCALL' in str(commit_error) or 'connection' in str(commit_error).lower():
                                    if commit_attempt < max_commit_retries - 1:
                                        db.session.rollback()
                                        import time
                                        time.sleep(0.5)
                                        db.session.add(deal)
                                        continue
                                    else:
                                        raise
                                else:
                                    raise
                            except Exception as commit_error:
                                if 'EOF' in str(commit_error) or 'SSL SYSCALL' in str(commit_error) or 'connection' in str(commit_error).lower():
                                    if commit_attempt < max_commit_retries - 1:
                                        db.session.rollback()
                                        import time
                                        time.sleep(0.5)
                                        db.session.add(deal)
                                        continue
                                    else:
                                        raise
                                else:
                                    raise
                    
                except Exception as e:
                    error_msg = f"Error processing email {idx + 1}: {str(e)}"
                    errors.append(error_msg)
                    emails_processed += 1
                    # Ensure session is clean after any error
                    try:
                        db.session.rollback()
                        db.session.expire_all()
                    except:
                        pass
                    print(f"❌ [TASK] {error_msg}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Update history_id
            if new_history_id:
                if gmail_token:
                    gmail_token.history_id = new_history_id
                else:
                    gmail_token = GmailToken(user_id=user_id, history_id=new_history_id)
                    db.session.add(gmail_token)
                # Commit with retry on connection errors
                max_commit_retries = 3
                for commit_attempt in range(max_commit_retries):
                    try:
                        db.session.commit()
                        break
                    except Exception as commit_error:
                        if 'EOF' in str(commit_error) or 'SSL SYSCALL' in str(commit_error) or 'connection' in str(commit_error).lower():
                            if commit_attempt < max_commit_retries - 1:
                                db.session.rollback()
                                import time
                                time.sleep(0.5)
                                if gmail_token:
                                    db.session.add(gmail_token)
                                continue
                            else:
                                raise
                        else:
                            raise
            
            # Return results with detailed breakdown
            print(f"📊 [TASK] Classification complete:")
            print(f"   - Emails fetched from Gmail: {len(emails)}")
            print(f"   - Emails processed: {emails_processed}")
            print(f"   - Emails classified: {emails_classified}")
            print(f"   - Emails skipped (duplicate by message_id): {emails_skipped_duplicate}")
            print(f"   - Emails failed classification: {emails_failed_classification}")
            print(f"   - Emails failed commit: {emails_failed_commit}")
            print(f"   - Total errors: {len(errors)}")
            
            result = {
                'status': 'complete',
                'emails_processed': emails_processed,
                'emails_classified': emails_classified,
                'emails_skipped_duplicate': emails_skipped_duplicate,
                'emails_failed_classification': emails_failed_classification,
                'emails_failed_commit': emails_failed_commit,
                'total_fetched': len(emails),
                'errors': errors[:10]  # Limit error list
            }
            
            return result
            
        except Exception as e:
            error_msg = f"Task failed: {str(e)}"
            print(f"❌ {error_msg}")
            return {'status': 'error', 'error': error_msg}


@celery.task(bind=True, name='tasks.fetch_older_emails')
def fetch_older_emails(self, user_id, max_emails=200):
    """
    Background task to fetch older emails (before the initial 60) slowly to avoid rate limits.
    
    Args:
        user_id: User ID to fetch emails for
        max_emails: Maximum number of older emails to fetch (default 200)
    
    Returns:
        dict: Status and results
    """
    import os
    import time
    
    try:
        from app import app, db
    except ImportError:
        import sys
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        if '/app' not in sys.path:
            sys.path.insert(0, '/app')
        from app import app, db
    
    from models import User, GmailToken, EmailClassification
    from gmail_client import GmailClient
    from email_classifier import EmailClassifier
    from openai_client import OpenAIClient
    from lambda_client import LambdaClient
    from auth import decrypt_token
    from threading import Semaphore
    
    CLASSIFICATION_SEMAPHORE = Semaphore(20)  # Increased to 20 for faster processing
    
    print(f"📧 [TASK] fetch_older_emails STARTING for user {user_id}, max_emails={max_emails}")
    
    try:
        with app.app_context():
            print(f"📧 [TASK] App context acquired, starting task execution...")
            
            # Update task state
            try:
                self.update_state(
                    state='PROGRESS',
                    meta={'status': 'initializing', 'progress': 0, 'total': max_emails, 'fetched': 0, 'classified': 0}
                )
                print(f"📧 [TASK] Task state updated to PROGRESS")
            except Exception as state_error:
                print(f"⚠️ [TASK] Error updating state: {state_error}")
                # Continue anyway
            
            # Get user
            user = User.query.get(user_id)
            if not user:
                print(f"❌ [TASK] User {user_id} not found")
                return {'status': 'error', 'error': 'User not found'}
            
            if not user.gmail_token:
                print(f"❌ [TASK] User {user_id} has no Gmail token")
                return {'status': 'error', 'error': 'Gmail not connected'}
            
            # Get Gmail client
            print(f"🔐 [TASK] Decrypting token and creating Gmail client...")
            token_json = decrypt_token(user.gmail_token.encrypted_token)
            gmail = GmailClient(token_json=token_json)
            
            if not gmail.service:
                print(f"❌ [TASK] Failed to create Gmail service")
                return {'status': 'error', 'error': 'Failed to connect to Gmail'}
            
            print(f"✅ [TASK] Gmail client created successfully")
            
            # Progress callback to update task state
            def progress_callback(fetched, total):
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'status': 'fetching',
                        'progress': fetched,
                        'total': total,
                        'fetched': fetched,
                        'classified': 0
                    }
                )
            
            # Get existing message IDs to skip duplicates
            existing_classifications = EmailClassification.query.filter_by(user_id=user_id).all()
            existing_message_ids = {c.message_id for c in existing_classifications}
            existing_count = len(existing_message_ids)
            print(f"📊 Found {existing_count} existing emails in database, will skip duplicates")
            
            # Calculate how many more emails we need to reach max_emails total
            # If we already have 60 and want 200 total, we need 140 more
            needed_count = max(0, max_emails - existing_count)
            
            if needed_count == 0:
                print(f"✅ Already have {existing_count} emails (>= {max_emails}), no need to fetch more")
                return {
                    'status': 'complete',
                    'emails_fetched': 0,
                    'emails_classified': 0,
                    'message': f'Already have {existing_count} emails (target: {max_emails})'
                }
            
            print(f"📧 Starting to fetch older emails for user {user_id}: have {existing_count}, need {needed_count} more to reach {max_emails} total...")
            emails, next_page_token, total_fetched = gmail.get_older_emails(
                max_results=needed_count,  # Fetch only the needed amount
                progress_callback=progress_callback,
                skip_existing_ids=existing_message_ids
            )
            
            if not emails:
                return {
                    'status': 'complete',
                    'emails_fetched': 0,
                    'emails_classified': 0,
                    'message': 'No older emails found'
                }
            
            print(f"✅ Fetched {len(emails)} older emails. Starting classification...")
            
            # Initialize classifier
            openai_client = OpenAIClient()
            lambda_client = LambdaClient() if os.getenv('USE_LAMBDA', 'false').lower() == 'true' else None
            classifier = EmailClassifier(openai_client=openai_client, lambda_client=lambda_client)
            
            # Classify emails one by one (slowly to avoid rate limits)
            emails_classified = 0
            errors = []
            
            for idx, email in enumerate(emails):
                try:
                    # Update progress
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'status': 'classifying',
                            'progress': total_fetched,
                            'total': max_emails,
                            'fetched': total_fetched,
                            'classified': emails_classified,
                            'current': idx + 1
                        }
                    )
                    
                    # Check if email already exists (prevent duplicates)
                    existing_classification = EmailClassification.query.filter_by(
                        user_id=user_id,
                        message_id=email.get('id', '')
                    ).first()
                    
                    if existing_classification:
                        print(f"⏭️  Email {email.get('id', '')} already exists, skipping...")
                        emails_classified += 1
                        continue
                    
                    # Classify email
                    with CLASSIFICATION_SEMAPHORE:
                        classification_result = classifier.classify_email(
                            subject=email.get('subject', ''),
                            body=email.get('body', ''),
                            headers=email.get('headers', {}),
                            sender=email.get('from', ''),
                            thread_id=email.get('thread_id', ''),
                            user_id=str(user_id)
                        )
                    
                    # Store classification
                    new_classification = EmailClassification(
                        user_id=user_id,
                        thread_id=email.get('thread_id', ''),
                        message_id=email.get('id', ''),
                        sender=email.get('from', 'Unknown'),
                        email_date=email.get('date'),
                        category=classification_result['category'],
                        tags=','.join(classification_result.get('tags', [])),
                        confidence=classification_result.get('confidence', 0.0),
                        extracted_links=json.dumps(classification_result.get('links', []))
                    )
                    new_classification.set_subject_encrypted(email.get('subject', 'No Subject'))
                    new_classification.set_snippet_encrypted(email.get('snippet', ''))
                    db.session.add(new_classification)
                    
                    # Commit with retry and handle duplicate key errors
                    max_commit_retries = 3
                    commit_success = False
                    duplicate_detected = False
                    
                    for commit_attempt in range(max_commit_retries):
                        try:
                            db.session.commit()
                            commit_success = True
                            break
                        except Exception as commit_error:
                            error_str = str(commit_error)
                            # Handle connection errors
                            if 'EOF' in error_str or 'SSL SYSCALL' in error_str or 'connection' in error_str.lower():
                                if commit_attempt < max_commit_retries - 1:
                                    db.session.rollback()
                                    time.sleep(0.5)
                                    db.session.add(new_classification)
                                    continue
                                else:
                                    raise
                            # Handle duplicate key errors (unique constraint violation)
                            elif 'UniqueViolation' in error_str or 'duplicate key' in error_str.lower() or 'uq_user_message' in error_str:
                                db.session.rollback()
                                # Expire the object to clear it from session
                                try:
                                    db.session.expunge(new_classification)
                                except:
                                    pass
                                # Clear all pending changes to ensure clean state for next email
                                db.session.expire_all()
                                print(f"⏭️  [TASK] Email {idx + 1}/{len(emails)} (message_id: {email.get('id', 'unknown')[:16]}...): Duplicate key error - already exists, skipping")
                                duplicate_detected = True
                                break  # Skip this email, continue to next
                            else:
                                db.session.rollback()
                                # Expire the object to clear it from session
                                try:
                                    db.session.expunge(new_classification)
                                except:
                                    pass
                                raise
                    
                    if duplicate_detected:
                        emails_classified += 1  # Count as processed but not newly classified
                        continue  # Skip to next email
                    
                    if not commit_success:
                        # Commit failed for other reasons, skip this email
                        continue
                    
                    emails_classified += 1
                    
                    # Add delay between classifications (2 seconds for super slow background fetching)
                    if idx < len(emails) - 1:
                        time.sleep(2.0)
                    
                except Exception as e:
                    error_msg = f"Error processing email {idx}: {str(e)}"
                    print(f"⚠️  {error_msg}")
                    errors.append(error_msg)
                    continue
            
            print(f"✅ [TASK] fetch_older_emails completed: {emails_classified} emails classified")
            return {
                'status': 'complete',
                'emails_fetched': total_fetched,
                'emails_classified': emails_classified,
                'errors': errors[:10]
            }
    except Exception as e:
        # Catch all exceptions (both from app context and before)
        error_msg = f"Task failed: {str(e)}"
        print(f"❌ [TASK] fetch_older_emails exception: {error_msg}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': error_msg}



@celery.task(name='tasks.periodic_email_sync')
def periodic_email_sync():
    """
    Periodic task to check for new emails using incremental sync (Gmail History API)
    Runs every 5 minutes via Celery Beat
    Only syncs if user has 200+ emails already (initial setup complete)
    """
    try:
        from app import app, db
        from models import User, GmailToken
        
        with app.app_context():
            # Get all users with Gmail connected
            users = User.query.join(GmailToken).filter(
                GmailToken.history_id.isnot(None)
            ).all()
            
            print(f"🔄 [PERIODIC] Checking {len(users)} users for new emails...")
            
            synced_count = 0
            errors = []
            
            for user in users:
                try:
                    # Check if user has completed initial setup (has 200+ emails)
                    from models import EmailClassification
                    email_count = EmailClassification.query.filter_by(user_id=user.id).count()
                    
                    # Only sync if user has completed initial setup (has 200+ emails)
                    if email_count >= 200:
                        # Trigger incremental sync (no limit, force_full_sync=False)
                        # Call the task directly (we're in the same module)
                        task = sync_user_emails.delay(
                            user_id=user.id,
                            max_emails=200,  # This will be ignored for incremental sync
                            force_full_sync=False  # Use incremental sync
                        )
                        synced_count += 1
                        print(f"✅ [PERIODIC] Triggered incremental sync for user {user.id} (has {email_count} emails)")
                    else:
                        print(f"⏭️  [PERIODIC] Skipping user {user.id} - still in setup ({email_count} emails, need 200+)")
                        
                except Exception as e:
                    error_msg = f"Error syncing user {user.id}: {str(e)}"
                    errors.append(error_msg)
                    print(f"⚠️  [PERIODIC] {error_msg}")
                    continue
            
            print(f"📧 [PERIODIC] Sync complete: {synced_count} users synced, {len(errors)} errors")
            return {
                'status': 'complete',
                'users_synced': synced_count,
                'errors': errors[:10]
            }
            
    except Exception as e:
        error_msg = f"Periodic email sync failed: {str(e)}"
        print(f"❌ [PERIODIC] {error_msg}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': error_msg}

@celery.task(name='tasks.send_whatsapp_followups')
def send_whatsapp_followups():
    """
    Send follow-up WhatsApp messages for deals every 6 hours
    Runs periodically via Celery Beat
    """
    try:
        from app import app
        from models import db, Deal, User
        from whatsapp_service import WhatsAppService
        
        with app.app_context():
            whatsapp = WhatsAppService()
            six_hours_ago = datetime.utcnow() - timedelta(hours=6)
            
            # Find deals that need follow-ups:
            # 1. Alert was sent
            # 2. Last follow-up was >6 hours ago (or never)
            # 3. Deal state is still "New" or "Ask-More"
            # 4. User hasn't stopped follow-ups
            deals = Deal.query.filter(
                Deal.whatsapp_alert_sent == True,
                Deal.whatsapp_stopped == False,
                Deal.state.in_(['New', 'Ask-More']),
                (
                    (Deal.whatsapp_last_followup_at == None) |
                    (Deal.whatsapp_last_followup_at < six_hours_ago)
                )
            ).all()
            
            print(f"📱 [WHATSAPP] Checking {len(deals)} deals for follow-ups...")
            
            followups_sent = 0
            errors = []
            
            for deal in deals:
                try:
                    user = User.query.get(deal.user_id)
                    if not user or not user.whatsapp_enabled or not user.whatsapp_number:
                        continue
                    
                    deal.whatsapp_followup_count += 1
                    deal.whatsapp_last_followup_at = datetime.utcnow()
                    
                    whatsapp.send_followup(deal, user.whatsapp_number, deal.whatsapp_followup_count)
                    
                    db.session.commit()
                    followups_sent += 1
                    print(f"✅ [WHATSAPP] Follow-up #{deal.whatsapp_followup_count} sent for deal {deal.id}")
                    
                except Exception as e:
                    error_msg = f"Error sending follow-up for deal {deal.id}: {str(e)}"
                    errors.append(error_msg)
                    print(f"⚠️  [WHATSAPP] {error_msg}")
                    db.session.rollback()
                    continue
            
            print(f"📱 [WHATSAPP] Follow-up task complete: {followups_sent} sent, {len(errors)} errors")
            return {
                'status': 'complete',
                'followups_sent': followups_sent,
                'errors': errors[:10]
            }
            
    except Exception as e:
        error_msg = f"WhatsApp follow-up task failed: {str(e)}"
        print(f"❌ [WHATSAPP] {error_msg}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': error_msg}
