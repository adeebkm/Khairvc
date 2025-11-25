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
def sync_user_emails(self, user_id, max_emails=50, force_full_sync=False, new_history_id=None):
    """
    Background task to sync and classify emails for a user
    
    Args:
        user_id: User ID to sync emails for
        max_emails: Maximum number of emails to fetch
        force_full_sync: Force full sync (ignore history_id)
        new_history_id: Optional new history_id from Pub/Sub notification to update after sync
    
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
            deleted_message_ids = []
            label_changes = {}
            if start_history_id:
                # Incremental sync: fetch ALL new emails (no limit), deletions, and label changes
                print(f"📧 [TASK] Incremental sync: Fetching ALL new emails, deletions, and label changes since history_id={start_history_id}")
                # Use the internal method to get the full result with deletions and label changes
                result = gmail._get_emails_incremental(start_history_id, unread_only=False)
                emails = result['new_emails']
                deleted_message_ids = result['deleted_ids']
                label_changes = result.get('label_changes', {})  # NEW: Get label changes for read/unread sync
                api_history_id = result['history_id']  # History ID from Gmail API response
                
                # Process label changes (read/unread sync from Gmail)
                if label_changes:
                    print(f"🏷️  [TASK] Processing {len(label_changes)} label changes (read/unread sync)...")
                    
                    # Store label changes for frontend to fetch (real-time sync)
                    import time
                    from app import pending_label_changes
                    
                    if user_id not in pending_label_changes:
                        pending_label_changes[user_id] = {}
                    
                    for message_id, change_info in label_changes.items():
                        is_read = change_info['is_read']
                        label_ids = change_info.get('label_ids', [])
                        
                        # Store for frontend polling
                        pending_label_changes[user_id][message_id] = {
                            'is_read': is_read,
                            'label_ids': label_ids,
                            'timestamp': time.time()
                        }
                        
                        # Update classification in database (if exists)
                        classification = EmailClassification.query.filter_by(
                            user_id=user_id,
                            message_id=message_id
                        ).first()
                        
                        if classification:
                            # Note: EmailClassification doesn't have is_read field
                            # Frontend will update UI cache when it polls for changes
                            print(f"  {'✅' if is_read else '📧'} Message {message_id[:16]}: marked as {'read' if is_read else 'unread'} in Gmail")
                        else:
                            print(f"  ⚠️  Message {message_id[:16]}: label changed but not in database (may not be classified yet)")
                    
                    print(f"✅ [TASK] Processed {len(label_changes)} label changes, stored for frontend sync")
                
                # Process deletions from Gmail
                if deleted_message_ids:
                    print(f"🗑️  [TASK] Processing {len(deleted_message_ids)} deleted emails...")
                    deleted_count = EmailClassification.query.filter(
                        EmailClassification.user_id == user_id,
                        EmailClassification.message_id.in_(deleted_message_ids)
                    ).delete(synchronize_session=False)
                    db.session.commit()
                    print(f"🗑️  [TASK] Removed {deleted_count} deleted emails from database")
            else:
                # Full sync: respect max_emails limit
                print(f"📧 [TASK] Full sync: Fetching up to {max_emails} emails...")
                emails, api_history_id = gmail.get_emails(
                    max_results=max_emails,
                    unread_only=False,
                    start_history_id=None
                )
            if start_history_id:
                print(f"📧 [TASK] Incremental sync: Fetched {len(emails)} new emails, {len(deleted_message_ids)} deletions")
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
            
            # Check for unprocessed emails BEFORE processing new ones
            # This allows bidirectional classification to work on existing unprocessed emails
            unprocessed_count_before = EmailClassification.query.filter_by(
                user_id=user_id,
                processed=False
            ).count()
            
            print(f"📊 [TASK] Unprocessed emails before processing: {unprocessed_count_before}")
            
            # If there are many unprocessed emails OR this is an initial sync (200 emails),
            # trigger bidirectional classification and let it handle both old and new emails
            # Initial syncs should always use bidirectional for faster processing
            is_initial_sync = emails and len(emails) >= 200 and unprocessed_count_before == 0
            should_use_bidirectional = unprocessed_count_before > 50 or is_initial_sync
            
            if should_use_bidirectional:
                if is_initial_sync:
                    print(f"🚀 [TASK] Initial sync detected ({len(emails)} emails). Using bidirectional classification for faster processing.")
                else:
                    print(f"🚀 [TASK] Many unprocessed emails ({unprocessed_count_before}) detected. Will trigger bidirectional classification after inserting new emails.")
            
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
            classifications_to_mark_processed = []  # Track classifications to mark as processed after commit
            
            for idx, email in enumerate(emails):
                message_id = email.get('id', '')
                
                # Skip if we've already processed this message_id in this task run
                if message_id in processed_message_ids:
                    emails_skipped_duplicate += 1
                    print(f"⏭️  [TASK] Email {idx + 1}/{len(emails)}: Skipped (already processed in this task run: {message_id[:16]}...)")
                    continue
                
                processed_message_ids.add(message_id)
                try:
                    # Check if email already exists FIRST (before any processing to save API calls and prevent re-processing)
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
                    
                    # If email exists and is already processed, skip entirely (no re-classification, no PDF extraction)
                    if existing_classification and existing_classification.processed:
                        emails_processed += 1
                        emails_skipped_duplicate += 1
                        if (idx + 1) % 10 == 0 or emails_skipped_duplicate <= 5:  # Log first 5 and every 10th
                            print(f"⏭️  [TASK] Email {idx + 1}/{len(emails)}: Skipped (already processed: {email.get('id', 'unknown')[:16]}...) - Total skipped: {emails_skipped_duplicate}")
                        continue  # Skip this email entirely - already processed
                    
                    # If email exists but not processed, skip it (might be in progress or failed - don't reprocess)
                    if existing_classification:
                        emails_processed += 1
                        emails_skipped_duplicate += 1
                        if (idx + 1) % 10 == 0 or emails_skipped_duplicate <= 5:  # Log first 5 and every 10th
                            print(f"⏭️  [TASK] Email {idx + 1}/{len(emails)}: Skipped (exists but not processed: {email.get('id', 'unknown')[:16]}...) - Total skipped: {emails_skipped_duplicate}")
                        continue  # Skip this email entirely
                    
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
                    
                    # If using bidirectional classification, skip inline classification
                    # Just insert the email with processed=False and let bidirectional workers handle it
                    if should_use_bidirectional:
                        # Insert email without classification (bidirectional workers will classify it)
                        new_classification = EmailClassification(
                            user_id=user_id,
                            thread_id=email.get('thread_id', ''),
                            message_id=email.get('id', ''),
                            sender=email.get('from', 'Unknown'),
                            email_date=email.get('date'),
                            category='GENERAL',  # Temporary category, will be updated by bidirectional workers
                            tags='',
                            confidence=0.0,
                            processed=False,  # Not processed yet - bidirectional workers will handle it
                            extracted_links=json.dumps([])
                        )
                        # Use encrypted field setters
                        new_classification.set_subject_encrypted(email.get('subject', 'No Subject'))
                        new_classification.set_snippet_encrypted(email.get('snippet', ''))
                        db.session.add(new_classification)
                        emails_processed += 1
                        print(f"📝 [TASK] Email {idx + 1}/{len(emails)}: Inserted with processed=False (will be classified by bidirectional workers)")
                        continue  # Skip to next email
                    
                    # Normal inline classification flow
                    # Extract email data (only if not already processed)
                    headers = email.get('headers', {})
                    # Use combined_text if available (includes attachment content, limited to 1500 chars)
                    # Otherwise fall back to body
                    email_body = email.get('combined_text', email.get('body', ''))
                    
                    # Extract attachment text from combined_text if present (for check_four_basics)
                    attachment_text = None
                    if '--- Attachment Content ---' in email_body:
                        # Extract just the attachment portion (already limited to 1500 chars in gmail_client)
                        parts = email_body.split('--- Attachment Content ---')
                        if len(parts) > 1:
                            attachment_text = parts[1].strip()
                            # Ensure it doesn't exceed 1500 chars (safety check)
                            if len(attachment_text) > 1500:
                                attachment_text = attachment_text[:1500] + "... [truncated]"
                    
                    pdf_attachments = []
                    if email.get('attachments'):
                        for att in email['attachments']:
                            if att.get('mimeType', '').startswith('application/pdf'):
                                pdf_attachments.append(att)
                    
                    # Classify email (with rate limiting)
                    try:
                        with CLASSIFICATION_SEMAPHORE:
                            print(f"🤖 [TASK] Email {idx + 1}/{len(emails)}: Classifying (message_id: {email.get('id', 'unknown')[:16]}...)")
                            print(f"   📧 Subject: {email.get('subject', 'No Subject')[:50]}")
                            print(f"   👤 From: {email.get('from', 'Unknown')[:50]}")
                            classification_result = classifier.classify_email(
                                subject=email.get('subject', ''),
                                body=email_body,
                                headers=headers,
                                sender=email.get('from', ''),
                                thread_id=email.get('thread_id', ''),
                                user_id=str(user_id)
                            )
                            category = classification_result.get('category', 'UNKNOWN')
                            confidence = classification_result.get('confidence', 0.0)
                            print(f"✅ [TASK] Email {idx + 1}/{len(emails)}: Classified as {category} (confidence: {confidence:.2f})")
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
                    # Track non-deal-flow classifications to mark as processed after successful commit
                    # Deal-flow emails will be marked as processed after deal creation
                    if classification_result['category'] != CATEGORY_DEAL_FLOW:
                        classifications_to_mark_processed.append(new_classification)
                    
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
                                # Mark all classifications in this batch as processed (prevents re-processing)
                                # But only if not using bidirectional classification
                                if not should_use_bidirectional:
                                    for classification in classifications_to_mark_processed:
                                        if not classification.processed:
                                            classification.processed = True
                                    # Commit the processed flags
                                    if any(not c.processed for c in classifications_to_mark_processed):
                                        db.session.commit()
                                # Clear the list after successful commit
                                classifications_to_mark_processed = []
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
                    deal_created = False
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
                                deal_created = True
                                # Mark email as fully processed (classification + deal creation complete)
                                new_classification.processed = True
                                db.session.commit()
                                # Send WhatsApp alert if enabled
                                try:
                                    from whatsapp_service import WhatsAppService
                                    user = User.query.get(user_id)
                                    
                                    if user:
                                        print(f"📱 [TASK] Checking WhatsApp for deal {deal.id}: enabled={user.whatsapp_enabled}, number={user.whatsapp_number[:10] + '...' if user.whatsapp_number else 'None'}")
                                        
                                        # Only send WhatsApp alerts for NEW emails from Pub/Sub, not initial sync
                                        if new_history_id is not None:
                                            if user.whatsapp_enabled and user.whatsapp_number:
                                                print(f"📱 [TASK] Sending WhatsApp alert for deal {deal.id} to {user.whatsapp_number}")
                                                print(f"   📧 Deal subject: {deal.subject or 'No subject'}")
                                                print(f"   👤 Founder: {deal.founder_name or 'Unknown'}")
                                                whatsapp = WhatsAppService()
                                                whatsapp.send_deal_alert(deal, user.whatsapp_number)
                                                deal.whatsapp_alert_sent = True
                                                deal.whatsapp_alert_sent_at = datetime.utcnow()
                                                db.session.commit()
                                                print(f"✅ [TASK] WhatsApp alert sent for deal {deal.id}")
                                            else:
                                                print(f"⚠️  [TASK] WhatsApp not enabled or number not set for user {user.id}")
                                                print(f"   Enabled: {user.whatsapp_enabled}, Number: {user.whatsapp_number[:10] + '...' if user.whatsapp_number else 'None'}")
                                        else:
                                            print(f"📧 [TASK] Skipping WhatsApp alert for deal {deal.id} (initial sync, not real-time notification)")
                                    else:
                                        print(f"⚠️  [TASK] User {user_id} not found for WhatsApp alert")
                                except Exception as whatsapp_error:
                                    error_msg = str(whatsapp_error)
                                    print(f"❌ [TASK] WhatsApp alert failed for deal {deal.id}: {error_msg}")
                                    
                                    # Check if it's an access token expiration error
                                    if '401' in error_msg or 'expired' in error_msg.lower() or 'OAuthException' in error_msg:
                                        print(f"⚠️  [TASK] WhatsApp access token has expired. Please update WHATSAPP_ACCESS_TOKEN in Railway environment variables.")
                                        print(f"   Get a new token from: https://developers.facebook.com/apps/")
                                    
                                    import traceback
                                    traceback.print_exc()
                                    # Don't fail the whole task if WhatsApp fails
                                
                                # Send auto-reply for deal flow emails (only for new emails, not initial sync)
                                # Check if this is an incremental sync (new email, not initial 200)
                                # Use new_history_id for Pub/Sub notifications, fallback to start_history_id for regular syncs
                                is_incremental_sync = (new_history_id is not None) or (start_history_id is not None)
                                if is_incremental_sync:
                                    # Before sending, check if we've already auto-replied for this thread
                                    try:
                                        from models import EmailClassification  # Local import to avoid circulars
                                        existing_auto_reply = EmailClassification.query.filter_by(
                                            user_id=user_id,
                                            thread_id=email.get('thread_id', ''),
                                            reply_sent=True
                                        ).first()
                                    except Exception:
                                        existing_auto_reply = None
                                    
                                    if existing_auto_reply:
                                        print(f"📧 [TASK] Skipping auto-reply for deal {deal.id} - reply already sent for thread {email.get('thread_id', '')}")
                                    else:
                                        # Check if auto-reply is enabled
                                        # Default to enabled unless explicitly disabled
                                        auto_reply_disabled = os.getenv('AUTO_REPLY_DISABLED', 'false').lower() == 'true'
                                        send_emails = os.getenv('SEND_EMAILS', 'false').lower() == 'true'
                                        
                                        # Auto-reply is enabled if:
                                        # 1. AUTO_REPLY_DISABLED is not true, AND
                                        # 2. SEND_EMAILS is true (required for sending emails)
                                        if not auto_reply_disabled and send_emails:
                                            # Schedule auto-reply to send after 10 minutes instead of immediately
                                            try:
                                                # Extract sender email
                                                sender_email = email.get('from', '')
                                                if '<' in sender_email and '>' in sender_email:
                                                    sender_email = sender_email.split('<')[1].split('>')[0]
                                                
                                                # Generate nice "we'll reply soon" message
                                                reply_subject = email.get('subject', 'No Subject')
                                                if not reply_subject.startswith('Re:'):
                                                    reply_subject = f"Re: {reply_subject}"
                                                
                                                # Create a professional, warm auto-reply message (HTML format to preserve signature)
                                                founder_greeting = founder_name if founder_name else 'there'
                                                reply_body = f"""<p>Hi {founder_greeting},</p>
<p>Thank you for reaching out and sharing your opportunity with us. We've received your email and are currently reviewing it.</p>
<p>We appreciate you taking the time to connect, and we'll get back to you soon with our thoughts and next steps.</p>
<p>Looking forward to learning more about your venture.</p>
<p>Best regards</p>"""
                                                
                                                # Schedule delayed auto-reply (10 minutes = 600 seconds)
                                                from celery_config import celery
                                                celery.send_task(
                                                    'tasks.send_delayed_auto_reply',
                                                    args=[user_id, deal.id, sender_email, reply_subject, reply_body, email.get('thread_id', ''), new_classification.id],
                                                    countdown=600  # 10 minutes delay
                                                )
                                                print(f"📧 [TASK] Scheduled auto-reply for deal {deal.id} to {sender_email} (will send in 10 minutes)")
                                            except Exception as schedule_error:
                                                error_msg = str(schedule_error)
                                                print(f"❌ [TASK] Failed to schedule auto-reply for deal {deal.id}: {error_msg}")
                                                import traceback
                                                traceback.print_exc()
                                                # Don't fail the whole task if scheduling fails
                                        else:
                                            if not send_emails:
                                                print(f"📧 [TASK] Email sending disabled (SEND_EMAILS=false), skipping auto-reply for deal {deal.id}")
                                            else:
                                                print(f"📧 [TASK] Auto-reply disabled (AUTO_REPLY_DISABLED=true), skipping auto-reply for deal {deal.id}")
                                else:
                                    print(f"📧 [TASK] Skipping auto-reply for deal {deal.id} (initial sync, not new email)")
                                
                                # Trigger scheduled email generation for new deal flow emails
                                # Only for incremental sync (new emails), not initial 200
                                # Use new_history_id for Pub/Sub notifications, fallback to start_history_id for regular syncs
                                if is_incremental_sync:
                                    try:
                                        # Use celery.send_task to avoid circular import
                                        from celery_config import celery
                                        print(f"📅 [TASK] About to trigger scheduled email generation for deal {deal.id} (is_incremental_sync=True)")
                                        result = celery.send_task('tasks.generate_scheduled_email', args=[deal.id])
                                        print(f"📅 [TASK] ✅ Triggered scheduled email generation for deal {deal.id} (task_id: {result.id})")
                                    except Exception as schedule_error:
                                        print(f"⚠️  [TASK] ❌ Failed to trigger scheduled email generation for deal {deal.id}: {str(schedule_error)}")
                                        import traceback
                                        traceback.print_exc()
                                        # Don't fail the whole task if scheduling fails
                                else:
                                    print(f"📅 [TASK] Skipping scheduled email generation for deal {deal.id} (not incremental sync: new_history_id={new_history_id}, start_history_id={start_history_id})")
                                
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
            # Priority: Use new_history_id from Pub/Sub notification if provided, otherwise use the one from Gmail API response
            final_history_id = None
            if new_history_id:  # From Pub/Sub notification parameter (passed in)
                final_history_id = new_history_id
                print(f"📊 [TASK] Using history_id from Pub/Sub notification: {final_history_id}")
            elif 'api_history_id' in locals() and api_history_id:  # From Gmail API response
                final_history_id = api_history_id
                print(f"📊 [TASK] Using history_id from Gmail API response: {final_history_id}")
            
            if final_history_id:
                if gmail_token:
                    gmail_token.history_id = final_history_id
                else:
                    gmail_token = GmailToken(user_id=user_id, history_id=final_history_id)
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
            
            # Check for unprocessed emails and trigger bidirectional classification if needed
            unprocessed_count = EmailClassification.query.filter_by(
                user_id=user_id,
                processed=False
            ).count()
            
            print(f"📊 [TASK] Unprocessed emails after processing: {unprocessed_count}")
            
            # Trigger bidirectional classification if:
            # 1. We used bidirectional mode (should_use_bidirectional was True) - always trigger
            # 2. OR there are many unprocessed emails (>50)
            should_trigger_bidirectional = should_use_bidirectional or unprocessed_count > 50
            
            if should_trigger_bidirectional:
                if should_use_bidirectional:
                    print(f"🚀 [TASK] Triggering bidirectional classification for {unprocessed_count} unprocessed emails (bidirectional mode enabled)")
                else:
                    print(f"🚀 [TASK] Triggering bidirectional classification for {unprocessed_count} unprocessed emails")
                
                try:
                    # Start forward worker (oldest first)
                    forward_task = classify_bidirectional.apply_async(
                        args=[user_id, 50, 'forward'],
                        queue='email_sync'
                    )
                    print(f"✅ [TASK] Started forward worker: {forward_task.id}")
                    
                    # Start backward worker (newest first)
                    backward_task = classify_bidirectional.apply_async(
                        args=[user_id, 50, 'backward'],
                        queue='email_sync'
                    )
                    print(f"✅ [TASK] Started backward worker: {backward_task.id}")
                except Exception as e:
                    print(f"⚠️  [TASK] Failed to start bidirectional workers: {e}")
            
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
                'unprocessed_count': unprocessed_count,
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
                    
                    # Check if email already exists and is processed (prevent duplicates and re-processing)
                    existing_classification = EmailClassification.query.filter_by(
                        user_id=user_id,
                        message_id=email.get('id', '')
                    ).first()
                    
                    if existing_classification:
                        if existing_classification.processed:
                            print(f"⏭️  Email {email.get('id', '')} already processed, skipping...")
                        else:
                            print(f"⏭️  Email {email.get('id', '')} exists but not processed, skipping...")
                        emails_classified += 1
                        continue
                    
                    # Classify email
                    with CLASSIFICATION_SEMAPHORE:
                        # Use combined_text if available (includes attachment content, limited to 1500 chars)
                        email_body_for_classification = email.get('combined_text', email.get('body', ''))
                        classification_result = classifier.classify_email(
                            subject=email.get('subject', ''),
                            body=email_body_for_classification,
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
                            # Mark as processed after successful classification (prevents re-processing)
                            # But only if not using bidirectional classification
                            if not should_use_bidirectional:
                                new_classification.processed = True
                                db.session.commit()
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
        from app import app, db
    except ImportError:
        import sys
        import os
        # Add the parent directory to the path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, current_dir)
        from app import app, db
    
    from models import Deal, User
    from whatsapp_service import WhatsAppService
    
    try:
        with app.app_context():
            whatsapp = WhatsAppService()
            six_hours_ago = datetime.utcnow() - timedelta(hours=6)
            
            # Find deals that need follow-ups:
            # 1. Alert was sent
            # 2. Alert was sent >6 hours ago (for first follow-up)
            # 3. Last follow-up was >6 hours ago (for subsequent follow-ups)
            # 4. Deal state is still "New" or "Ask-More"
            # 5. User hasn't stopped follow-ups
            deals = Deal.query.filter(
                Deal.whatsapp_alert_sent == True,
                Deal.whatsapp_stopped == False,
                Deal.state.in_(['New', 'Ask-More']),
                # First follow-up: alert sent >6 hours ago AND no follow-up sent yet
                (
                    (
                        (Deal.whatsapp_last_followup_at == None) &
                        (Deal.whatsapp_alert_sent_at < six_hours_ago)
                    ) |
                    # Subsequent follow-ups: last follow-up >6 hours ago
                    (
                        (Deal.whatsapp_last_followup_at != None) &
                        (Deal.whatsapp_last_followup_at < six_hours_ago)
                    )
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
                    
                    # Check if first email in thread has been replied to
                    try:
                        from gmail_client import GmailClient
                        from auth import decrypt_token
                        
                        if not user.gmail_token:
                            print(f"⚠️  [WHATSAPP] No Gmail token for user {user.id}, skipping deal {deal.id}")
                            continue
                        
                        token_json = decrypt_token(user.gmail_token.encrypted_token)
                        gmail = GmailClient(token_json=token_json)
                        
                        # Get thread messages
                        thread_messages = gmail.get_thread_messages(deal.thread_id)
                        
                        if not thread_messages:
                            print(f"⚠️  [WHATSAPP] Could not fetch thread messages for deal {deal.id}")
                            continue
                        
                        # Check if any message in thread is from user (sent by us)
                        has_reply = False
                        user_email = user.email.lower()
                        
                        for message in thread_messages:
                            from_header = message.get('from', '').lower()
                            # Check if message is from user (sent by us)
                            if user_email in from_header or f'<{user_email}>' in from_header:
                                has_reply = True
                                print(f"⏭️  [WHATSAPP] Skipping follow-up for deal {deal.id} - reply already sent (found in thread)")
                                break
                        
                        if has_reply:
                            continue
                            
                    except Exception as check_error:
                        print(f"⚠️  [WHATSAPP] Error checking thread for deal {deal.id}: {str(check_error)}")
                        # Continue anyway - don't block follow-up if check fails
                        import traceback
                        traceback.print_exc()
                    
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


@celery.task(name='tasks.send_delayed_auto_reply')
def send_delayed_auto_reply(user_id, deal_id, sender_email, reply_subject, reply_body, thread_id, classification_id):
    """
    Send delayed auto-reply (10 minutes after email received)
    This task is scheduled with countdown=600 (10 minutes)
    """
    try:
        from app import app, db
    except ImportError:
        import sys
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, current_dir)
        from app import app, db
    
    from models import User, EmailClassification
    from gmail_client import GmailClient
    from auth import decrypt_token
    
    try:
        with app.app_context():
            # Check if reply was already sent manually (don't send if user already replied)
            classification = EmailClassification.query.get(classification_id)
            if not classification:
                print(f"⚠️  [AUTO-REPLY] Classification {classification_id} not found, skipping auto-reply")
                return {'status': 'skipped', 'reason': 'Classification not found'}
            
            # Check if reply was already sent (either manually or by another auto-reply)
            if classification.reply_sent:
                print(f"📧 [AUTO-REPLY] Skipping auto-reply for deal {deal_id} - reply already sent")
                return {'status': 'skipped', 'reason': 'Reply already sent'}
            
            user = User.query.get(user_id)
            if not user or not user.gmail_token:
                print(f"⚠️  [AUTO-REPLY] User {user_id} or Gmail token not found")
                return {'status': 'error', 'error': 'User or Gmail token not found'}
            
            # Get Gmail client
            token_json = decrypt_token(user.gmail_token.encrypted_token)
            gmail = GmailClient(token_json=token_json)
            
            # Get user's selected signature email preference
            selected_email = user.gmail_token.selected_signature_email if user.gmail_token else None
            
            # Send the auto-reply
            print(f"📧 [AUTO-REPLY] Sending delayed auto-reply for deal {deal_id} to {sender_email}")
            success = gmail.send_reply(
                to_email=sender_email,
                subject=reply_subject,
                body=reply_body,
                thread_id=thread_id,
                send_as_email=selected_email
            )
            
            if success:
                print(f"✅ [AUTO-REPLY] Auto-reply sent successfully for deal {deal_id}")
                # Mark classification as replied so we never auto-reply this thread again
                try:
                    classification.reply_sent = True
                    db.session.commit()
                except Exception as mark_error:
                    print(f"⚠️  [AUTO-REPLY] Failed to mark auto-reply as sent for deal {deal_id}: {mark_error}")
                    db.session.rollback()
                return {'status': 'success', 'deal_id': deal_id}
            else:
                print(f"⚠️  [AUTO-REPLY] Failed to send auto-reply for deal {deal_id}")
                return {'status': 'error', 'error': 'Failed to send email'}
                
    except Exception as e:
        error_msg = f"Delayed auto-reply failed: {str(e)}"
        print(f"❌ [AUTO-REPLY] {error_msg}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': error_msg}


@celery.task(name='tasks.generate_scheduled_email')
def generate_scheduled_email(deal_id):
    """
    Generate scheduled email for a deal using Lambda/Kimi AI
    Creates a scheduled email that will be sent after 6 hours if no reply is sent
    """
    print(f"📅 [SCHEDULED] Starting scheduled email generation for deal {deal_id}")
    try:
        from app import app, db
    except ImportError:
        import sys
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, current_dir)
        from app import app, db
    
    from models import Deal, User, ScheduledEmail
    from gmail_client import GmailClient
    from lambda_client import LambdaClient
    from auth import decrypt_token
    
    try:
        with app.app_context():
            deal = Deal.query.get(deal_id)
            if not deal:
                print(f"❌ [SCHEDULED] Deal {deal_id} not found")
                return {'status': 'error', 'error': 'Deal not found'}
            
            user = User.query.get(deal.user_id)
            if not user or not user.gmail_token:
                return {'status': 'error', 'error': 'User or Gmail token not found'}
            
            # Check if scheduled email already exists for this deal
            existing = ScheduledEmail.query.filter_by(
                deal_id=deal.id,
                status='pending'
            ).first()
            
            if existing:
                print(f"⏭️  [SCHEDULED] Scheduled email already exists for deal {deal.id}")
                return {'status': 'skipped', 'reason': 'Already exists'}
            
            # Get Gmail client
            token_json = decrypt_token(user.gmail_token.encrypted_token)
            gmail = GmailClient(token_json=token_json)
            
            # Get first email in thread
            thread_messages = gmail.get_thread_messages(deal.thread_id)
            if not thread_messages:
                return {'status': 'error', 'error': 'Thread not found'}
            
            first_email = thread_messages[0]  # First email in thread
            
            # Extract email data
            email_subject = first_email.get('subject', deal.subject or 'No Subject')
            email_body = first_email.get('body', '')
            email_sender = first_email.get('from', deal.founder_email or '')
            
            # Call Lambda to generate email
            try:
                lambda_client = LambdaClient()
                generated_body = lambda_client.generate_scheduled_email(
                    subject=email_subject,
                    body=email_body,
                    sender=email_sender,
                    founder_name=deal.founder_name,
                    thread_id=deal.thread_id,
                    user_id=str(user.id)
                )
            except Exception as lambda_error:
                print(f"❌ [SCHEDULED] Lambda error for deal {deal.id}: {str(lambda_error)}")
                return {'status': 'error', 'error': f'Lambda error: {str(lambda_error)}'}
            
            # Create scheduled email
            scheduled_at = datetime.utcnow() + timedelta(hours=6)
            scheduled_email = ScheduledEmail(
                user_id=user.id,
                deal_id=deal.id,
                thread_id=deal.thread_id,
                to_email=deal.founder_email or email_sender,
                subject=f"Re: {email_subject}" if not email_subject.startswith('Re:') else email_subject,
                body=generated_body,
                scheduled_at=scheduled_at,
                status='pending'
            )
            
            db.session.add(scheduled_email)
            db.session.commit()
            
            print(f"✅ [SCHEDULED] Generated scheduled email for deal {deal.id}, scheduled for {scheduled_at}")
            
            return {
                'status': 'success',
                'scheduled_email_id': scheduled_email.id,
                'scheduled_at': scheduled_at.isoformat()
            }
            
    except Exception as e:
        error_msg = f"Scheduled email generation failed: {str(e)}"
        print(f"❌ [SCHEDULED] {error_msg}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': error_msg}


@celery.task(name='tasks.send_scheduled_emails')
def send_scheduled_emails():
    """
    Send scheduled emails that are due
    Runs periodically via Celery Beat
    Checks if reply has been sent, cancels if so, otherwise sends the email
    """
    try:
        from app import app, db
    except ImportError:
        import sys
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, current_dir)
        from app import app, db
    
    from models import ScheduledEmail, User, Deal
    from gmail_client import GmailClient
    from auth import decrypt_token
    
    try:
        with app.app_context():
            now = datetime.utcnow()
            
            # Get scheduled emails that are due and pending
            scheduled_emails = ScheduledEmail.query.filter(
                ScheduledEmail.status == 'pending',
                ScheduledEmail.scheduled_at <= now
            ).all()
            
            print(f"📧 [SCHEDULED] Checking {len(scheduled_emails)} scheduled emails...")
            
            sent_count = 0
            cancelled_count = 0
            failed_count = 0
            errors = []
            
            for scheduled_email in scheduled_emails:
                try:
                    user = User.query.get(scheduled_email.user_id)
                    if not user or not user.gmail_token:
                        print(f"⚠️  [SCHEDULED] User or Gmail token not found for scheduled email {scheduled_email.id}")
                        continue
                    
                    # Check if reply has been sent (same logic as WhatsApp follow-up)
                    try:
                        token_json = decrypt_token(user.gmail_token.encrypted_token)
                        gmail = GmailClient(token_json=token_json)
                        
                        thread_messages = gmail.get_thread_messages(scheduled_email.thread_id)
                        
                        if not thread_messages:
                            print(f"⚠️  [SCHEDULED] Could not fetch thread for scheduled email {scheduled_email.id}")
                            continue
                        
                        # Check if any message is from user
                        has_reply = False
                        user_email = user.email.lower()
                        
                        for message in thread_messages:
                            from_header = message.get('from', '').lower()
                            if user_email in from_header or f'<{user_email}>' in from_header:
                                has_reply = True
                                break
                        
                        if has_reply:
                            # Cancel scheduled email - reply already sent
                            scheduled_email.status = 'cancelled'
                            scheduled_email.cancelled_at = datetime.utcnow()
                            db.session.commit()
                            cancelled_count += 1
                            print(f"⏭️  [SCHEDULED] Cancelled scheduled email {scheduled_email.id} - reply already sent")
                            continue
                            
                    except Exception as check_error:
                        print(f"⚠️  [SCHEDULED] Error checking thread for scheduled email {scheduled_email.id}: {str(check_error)}")
                        # Continue anyway - try to send
                    
                    # Send the scheduled email
                    selected_email = user.gmail_token.selected_signature_email if user.gmail_token else None
                    success = gmail.send_reply(
                        to_email=scheduled_email.to_email,
                        subject=scheduled_email.subject,
                        body=scheduled_email.body,
                        thread_id=scheduled_email.thread_id,
                        send_as_email=selected_email
                    )
                    
                    if success:
                        scheduled_email.status = 'sent'
                        scheduled_email.sent_at = datetime.utcnow()
                        sent_count += 1
                        print(f"✅ [SCHEDULED] Sent scheduled email {scheduled_email.id}")
                    else:
                        scheduled_email.status = 'failed'
                        failed_count += 1
                        print(f"⚠️  [SCHEDULED] Failed to send scheduled email {scheduled_email.id}")
                    
                    db.session.commit()
                    
                except Exception as e:
                    error_msg = f"Error processing scheduled email {scheduled_email.id}: {str(e)}"
                    errors.append(error_msg)
                    print(f"❌ [SCHEDULED] {error_msg}")
                    db.session.rollback()
                    continue
            
            print(f"📧 [SCHEDULED] Task complete: {sent_count} sent, {cancelled_count} cancelled, {failed_count} failed, {len(errors)} errors")
            return {
                'status': 'complete',
                'sent': sent_count,
                'cancelled': cancelled_count,
                'failed': failed_count,
                'errors': errors[:10]
            }
            
    except Exception as e:
        error_msg = f"Scheduled email sending task failed: {str(e)}"
        print(f"❌ [SCHEDULED] {error_msg}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': error_msg}


@celery.task(bind=True, name='tasks.process_pubsub_notification', time_limit=300, soft_time_limit=270)
def process_pubsub_notification(self, user_id, history_id):
    """
    High-priority task to process Pub/Sub notifications instantly.
    This task runs on the dedicated pubsub_notifications queue with a dedicated worker.
    
    Args:
        user_id: User ID to sync emails for
        history_id: Gmail history ID from Pub/Sub notification
    
    Returns:
        dict: Status and results
    """
    # Import inside function to avoid circular imports
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
    
    from models import User, GmailToken
    from gmail_client import GmailClient
    from auth import decrypt_token
    
    with app.app_context():
        try:
            print(f"🚀 [PUB/SUB] Processing notification instantly for user {user_id}, historyId: {history_id}")
            
            # Get user
            user = User.query.get(user_id)
            if not user:
                return {'status': 'error', 'error': 'User not found'}
            
            if not user.gmail_token:
                return {'status': 'error', 'error': 'Gmail not connected'}
            
            # IMPORTANT: Don't update history_id yet! We need to use the OLD history_id to query for changes
            # The notification gives us the NEW history_id (955507), but we need to query FROM the OLD one
            # Store the old history_id for the sync, then update to new one after sync completes
            old_history_id = user.gmail_token.history_id if user.gmail_token else None
            print(f"📊 [PUB/SUB] Current stored history_id: {old_history_id}, Notification history_id: {history_id}")
            
            # IMPORTANT: Add a delay before syncing to allow Gmail to fully process the email
            # Pub/Sub notifications can arrive before Gmail has finished processing the email
            # Wait 5 seconds to ensure the email is available in Gmail's History API
            import time
            print(f"⏳ [PUB/SUB] Waiting 5 seconds for Gmail to process email before syncing...")
            print(f"📊 [PUB/SUB] Will query from history_id {old_history_id} to {history_id}")
            time.sleep(5)
            
            # CRITICAL: Ensure we use the OLD history_id for querying
            # Temporarily set it back if it was already updated (defensive programming)
            if user.gmail_token and user.gmail_token.history_id != old_history_id:
                print(f"⚠️  [PUB/SUB] History_id was already updated to {user.gmail_token.history_id}, resetting to {old_history_id} for query")
                user.gmail_token.history_id = old_history_id
                db.session.commit()
            
            # Trigger incremental sync using the OLD history_id (so it queries from old to new)
            # Pass the new history_id as a parameter so we can update it after sync
            from tasks import sync_user_emails
            # Queue sync task on email_sync queue (not pubsub queue - keep pubsub queue for notifications only)
            # Pass new_history_id so sync can update it after processing
            sync_task = sync_user_emails.apply_async(
                args=[user_id, 10000],  # High limit for incremental sync
                kwargs={
                    'force_full_sync': False,  # Use incremental sync with history_id
                    'new_history_id': str(history_id)  # New history_id to update after sync
                },
                queue='email_sync',  # Route to email_sync queue
                countdown=3  # Additional 3 second delay before task starts (total 8 seconds)
            )
            
            print(f"✅ [PUB/SUB] Queued incremental sync task {sync_task.id} for user {user_id}")
            
            return {
                'status': 'success',
                'sync_task_id': sync_task.id,
                'user_id': user_id,
                'history_id': history_id
            }
            
        except Exception as e:
            error_msg = f"Pub/Sub notification processing failed: {str(e)}"
            print(f"❌ [PUB/SUB] {error_msg}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'error': error_msg}


@celery.task(bind=True, name='tasks.classify_bidirectional')
def classify_bidirectional(self, user_id, batch_size=50, direction='forward'):
    """
    Classify emails from either end (forward or backward)
    Used for faster classification when there are many unprocessed emails
    
    Args:
        user_id: User to classify for
        batch_size: Number of emails to process in this batch
        direction: 'forward' (oldest→newest) or 'backward' (newest→oldest)
    """
    # Import inside function to avoid circular imports
    # Try multiple import strategies for Railway worker
    import os
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
    
    from models import EmailClassification
    from email_classifier import EmailClassifier
    from openai_client import OpenAIClient
    
    with app.app_context():
        try:
            print(f"🔄 [BIDIRECTIONAL] Starting {direction} classification for user {user_id} (batch size: {batch_size})")
            
            # Get unprocessed emails in the specified order
            query = EmailClassification.query.filter_by(
                user_id=user_id,
                processed=False
            )
            
            if direction == 'forward':
                query = query.order_by(EmailClassification.email_date.asc())
            else:  # backward
                query = query.order_by(EmailClassification.email_date.desc())
            
            emails = query.limit(batch_size).all()
            
            if not emails:
                print(f"✅ [BIDIRECTIONAL] No more unprocessed emails for user {user_id} (direction: {direction})")
                return {'status': 'complete', 'direction': direction, 'classified': 0}
            
            print(f"🔄 [BIDIRECTIONAL] Processing {len(emails)} emails (direction: {direction})")
            
            # Initialize classifier
            try:
                openai_client = OpenAIClient()
                classifier = EmailClassifier(openai_client)
            except Exception as e:
                print(f"❌ [BIDIRECTIONAL] Failed to initialize classifier: {e}")
                return {'status': 'error', 'error': str(e), 'direction': direction}
            
            classified_count = 0
            skipped_count = 0
            
            for email in emails:
                # Use SELECT FOR UPDATE to prevent race conditions
                try:
                    with db.session.begin_nested():
                        email_locked = db.session.query(EmailClassification).filter_by(
                            id=email.id
                        ).with_for_update(nowait=True).first()
                        
                        if not email_locked or email_locked.processed:
                            skipped_count += 1
                            continue
                        
                        # Check if email has minimum required data
                        if not email_locked.subject and not email_locked.snippet:
                            print(f"⚠️  [BIDIRECTIONAL] Skipping email {email_locked.message_id[:16]}: No subject or snippet")
                            email_locked.processed = True
                            email_locked.category = 'GENERAL'
                            email_locked.confidence = 0.0
                            skipped_count += 1
                            continue
                        
                        # Classify the email
                        try:
                            # Log progress for each email
                            print(f"🤖 [BIDIRECTIONAL] Classifying email {classified_count + skipped_count + 1}/{len(emails)} (direction: {direction}, message_id: {email_locked.message_id[:16]}...)")
                            print(f"   📧 Subject: {(email_locked.subject or 'No Subject')[:50]}")
                            print(f"   👤 From: {(email_locked.sender or 'Unknown')[:50]}")
                            
                            # Call classify_email with keyword arguments (not a dictionary)
                            classification_result = classifier.classify_email(
                                subject=email_locked.subject or '',
                                body=email_locked.snippet or '',  # Use snippet as body for classification
                                headers={},  # Headers not stored in EmailClassification model
                                sender=email_locked.sender or '',
                                thread_id=email_locked.thread_id or '',
                                user_id=str(user_id)
                            )
                            
                            # Update classification
                            category = classification_result.get('category', 'GENERAL')
                            confidence = classification_result.get('confidence', 0.0)
                            tags = classification_result.get('tags', [])
                            
                            email_locked.category = category
                            email_locked.tags = ','.join(tags) if isinstance(tags, list) else tags
                            email_locked.confidence = confidence
                            email_locked.processed = True
                            
                            classified_count += 1
                            
                            print(f"✅ [BIDIRECTIONAL] Email classified as {category} (confidence: {confidence:.2f})")
                            
                            # If this is a deal flow email, create Deal record
                            if category == 'DEAL_FLOW':
                                from models import Deal
                                
                                # Check if deal already exists for this thread
                                existing_deal = Deal.query.filter_by(
                                    user_id=user_id,
                                    thread_id=email_locked.thread_id
                                ).first()
                                
                                if not existing_deal:
                                    # Create Deal record
                                    founder_name = email_locked.sender.split('<')[0].strip() if email_locked.sender else 'Unknown'
                                    founder_email = email_locked.sender if email_locked.sender else ''
                                    
                                    deal = Deal(
                                        user_id=user_id,
                                        thread_id=email_locked.thread_id,
                                        classification_id=email_locked.id,
                                        founder_name=founder_name,
                                        founder_email=founder_email,
                                        subject=email_locked.subject or '',
                                        deck_link=email_locked.deck_link,
                                        has_deck=bool(email_locked.deck_link),
                                        has_team_info=False,
                                        has_traction=False,
                                        state='NEW'
                                    )
                                    db.session.add(deal)
                                    print(f"📊 [BIDIRECTIONAL] Created Deal record for thread {email_locked.thread_id[:16]}")
                            
                            if classified_count % 10 == 0:
                                print(f"📊 [BIDIRECTIONAL] {direction}: {classified_count} classified, {skipped_count} skipped")
                            
                        except Exception as e:
                            import traceback
                            print(f"❌ [BIDIRECTIONAL] Error classifying email {email_locked.message_id[:16] if email_locked else 'unknown'}: {e}")
                            print(f"   Traceback: {traceback.format_exc()}")
                            continue
                    
                    db.session.commit()
                    
                except Exception as e:
                    if 'could not obtain lock' in str(e).lower() or 'nowait' in str(e).lower():
                        # Another worker is processing this email, skip it
                        skipped_count += 1
                        db.session.rollback()
                        continue
                    else:
                        print(f"❌ [BIDIRECTIONAL] Database error: {e}")
                        db.session.rollback()
                        continue
            
            # Check if there are more emails to process
            remaining = EmailClassification.query.filter_by(
                user_id=user_id,
                processed=False
            ).count()
            
            print(f"✅ [BIDIRECTIONAL] {direction} batch complete: {classified_count} classified, {skipped_count} skipped, {remaining} remaining")
            
            # Continue processing if there are more emails
            if remaining > 0 and classified_count > 0:
                # Queue next batch
                classify_bidirectional.apply_async(
                    args=[user_id, batch_size, direction],
                    countdown=2,  # Wait 2 seconds before next batch
                    queue='email_sync'
                )
                print(f"📋 [BIDIRECTIONAL] Queued next {direction} batch")
            
            return {
                'status': 'processing' if remaining > 0 else 'complete',
                'direction': direction,
                'classified': classified_count,
                'skipped': skipped_count,
                'remaining': remaining
            }
            
        except Exception as e:
            error_msg = f"Bidirectional classification failed: {str(e)}"
            print(f"❌ [BIDIRECTIONAL] {error_msg}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'error': error_msg, 'direction': direction}
