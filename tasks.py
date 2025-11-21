"""
Background tasks for email processing
"""
import os
import sys
import json
from celery import current_task
from celery_config import celery

# Ensure the app directory is in Python path (for Railway worker)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

# Import models and clients inside functions to avoid circular imports


@celery.task(bind=True, name='tasks.sync_user_emails')
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
    CLASSIFICATION_SEMAPHORE = Semaphore(10)
    
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
            emails, new_history_id = gmail.get_emails(
                max_results=max_emails,
                unread_only=False,
                start_history_id=start_history_id
            )
            
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
            errors = []
            
            import time  # For rate limiting delays
            
            for idx, email in enumerate(emails):
                try:
                    # Update progress
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'status': 'classifying',
                            'progress': idx + 1,
                            'total': len(emails),
                            'current_email': email.get('subject', 'No Subject')[:50]
                        }
                    )
                    
                    # Check if already classified (with retry on connection errors)
                    max_retries = 3
                    existing = None
                    for attempt in range(max_retries):
                        try:
                            existing = EmailClassification.query.filter_by(
                                user_id=user_id,
                                thread_id=email.get('thread_id', '')
                            ).first()
                            break
                        except Exception as db_error:
                            if 'EOF' in str(db_error) or 'SSL SYSCALL' in str(db_error) or 'connection' in str(db_error).lower():
                                if attempt < max_retries - 1:
                                    db.session.rollback()
                                    import time
                                    time.sleep(0.5)
                                    continue
                                else:
                                    raise
                            else:
                                raise
                    
                    if existing:
                        emails_processed += 1
                        continue
                    
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
                    
                    # Classify email (with rate limiting)
                    with CLASSIFICATION_SEMAPHORE:
                        classification_result = classifier.classify_email(
                            subject=email.get('subject', ''),
                            body=email_body,
                            headers=headers,
                            sender=email.get('from', ''),
                            thread_id=email.get('thread_id', ''),
                            user_id=str(user_id)
                        )
                    
                    # Add delay between classifications to avoid rate limits
                    # 1 second delay for background fetches (silent, can take time)
                    if idx < len(emails) - 1:  # Don't delay after last email
                        time.sleep(1.0)  # 1 second delay between emails
                    
                    # Check if email already exists (prevent duplicates)
                    existing_classification = EmailClassification.query.filter_by(
                        user_id=user_id,
                        message_id=email.get('id', '')
                    ).first()
                    
                    if existing_classification:
                        # Update existing classification instead of creating duplicate
                        new_classification = existing_classification
                        new_classification.category = classification_result['category']
                        new_classification.tags = ','.join(classification_result.get('tags', []))
                        new_classification.confidence = classification_result.get('confidence', 0.0)
                        new_classification.extracted_links = json.dumps(classification_result.get('links', []))
                        new_classification.sender = email.get('from', 'Unknown')
                        new_classification.email_date = email.get('date')
                        # Update encrypted fields
                        new_classification.set_subject_encrypted(email.get('subject', 'No Subject'))
                        new_classification.set_snippet_encrypted(email.get('snippet', ''))
                    else:
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
                                    # Re-add the classification
                                    db.session.add(new_classification)
                                    continue
                                else:
                                    raise
                            else:
                                raise
                    
                    emails_processed += 1
                    emails_classified += 1
                    
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
                    
                except Exception as e:
                    error_msg = f"Error processing email {idx + 1}: {str(e)}"
                    errors.append(error_msg)
                    print(f"⚠️  {error_msg}")
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
            
            # Return results
            result = {
                'status': 'complete',
                'emails_processed': emails_processed,
                'emails_classified': emails_classified,
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
    
    CLASSIFICATION_SEMAPHORE = Semaphore(10)
    
    with app.app_context():
        try:
            # Update task state
            self.update_state(
                state='PROGRESS',
                meta={'status': 'initializing', 'progress': 0, 'total': max_emails, 'fetched': 0, 'classified': 0}
            )
            
            # Get user
            user = User.query.get(user_id)
            if not user:
                return {'status': 'error', 'error': 'User not found'}
            
            if not user.gmail_token:
                return {'status': 'error', 'error': 'Gmail not connected'}
            
            # Get Gmail client
            token_json = decrypt_token(user.gmail_token.encrypted_token)
            gmail = GmailClient(token_json=token_json)
            
            if not gmail.service:
                return {'status': 'error', 'error': 'Failed to connect to Gmail'}
            
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
            
            # Fetch older emails slowly
            print(f"📧 Starting to fetch older emails for user {user_id} (target: {max_emails})...")
            emails, next_page_token, total_fetched = gmail.get_older_emails(
                max_results=max_emails,
                progress_callback=progress_callback
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
                    
                    # Commit with retry
                    max_commit_retries = 3
                    for commit_attempt in range(max_commit_retries):
                        try:
                            db.session.commit()
                            break
                        except Exception as commit_error:
                            if 'EOF' in str(commit_error) or 'SSL SYSCALL' in str(commit_error) or 'connection' in str(commit_error).lower():
                                if commit_attempt < max_commit_retries - 1:
                                    db.session.rollback()
                                    time.sleep(0.5)
                                    db.session.add(new_classification)
                                    continue
                                else:
                                    raise
                            else:
                                raise
                    
                    emails_classified += 1
                    
                    # Add delay between classifications (2 seconds for super slow background fetching)
                    if idx < len(emails) - 1:
                        time.sleep(2.0)
                    
                except Exception as e:
                    error_msg = f"Error processing email {idx}: {str(e)}"
                    print(f"⚠️  {error_msg}")
                    errors.append(error_msg)
                    continue
            
            return {
                'status': 'complete',
                'emails_fetched': total_fetched,
                'emails_classified': emails_classified,
                'errors': errors[:10]
            }
            
        except Exception as e:
            error_msg = f"Task failed: {str(e)}"
            print(f"❌ {error_msg}")
            return {'status': 'error', 'error': error_msg}

