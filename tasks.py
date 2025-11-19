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
    try:
        from app import app, db
    except ImportError:
        # Fallback: add current directory to path and try again
        import sys
        import os
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
                    db.session.commit()
                
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
            
            # Initialize classifier
            openai_client = OpenAIClient()
            # EmailClassifier initializes LambdaClient internally, don't pass it
            classifier = EmailClassifier(openai_client)
            
            # Process emails
            emails_processed = 0
            emails_classified = 0
            errors = []
            
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
                    
                    # Check if already classified
                    existing = EmailClassification.query.filter_by(
                        user_id=user_id,
                        thread_id=email.get('thread_id', '')
                    ).first()
                    
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
                    # Use encrypted field setters
                    new_classification.set_subject_encrypted(email.get('subject', 'No Subject'))
                    new_classification.set_snippet_encrypted(email.get('snippet', ''))
                    
                    db.session.add(new_classification)
                    db.session.commit()
                    
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
                        db.session.commit()
                    
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
                db.session.commit()
            
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

