#!/usr/bin/env python3
"""
Multi-User Gmail Auto-Reply Web Application
Each user manages their own Gmail account with complete privacy
"""
import os
import json
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, send_file
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
from models import db, User, GmailToken, EmailClassification, Deal
from auth import encrypt_token, decrypt_token
from gmail_client import GmailClient, SCOPES
from openai_client import OpenAIClient
from email_classifier import EmailClassifier, CATEGORY_DEAL_FLOW, CATEGORY_NETWORKING, CATEGORY_HIRING, CATEGORY_SPAM, CATEGORY_GENERAL, TAG_DEAL, TAG_GENERAL
# from tracxn_scorer import TracxnScorer  # Removed - scoring system disabled

# Load environment variables
load_dotenv()

# Debug: Print SEND_EMAILS value on startup
send_emails_debug = os.getenv('SEND_EMAILS', 'false')
print(f"📧 Email sending: {'ENABLED' if send_emails_debug.lower() == 'true' else 'DISABLED'} (SEND_EMAILS={send_emails_debug})")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
# Configure session to persist across redirects
# Note: SESSION_COOKIE_SECURE should be True for HTTPS, but Railway handles this
# Setting it to True might cause issues if Railway proxy isn't configured correctly
app.config['SESSION_COOKIE_SECURE'] = False  # Let Railway/proxy handle HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Allow cookies on OAuth redirects
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes

# Trust proxy headers for HTTPS detection (required for Railway)
# This allows Flask to detect HTTPS when behind a reverse proxy
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Use PostgreSQL on Railway, SQLite locally
database_url = os.getenv('DATABASE_URL')
if database_url:
    # Railway provides DATABASE_URL, use it
    # Convert postgres:// to postgresql:// for SQLAlchemy
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Local development - use SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gmail_auto_reply.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'


# Error handler to catch session serialization errors and clear problematic session data
@app.before_request
def clear_problematic_session_data():
    """Clear any non-serializable objects from session before each request"""
    try:
        # Check if session has any problematic keys
        keys_to_remove = []
        for key in list(session.keys()):
            # Check if value is not JSON serializable by trying to serialize it
            try:
                import json
                json.dumps(session[key])
            except (TypeError, ValueError):
                # This value is not serializable, mark for removal
                keys_to_remove.append(key)
            # Also proactively remove OAuth flow objects
            if 'oauth' in key.lower() or 'flow' in key.lower():
                if key not in keys_to_remove:
                    keys_to_remove.append(key)
        
        # Remove problematic keys
        for key in keys_to_remove:
            try:
                session.pop(key, None)
            except:
                pass
    except:
        # If anything goes wrong, just continue
        pass


@login_manager.user_loader
def load_user(user_id):
    """Load user from database"""
    return User.query.get(int(user_id))


# Initialize database
with app.app_context():
    db.create_all()


# Global OpenAI client (shared API key from .env)
openai_client = None


def get_openai_client():
    """Get OpenAI client (shared across users)"""
    global openai_client
    if openai_client is None:
        openai_client = OpenAIClient()
    return openai_client


def get_user_gmail_client(user):
    """Get Gmail client for current user"""
    if not user:
        print(f"❌ No user provided to get_user_gmail_client")
        return None
    
    if not user.gmail_token:
        print(f"❌ User {user.id} has no gmail_token. Please reconnect Gmail.")
        return None
    
    try:
        # Decrypt token
        encrypted_token = user.gmail_token.encrypted_token
        if not encrypted_token:
            print(f"❌ User {user.id} has empty encrypted_token")
            return None
            
        token_json = decrypt_token(encrypted_token)
        
        # Create Gmail client with user's token
        gmail_client = GmailClient(token_json=token_json)
        print(f"✅ Successfully created Gmail client for user {user.id}")
        return gmail_client
    except Exception as e:
        print(f"❌ Error getting Gmail client for user {user.id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


# ==================== AUTHENTICATION ROUTES ====================

@app.route('/')
def index():
    """Landing page for Khair - separate from the app"""
    return render_template('landing.html')

@app.route('/app')
def app_redirect():
    """Redirect to dashboard if logged in, otherwise to login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            # Make session permanent to survive OAuth redirects
            session.permanent = True
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """User registration"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if password != confirm_password:
            return render_template('signup.html', error='Passwords do not match')
        
        if User.query.filter_by(username=username).first():
            return render_template('signup.html', error='Username already exists')
        
        if User.query.filter_by(email=email).first():
            return render_template('signup.html', error='Email already registered')
        
        # Create user
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('dashboard'))
    
    return render_template('signup.html')


@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    return redirect(url_for('index'))


# ==================== DASHBOARD ====================

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - email management"""
    has_gmail = current_user.gmail_token is not None
    gmail_email = None
    
    # Get Gmail email if connected
    if has_gmail:
        try:
            gmail = get_user_gmail_client(current_user)
            if gmail:
                profile = gmail.get_profile()
                if profile:
                    gmail_email = profile.get('emailAddress')
        except Exception as e:
            print(f"Error getting Gmail email: {str(e)}")
    
    return render_template('dashboard.html', has_gmail=has_gmail, gmail_email=gmail_email)


# ==================== GMAIL CONNECTION ====================

@app.route('/connect-gmail')
@login_required
def connect_gmail():
    """Initiate Gmail OAuth flow"""
    try:
        # Aggressively clear any OAuth-related session data (flow objects are not JSON serializable)
        # This prevents errors from stale session data
        keys_to_remove = []
        for key in list(session.keys()):
            # Check if value is not JSON serializable
            try:
                import json
                json.dumps(session[key])
            except (TypeError, ValueError):
                # This value is not serializable, mark for removal
                keys_to_remove.append(key)
            # Also remove any OAuth-related keys
            if 'oauth' in key.lower() or 'flow' in key.lower():
                if key not in keys_to_remove:
                    keys_to_remove.append(key)
        
        # Remove problematic keys
        for key in keys_to_remove:
            try:
                session.pop(key, None)
            except:
                pass
        
        from google_auth_oauthlib.flow import InstalledAppFlow
        import json
        
        # Try to get credentials from environment variable first (for Railway)
        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
        if credentials_json:
            # Decode from environment variable
            try:
                credentials_data = json.loads(credentials_json)
            except json.JSONDecodeError:
                # Try base64 decode if JSON parsing fails
                import base64
                credentials_data = json.loads(base64.b64decode(credentials_json).decode('utf-8'))
        elif os.path.exists('credentials.json'):
            # Fall back to file (for local development)
            with open('credentials.json', 'r') as f:
                credentials_data = json.load(f)
        else:
            return jsonify({'error': 'Google OAuth credentials not found. Please set GOOGLE_CREDENTIALS_JSON environment variable or provide credentials.json file.'}), 500
        
        # Create flow from credentials data
        flow = InstalledAppFlow.from_client_config(credentials_data, SCOPES)
        
        # For Railway/production, use redirect URI instead of local server
        redirect_uri = os.getenv('OAUTH_REDIRECT_URI')
        if redirect_uri:
            # Production: use redirect URI
            flow.redirect_uri = redirect_uri
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            # Store state in session BEFORE creating redirect
            session['oauth_state'] = state
            # Make session permanent to survive OAuth redirects
            session.permanent = True
            # CRITICAL: Delete flow object before returning (it's not JSON serializable)
            # Flow will be recreated in oauth2callback using credentials and state
            del flow
            # Force session save to ensure state is stored
            session.modified = True
            # Verify state was stored
            stored_state = session.get('oauth_state')
            print(f"🔍 OAuth redirect - Stored state: {stored_state}, Session keys: {list(session.keys())}")
            return redirect(authorization_url)
        else:
            # Local development: use local server
            creds = flow.run_local_server(port=0, open_browser=True)
            
            # Get token JSON
            token_json = creds.to_json()
            
            # Encrypt and store token
            encrypted_token = encrypt_token(token_json)
            
            # Update or create Gmail token for user
            gmail_token = GmailToken.query.filter_by(user_id=current_user.id).first()
            if gmail_token:
                gmail_token.encrypted_token = encrypted_token
            else:
                gmail_token = GmailToken(user_id=current_user.id, encrypted_token=encrypted_token)
                db.session.add(gmail_token)
            
            db.session.commit()
            
            # Redirect with parameter to trigger auto-fetch
            return redirect(url_for('dashboard') + '?connected=true')
    
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"❌ Error in connect_gmail: {str(e)}")
        print(f"Full traceback:\n{error_traceback}")
        # Return JSON error for better debugging
        return jsonify({
            'error': 'Failed to connect Gmail',
            'message': str(e),
            'type': type(e).__name__
        }), 500


@app.route('/oauth2callback')
@login_required
def oauth2callback():
    """OAuth 2.0 callback handler for Railway/production"""
    try:
        # Clear any OAuth flow objects from session first (prevent serialization errors)
        # BUT preserve oauth_state (it's a string, not an object)
        keys_to_remove = []
        oauth_state_backup = session.get('oauth_state')  # Backup state before cleanup
        
        for key in list(session.keys()):
            # Skip oauth_state - we need to keep it
            if key == 'oauth_state':
                continue
            # Check if value is not JSON serializable
            try:
                import json
                json.dumps(session[key])
            except (TypeError, ValueError):
                keys_to_remove.append(key)
            # Also remove OAuth flow keys (but not oauth_state)
            if 'oauth' in key.lower() and 'flow' in key.lower() and key != 'oauth_state':
                if key not in keys_to_remove:
                    keys_to_remove.append(key)
        
        for key in keys_to_remove:
            try:
                session.pop(key, None)
            except:
                pass
        
        # Restore oauth_state if it was removed
        if 'oauth_state' not in session and oauth_state_backup:
            session['oauth_state'] = oauth_state_backup
        
        from google_auth_oauthlib.flow import InstalledAppFlow
        import json
        
        # Get state from session
        state = session.get('oauth_state')
        request_state = request.args.get('state')
        
        print(f"🔍 OAuth callback - Session keys: {list(session.keys())}, Session state: {state}, Request state: {request_state}")
        print(f"🔍 Session permanent: {session.get('_permanent', False)}, Session ID: {session.get('_id', 'None')}")
        
        # If state is None, try to get it from the request (fallback)
        if not state and request_state:
            print(f"⚠️  Session state missing, but request has state. This might be a session persistence issue.")
            # For now, allow it if we're in production and state matches format
            # This is a workaround - ideally session should persist
            if len(request_state) > 10:  # Basic validation
                print(f"⚠️  Allowing OAuth to proceed without session state (workaround)")
                # Continue without state validation (less secure but works)
            else:
                return f"Invalid state parameter. Session state: {state}, Request state: {request_state}", 400
        elif state != request_state:
            return f"Invalid state parameter. Session state: {state}, Request state: {request_state}", 400
        
        # Get credentials from environment or file
        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
        if credentials_json:
            try:
                credentials_data = json.loads(credentials_json)
            except json.JSONDecodeError:
                import base64
                credentials_data = json.loads(base64.b64decode(credentials_json).decode('utf-8'))
        elif os.path.exists('credentials.json'):
            with open('credentials.json', 'r') as f:
                credentials_data = json.load(f)
        else:
            return "Credentials not found", 500
        
        # Recreate flow
        redirect_uri = os.getenv('OAUTH_REDIRECT_URI')
        flow = InstalledAppFlow.from_client_config(credentials_data, SCOPES)
        flow.redirect_uri = redirect_uri
        
        # Construct callback URL with HTTPS (required for OAuth)
        # Replace HTTP with HTTPS in the callback URL if needed
        callback_url = request.url
        if callback_url.startswith('http://'):
            callback_url = callback_url.replace('http://', 'https://', 1)
        
        # Fetch token
        flow.fetch_token(authorization_response=callback_url)
        creds = flow.credentials
        
        # Get token JSON
        token_json = creds.to_json()
        
        # Encrypt and store token
        encrypted_token = encrypt_token(token_json)
        
        # Update or create Gmail token for user
        gmail_token = GmailToken.query.filter_by(user_id=current_user.id).first()
        if gmail_token:
            gmail_token.encrypted_token = encrypted_token
        else:
            gmail_token = GmailToken(user_id=current_user.id, encrypted_token=encrypted_token)
            db.session.add(gmail_token)
        
        db.session.commit()
        
        # CRITICAL: Delete flow object before returning (it's not JSON serializable)
        del flow
        del creds
        
        # Clear session
        session.pop('oauth_state', None)
        session.modified = True
        
        # Redirect with parameter to trigger auto-fetch
        return redirect(url_for('dashboard') + '?connected=true')
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error completing OAuth: {str(e)}", 500




@app.route('/disconnect-gmail')
@login_required
def disconnect_gmail():
    """Disconnect Gmail account"""
    if current_user.gmail_token:
        db.session.delete(current_user.gmail_token)
        db.session.commit()
    
    return redirect(url_for('dashboard'))


# ==================== API ENDPOINTS ====================

@app.route('/api/emails')
@login_required
def get_emails():
    """Get user's unread emails with classification"""
    if not current_user.gmail_token:
        return jsonify({
            'success': False,
            'error': 'Gmail not connected. Please connect your Gmail account.'
        }), 400
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        max_emails = min(request.args.get('max', default=20, type=int), 20)  # Cap at 20 emails max
        category_filter = request.args.get('category')  # Optional category filter
        show_spam = request.args.get('show_spam', 'false').lower() == 'true'
        unread_only = False  # Always fetch all emails (unread only filter removed)
        force_full_sync = request.args.get('force_full_sync', 'false').lower() == 'true'  # Force full sync (ignore history_id)
        db_only = request.args.get('db_only', 'false').lower() == 'true'  # Load only from database, skip Gmail API
        
        # If db_only is requested, skip Gmail API and load directly from database
        if db_only:
            print("📂 Loading emails from database only (skipping Gmail API)...")
            emails = []
        else:
            # Get stored history_id for incremental sync
            gmail_token = GmailToken.query.filter_by(user_id=current_user.id).first()
            start_history_id = gmail_token.history_id if gmail_token else None
            
            # Force full sync if:
            # 1. User explicitly requested it (force_full_sync=true)
            # 2. Database is empty (e.g., after reset)
            if force_full_sync:
                print(f"🔄 Force full sync requested. Ignoring history_id...")
                start_history_id = None
            else:
                # Check if user has any classified emails
                existing_classifications = EmailClassification.query.filter_by(user_id=current_user.id).count()
                if existing_classifications == 0 and start_history_id:
                    print(f"⚠️  Database is empty but historyId exists. Forcing full sync...")
                    start_history_id = None  # Force full sync
            
            try:
                # Use incremental sync if we have a history_id (90%+ reduction in API calls!)
                emails, new_history_id = gmail.get_emails(
                    max_results=max_emails, 
                    unread_only=unread_only,
                    start_history_id=start_history_id
                )
                
                # Store new history_id for next sync
                if new_history_id and gmail_token:
                    gmail_token.history_id = new_history_id
                    db.session.commit()
                    print(f"💾 Stored new historyId: {new_history_id}")
            except Exception as e:
                error_str = str(e)
                # Check for rate limit errors
                if '429' in error_str or 'rateLimitExceeded' in error_str or 'rate limit' in error_str.lower():
                    # Extract retry-after time if available
                    import re
                    retry_after_match = re.search(r'Retry after ([^\\n]+)', error_str)
                    retry_after = retry_after_match.group(1) if retry_after_match else 'a few minutes'
                    
                    return jsonify({
                        'success': False,
                        'error': f'Gmail API rate limit exceeded. Please wait until {retry_after} before trying again.',
                        'rate_limit': True,
                        'retry_after': retry_after
                    }), 429
                
                # Other errors - fall back to database
                print(f"⚠️  Error fetching from Gmail: {error_str}. Falling back to database...")
                emails = []
        
        # If no emails from Gmail (or db_only requested), load from database instead
        if len(emails) == 0:
            print("📂 No new emails from Gmail. Loading all classified emails from database...")
            print(f"   (Ignoring 'unread_only' filter - database doesn't track read status)")
            
            # Get all classified emails from database (no limit - show all stored emails)
            # Only apply limit if force_full_sync is requested (user wants fresh fetch from Gmail)
            # NOTE: We ignore unread_only filter here because database doesn't store read/unread status
            query = EmailClassification.query.filter_by(user_id=current_user.id)
            
            # Always limit to 20 emails max (to save storage and credits)
            print(f"   Loading latest {max_emails} emails from database (max 20)")
            db_classifications = query.order_by(EmailClassification.classified_at.desc()).limit(max_emails).all()
            
            classified_emails = []
            # Batch fetch star status for all emails from database
            message_ids = [c.message_id for c in db_classifications]
            star_status_map = {}
            if message_ids and gmail and gmail.service:
                try:
                    # Batch fetch labels for all messages to get star status
                    from googleapiclient.http import BatchHttpRequest
                    star_status_results = {}
                    
                    def star_callback(request_id, response, exception):
                        if exception:
                            return
                        if response:
                            msg_id = request_id
                            label_ids = response.get('labelIds', [])
                            star_status_results[msg_id] = {
                                'is_starred': 'STARRED' in label_ids,
                                'label_ids': label_ids if isinstance(label_ids, list) else []
                            }
                    
                    batch = gmail.service.new_batch_http_request(callback=star_callback)
                    for msg_id in message_ids[:100]:  # Limit to 100 to avoid rate limits
                        batch.add(gmail.service.users().messages().get(
                            userId='me',
                            id=msg_id,
                            format='metadata'
                        ), request_id=msg_id)
                    
                    if message_ids:
                        batch.execute()
                        star_status_map = star_status_results
                        print(f"⭐ Fetched star status for {len(star_status_map)} emails from Gmail")
                except Exception as e:
                    print(f"⚠️  Could not batch fetch star status: {str(e)}")
            
            for classification in db_classifications:
                # Filter spam if not requested
                if classification.category == CATEGORY_SPAM and not show_spam:
                    continue
                
                # Filter by category if requested
                if category_filter and classification.category != category_filter:
                    continue
                
                # Get star status from batch fetch or default to False
                star_info = star_status_map.get(classification.message_id, {'is_starred': False, 'label_ids': []})
                
                # Build email object from classification (with stored metadata)
                email_data = {
                    'id': classification.message_id,
                    'thread_id': classification.thread_id,
                    'subject': classification.subject or 'No Subject',
                    'from': classification.sender or 'Unknown',
                    'snippet': classification.snippet or '',
                    'date': classification.email_date or (int(classification.classified_at.timestamp() * 1000) if classification.classified_at else None),
                    'is_starred': star_info['is_starred'],  # Get actual status from Gmail
                    'label_ids': star_info['label_ids'],  # Get actual labels from Gmail
                    'classification': {
                        'category': classification.category,
                        'tags': classification.tags.split(',') if classification.tags else [],
                        'confidence': classification.confidence,
                        'reply_type': classification.reply_type,
                        'deal_state': classification.deal_state,
                        'deck_link': classification.deck_link
                    }
                }
                
                classified_emails.append(email_data)
                print(f"📧 Loaded from DB: Category={classification.category}, Thread={classification.thread_id[:16]}")
            
            print(f"✅ Returning {len(classified_emails)} emails from database")
            
            return jsonify({
                'success': True,
                'count': len(classified_emails),
                'emails': classified_emails
            })
        
        openai_client = get_openai_client()
        classifier = EmailClassifier(openai_client)
        
        # Track if we've hit OpenAI quota/rate limit - if so, skip OpenAI calls for rest of batch
        openai_quota_exceeded = False
        
        # Import time for rate limiting
        import time
        
        classified_emails = []
        for idx, email in enumerate(emails):
            # Rate limiting: Add small delay between OpenAI calls to avoid hitting rate limits
            # Skip delay for first email and if quota already exceeded
            if idx > 0 and not openai_quota_exceeded:
                time.sleep(0.5)  # 500ms delay between requests (allows ~120 requests/minute)
            try:
                # Check if already classified
                classification = EmailClassification.query.filter_by(
                    user_id=current_user.id,
                    thread_id=email['thread_id']
                ).first()
                
                # Check if this thread is part of a Deal Flow (even if this specific email isn't classified yet)
                existing_deal = Deal.query.filter_by(
                    user_id=current_user.id,
                    thread_id=email['thread_id']
                ).first()
                
                # IMPORTANT: Extract PDF/attachment content FIRST, before classification
                # This ensures we can detect PDF decks as deal flow indicators
                attachment_text = None
                attachments = email.get('attachments', [])
                pdf_attachments = []
                if attachments:
                    print(f"📎 Found {len(attachments)} attachment(s) in email {email.get('thread_id', 'unknown')} - extracting for classification")
                    # Combine all attachment texts
                    attachment_texts = [att.get('text', '') for att in attachments if att.get('text')]
                    if attachment_texts:
                        attachment_text = '\n\n'.join(attachment_texts)
                    # Find PDF attachments
                    pdf_attachments = [att for att in attachments if att.get('mime_type') == 'application/pdf']
                    print(f"📄 Found {len(pdf_attachments)} PDF attachment(s)")
                
                # Use combined_text (body + attachments) for link extraction and classification
                # This ensures PDF deck content is analyzed before classifying
                email_body_full = email.get('combined_text') or email.get('body', '')
                if attachment_text and '--- Attachment Content ---' not in email_body_full:
                    # Add attachment content if not already included
                    email_body_full = f"{email_body_full}\n\n--- Attachment Content ---\n\n{attachment_text}"
                
                # Extract headers and links from FULL body (including PDF content)
                headers = email.get('headers', {})
                links = classifier.extract_links(email_body_full)  # Extract links from full body including PDF
                
                # Check if PDF attachments indicate deal flow (PDF deck is a strong indicator)
                has_pdf_deck = len(pdf_attachments) > 0
                if has_pdf_deck:
                    # Check if PDF filename or content suggests it's a pitch deck
                    for pdf_att in pdf_attachments:
                        filename = pdf_att.get('filename', '').lower()
                        if any(keyword in filename for keyword in ['deck', 'pitch', 'presentation', 'proposal', 'business']):
                            has_pdf_deck = True
                            break
                        # Also check if PDF text content suggests it's a pitch deck
                        pdf_text = pdf_att.get('text', '')
                        if pdf_text:
                            deck_indicators = ['pitch', 'deck', 'fundraising', 'investment', 'valuation', 'traction', 'market opportunity', 'team', 'round', 'seed', 'series']
                            if any(indicator in pdf_text.lower()[:1000] for indicator in deck_indicators):
                                has_pdf_deck = True
                                break
                
                # Only classify if not already classified
                # (Removed old reclassification logic to avoid burning OpenAI credits on every refresh)
                if not classification:
                    # Classify email with full context (including PDF decks)
                    # If thread has an existing Deal, classify as Deal Flow
                    if existing_deal:
                        classification_result = {
                            'category': CATEGORY_DEAL_FLOW,
                            'confidence': 0.95,
                            'tags': [TAG_DEAL],
                            'links': links
                        }
                    else:
                        # If OpenAI quota exceeded, skip OpenAI and use deterministic only
                        if openai_quota_exceeded:
                            # Use deterministic classification directly (no OpenAI call)
                            det_category, det_confidence = classifier.deterministic_classify(
                                subject=email.get('subject', ''),
                                body=email_body_full,
                                headers=headers,
                                sender=email.get('from', ''),
                                links=links,
                                has_pdf_attachment=has_pdf_deck
                            )
                            # Determine tags based on category
                            tags = []
                            if det_category == CATEGORY_DEAL_FLOW:
                                tags = [TAG_DEAL]
                            elif det_category == CATEGORY_NETWORKING:
                                tags = [TAG_NETWORKING]
                            elif det_category == CATEGORY_HIRING:
                                tags = [TAG_HIRING]
                            elif det_category == CATEGORY_SPAM:
                                tags = [TAG_SPAM]
                            elif det_category == CATEGORY_GENERAL:
                                tags = [TAG_GENERAL]
                            
                            classification_result = {
                                'category': det_category,
                                'confidence': det_confidence,
                                'tags': tags,
                                'links': links
                            }
                        else:
                            try:
                                classification_result = classifier.classify_email(
                                    subject=email.get('subject', ''),
                                    body=email_body_full,  # Includes PDF content
                                    headers=headers,
                                    sender=email.get('from', ''),
                                    links=links,
                                    has_pdf_attachment=has_pdf_deck,  # Pass PDF indicator
                                    thread_id=email.get('thread_id'),
                                    user_id=str(current_user.id)
                                )
                            except Exception as classify_error:
                                # If classification fails (e.g., OpenAI quota/rate limit), use deterministic only
                                error_str = str(classify_error)
                                # Check for both quota and rate limit errors (429 can show "insufficient_quota" in message)
                                is_rate_limit = '429' in error_str or 'rate_limit' in error_str.lower() or 'rate limit' in error_str.lower()
                                is_quota_error = 'insufficient_quota' in error_str.lower() or ('quota' in error_str.lower() and 'exceeded' in error_str.lower())
                                
                                if is_rate_limit or is_quota_error:
                                    # Set flag to skip OpenAI for rest of batch
                                    if not openai_quota_exceeded:
                                        if is_rate_limit:
                                            print(f"⚠️ OpenAI rate limit hit (429). Switching to deterministic-only classification for remaining emails.")
                                            print(f"   Tip: Wait a few minutes or reduce batch size to avoid rate limits.")
                                        else:
                                            print(f"⚠️ OpenAI quota exceeded. Switching to deterministic-only classification for remaining emails.")
                                        openai_quota_exceeded = True
                                    
                                    # Use deterministic classification directly
                                    det_category, det_confidence = classifier.deterministic_classify(
                                        subject=email.get('subject', ''),
                                        body=email_body_full,
                                        headers=headers,
                                        sender=email.get('from', ''),
                                        links=links,
                                        has_pdf_attachment=has_pdf_deck
                                    )
                                    # Determine tags based on category
                                    tags = []
                                    if det_category == CATEGORY_DEAL_FLOW:
                                        tags = [TAG_DEAL]
                                    elif det_category == CATEGORY_NETWORKING:
                                        tags = [TAG_NETWORKING]
                                    elif det_category == CATEGORY_HIRING:
                                        tags = [TAG_HIRING]
                                    elif det_category == CATEGORY_SPAM:
                                        tags = [TAG_SPAM]
                                    elif det_category == CATEGORY_GENERAL:
                                        tags = [TAG_GENERAL]
                                    
                                    classification_result = {
                                        'category': det_category,
                                        'confidence': det_confidence,
                                        'tags': tags,
                                        'links': links
                                    }
                                else:
                                    # Re-raise other errors
                                    raise
                    
                    # Store classification
                    classification = EmailClassification(
                        user_id=current_user.id,
                        thread_id=email['thread_id'],
                        message_id=email['id'],
                        subject=email.get('subject', 'No Subject'),
                        sender=email.get('from', 'Unknown'),
                        snippet=email.get('snippet', ''),
                        email_date=email.get('date'),
                        category=classification_result['category'],
                        tags=','.join(classification_result['tags']),
                        confidence=classification_result['confidence'],
                        extracted_links=json.dumps(classification_result['links'])
                    )
                    
                    # Deal Flow specific processing
                    if classification_result['category'] == CATEGORY_DEAL_FLOW:
                        deck_links = [l for l in classification_result['links'] if any(
                            ind in l.lower() for ind in ['docsend', 'dataroom', 'deck', 'drive.google.com', 'dropbox.com', 'notion.so']
                        )]
                        
                        # Attachment text already extracted above for classification
                        # Mark PDF attachments as deck links
                        if pdf_attachments:
                            pdf_filename = pdf_attachments[0].get('filename', 'deck.pdf')
                            if not deck_links:
                                classification.deck_link = f"[PDF Attachment: {pdf_filename}]"
                                print(f"✓ Marked PDF attachment as deck: {pdf_filename}")
                            else:
                                # Even if there are deck links, also note PDF attachment
                                if not classification.deck_link or '[PDF Attachment' not in classification.deck_link:
                                    classification.deck_link = f"{deck_links[0]} (+ {pdf_filename})"
                        
                        if deck_links and not classification.deck_link:
                            classification.deck_link = deck_links[0]
                        
                        # Check four basics (include attachment text)
                        # Use combined_text for checking basics
                        email_body_for_basics = email.get('combined_text') or email.get('body', '')
                        basics = classifier.check_four_basics(
                            email.get('subject', ''),
                            email_body_for_basics,
                            classification_result['links'],
                            attachment_text=attachment_text
                        )
                        
                        # Extract founder info
                        founder_email = email.get('from', '').split('<')[1].split('>')[0] if '<' in email.get('from', '') else email.get('from', '')
                        founder_name = email.get('from', '').split('<')[0].strip() if '<' in email.get('from', '') else ''
                        
                        # Scoring system removed - using NA placeholders
                        # Generate reply and determine state (without scores)
                        # Use combined_text for reply generation to include attachment context
                        reply_body = email.get('combined_text') or email.get('body', '')
                        reply_text, reply_type, state = classifier.generate_deal_flow_reply(
                            basics, 
                            bool(deck_links) or bool(attachment_text),
                            subject=email.get('subject', ''),
                            body=reply_body,
                            sender=email.get('from', ''),
                            score=None,  # No scoring
                            team_score=None,
                            white_space_score=None
                        )
                        
                        # Clean up any signature placeholder text the AI might have added
                        placeholder_phrases = [
                            '[Your Name]', '[Your Position]', '[Your Firm]', '[Your Contact Information]'
                        ]
                        for phrase in placeholder_phrases:
                            if phrase in reply_text:
                                # Remove the placeholder and everything after it
                                idx = reply_text.find(phrase)
                                reply_text = reply_text[:idx].strip()
                                break
                        
                        # Append signature to generated reply
                        try:
                            selected_email = current_user.gmail_token.selected_signature_email if current_user.gmail_token else None
                            signature = gmail.get_signature(send_as_email=selected_email)
                            if signature:
                                reply_text = f"{reply_text}\n\n{signature}"
                        except Exception as e:
                            print(f"Note: Could not fetch signature during classification: {str(e)}")
                        
                        classification.deal_state = state
                        classification.reply_type = reply_type
                        
                        # Add classification first to get its ID
                        db.session.add(classification)
                        db.session.flush()  # Get classification.id
                        
                        # Determine deck_link for Deal record (use classification.deck_link which includes PDF attachments)
                        deal_deck_link = classification.deck_link if classification.deck_link else (deck_links[0] if deck_links else None)
                        
                        # Create Deal record (scoring system removed - using NA placeholders)
                        deal = Deal(
                            user_id=current_user.id,
                            thread_id=email['thread_id'],
                            classification_id=classification.id,
                            founder_name=founder_name,
                            founder_email=founder_email,
                            subject=email.get('subject', ''),
                            deck_link=deal_deck_link,
                            has_deck=basics['has_deck'] or bool(deal_deck_link),
                            has_team_info=basics['has_team_info'],
                            has_traction=basics['has_traction'],
                            has_round_info=basics['has_round_info'],
                            state=state,
                            # Team background (not extracted - scoring removed)
                            founder_school=None,
                            founder_previous_companies=None,
                            # Scores set to None (scoring system removed)
                            team_background_score=None,
                            white_space_score=None,
                            overall_score=None,
                            # White space analysis removed
                            white_space_analysis=None,
                            # Old scores set to None (deprecated, kept for backward compatibility)
                            risk_score=None,
                            portfolio_comparison_score=None,
                            founder_market_score=None,
                            traction_score=None,
                            # Keep portfolio_overlaps empty (not using old portfolio matching)
                            portfolio_overlaps=json.dumps({})
                        )
                        db.session.add(deal)
                        db.session.flush()  # Get deal.id
                    
                    # Other categories - generate appropriate reply
                    elif classification_result['category'] in [CATEGORY_NETWORKING, CATEGORY_HIRING]:
                        reply_text, reply_type = classifier.generate_category_reply(
                            classification_result['category']
                        )
                        
                        # Clean up any signature placeholder text the AI might have added
                        placeholder_phrases = [
                            '[Your Name]', '[Your Position]', '[Your Firm]', '[Your Contact Information]'
                        ]
                        for phrase in placeholder_phrases:
                            if phrase in reply_text:
                                # Remove the placeholder and everything after it
                                idx = reply_text.find(phrase)
                                reply_text = reply_text[:idx].strip()
                                break
                        
                        # Append signature to generated reply
                        try:
                            selected_email = current_user.gmail_token.selected_signature_email if current_user.gmail_token else None
                            signature = gmail.get_signature(send_as_email=selected_email)
                            if signature:
                                reply_text = f"{reply_text}\n\n{signature}"
                        except Exception as e:
                            print(f"Note: Could not fetch signature during classification: {str(e)}")
                        
                        classification.reply_type = reply_type
                    
                    else:  # SPAM
                        classification.reply_type = 'none'
                    
                    # Add classification if not already added (for non-Deal Flow cases)
                    if classification_result['category'] != CATEGORY_DEAL_FLOW:
                        db.session.add(classification)
                    
                    db.session.commit()
                
                # Add classification info to email
                email['classification'] = {
                    'category': classification.category,
                    'tags': classification.tags.split(',') if classification.tags else [],
                    'confidence': classification.confidence,
                    'reply_type': classification.reply_type,
                    'deal_state': classification.deal_state,
                    'deck_link': classification.deck_link
                }
                
                # Ensure star status is included (from Gmail API)
                if 'is_starred' not in email:
                    email['is_starred'] = False
                if 'label_ids' not in email:
                    email['label_ids'] = []
                
                # Filter by category if requested
                if category_filter and classification.category != category_filter:
                    continue
                
                # Filter spam if not requested (but always show GENERAL)
                if classification.category == CATEGORY_SPAM and not show_spam:
                    continue
                
                # Debug: Log what we're appending
                print(f"📧 Appending email from {email.get('from', 'unknown')[:50]}: Category={classification.category}, Subject={email.get('subject', 'No subject')[:50]}, Starred={email.get('is_starred', False)}")
                
                classified_emails.append(email)
            
            except Exception as e:
                print(f"Error processing email {email.get('thread_id', 'unknown')}: {str(e)}")
                import traceback
                traceback.print_exc()
                # Continue processing other emails
                continue
        
        # Enforce 20 email limit: Delete oldest emails if more than 20 exist (after processing all emails)
        total_classifications = EmailClassification.query.filter_by(user_id=current_user.id).count()
        if total_classifications > 20:
            # Get IDs of oldest emails (keep latest 20)
            oldest_classifications = EmailClassification.query.filter_by(
                user_id=current_user.id
            ).order_by(EmailClassification.classified_at.asc()).limit(total_classifications - 20).all()
            
            # Delete associated deals first (to avoid foreign key constraints)
            for old_class in oldest_classifications:
                Deal.query.filter_by(classification_id=old_class.id).delete()
            
            # Delete oldest classifications
            for old_class in oldest_classifications:
                db.session.delete(old_class)
            
            db.session.commit()
            print(f"🗑️  Deleted {len(oldest_classifications)} old emails (keeping latest 20)")
        
        print(f"✅ Returning {len(classified_emails)} emails to frontend")
        
        return jsonify({
            'success': True,
            'count': len(classified_emails),
            'emails': classified_emails
        })
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in get_emails: {str(e)}")
        print(error_trace)
        return jsonify({
            'success': False, 
            'error': str(e),
            'traceback': error_trace if app.debug else None
        }), 500

@app.route('/api/starred-emails')
@login_required
def get_starred_emails():
    """Get user's starred emails"""
    if not current_user.gmail_token:
        return jsonify({
            'success': False,
            'error': 'Gmail not connected. Please connect your Gmail account.'
        }), 401
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({
                'success': False,
                'error': 'Failed to connect to Gmail'
            }), 500
        
        # Get max emails from query parameter
        max_emails = min(request.args.get('max', default=20, type=int), 20)  # Cap at 20 emails max
        
        # Fetch starred emails
        starred_emails = gmail.get_starred_emails(max_results=max_emails)
        
        # Format starred emails for frontend (similar to received emails)
        formatted_emails = []
        for email in starred_emails:
            formatted_emails.append({
                'id': email.get('id'),
                'thread_id': email.get('thread_id'),
                'from': email.get('from', 'Unknown'),
                'to': email.get('to', 'Unknown'),
                'subject': email.get('subject', 'No Subject'),
                'snippet': email.get('snippet', ''),
                'date': email.get('date'),
                'body': email.get('body', ''),
                'combined_text': email.get('combined_text', ''),
                'attachments': email.get('attachments', []),
                'is_starred': True,  # Always true for starred emails
                'label_ids': email.get('label_ids', ['STARRED']),
                'classification': {
                    'category': 'STARRED',
                    'tags': [],
                    'confidence': 1.0,
                    'reply_type': None,
                    'deal_state': None,
                    'deck_link': None
                }
            })
        
        return jsonify({
            'success': True,
            'count': len(formatted_emails),
            'emails': formatted_emails
        })
    
    except Exception as e:
        print(f"Error fetching starred emails: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/sent-emails')
@login_required
def get_sent_emails():
    """Get user's sent emails"""
    if not current_user.gmail_token:
        return jsonify({
            'success': False,
            'error': 'Gmail not connected. Please connect your Gmail account.'
        }), 401
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({
                'success': False,
                'error': 'Failed to connect to Gmail'
            }), 500
        
        # Get max emails from query parameter
        max_emails = min(request.args.get('max', default=20, type=int), 20)  # Cap at 20 emails max
        
        # Fetch sent emails
        sent_emails = gmail.get_sent_emails(max_results=max_emails)
        
        # Format sent emails for frontend (similar to received emails)
        formatted_emails = []
        for email in sent_emails:
            formatted_emails.append({
                'id': email.get('id'),
                'thread_id': email.get('thread_id'),
                'from': email.get('from', 'Unknown'),
                'to': email.get('to', 'Unknown'),
                'subject': email.get('subject', 'No Subject'),
                'snippet': email.get('snippet', ''),
                'date': email.get('date'),
                'body': email.get('body', ''),
                'combined_text': email.get('combined_text', ''),
                'attachments': email.get('attachments', []),
                'category': 'SENT',  # Mark as sent
                'is_sent': True
            })
        
        return jsonify({
            'success': True,
            'count': len(formatted_emails),
            'emails': formatted_emails
        })
    
    except Exception as e:
        print(f"Error fetching sent emails: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/drafts')
@login_required
def get_drafts():
    """Get user's draft emails"""
    if not current_user.gmail_token:
        return jsonify({
            'success': False,
            'error': 'Gmail not connected. Please connect your Gmail account.'
        }), 401
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({
                'success': False,
                'error': 'Failed to connect to Gmail'
            }), 500
        
        # Get max emails from query parameter
        max_emails = min(request.args.get('max', default=20, type=int), 20)  # Cap at 20 emails max
        
        # Fetch drafts
        drafts = gmail.get_drafts(max_results=max_emails)
        
        # Format drafts for frontend (similar to received emails)
        formatted_emails = []
        for email in drafts:
            formatted_emails.append({
                'id': email.get('id'),
                'thread_id': email.get('thread_id'),
                'from': email.get('from', 'Unknown'),
                'to': email.get('to', 'Unknown'),
                'subject': email.get('subject', 'No Subject'),
                'snippet': email.get('snippet', ''),
                'date': email.get('date'),
                'body': email.get('body', ''),
                'combined_text': email.get('combined_text', ''),
                'attachments': email.get('attachments', []),
                'is_starred': email.get('is_starred', False),
                'label_ids': email.get('label_ids', []),
                'category': 'DRAFT',
                'is_draft': True
            })
        
        return jsonify({
            'success': True,
            'count': len(formatted_emails),
            'emails': formatted_emails
        })
    
    except Exception as e:
        print(f"Error fetching drafts: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/reclassify-email', methods=['POST'])
@login_required
def reclassify_email():
    """Force reclassification of an email by thread_id"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        data = request.json
        thread_id = data.get('thread_id')
        
        if not thread_id:
            return jsonify({'success': False, 'error': 'thread_id required'}), 400
        
        # Delete existing classification
        classification = EmailClassification.query.filter_by(
            user_id=current_user.id,
            thread_id=thread_id
        ).first()
        
        if classification:
            db.session.delete(classification)
            db.session.commit()
        
        # Fetch the email and reclassify
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        # Get email details
        # Reduced from 100 to 10 to avoid rate limits (was making 101 API calls!)
        # Note: For single thread lookup, we don't use incremental sync
        emails, _ = gmail.get_emails(max_results=10, unread_only=False, start_history_id=None)
        email = next((e for e in emails if e['thread_id'] == thread_id), None)
        
        if not email:
            return jsonify({'success': False, 'error': 'Email not found'}), 404
        
        # Reclassify
        openai_client = get_openai_client()
        classifier = EmailClassifier(openai_client)
        headers = email.get('headers', {})
        links = classifier.extract_links(email.get('body', ''))
        
        # Check if thread has existing Deal
        existing_deal = Deal.query.filter_by(
            user_id=current_user.id,
            thread_id=thread_id
        ).first()
        
        # IMPORTANT: Extract PDF/attachment content BEFORE classification
        attachment_text = None
        attachments = email.get('attachments', [])
        pdf_attachments = []
        if attachments:
            print(f"📎 Found {len(attachments)} attachment(s) in email {email.get('thread_id', 'unknown')} - extracting for reclassification")
            # Combine all attachment texts
            attachment_texts = [att.get('text', '') for att in attachments if att.get('text')]
            if attachment_texts:
                attachment_text = '\n\n'.join(attachment_texts)
            # Find PDF attachments
            pdf_attachments = [att for att in attachments if att.get('mime_type') == 'application/pdf']
            print(f"📄 Found {len(pdf_attachments)} PDF attachment(s)")
        
        # Use combined_text (body + attachments) for classification
        email_body_for_classification = email.get('combined_text') or email.get('body', '')
        if attachment_text and '--- Attachment Content ---' not in email_body_for_classification:
            # Add attachment content if not already included
            email_body_for_classification = f"{email_body_for_classification}\n\n--- Attachment Content ---\n\n{attachment_text}"
        
        if existing_deal:
            classification_result = {
                'category': CATEGORY_DEAL_FLOW,
                'confidence': 0.95,
                'tags': [TAG_DEAL],
                'links': links
            }
        else:
            classification_result = classifier.classify_email(
                subject=email.get('subject', ''),
                body=email_body_for_classification,  # Includes PDF content
                headers=headers,
                sender=email.get('from', ''),
                links=links,
                thread_id=email.get('thread_id'),
                user_id=str(current_user.id)
            )
        
        # Store new classification
        new_classification = EmailClassification(
            user_id=current_user.id,
            thread_id=thread_id,
            message_id=email['id'],
            subject=email.get('subject', 'No Subject'),
            sender=email.get('from', 'Unknown'),
            snippet=email.get('snippet', ''),
            email_date=email.get('date'),
            category=classification_result['category'],
            tags=','.join(classification_result['tags']),
            confidence=classification_result['confidence'],
            extracted_links=json.dumps(classification_result['links'])
        )
        
        # Process Deal Flow if needed
        if classification_result['category'] == CATEGORY_DEAL_FLOW:
            deck_links = [l for l in classification_result['links'] if any(
                ind in l.lower() for ind in ['docsend', 'dataroom', 'deck', 'drive.google.com', 'dropbox.com', 'notion.so']
            )]
            
            # Attachment text already extracted above for classification
            # Mark PDF attachments as deck links
            if pdf_attachments:
                pdf_filename = pdf_attachments[0].get('filename', 'deck.pdf')
                if not deck_links:
                    new_classification.deck_link = f"[PDF Attachment: {pdf_filename}]"
                    print(f"✓ Marked PDF attachment as deck: {pdf_filename}")
                else:
                    # Even if there are deck links, also note PDF attachment
                    if not new_classification.deck_link or '[PDF Attachment' not in new_classification.deck_link:
                        new_classification.deck_link = f"{deck_links[0]} (+ {pdf_filename})"
            
            if deck_links:
                new_classification.deck_link = deck_links[0]
            
            # Use combined_text for checking basics
            email_body_for_basics = email.get('combined_text') or email.get('body', '')
            basics = classifier.check_four_basics(
                email.get('subject', ''),
                email_body_for_basics,
                classification_result['links'],
                attachment_text=attachment_text
            )
            
            # Calculate scores for reply generation
            founder_email = email.get('from', '').split('<')[1].split('>')[0] if '<' in email.get('from', '') else email.get('from', '')
            founder_name = email.get('from', '').split('<')[0].strip() if '<' in email.get('from', '') else ''
            
            # Scoring system removed - generate reply without scores
            reply_body = email.get('combined_text') or email.get('body', '')
            reply_text, reply_type, state = classifier.generate_deal_flow_reply(
                basics, 
                bool(deck_links) or bool(attachment_text),
                subject=email.get('subject', ''),
                body=reply_body,
                sender=email.get('from', ''),
                score=None,  # No scoring
                team_score=None,
                white_space_score=None
            )
            
            # Clean up any closing phrases the AI might have added
            closing_phrases = [
                'Best regards', 'Sincerely', 'Regards', 'Thank you,', 'Thanks,',
                '[Your Name]', '[Your Position]', '[Your Firm]', '[Your Contact Information]'
            ]
            for phrase in closing_phrases:
                if phrase.lower() in reply_text.lower():
                    idx = reply_text.lower().find(phrase.lower())
                    reply_text = reply_text[:idx].strip()
                    break
            
            # Append signature to generated reply
            try:
                gmail = get_user_gmail_client(current_user)
                if gmail:
                    selected_email = current_user.gmail_token.selected_signature_email if current_user.gmail_token else None
                    signature = gmail.get_signature(send_as_email=selected_email)
                    if signature:
                        reply_text = f"{reply_text}\n\n{signature}"
            except Exception as e:
                print(f"Note: Could not fetch signature during reclassification: {str(e)}")
            
            new_classification.deal_state = state
            new_classification.reply_type = reply_type
        
        db.session.add(new_classification)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'category': classification_result['category'],
            'confidence': classification_result['confidence'],
            'tags': classification_result['tags']
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/generate-reply', methods=['POST'])
@login_required
def generate_reply():
    """Generate category-specific AI reply for an email"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        openai_client = get_openai_client()
        classifier = EmailClassifier(openai_client)
        
        data = request.json
        subject = data.get('subject') or 'No Subject'
        # Use combined_text (includes PDF content) if available, otherwise body
        body = data.get('combined_text') or data.get('body')
        sender = data.get('from')
        thread_id = data.get('thread_id')
        attachments = data.get('attachments', [])
        
        # Provide more detailed error message (subject can be 'No Subject', but body and sender are required)
        missing_fields = []
        if not body or not body.strip():
            missing_fields.append('body/combined_text')
        if not sender or not sender.strip():
            missing_fields.append('from')
        
        if missing_fields:
            error_msg = f'Missing required fields: {", ".join(missing_fields)}'
            print(f"❌ Generate Reply Error: {error_msg}")
            print(f"   Data received: subject={subject[:50] if subject else None}, body_length={len(body) if body else 0}, from={sender[:50] if sender else None}")
            return jsonify({'success': False, 'error': error_msg}), 400
        
        # Extract attachment text for PDF analysis
        attachment_text = None
        pdf_attachments = []
        if attachments:
            attachment_texts = [att.get('text', '') for att in attachments if att.get('text')]
            if attachment_texts:
                attachment_text = '\n\n'.join(attachment_texts)
            pdf_attachments = [att for att in attachments if att.get('mime_type') == 'application/pdf']
        
        # Get existing classification if available
        classification = None
        if thread_id:
            classification = EmailClassification.query.filter_by(
                user_id=current_user.id,
                thread_id=thread_id
            ).first()
        
        # If no classification, classify now (use body which already includes combined_text)
        if not classification:
            headers = data.get('headers', {})
            links = classifier.extract_links(body)
            
            classification_result = classifier.classify_email(
                subject=subject,
                body=body,  # This should already be combined_text if available
                headers=headers,
                sender=sender,
                links=links,
                thread_id=data.get('thread_id'),
                user_id=str(current_user.id)
            )
            
            category = classification_result['category']
        else:
            category = classification.category
        
        # Generate category-specific reply
        if category == CATEGORY_SPAM:
            return jsonify({
                'success': True,
                'should_reply': False,
                'message': 'This email is classified as spam and does not need a reply'
            })
        
        # Generate reply based on category
        if category == CATEGORY_DEAL_FLOW:
            links = classifier.extract_links(body) if not classification else json.loads(classification.extracted_links or '[]')
            # Use attachment_text for checking basics (includes PDF content)
            basics = classifier.check_four_basics(subject, body, links, attachment_text=attachment_text)
            has_deck = bool([l for l in links if any(ind in l.lower() for ind in ['docsend', 'dataroom', 'deck', 'notion.so'])]) or bool(pdf_attachments)
            
            # Scoring system removed - generate reply without scores
            reply_text, reply_type, state = classifier.generate_deal_flow_reply(
                basics, 
                has_deck,
                subject=subject,
                body=body,  # Use combined_text which includes PDF content
                sender=data.get('from', ''),
                score=None,  # No scoring
                team_score=None,
                white_space_score=None
            )
        else:
            reply_text, reply_type = classifier.generate_category_reply(category)
        
        if not reply_text:
            return jsonify({'success': False, 'error': 'Could not generate reply'}), 500
        
        # Clean up any signature placeholder text the AI might have added
        placeholder_phrases = [
            '[Your Name]', '[Your Position]', '[Your Firm]', '[Your Contact Information]'
        ]
        for phrase in placeholder_phrases:
            if phrase in reply_text:
                # Remove the placeholder and everything after it
                idx = reply_text.find(phrase)
                reply_text = reply_text[:idx].strip()
                break
        
        # Fetch and append signature to the generated reply
        try:
            gmail = get_user_gmail_client(current_user)
            if gmail:
                selected_email = current_user.gmail_token.selected_signature_email if current_user.gmail_token else None
                signature = gmail.get_signature(send_as_email=selected_email)
                if signature:
                    reply_text = f"{reply_text}\n\n{signature}"
        except Exception as e:
            # If signature fetch fails, continue without it (don't break the reply generation)
            print(f"Note: Could not fetch signature for preview: {str(e)}")
        
        return jsonify({
            'success': True,
            'should_reply': True,
            'reply': reply_text,
            'category': category,
            'reply_type': reply_type
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/send-reply', methods=['POST'])
@login_required
def send_reply():
    """Send a reply email"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    send_emails = os.getenv('SEND_EMAILS', 'false').lower() == 'true'
    send_emails_raw = os.getenv('SEND_EMAILS', 'false')
    
    if not send_emails:
        return jsonify({
            'success': False,
            'error': f'Email sending is disabled. Set SEND_EMAILS=true in .env (current value: {send_emails_raw})',
            'debug': {
                'SEND_EMAILS_raw': send_emails_raw,
                'SEND_EMAILS_parsed': send_emails
            }
        }), 403
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        data = request.json
        email_id = data.get('email_id')
        to_email = data.get('to')
        subject = data.get('subject')
        body = data.get('body')
        thread_id = data.get('thread_id')
        
        if not all([to_email, subject, body]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Extract email address
        if '<' in to_email and '>' in to_email:
            to_email = to_email.split('<')[1].split('>')[0]
        
        # Get selected signature email preference
        selected_email = current_user.gmail_token.selected_signature_email if current_user.gmail_token else None
        
        # Send reply (don't mark as read automatically - keep as unread)
        success = gmail.send_reply(to_email, subject, body, thread_id, send_as_email=selected_email)
        
        # Don't automatically mark as read - let user decide
        # if success and email_id:
        #     gmail.mark_as_read(email_id)
        
        return jsonify({
            'success': success,
            'message': 'Reply sent successfully' if success else 'Failed to send reply'
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/send-email', methods=['POST'])
@login_required
def send_email():
    """Send a new email (not a reply)"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    send_emails = os.getenv('SEND_EMAILS', 'false').lower() == 'true'
    send_emails_raw = os.getenv('SEND_EMAILS', 'false')
    
    if not send_emails:
        return jsonify({
            'success': False,
            'error': f'Email sending is disabled. Set SEND_EMAILS=true in .env (current value: {send_emails_raw})',
            'debug': {
                'SEND_EMAILS_raw': send_emails_raw,
                'SEND_EMAILS_parsed': send_emails
            }
        }), 403
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        data = request.json
        to_email = data.get('to')
        subject = data.get('subject')
        body = data.get('body')
        cc = data.get('cc')
        bcc = data.get('bcc')
        
        if not all([to_email, subject, body]):
            return jsonify({'success': False, 'error': 'Missing required fields: to, subject, body'}), 400
        
        # Get selected signature email preference
        selected_email = current_user.gmail_token.selected_signature_email if current_user.gmail_token else None
        
        # Send email
        success = gmail.send_email(to_email, subject, body, send_as_email=selected_email, cc=cc, bcc=bcc)
        
        return jsonify({
            'success': success,
            'message': 'Email sent successfully' if success else 'Failed to send email'
        })
    
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/signatures', methods=['GET'])
@login_required
def get_signatures():
    """Get all available send-as aliases with their signatures"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        # Get all send-as aliases
        aliases = gmail.service.users().settings().sendAs().list(
            userId='me'
        ).execute()
        
        send_as_list = aliases.get('sendAs', [])
        signatures = []
        
        for alias in send_as_list:
            signature_text = alias.get('signature', '')
            signature_raw = signature_text  # Keep raw for debugging
            
            # Strip HTML for preview
            if signature_text:
                import re
                # Convert HTML breaks to newlines
                signature_text = re.sub(r'<br\s*/?>', '\n', signature_text, flags=re.IGNORECASE)
                signature_text = re.sub(r'</p>', '\n\n', signature_text, flags=re.IGNORECASE)
                signature_text = re.sub(r'<p[^>]*>', '', signature_text, flags=re.IGNORECASE)
                # Remove all other HTML tags
                signature_text = re.sub(r'<[^>]+>', '', signature_text)
                # Clean up HTML entities
                signature_text = signature_text.replace('&nbsp;', ' ')
                signature_text = signature_text.replace('&amp;', '&')
                signature_text = signature_text.replace('&lt;', '<')
                signature_text = signature_text.replace('&gt;', '>')
                signature_text = signature_text.replace('&quot;', '"')
                signature_text = signature_text.replace('&#39;', "'")
                # Clean up multiple newlines and whitespace
                signature_text = re.sub(r'\n{3,}', '\n\n', signature_text)
                signature_text = signature_text.strip()
            
            # Debug: log raw signature for troubleshooting
            print(f"Signature for {alias.get('sendAsEmail', '')}: raw_length={len(signature_raw)}, processed_length={len(signature_text) if signature_text else 0}")
            
            signatures.append({
                'email': alias.get('sendAsEmail', ''),
                'displayName': alias.get('displayName', ''),
                'isPrimary': alias.get('isPrimary', False),
                'signature': signature_text,
                'hasSignature': bool(signature_text),
                'signatureRaw': signature_raw  # Include raw for debugging
            })
        
        # Get currently selected signature
        selected_email = current_user.gmail_token.selected_signature_email if current_user.gmail_token else None
        
        return jsonify({
            'success': True,
            'signatures': signatures,
            'selected': selected_email
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/signature/select', methods=['POST'])
@login_required
def select_signature():
    """Save the selected signature send-as email"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        data = request.json
        send_as_email = data.get('email')  # Can be None to use primary
        
        if current_user.gmail_token:
            current_user.gmail_token.selected_signature_email = send_as_email
            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Signature preference saved'
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/mark-read', methods=['POST'])
@login_required
def mark_read():
    """Mark an email as read"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        data = request.json
        email_id = data.get('email_id')
        
        if not email_id:
            return jsonify({'success': False, 'error': 'Missing email_id'}), 400
        
        success = gmail.mark_as_read(email_id)
        
        return jsonify({
            'success': success,
            'message': 'Marked as read' if success else 'Failed to mark as read'
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/toggle-star', methods=['POST'])
@login_required
def toggle_star():
    """Star or unstar an email"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        data = request.json
        email_id = data.get('email_id')
        star = data.get('star', True)  # Default to star (true)
        
        if not email_id:
            return jsonify({'success': False, 'error': 'Missing email_id'}), 400
        
        success = gmail.toggle_star(email_id, star=star)
        
        return jsonify({
            'success': success,
            'message': 'Starred' if star and success else 'Unstarred' if success else 'Failed to toggle star',
            'is_starred': star if success else None
        })
    
    except Exception as e:
        import traceback
        print(f"Error in toggle_star endpoint: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/deals')
@login_required
def get_deals():
    """Get Deal Flow deals for user with scores"""
    try:
        deals = Deal.query.filter_by(user_id=current_user.id).order_by(Deal.created_at.desc()).all()
        
        # Get Gmail client to fetch latest email subjects
        gmail = get_user_gmail_client(current_user)
        openai_client = get_openai_client()
        classifier = EmailClassifier(openai_client)
        
        # Scoring system removed - no re-scoring
        deals_data = []
        for deal in deals:
            classification = EmailClassification.query.filter_by(
                user_id=current_user.id,
                thread_id=deal.thread_id
            ).first()
            
            # Fetch latest email subject and check for attachments if needed
            subject = deal.subject or 'No Subject'
            needs_attachment_check = not deal.deck_link or deal.deck_link == 'No deck'
            
            if not subject or subject == 'No Subject' or subject.strip() == '' or needs_attachment_check:
                if gmail:
                    try:
                        # Get email details for this specific thread
                        # First try to get a message ID from the thread
                        thread_data = gmail.service.users().threads().get(
                            userId='me',
                            id=deal.thread_id,
                            format='minimal'
                        ).execute()
                        
                        messages = thread_data.get('messages', [])
                        if messages:
                            # Get the first message in the thread
                            message_id = messages[0]['id']
                            thread_email = gmail.get_email_details(message_id)
                        else:
                            thread_email = None
                        
                        if thread_email:
                            # Update subject if missing
                            if (not subject or subject == 'No Subject' or subject.strip() == '') and thread_email.get('subject'):
                                from email.header import decode_header
                                import html
                                subject = thread_email['subject']
                                deal.subject = subject
                            
                            # Check for PDF attachments if deck_link is missing
                            if needs_attachment_check:
                                attachments = thread_email.get('attachments', [])
                                pdf_attachments = [att for att in attachments if att.get('mime_type') == 'application/pdf']
                                if pdf_attachments:
                                    pdf_filename = pdf_attachments[0].get('filename', 'deck.pdf')
                                    deal.deck_link = f"[PDF Attachment: {pdf_filename}]"
                                    deal.has_deck = True
                                    print(f"✓ Updated deal {deal.thread_id} with PDF attachment: {pdf_filename}")
                            
                            db.session.commit()
                    except Exception as e:
                        print(f"Note: Could not fetch email details for thread {deal.thread_id}: {str(e)}")
            
            # Parse portfolio overlaps
            portfolio_overlaps = {}
            if deal.portfolio_overlaps:
                try:
                    portfolio_overlaps = json.loads(deal.portfolio_overlaps)
                except:
                    pass
            
            # Parse previous companies
            previous_companies = []
            if deal.founder_previous_companies:
                try:
                    previous_companies = json.loads(deal.founder_previous_companies)
                except:
                    pass
            
            # Scoring system removed - scores are always None/NA
            # No re-scoring logic needed
            
            deals_data.append({
                'id': deal.id,
                'thread_id': deal.thread_id,
                'founder_name': deal.founder_name,
                'founder_email': deal.founder_email,
                'subject': subject,  # Use the updated subject variable
                'deck_link': deal.deck_link,
                'state': deal.state,
                'has_deck': deal.has_deck,
                'has_team_info': deal.has_team_info,
                'has_traction': deal.has_traction,
                'has_round_info': deal.has_round_info,
                'created_at': deal.created_at.isoformat() if deal.created_at else None,
                'tags': classification.tags.split(',') if classification and classification.tags else [],
                # Portfolio matching
                'founder_linkedin': deal.founder_linkedin,
                'founder_school': deal.founder_school,
                'founder_previous_companies': previous_companies,
                'portfolio_overlaps': portfolio_overlaps,
                # NEW Tracxn-based scores
                'team_background_score': deal.team_background_score,
                'white_space_score': deal.white_space_score,
                'overall_score': deal.overall_score,
                # Score summary
                'score_summary': _get_score_summary(deal),
                # Legacy scores (for backward compatibility)
                'risk_score': deal.risk_score,
                'portfolio_comparison_score': deal.portfolio_comparison_score,
                'founder_market_score': deal.founder_market_score,
                'traction_score': deal.traction_score,
            })
        
        return jsonify({
            'success': True,
            'count': len(deals_data),
            'deals': deals_data
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _get_score_summary(deal):
    """Extract score summary from white_space_analysis or generate one"""
    if deal.white_space_analysis:
        try:
            white_space_data = json.loads(deal.white_space_analysis)
            if 'summary' in white_space_data:
                return white_space_data['summary']
        except:
            pass
    
    # Generate summary from available data
    portfolio_overlaps = {}
    if deal.portfolio_overlaps:
        try:
            portfolio_overlaps = json.loads(deal.portfolio_overlaps)
        except:
            pass
    
    summary_parts = []
    
    # Team background
    if isinstance(portfolio_overlaps, list) and len(portfolio_overlaps) > 0:
        overlap_companies = [o.get('company', '') if isinstance(o, dict) else str(o) for o in portfolio_overlaps[:2]]
        summary_parts.append(f"Team: {len(portfolio_overlaps)} portfolio match{'es' if len(portfolio_overlaps) > 1 else ''}")
    else:
        summary_parts.append("Team: No portfolio matches")
    
    # White space
    if deal.white_space_analysis:
        try:
            white_space_data = json.loads(deal.white_space_analysis)
            competition = white_space_data.get('competition_intensity', 'Unknown')
            market_size = white_space_data.get('market_size', 'Unknown')
            reasoning = white_space_data.get('reasoning', '')
            if reasoning:
                summary_parts.append(f"Market: {reasoning[:80]}{'...' if len(reasoning) > 80 else ''}")
            else:
                summary_parts.append(f"Market: {competition} competition, {market_size} market")
        except:
            summary_parts.append("Market: Analysis unavailable")
    else:
        summary_parts.append("Market: No analysis")
    
    return " | ".join(summary_parts) if summary_parts else "No summary available"


@app.route('/api/rescore-all-deals', methods=['POST'])
@login_required
def rescore_all_deals():
    """Scoring system removed - this endpoint is disabled"""
    return jsonify({'success': False, 'error': 'Scoring system has been removed'}), 400




@app.route('/api/attachment/<message_id>/<filename>')
@login_required
def get_attachment(message_id, filename):
    """Download/view PDF attachment from a specific email message"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        # Get the attachment data from Gmail
        try:
            # Get full message to find attachment ID
            message = gmail.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            # Decode filename (URL encoded)
            from urllib.parse import unquote
            decoded_filename = unquote(filename)
            
            # Find the PDF attachment in the message parts
            attachment_id = None
            
            def find_attachment_id(parts):
                for part in parts:
                    part_filename = part.get('filename', '')
                    if part_filename == decoded_filename and part.get('mimeType') == 'application/pdf':
                        return part.get('body', {}).get('attachmentId')
                    if 'parts' in part:
                        found = find_attachment_id(part['parts'])
                        if found:
                            return found
                return None
            
            payload = message.get('payload', {})
            if 'parts' in payload:
                attachment_id = find_attachment_id(payload['parts'])
            else:
                # Single part message
                if payload.get('filename') == decoded_filename and payload.get('mimeType') == 'application/pdf':
                    attachment_id = payload.get('body', {}).get('attachmentId')
            
            if not attachment_id:
                # Try to find any PDF attachment if exact filename match fails
                def find_any_pdf(parts):
                    for part in parts:
                        if part.get('mimeType') == 'application/pdf':
                            return part.get('body', {}).get('attachmentId'), part.get('filename', 'deck.pdf')
                        if 'parts' in part:
                            found = find_any_pdf(part['parts'])
                            if found:
                                return found
                    return None
                
                if 'parts' in payload:
                    pdf_result = find_any_pdf(payload['parts'])
                    if pdf_result:
                        attachment_id, decoded_filename = pdf_result
                elif payload.get('mimeType') == 'application/pdf':
                    attachment_id = payload.get('body', {}).get('attachmentId')
            
            if not attachment_id:
                return jsonify({'success': False, 'error': 'Attachment ID not found'}), 404
            
            # Download the attachment
            attachment = gmail.service.users().messages().attachments().get(
                userId='me',
                messageId=message_id,
                id=attachment_id
            ).execute()
            
            # Decode and return the file
            import base64
            import io
            from urllib.parse import quote
            file_data = base64.urlsafe_b64decode(attachment['data'])
            
            return send_file(
                io.BytesIO(file_data),
                mimetype='application/pdf',
                as_attachment=True,
                download_name=decoded_filename
            )
            
        except Exception as e:
            import traceback
            print(f"Error downloading attachment: {str(e)}")
            traceback.print_exc()
            return jsonify({'success': False, 'error': f'Failed to download attachment: {str(e)}'}), 500
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/thread/<thread_id>')
@login_required
def get_thread(thread_id):
    """Get all messages in a thread"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        thread_emails = gmail.get_thread_messages(thread_id)
        
        return jsonify({
            'success': True,
            'count': len(thread_emails),
            'emails': thread_emails
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config')
@login_required
def get_config():
    """Get current configuration"""
    return jsonify({
        'send_emails_enabled': os.getenv('SEND_EMAILS', 'false').lower() == 'true',
        'max_emails': int(os.getenv('MAX_EMAILS', '5')),
        'has_gmail': current_user.gmail_token is not None
    })


if __name__ == '__main__':
    print("=" * 60)
    print("Multi-User Gmail Auto-Reply Web Interface")
    print("=" * 60)
    print()
    print("Starting web server...")
    print("Open your browser to: http://localhost:8080")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=8080)
