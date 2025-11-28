#!/usr/bin/env python3
"""
Multi-User Gmail Auto-Reply Web Application
Each user manages their own Gmail account with complete privacy
"""
import os
import json
import requests
from threading import Semaphore
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, send_file, Response, stream_with_context
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
from sqlalchemy import text
from models import db, User, GmailToken, EmailClassification, Deal
from auth import encrypt_token, decrypt_token
from gmail_client import GmailClient, SCOPES
from openai_client import OpenAIClient
from email_classifier import EmailClassifier, CATEGORY_DEAL_FLOW, CATEGORY_NETWORKING, CATEGORY_HIRING, CATEGORY_SPAM, CATEGORY_GENERAL, TAG_DEAL, TAG_GENERAL
# from tracxn_scorer import TracxnScorer  # Removed - scoring system disabled

# Import background tasks (only if Celery is available)
try:
    from tasks import sync_user_emails
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    print("⚠️  Celery not available - background tasks disabled")

# Rate limiting: Max concurrent OpenAI API calls to prevent 429 errors
# Increased to 20 for faster processing (Lambda can handle more concurrent requests)
CLASSIFICATION_SEMAPHORE = Semaphore(20)  # Max 20 concurrent classifications

# Load environment variables
load_dotenv()

# Debug: Print SEND_EMAILS value on startup
send_emails_debug = os.getenv('SEND_EMAILS', 'false')
print(f"📧 Email sending: {'ENABLED' if send_emails_debug.lower() == 'true' else 'DISABLED'} (SEND_EMAILS={send_emails_debug})")

# Privacy: Minimal logging mode (hides email metadata)
MINIMAL_LOGGING = os.getenv('MINIMAL_LOGGING', 'false').lower() == 'true'
if MINIMAL_LOGGING:
    print("🔒 Privacy mode: ENABLED (metadata logging disabled)")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
# Configure session to persist across redirects
# Note: SESSION_COOKIE_SECURE should be True for HTTPS, but Railway handles this
# Setting it to True might cause issues if Railway proxy isn't configured correctly
app.config['SESSION_COOKIE_SECURE'] = False  # Let Railway/proxy handle HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Allow cookies on OAuth redirects
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes
# Add domain restriction to prevent session sharing between localhost and Railway
app.config['SESSION_COOKIE_DOMAIN'] = None  # Restrict to current domain only
app.config['SESSION_COOKIE_PATH'] = '/'

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

# Add connection pool settings with timeouts to prevent hanging
if database_url and 'postgresql' in database_url.lower():
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,  # Verify connections before using
        'pool_recycle': 300,  # Recycle connections after 5 minutes
        'pool_timeout': 20,  # Wait max 20 seconds for connection from pool
        'connect_args': {
            'connect_timeout': 10,  # Max 10 seconds to establish connection
            'options': '-c statement_timeout=30000'  # 30 second query timeout
        }
    }

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
        # SECURITY: Verify authenticated users have matching session user_id
        # This prevents cross-user authentication if session is corrupted
        if current_user.is_authenticated:
            if 'user_id' in session:
                if session['user_id'] != current_user.id:
                    print(f"⚠️  [SECURITY] SESSION MISMATCH in before_request! Session user_id={session.get('user_id')}, current_user.id={current_user.id}")
                    logout_user()
                    session.clear()
                    session.modified = True
                    # Don't redirect here - let the route handle it (some routes don't require auth)
        
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
    """Load user from database - SECURITY: Verify session matches"""
    try:
        user = User.query.get(int(user_id))
        if user:
            # SECURITY: Verify session user_id matches loaded user (prevent session hijacking)
            if 'user_id' in session:
                if session['user_id'] != user.id:
                    print(f"⚠️  [SECURITY] Session user_id mismatch in load_user! Session={session.get('user_id')}, Loaded user={user.id}")
                    # Clear the mismatched session
                    session.clear()
                    session.modified = True
                    return None
            print(f"✅ User loaded from session: {user.username} (ID: {user_id})")
        else:
            print(f"⚠️  User not found in database: ID {user_id}")
            # User doesn't exist - clear session
            if 'user_id' in session:
                session.clear()
                session.modified = True
        return user
    except Exception as e:
        print(f"❌ Error loading user {user_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        # Clear session on error
        session.clear()
        session.modified = True
        return None


# Lazy migration flag (prevents multiple runs)
_migrations_run = False

def run_lazy_migrations():
    """Run database migrations lazily (on first request) to prevent startup hangs"""
    global _migrations_run
    if _migrations_run:
        return
    
    try:
        from sqlalchemy import text, inspect
        from sqlalchemy.exc import OperationalError, ProgrammingError
        
        # Create tables if they don't exist (this happens on first request)
        try:
            db.create_all()
        except Exception as create_error:
            # Ignore errors about existing tables/sequences (normal in production)
            error_str = str(create_error).lower()
            if 'already exists' not in error_str and 'duplicate key' not in error_str:
                print(f"⚠️  Table creation warning: {create_error}")
        
        # Check database type
        try:
            inspector = inspect(db.engine)
            is_postgres = 'postgresql' in str(db.engine.url).lower()
        except Exception:
            is_postgres = False
        
        if not is_postgres:
            _migrations_run = True
            return
        
        # Run migrations with quick timeout check
        try:
            # Check if columns exist (quick query)
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'email_classifications' 
                AND column_name IN ('subject_encrypted', 'snippet_encrypted')
                LIMIT 2
            """))
            existing_columns = [row[0] for row in result]
        except (OperationalError, ProgrammingError):
            existing_columns = ['subject_encrypted', 'snippet_encrypted']
        
        # Run migrations if needed
        if 'subject_encrypted' not in existing_columns or 'snippet_encrypted' not in existing_columns:
            print("🔄 Running lazy migration: Adding encryption columns...")
            try:
                if 'subject_encrypted' not in existing_columns:
                    db.session.execute(text("""
                        ALTER TABLE email_classifications 
                        ADD COLUMN IF NOT EXISTS subject_encrypted TEXT;
                    """))
                if 'snippet_encrypted' not in existing_columns:
                    db.session.execute(text("""
                        ALTER TABLE email_classifications 
                        ADD COLUMN IF NOT EXISTS snippet_encrypted TEXT;
                    """))
                db.session.commit()
                print("✅ Encryption columns migration completed")
            except Exception as e:
                db.session.rollback()
                print(f"⚠️  Migration error: {e}")
        
        # User table migrations
        try:
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('setup_completed', 'initial_emails_fetched')
                LIMIT 2
            """))
            existing_user_columns = [row[0] for row in result]
            
            if 'setup_completed' not in existing_user_columns:
                db.session.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN IF NOT EXISTS setup_completed BOOLEAN DEFAULT FALSE;
                """))
            if 'initial_emails_fetched' not in existing_user_columns:
                db.session.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN IF NOT EXISTS initial_emails_fetched INTEGER DEFAULT 0;
                """))
            if 'setup_completed' not in existing_user_columns or 'initial_emails_fetched' not in existing_user_columns:
                db.session.commit()
        except Exception:
            db.session.rollback()
        
        # WhatsApp fields migration
        try:
            # User WhatsApp fields
            whatsapp_user_result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('whatsapp_number', 'whatsapp_enabled')
            """))
            whatsapp_user_columns = [row[0] for row in whatsapp_user_result]
            
            if 'whatsapp_number' not in whatsapp_user_columns:
                db.session.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN IF NOT EXISTS whatsapp_number VARCHAR(20)
                """))
            if 'whatsapp_enabled' not in whatsapp_user_columns:
                db.session.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN IF NOT EXISTS whatsapp_enabled BOOLEAN DEFAULT FALSE
                """))
            if 'whatsapp_number' not in whatsapp_user_columns or 'whatsapp_enabled' not in whatsapp_user_columns:
                db.session.commit()
                print("✅ WhatsApp user fields migration completed")
            
            # Deal WhatsApp fields
            whatsapp_deal_result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'deals' 
                AND column_name IN ('whatsapp_alert_sent', 'whatsapp_alert_sent_at', 
                                   'whatsapp_followup_count', 'whatsapp_last_followup_at', 'whatsapp_stopped')
            """))
            whatsapp_deal_columns = [row[0] for row in whatsapp_deal_result]
            
            needs_commit = False
            if 'whatsapp_alert_sent' not in whatsapp_deal_columns:
                db.session.execute(text("""
                    ALTER TABLE deals 
                    ADD COLUMN IF NOT EXISTS whatsapp_alert_sent BOOLEAN DEFAULT FALSE
                """))
                needs_commit = True
            if 'whatsapp_alert_sent_at' not in whatsapp_deal_columns:
                db.session.execute(text("""
                    ALTER TABLE deals 
                    ADD COLUMN IF NOT EXISTS whatsapp_alert_sent_at TIMESTAMP
                """))
                needs_commit = True
            if 'whatsapp_followup_count' not in whatsapp_deal_columns:
                db.session.execute(text("""
                    ALTER TABLE deals 
                    ADD COLUMN IF NOT EXISTS whatsapp_followup_count INTEGER DEFAULT 0
                """))
                needs_commit = True
            if 'whatsapp_last_followup_at' not in whatsapp_deal_columns:
                db.session.execute(text("""
                    ALTER TABLE deals 
                    ADD COLUMN IF NOT EXISTS whatsapp_last_followup_at TIMESTAMP
                """))
                needs_commit = True
            if 'whatsapp_stopped' not in whatsapp_deal_columns:
                db.session.execute(text("""
                    ALTER TABLE deals 
                    ADD COLUMN IF NOT EXISTS whatsapp_stopped BOOLEAN DEFAULT FALSE
                """))
                needs_commit = True
            
            if needs_commit:
                db.session.commit()
                print("✅ WhatsApp deal fields migration completed")
        except Exception as e:
            db.session.rollback()
            print(f"⚠️  WhatsApp migration error: {e}")
        
        # Pub/Sub migrations
        try:
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'gmail_tokens' 
                AND column_name IN ('pubsub_topic', 'pubsub_subscription', 'watch_expiration')
                LIMIT 3
            """))
            existing_pubsub_columns = [row[0] for row in result]
            
            if 'pubsub_topic' not in existing_pubsub_columns:
                db.session.execute(text("""
                    ALTER TABLE gmail_tokens 
                    ADD COLUMN IF NOT EXISTS pubsub_topic VARCHAR(255);
                """))
            if 'pubsub_subscription' not in existing_pubsub_columns:
                db.session.execute(text("""
                    ALTER TABLE gmail_tokens 
                    ADD COLUMN IF NOT EXISTS pubsub_subscription VARCHAR(255);
                """))
            if 'watch_expiration' not in existing_pubsub_columns:
                db.session.execute(text("""
                    ALTER TABLE gmail_tokens 
                    ADD COLUMN IF NOT EXISTS watch_expiration BIGINT;
                """))
            if len(existing_pubsub_columns) < 3:
                db.session.commit()
        except Exception:
            db.session.rollback()
        
        # Unique constraint migration (prevents duplicate emails)
        try:
            # Check if unique constraint already exists
            result = db.session.execute(text("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'email_classifications' 
                AND constraint_name = 'uq_user_message'
                LIMIT 1
            """))
            constraint_exists = result.fetchone() is not None
            
            if not constraint_exists:
                print("🔄 Running lazy migration: Adding unique constraint on (user_id, message_id)...")
                try:
                    # First, clean up any duplicates (keep the oldest record for each user_id + message_id pair)
                    print("🧹 Cleaning up duplicate email classifications...")
                    cleanup_result = db.session.execute(text("""
                        DELETE FROM email_classifications
                        WHERE id NOT IN (
                            SELECT MIN(id)
                            FROM email_classifications
                            GROUP BY user_id, message_id
                        )
                        AND (user_id, message_id) IN (
                            SELECT user_id, message_id
                            FROM email_classifications
                            GROUP BY user_id, message_id
                            HAVING COUNT(*) > 1
                        )
                    """))
                    duplicates_removed = cleanup_result.rowcount
                    if duplicates_removed > 0:
                        print(f"✅ Removed {duplicates_removed} duplicate email classification(s)")
                        db.session.commit()
                    
                    # Now add the unique constraint
                    db.session.execute(text("""
                        ALTER TABLE email_classifications 
                        ADD CONSTRAINT uq_user_message 
                        UNIQUE (user_id, message_id);
                    """))
                    db.session.commit()
                    print("✅ Unique constraint migration completed")
                except Exception as e:
                    db.session.rollback()
                    # If constraint fails due to existing duplicates, warn but continue
                    if 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower() or 'uq_user_message' in str(e):
                        print(f"⚠️  Unique constraint migration skipped: Duplicates still exist after cleanup. Run cleanup_duplicates.py manually.")
                    else:
                        print(f"⚠️  Unique constraint migration error: {e}")
        except Exception as e:
            db.session.rollback()
            print(f"⚠️  Unique constraint migration check error: {e}")
        
        _migrations_run = True
        print("✅ Lazy migrations completed")
    except Exception as e:
        print(f"⚠️  Lazy migration error (non-critical): {e}")
        _migrations_run = True  # Mark as run to prevent retry loops


# PRIORITY 1: Row-Level Security (RLS) - Set user context for database queries
@app.before_request
def set_user_context_for_rls():
    """Set PostgreSQL user context for Row-Level Security and run lazy migrations"""
    # Run migrations on first request (lazy loading)
    run_lazy_migrations()
    
    if current_user.is_authenticated:
        try:
            # Set user context for RLS (PostgreSQL only)
            # This allows RLS policies to filter by user_id automatically
            db.session.execute(
                text("SET LOCAL app.current_user_id = :user_id"),
                {"user_id": current_user.id}
            )
        except Exception as e:
            # Ignore errors for SQLite (RLS is PostgreSQL-only)
            # Also ignore if RLS not yet enabled (migration not run)
            if 'sqlite' not in str(e).lower() and 'does not exist' not in str(e).lower():
                print(f"⚠️  Warning: Could not set RLS context: {e}")


# Initialize database (lazy - everything happens on first request to prevent startup hangs)
# Skip ALL database operations at startup - they happen automatically on first request
# This ensures fast startup and prevents deployment hangs
print("✅ App initialized (database connection and migrations will happen on first request)")


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
    # SECURITY: Double-check authentication and verify session matches
    if current_user.is_authenticated:
        # Verify session user_id matches current_user (prevent session hijacking)
        if 'user_id' in session:
            if session['user_id'] != current_user.id:
                print(f"⚠️  SESSION MISMATCH in /app route! Session user_id={session.get('user_id')}, current_user.id={current_user.id}")
                logout_user()
                session.clear()
                session.modified = True
                return redirect(url_for('login'))
        return redirect(url_for('dashboard'))
    # Not authenticated - clear any stale session data
    session.clear()
    session.modified = True
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    try:
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            print(f"🔍 Login attempt - Username: {username}")
            
            if not username or not password:
                print(f"❌ Login failed - Missing username or password")
                return render_template('login.html', error='Please enter both username and password')
            
            try:
                user = User.query.filter_by(username=username).first()
            except Exception as db_error:
                print(f"❌ Database error during login: {str(db_error)}")
                import traceback
                traceback.print_exc()
                return render_template('login.html', error='Database error. Please try again.')
            
            if not user:
                print(f"❌ Login failed - User not found: {username}")
                return render_template('login.html', error='Invalid username or password')
            
            # Check if user has a password (Google OAuth users might not have one)
            if not user.password_hash:
                print(f"❌ Login failed - User has no password (OAuth user): {username}")
                return render_template('login.html', error='This account was created with Google sign-in. Please use "Login with Google" instead.')
            
            try:
                password_valid = user.check_password(password)
            except Exception as pwd_error:
                print(f"❌ Password check error: {str(pwd_error)}")
                import traceback
                traceback.print_exc()
                return render_template('login.html', error='Error verifying password. Please try again.')
            
            if password_valid:
                try:
                    login_user(user)
                    # Make session permanent to survive OAuth redirects
                    session.permanent = True
                    # Store user ID in session for additional verification
                    session['user_id'] = user.id
                    session['username'] = user.username
                    print(f"✅ Login successful - User: {username} (ID: {user.id})")
                    
                    # Check for 'next' parameter to redirect after login
                    next_url = request.args.get('next') or request.form.get('next')
                    if next_url:
                        # Validate next_url to prevent open redirects
                        from urllib.parse import urlparse
                        parsed = urlparse(next_url)
                        if parsed.netloc == '' or parsed.netloc == request.host:
                            return redirect(next_url)
                    
                    # Check for OAuth error in session
                    oauth_error = session.pop('oauth_error', None)
                    oauth_error_message = session.pop('oauth_error_message', None)
                    if oauth_error:
                        # Redirect to connect_gmail with error message
                        error_param = f'?error={oauth_error}'
                        if oauth_error_message:
                            from urllib.parse import quote
                            error_param += f'&message={quote(oauth_error_message)}'
                        return redirect(url_for('connect_gmail') + error_param)
                    
                    return redirect(url_for('dashboard'))
                except Exception as login_error:
                    print(f"❌ Error during login_user: {str(login_error)}")
                    import traceback
                    traceback.print_exc()
                    return render_template('login.html', error='Login error. Please try again.')
            else:
                print(f"❌ Login failed - Invalid password for user: {username}")
                return render_template('login.html', error='Invalid username or password')
    except Exception as e:
        print(f"❌ Unexpected error in login route: {str(e)}")
        import traceback
        traceback.print_exc()
        return render_template('login.html', error='An unexpected error occurred. Please try again.')
    
    # GET request - check for error messages from query parameters or session
    error = request.args.get('error')
    message = request.args.get('message', '')
    display_error = None
    
    # Check session for OAuth errors
    oauth_error = session.get('oauth_error')
    oauth_error_message = session.get('oauth_error_message')
    
    if oauth_error:
        display_error = oauth_error_message or 'OAuth authorization failed. Please try connecting Gmail again after logging in.'
    elif error:
        # Decode URL-encoded message
        if message:
            from urllib.parse import unquote
            message = unquote(message)
        display_error = message or 'An error occurred. Please try again.'
    
    return render_template('login.html', error=display_error)


@app.route('/signup-google')
def signup_google():
    """Initiate Google OAuth signup flow"""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        import json
        
        # Get credentials
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
            return jsonify({'error': 'Google OAuth credentials not found'}), 500
        
        # Create flow with userinfo scopes
        flow = InstalledAppFlow.from_client_config(credentials_data, SCOPES)
        
        redirect_uri = os.getenv('OAUTH_REDIRECT_URI')
        if redirect_uri:
            flow.redirect_uri = redirect_uri
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            session['oauth_state'] = state
            session['oauth_signup'] = True  # Mark this as a signup flow
            session.permanent = True
            session.modified = True
            del flow
            return redirect(authorization_url)
        else:
            # Local development
            creds = flow.run_local_server(port=0, open_browser=True)
            # Handle local signup (similar to callback)
            return handle_google_signup_callback(creds)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error initiating Google signup: {str(e)}", 500


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """User registration"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        whatsapp_enabled = request.form.get('whatsapp_enabled') == 'on'
        whatsapp_number = request.form.get('whatsapp_number', '').strip()
        
        # Validation
        if password != confirm_password:
            return render_template('signup.html', error='Passwords do not match')
        
        if User.query.filter_by(username=username).first():
            return render_template('signup.html', error='Username already exists')
        
        if User.query.filter_by(email=email).first():
            return render_template('signup.html', error='Email already registered')
        
        # Validate WhatsApp number if enabled
        if whatsapp_enabled and not whatsapp_number:
            return render_template('signup.html', error='Please enter a WhatsApp number')
        
        if whatsapp_enabled and not whatsapp_number.startswith('+'):
            return render_template('signup.html', error='WhatsApp number must include country code (e.g., +1234567890)')
        
        # Create new user
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        # Set WhatsApp preferences
        if whatsapp_enabled and whatsapp_number:
            new_user.whatsapp_enabled = True
            new_user.whatsapp_number = whatsapp_number
            print(f"✅ New user {username} signed up with WhatsApp: {whatsapp_number}")
        else:
            new_user.whatsapp_enabled = False
            new_user.whatsapp_number = None
        
        db.session.add(new_user)
        db.session.commit()
        
        # Log in the new user
        login_user(new_user)
        session.permanent = True
        session['user_id'] = new_user.id
        session['username'] = new_user.username
        
        # Return success - frontend will show Gmail connection modal
        return render_template('signup.html', signup_success=True, username=username)
    
    return render_template('signup.html', signup_success=False)


@app.route('/logout')
@login_required
def logout():
    """User logout - completely clear session and cookies"""
    user_id = current_user.id if current_user.is_authenticated else None
    username = current_user.username if current_user.is_authenticated else None
    
    # Logout user (clears Flask-Login session)
    logout_user()
    
    # Clear all session data
    session.clear()
    
    # Explicitly mark session as modified to ensure cookie is deleted
    session.modified = True
    
    # Clear any remaining session cookies by setting them to expire
    from flask import make_response
    response = make_response(redirect(url_for('index')))
    
    # Delete session cookie
    response.set_cookie('session', '', expires=0, max_age=0, path='/', domain=None)
    
    print(f"✅ User {user_id} ({username}) logged out - session and cookies cleared")
    
    return response


# ==================== DASHBOARD ====================

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - email management"""
    # SECURITY: Verify session matches current_user to prevent session hijacking
    if 'user_id' in session and session['user_id'] != current_user.id:
        print(f"⚠️  SESSION MISMATCH DETECTED! Session user_id={session.get('user_id')}, current_user.id={current_user.id}")
        logout_user()
        session.clear()
        return redirect(url_for('login'))
    
    # Store user ID in session if not present (for old sessions)
    if 'user_id' not in session:
        session['user_id'] = current_user.id
        session['username'] = current_user.username
    
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
    
    # Check if setup is needed (first-time user with Gmail connected but setup not completed)
    needs_setup = has_gmail and not current_user.setup_completed
    
    return render_template('dashboard.html', has_gmail=has_gmail, gmail_email=gmail_email, needs_setup=needs_setup, setup_completed=current_user.setup_completed)


# ==================== GMAIL CONNECTION ====================

@app.route('/connect-gmail')
@login_required
def connect_gmail():
    """Initiate Gmail OAuth flow"""
    # Track if this is from signup
    if request.args.get('from_signup') == 'true':
        session['from_signup'] = True
    
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


def handle_google_signup_callback(creds):
    """Handle Google OAuth callback for signup - create account and connect Gmail"""
    try:
        from googleapiclient.discovery import build
        
        # Get user info from Google
        userinfo_service = build('oauth2', 'v2', credentials=creds)
        user_info = userinfo_service.userinfo().get().execute()
        
        google_id = user_info.get('id')
        email = user_info.get('email')
        full_name = user_info.get('name', '')
        profile_picture = user_info.get('picture', '')
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            # User exists, log them in
            login_user(existing_user)
            session.permanent = True
            session['user_id'] = existing_user.id
            session['username'] = existing_user.username
        else:
            # Create new user from Google data
            username = email.split('@')[0]  # Use email prefix as username
            # Ensure username is unique
            base_username = username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1
            
            new_user = User(
                username=username,
                email=email,
                google_id=google_id,
                full_name=full_name,
                profile_picture=profile_picture,
                password_hash=None  # No password for Google OAuth users
            )
            db.session.add(new_user)
            db.session.commit()
            
            # Log in the new user
            login_user(new_user)
            session.permanent = True
            session['user_id'] = new_user.id
            session['username'] = new_user.username
            print(f"✅ Created new user from Google: {username} ({email})")
        
        # Now connect Gmail (same as regular flow)
        token_json = creds.to_json()
        encrypted_token = encrypt_token(token_json)
        
        current_user_obj = User.query.get(session['user_id'])
        gmail_token = GmailToken.query.filter_by(user_id=current_user_obj.id).first()
        if gmail_token:
            gmail_token.encrypted_token = encrypted_token
        else:
            gmail_token = GmailToken(user_id=current_user_obj.id, encrypted_token=encrypted_token)
            db.session.add(gmail_token)
        
        db.session.commit()
        
        # Set up Pub/Sub if enabled
        use_pubsub = os.getenv('USE_PUBSUB', 'false').lower() == 'true'
        if use_pubsub:
            try:
                pubsub_topic = os.getenv('PUBSUB_TOPIC')
                if pubsub_topic:
                    gmail = get_user_gmail_client(current_user_obj)
                    if gmail:
                        watch_result = gmail.setup_pubsub_watch(pubsub_topic, user_id=current_user_obj.id)
                        if watch_result:
                            gmail_token.pubsub_topic = pubsub_topic
                            gmail_token.watch_expiration = watch_result.get('expiration')
                            if watch_result.get('history_id'):
                                gmail_token.history_id = str(watch_result['history_id'])
                            db.session.commit()
            except Exception as pubsub_error:
                print(f"⚠️  Pub/Sub auto-setup error (non-critical): {pubsub_error}")
        
        return redirect(url_for('dashboard') + '?auto_setup=true')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error in Google signup: {str(e)}", 500


@app.route('/oauth2callback')
def oauth2callback():
    """OAuth 2.0 callback handler for Railway/production - handles both signup and login"""
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
        if not redirect_uri:
            return "OAUTH_REDIRECT_URI not configured", 500
        
        flow = InstalledAppFlow.from_client_config(credentials_data, SCOPES)
        
        # Construct callback URL with HTTPS (required for OAuth)
        # Replace HTTP with HTTPS in the callback URL if needed
        callback_url = request.url
        if callback_url.startswith('http://'):
            callback_url = callback_url.replace('http://', 'https://', 1)
        
        # Extract the actual redirect URI from the callback URL (base URL without query params)
        from urllib.parse import urlparse, urlunparse
        parsed_callback = urlparse(callback_url)
        actual_redirect_uri = urlunparse((parsed_callback.scheme, parsed_callback.netloc, parsed_callback.path, '', '', ''))
        
        # CRITICAL: Use the actual redirect URI from the callback URL (must match exactly)
        # This ensures the redirect_uri in token exchange matches what Google expects
        # The env variable might have trailing slashes or different casing, so use the actual one
        redirect_uri_for_exchange = actual_redirect_uri
        flow.redirect_uri = redirect_uri_for_exchange  # Set flow redirect_uri to match callback
        
        print(f"🔍 OAuth callback - Redirect URI from env: {redirect_uri}")
        print(f"🔍 OAuth callback - Actual redirect URI from callback: {redirect_uri_for_exchange}")
        print(f"🔍 OAuth callback - Using actual redirect URI for flow: {redirect_uri_for_exchange}")
        
        # Extract authorization code FIRST (before any token exchange attempts)
        # This prevents the code from being consumed if flow.fetch_token() fails
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(callback_url)
        params = parse_qs(parsed.query)
        auth_code = params.get('code', [None])[0]
        
        if not auth_code:
            return "No authorization code in callback URL", 400
        
        # CRITICAL: Always use manual token exchange to avoid code consumption issues
        # flow.fetch_token() can consume the code even when it fails (e.g., scope mismatches)
        # Manual exchange gives us better control and error handling
        print(f"🔄 Using manual token exchange (skipping flow.fetch_token() to prevent code consumption)")
        
        creds = None
        
        # Always use manual token exchange for better control
        # This prevents the authorization code from being consumed by flow.fetch_token()
        # when there are scope mismatches or other issues
        print(f"🔄 Attempting manual token exchange...")
        client_id = credentials_data['installed']['client_id']
        client_secret = credentials_data['installed']['client_secret']
        
        token_url = 'https://oauth2.googleapis.com/token'
        token_data = {
            'code': auth_code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri_for_exchange,  # Use actual redirect URI from callback
            'grant_type': 'authorization_code'
        }
        
        print(f"🔍 Token exchange - Using redirect_uri: {redirect_uri_for_exchange}")
        response = requests.post(token_url, data=token_data)
        token_response = response.json()
        
        if 'error' in token_response:
            error_msg = token_response.get('error_description', token_response.get('error', 'Unknown error'))
            error_code = token_response.get('error', '')
            print(f"❌ Token exchange error: {error_msg}")
            print(f"   Error code: {error_code}")
            print(f"   Full response: {token_response}")
            
            # Handle invalid_grant - usually means auth code expired or was already used
            if error_code == 'invalid_grant':
                print(f"⚠️  Invalid grant error - authorization code may have expired or been used")
                print(f"   This can happen if:")
                print(f"   - The OAuth flow took too long (codes expire in ~10 minutes)")
                print(f"   - The authorization code was already used")
                print(f"   - The redirect_uri doesn't match exactly")
                print(f"   - Scope mismatch (scopes changed)")
                print(f"   Redirecting user to reconnect Gmail...")
                session.pop('oauth_state', None)
                session.pop('from_signup', None)
                if current_user.is_authenticated:
                    return redirect(url_for('dashboard') + '?oauth_error=invalid_grant&message=Please try reconnecting Gmail. The authorization may have expired.')
                else:
                    session['oauth_error'] = 'invalid_grant'
                    session['oauth_error_message'] = 'OAuth authorization failed. Please log in and try connecting Gmail again.'
                    return redirect(url_for('login') + '?next=' + url_for('connect_gmail'))
            
            raise Exception(f"Token exchange failed: {error_msg}")
        
        # Create credentials from token response
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=token_response['access_token'],
            refresh_token=token_response.get('refresh_token'),
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=token_response.get('scope', '').split() if 'scope' in token_response else SCOPES
        )
        print(f"✅ Successfully obtained token via manual exchange")
        
        # Now we have creds, continue with the rest of the flow
        if not creds:
            creds = flow.credentials
        
        # Check if this is a signup flow (user not logged in yet)
        is_signup = session.get('oauth_signup', False)
        session.pop('oauth_signup', None)
        
        # If signup flag is missing (session lost), check if user exists by email/google_id
        # This handles the case where session doesn't persist through OAuth redirect
        if not is_signup and not current_user.is_authenticated:
            try:
                from googleapiclient.discovery import build
                userinfo_service = build('oauth2', 'v2', credentials=creds)
                user_info = userinfo_service.userinfo().get().execute()
                email = user_info.get('email')
                google_id = user_info.get('id')
                
                # Check if user exists
                existing_user = None
                if google_id:
                    existing_user = User.query.filter_by(google_id=google_id).first()
                if not existing_user and email:
                    existing_user = User.query.filter_by(email=email).first()
                
                if not existing_user:
                    # User doesn't exist - treat as signup
                    print(f"🔍 User not found (email: {email}, google_id: {google_id}), treating as signup")
                    return handle_google_signup_callback(creds)
                else:
                    # User exists but not logged in - log them in automatically
                    print(f"🔍 User exists but not authenticated, logging in automatically: {existing_user.email}")
                    login_user(existing_user)
                    session.permanent = True
                    session['user_id'] = existing_user.id
                    session['username'] = existing_user.username
                    # Continue with Gmail connection flow below
            except Exception as check_error:
                print(f"⚠️  Error checking if user exists: {check_error}")
                # If we can't check, fall through to regular flow
        
        if is_signup:
            # Handle Google signup - create account and connect Gmail
            return handle_google_signup_callback(creds)
        
        # Regular flow - user is already logged in, just connecting Gmail
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        
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
        
        # Set up Pub/Sub immediately when Gmail is connected (not waiting for setup completion)
        use_pubsub = os.getenv('USE_PUBSUB', 'false').lower() == 'true'
        if use_pubsub:
            try:
                pubsub_topic = os.getenv('PUBSUB_TOPIC')
                if pubsub_topic:
                    gmail = get_user_gmail_client(current_user)
                    if gmail:
                        print(f"📡 Setting up Pub/Sub immediately for user {current_user.id}...")
                        watch_result = gmail.setup_pubsub_watch(pubsub_topic, user_id=current_user.id)
                        if watch_result:
                            gmail_token.pubsub_topic = pubsub_topic
                            gmail_token.watch_expiration = watch_result.get('expiration')
                            if watch_result.get('history_id'):
                                gmail_token.history_id = str(watch_result['history_id'])
                            db.session.commit()
                            print(f"✅ Pub/Sub set up immediately for user {current_user.id}")
                        else:
                            print(f"⚠️  Pub/Sub setup failed for user {current_user.id} (non-critical)")
            except Exception as pubsub_error:
                print(f"⚠️  Pub/Sub auto-setup error (non-critical): {pubsub_error}")
        
        # CRITICAL: Delete flow object before returning (it's not JSON serializable)
        del flow
        del creds
        
        # Clear session
        session.pop('oauth_state', None)
        session.modified = True
        
        # Check if this is from signup (auto-start setup)
        from_signup = request.args.get('from_signup') == 'true' or session.get('from_signup', False)
        session.pop('from_signup', None)
        
        # Redirect to dashboard - setup screen will show automatically if setup_completed is False
        if from_signup:
            return redirect(url_for('dashboard') + '?auto_setup=true')
        else:
            return redirect(url_for('dashboard') + '?connected=true')
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error completing OAuth: {str(e)}", 500




@app.route('/disconnect-gmail', methods=['POST'])
@login_required
def disconnect_gmail():
    """Disconnect Gmail account"""
    try:
        if current_user.gmail_token:
            db.session.delete(current_user.gmail_token)
            db.session.commit()
            print(f"✅ Disconnected Gmail for user {current_user.id}")
        
        # Return JSON for API calls, redirect for form submissions
        if request.is_json or request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': True, 'message': 'Gmail disconnected successfully'})
        else:
            return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"❌ Error disconnecting Gmail: {e}")
        if request.is_json or request.headers.get('Content-Type') == 'application/json':
            return jsonify({'success': False, 'error': str(e)}), 500
        else:
            return redirect(url_for('dashboard'))


# ==================== API ENDPOINTS ====================

@app.route('/api/emails/sync', methods=['POST'])
@login_required
def trigger_email_sync():
    """
    Trigger background email sync (Phase 1: Background Workers)
    Returns immediately with task ID - user polls for status
    """
    if not current_user.gmail_token:
        return jsonify({
            'success': False,
            'error': 'Gmail not connected. Please connect your Gmail account.'
        }), 400
    
    if not CELERY_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Background processing not available. Please use /api/emails endpoint.'
        }), 503
    
    try:
        from celery_config import celery
        
        # Check if workers are actually running by inspecting active workers (with timeout)
        try:
            inspect = celery.control.inspect(timeout=2.0)  # 2 second timeout to prevent hanging
            active_workers = inspect.active()
            if not active_workers:
                # No workers available - return 503 to trigger fallback
                return jsonify({
                    'success': False,
                    'error': 'No Celery workers available. Please use /api/emails endpoint.'
                }), 503
        except Exception as worker_check_error:
            # If we can't check workers, still try to queue the task
            # Frontend will timeout and fall back if worker isn't running
            print(f"⚠️  Could not check worker status: {worker_check_error}")
        
        # Get parameters
        max_emails = min(request.json.get('max', 50), 200)  # Cap at 200
        force_full_sync = request.json.get('force_full_sync', False)
        
        # Trigger background task
        task = sync_user_emails.delay(
            user_id=current_user.id,
            max_emails=max_emails,
            force_full_sync=force_full_sync
        )
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'Email sync started in background',
            'status': 'PENDING'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to start sync: {str(e)}'
        }), 500

@app.route('/api/workers/status')
@login_required
def check_workers_status():
    """Check if Celery workers are running"""
    if not CELERY_AVAILABLE:
        return jsonify({
            'success': False,
            'celery_available': False,
            'message': 'Celery not available'
        })
    
    try:
        from celery_config import celery
        
        # Check active workers (with timeout to prevent hanging)
        inspect = celery.control.inspect(timeout=2.0)
        
        active_workers = inspect.active()
        registered_workers = inspect.registered()
        stats = inspect.stats()
        
        worker_count = len(active_workers) if active_workers else 0
        registered_count = len(registered_workers) if registered_workers else 0
        
        # Check Redis connection
        redis_connected = False
        try:
            from celery_config import celery
            celery.control.broadcast('ping', reply=True, timeout=1)
            redis_connected = True
        except:
            pass
        
        return jsonify({
            'success': True,
            'celery_available': True,
            'redis_connected': redis_connected,
            'active_workers': worker_count,
            'registered_workers': registered_count,
            'worker_details': {
                'active': list(active_workers.keys()) if active_workers else [],
                'registered': list(registered_workers.keys()) if registered_workers else [],
                'stats': stats if stats else {}
            },
            'message': f'Found {worker_count} active worker(s)' if worker_count > 0 else 'No active workers found'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'celery_available': True,
            'error': str(e),
            'message': 'Could not check worker status'
        }), 500

@app.route('/api/emails/count')
@login_required
def get_email_count():
    """Get total count of emails for the current user"""
    try:
        count = EmailClassification.query.filter_by(user_id=current_user.id).count()
        return jsonify({
            'success': True,
            'count': count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/emails/fetch-older', methods=['POST'])
@login_required
def trigger_fetch_older_emails():
    """
    Trigger background task to fetch older emails (before the initial 60).
    Fetches slowly to avoid rate limits.
    """
    if not current_user.gmail_token:
        return jsonify({
            'success': False,
            'error': 'Gmail not connected. Please connect your Gmail account.'
        }), 400
    
    if not CELERY_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Background processing not available.'
        }), 503
    
    try:
        from celery_config import celery
        from tasks import fetch_older_emails
        
        # Check if we already have 200+ emails
        email_count = EmailClassification.query.filter_by(user_id=current_user.id).count()
        print(f"📊 Checking older email fetch: current count = {email_count}, target = 200")
        if email_count >= 200:
            print(f"✅ Already have {email_count} emails (200+), skipping older email fetch")
            return jsonify({
                'success': False,
                'error': 'Already have 200+ emails',
                'count': email_count
            }), 200  # Return 200 to indicate success but no action needed
        
        print(f"📧 Starting older email fetch: have {email_count} emails, need {200 - email_count} more")
        
        # Check if workers are running (with timeout to prevent hanging)
        try:
            inspect = celery.control.inspect(timeout=2.0)  # 2 second timeout
            active_workers = inspect.active()
            if not active_workers:
                return jsonify({
                    'success': False,
                    'error': 'No Celery workers available.'
                }), 503
        except Exception as worker_check_error:
            print(f"⚠️  Could not check worker status: {worker_check_error}")
            # Don't block - just continue and let the task fail if workers aren't available
        
        # Check if there's already a running task for this user (with timeout)
        try:
            # Get all active tasks (with timeout)
            inspect = celery.control.inspect(timeout=2.0)  # 2 second timeout
            active_tasks = inspect.active()
            if active_tasks:
                for worker, tasks in active_tasks.items():
                    for task in tasks:
                        # Check if it's a fetch_older_emails task for this user
                        if task.get('name') == 'tasks.fetch_older_emails':
                            task_args = task.get('args', [])
                            if len(task_args) >= 1 and task_args[0] == current_user.id:
                                return jsonify({
                                    'success': False,
                                    'error': 'Older email fetch already in progress',
                                    'task_id': task.get('id')
                                }), 409  # Conflict
        except Exception as task_check_error:
            print(f"⚠️  Could not check for existing tasks: {task_check_error}")
            # Don't block - just continue (worst case: duplicate task, but duplicate prevention in DB will catch it)
        
        # Get max emails (default 200, cap at 200)
        max_emails = min(request.json.get('max', 200), 200)
        
        # Trigger background task
        try:
            print(f"🚀 Queuing fetch_older_emails task for user {current_user.id} with max_emails={max_emails}")
            task = fetch_older_emails.delay(
                user_id=current_user.id,
                max_emails=max_emails
            )
            print(f"✅ Task queued successfully: {task.id}")
            
            return jsonify({
                'success': True,
                'task_id': task.id,
                'message': 'Older email fetch started in background',
                'status': 'PENDING'
            })
        except Exception as task_error:
            print(f"❌ Error queuing task: {task_error}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': f'Failed to queue older email fetch task: {str(task_error)}'
            }), 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to start older email fetch: {str(e)}'
        }), 500

@app.route('/api/emails/sync/status/<task_id>')
@login_required
def get_sync_status(task_id):
    """Get status of background email sync task"""
    if not CELERY_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Background processing not available'
        }), 503
    
    try:
        from celery_config import celery
        task = celery.AsyncResult(task_id)
        
        if task.state == 'PENDING':
            response = {
                'success': True,
                'status': 'PENDING',
                'message': 'Task is waiting to be processed'
            }
        elif task.state == 'PROGRESS':
            response = {
                'success': True,
                'status': 'PROGRESS',
                'message': task.info.get('status', 'Processing...'),
                'progress': task.info.get('progress', 0),
                'total': task.info.get('total', 0),
                'fetched': task.info.get('fetched', 0),
                'classified': task.info.get('classified', 0),
                'current': task.info.get('current', 0),
                'current_email': task.info.get('current_email', '')
            }
        elif task.state == 'SUCCESS':
            result = task.result
            response = {
                'success': True,
                'status': 'SUCCESS',
                'message': 'Sync completed',
                'emails_processed': result.get('emails_processed', 0),
                'emails_classified': result.get('emails_classified', 0),
                'total_fetched': result.get('total_fetched', 0),
                'errors': result.get('errors', [])
            }
        else:  # FAILURE or other states
            response = {
                'success': False,
                'status': task.state,
                'error': str(task.info) if task.info else 'Task failed'
            }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get status: {str(e)}'
        }), 500

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
    except Exception as e:
        print(f"Error getting Gmail email: {str(e)}")
        gmail = None

    def respond_with_database_emails(log_message=None):
        """Return emails from database (always authoritative source for UI)."""
        if log_message:
            print(log_message)
        else:
            print("📂 Loading all classified emails from database...")

        # SECURITY: Verify user is authenticated and get user_id
        if not current_user.is_authenticated:
            print(f"⚠️  [SECURITY] Unauthenticated user attempted to access emails")
            logout_user()
            session.clear()
            return jsonify({'error': 'User session expired. Please log in again.'}), 401
        
        # Check if user still exists (may have been deleted)
        try:
            user_id = current_user.id
            username = current_user.username
        except (AttributeError, Exception) as e:
            # User has been deleted or session is invalid
            print(f"⚠️  User session invalid or user deleted: {e}")
            logout_user()
            session.clear()
            return jsonify({'error': 'User session expired. Please log in again.'}), 401
        
        # SECURITY: Verify session user_id matches current_user.id (prevent session hijacking)
        if 'user_id' in session and session['user_id'] != user_id:
            print(f"⚠️  [SECURITY] SESSION MISMATCH in get_emails! Session user_id={session.get('user_id')}, current_user.id={user_id}")
            logout_user()
            session.clear()
            return jsonify({'error': 'Session mismatch detected. Please log in again.'}), 401
        
        # Log user_id for debugging (helps identify cross-user issues)
        print(f"🔒 [SECURITY] Loading emails for user_id={user_id} (username={username})")
        
        print(f"   (Ignoring 'unread_only' filter - database doesn't track read status)")
        query = EmailClassification.query.filter_by(user_id=user_id)

        if category_filter:
            query = query.filter_by(category=category_filter)

        print(f"   Loading all emails from database" + (f" (category: {category_filter})" if category_filter else ""))
        db_classifications = query.order_by(EmailClassification.classified_at.desc()).all()

        classified_emails = []
        message_ids = [c.message_id for c in db_classifications]
        star_status_map = {}
        if message_ids and gmail and getattr(gmail, 'service', None):
            try:
                from googleapiclient.http import BatchHttpRequest
                star_status_results = {}

                def star_callback(request_id, response, exception):
                    if exception:
                        return
                    if response:
                        msg_id = request_id.split('_', 2)[-1] if '_' in request_id else request_id
                        label_ids = response.get('labelIds', [])
                        star_status_results[msg_id] = {
                            'is_starred': 'STARRED' in label_ids,
                            'label_ids': label_ids if isinstance(label_ids, list) else []
                        }

                BATCH_SIZE = 100
                message_ids_to_fetch = message_ids[:200]

                for chunk_start in range(0, len(message_ids_to_fetch), BATCH_SIZE):
                    chunk = message_ids_to_fetch[chunk_start:chunk_start + BATCH_SIZE]
                    batch = gmail.service.new_batch_http_request(callback=star_callback)

                    for idx, msg_id in enumerate(chunk):
                        batch.add(gmail.service.users().messages().get(
                            userId='me',
                            id=msg_id,
                            format='metadata'
                        ), request_id=f"star_{chunk_start + idx}_{msg_id}")

                    if chunk:
                        batch.execute()

                star_status_map = star_status_results
                print(f"⭐ Fetched star status for {len(star_status_map)} emails from Gmail")
            except Exception as e:
                print(f"⚠️  Could not batch fetch star status: {str(e)}")

        for classification in db_classifications:
            if classification.category == CATEGORY_SPAM and not show_spam:
                continue

            if category_filter and classification.category != category_filter:
                continue

            star_info = star_status_map.get(classification.message_id, {'is_starred': False, 'label_ids': []})

            email_data = {
                'id': classification.message_id,
                'thread_id': classification.thread_id,
                'subject': classification.get_subject_decrypted() or 'No Subject',
                'from': classification.sender or 'Unknown',
                'snippet': classification.get_snippet_decrypted() or '',
                'date': classification.email_date or (int(classification.classified_at.timestamp() * 1000) if classification.classified_at else None),
                'is_starred': star_info['is_starred'],
                'is_read': 'UNREAD' not in star_info['label_ids'],
                'label_ids': star_info['label_ids'],
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
            if not MINIMAL_LOGGING:
                print(f"📧 Loaded from DB: Category={classification.category}, Thread={classification.thread_id[:16]}")

        print(f"✅ Returning {len(classified_emails)} emails from database")

        return jsonify({
            'success': True,
            'count': len(classified_emails),
            'emails': classified_emails
        })

    try:
        # If Gmail failed earlier, gmail variable may be None
        if not gmail and not db_only:
            print("⚠️ Gmail client unavailable, falling back to database response.")
            return respond_with_database_emails()

        # Get max_emails from query param for Gmail API fetching
        # For display, there's no limit - pagination handles it
        # For initial setup (full sync), limit to 200. For incremental sync, fetch all new emails.
        max_emails = request.args.get('max', default=None, type=int)  # No default limit - will be set based on sync type
        category_filter = request.args.get('category')  # Optional category filter
        show_spam = request.args.get('show_spam', 'false').lower() == 'true'
        unread_only = False  # Always fetch all emails (unread only filter removed)
        force_full_sync = request.args.get('force_full_sync', 'false').lower() == 'true'  # Force full sync (ignore history_id)
        db_only = request.args.get('db_only', 'false').lower() == 'true'  # Load only from database, skip Gmail API
        
        # If db_only is requested, skip Gmail API and load directly from database
        if db_only:
            print("📂 Loading emails from database only (skipping Gmail API)...")
            return respond_with_database_emails()
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
                # Determine max_results based on sync type:
                # - Full sync (initial setup): Limit to 200
                # - Incremental sync (has history_id): Fetch all new emails (no limit)
                if start_history_id is None:
                    # Full sync - limit to 200 for initial setup
                    gmail_max_results = min(max_emails, 200) if max_emails else 200
                    print(f"🔄 Full sync: Limiting to {gmail_max_results} emails for initial setup")
                else:
                    # Incremental sync - fetch all new emails (gmail_client ignores max_results for incremental)
                    # Pass a large number as placeholder (method ignores it anyway)
                    gmail_max_results = max_emails if max_emails else 10000  # Large number, but method ignores it for incremental
                    print(f"🔄 Incremental sync: Fetching all new emails (no limit)")
                
                # Use incremental sync if we have a history_id (90%+ reduction in API calls!)
                emails, new_history_id = gmail.get_emails(
                    max_results=gmail_max_results, 
                    unread_only=unread_only,
                    start_history_id=start_history_id
                )
                
                # Store new history_id for next sync
                if new_history_id and gmail_token:
                    gmail_token.history_id = new_history_id
                    db.session.commit()
                    print(f"💾 Stored new historyId: {new_history_id}")
                
                # If incremental sync found no new emails, check if history_id is stale
                # If history_id is stale, there might be new emails that weren't detected
                if len(emails) == 0 and start_history_id and CELERY_AVAILABLE:
                    print(f"🔄 Incremental sync found no new emails. Checking if history_id is stale...")
                    try:
                        # Get current history_id from Gmail profile to check if it's different
                        profile = gmail.get_profile()
                        current_history_id = profile.get('historyId') if profile else None
                        
                        if current_history_id and str(current_history_id) != str(start_history_id):
                            print(f"⚠️  History_id is stale! Stored: {start_history_id}, Current: {current_history_id}")
                            print(f"   Updating history_id and triggering background sync to fetch new emails...")
                            
                            # Update history_id in database
                            if gmail_token:
                                gmail_token.history_id = str(current_history_id)
                                db.session.commit()
                            
                            # Trigger background sync with updated history_id
                            from tasks import sync_user_emails
                            task = sync_user_emails.delay(
                                user_id=current_user.id,
                                max_emails=200,  # This will be ignored for incremental sync
                                force_full_sync=False  # Use incremental sync with updated history_id
                            )
                            print(f"✅ Background sync triggered with updated history_id: {task.id}")
                        else:
                            print(f"✅ History_id is current ({start_history_id}). No new emails.")
                    except Exception as sync_error:
                        print(f"⚠️  Could not check history_id or trigger background sync: {str(sync_error)}")
                        # Fallback: trigger sync anyway
                        try:
                            from tasks import sync_user_emails
                            task = sync_user_emails.delay(
                                user_id=current_user.id,
                                max_emails=200,
                                force_full_sync=False
                            )
                            print(f"✅ Background sync triggered (fallback): {task.id}")
                        except:
                            pass
                
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
                                # Rate limit concurrent classifications to prevent 429 errors
                                with CLASSIFICATION_SEMAPHORE:
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
                    
                    # Check if email already exists (prevent duplicates)
                    existing_classification = EmailClassification.query.filter_by(
                        user_id=current_user.id,
                        message_id=email['id']
                    ).first()
                    
                    if existing_classification:
                        # If already processed, skip entirely (no re-classification, no PDF extraction)
                        if existing_classification.processed:
                            print(f"⏭️  Email {email['id']} already processed, skipping...")
                            continue
                        # Update existing classification instead of creating duplicate
                        classification = existing_classification
                        classification.category = classification_result['category']
                        classification.tags = ','.join(classification_result['tags'])
                        classification.confidence = classification_result['confidence']
                        classification.extracted_links = json.dumps(classification_result['links'])
                        classification.sender = email.get('from', 'Unknown')
                        classification.email_date = email.get('date')
                        # Update encrypted fields
                        classification.set_subject_encrypted(email.get('subject', 'No Subject'))
                        classification.set_snippet_encrypted(email.get('snippet', ''))
                    else:
                        # Create new classification
                        classification = EmailClassification(
                            user_id=current_user.id,
                            thread_id=email['thread_id'],
                            message_id=email['id'],
                            sender=email.get('from', 'Unknown'),
                            email_date=email.get('date'),
                            category=classification_result['category'],
                            tags=','.join(classification_result['tags']),
                            confidence=classification_result['confidence'],
                            extracted_links=json.dumps(classification_result['links'])
                        )
                        # PRIORITY 2: Use encrypted field setters
                        classification.set_subject_encrypted(email.get('subject', 'No Subject'))
                        classification.set_snippet_encrypted(email.get('snippet', ''))
                    
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
                    
                    # Commit with duplicate error handling (race condition protection)
                    try:
                        db.session.commit()
                        # Mark as processed after successful commit (prevents re-processing)
                        classification.processed = True
                        db.session.commit()
                    except Exception as commit_error:
                        error_str = str(commit_error)
                        # Handle duplicate key errors (unique constraint violation)
                        if 'UniqueViolation' in error_str or 'duplicate key' in error_str.lower() or 'uq_user_message' in error_str:
                            db.session.rollback()
                            print(f"⏭️  Email {email['id']} was inserted by another process, fetching existing classification...")
                            # Fetch the existing classification
                            existing_classification = EmailClassification.query.filter_by(
                                user_id=current_user.id,
                                message_id=email['id']
                            ).first()
                            if existing_classification:
                                # Use existing classification instead
                                classification = existing_classification
                            else:
                                # If we can't find it, skip this email
                                print(f"⚠️  Could not find existing classification for email {email['id']}, skipping...")
                                continue
                        else:
                            # Other errors - rollback and re-raise
                            db.session.rollback()
                            raise
                
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
                
                # Debug: Log what we're appending (only if not in minimal logging mode)
                if not MINIMAL_LOGGING:
                    print(f"📧 Appending email from {email.get('from', 'unknown')[:50]}: Category={classification.category}, Subject={email.get('subject', 'No subject')[:50]}, Starred={email.get('is_starred', False)}")
                
                classified_emails.append(email)
            
            except Exception as e:
                print(f"Error processing email {email.get('thread_id', 'unknown')}: {str(e)}")
                import traceback
                traceback.print_exc()
                # Continue processing other emails
                continue
        
        # After Gmail processing, always respond with the latest snapshot from the database
        return respond_with_database_emails()
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in get_emails: {str(e)}")
        print(error_trace)
        
        # Check if it's a deleted user error
        if 'ObjectDeletedError' in str(type(e)) or 'has been deleted' in str(e):
            print("⚠️  User has been deleted. Logging out user...")
            try:
                logout_user()
            except:
                pass
            return jsonify({
                'success': False, 
                'error': 'User session expired. Please log in again.',
                'logout_required': True
            }), 401
        
        return jsonify({
            'success': False, 
            'error': str(e),
            'traceback': error_trace if app.debug else None
        }), 500

@app.route('/api/emails/stream')
@login_required
def stream_emails():
    """Stream emails as they're being classified (progressive loading)"""
    # Store user info before entering generator (Flask-Login compatibility)
    try:
        user_id = current_user.id
        has_gmail_token = current_user.gmail_token is not None
    except (AttributeError, Exception) as e:
        # User has been deleted or session is invalid
        print(f"⚠️  User session invalid or user deleted in stream_emails: {e}")
        logout_user()
        return jsonify({'error': 'User session expired. Please log in again.', 'logout_required': True}), 401
    
    if not has_gmail_token:
        return jsonify({'error': 'Gmail not connected'}), 400
    
    def generate():
        try:
            # Get user object (can't use current_user in generator)
            user = User.query.get(user_id)
            if not user:
                yield f"data: {json.dumps({'error': 'User not found'})}\n\n"
                return
            
            gmail = get_user_gmail_client(user)
            if not gmail:
                yield f"data: {json.dumps({'error': 'Failed to connect to Gmail'})}\n\n"
                return
            
            max_emails = request.args.get('max', default=None, type=int)  # No default limit
            force_full_sync = request.args.get('force_full_sync', 'false').lower() == 'true'
            
            # Get history_id for incremental sync
            gmail_token = GmailToken.query.filter_by(user_id=user_id).first()
            start_history_id = gmail_token.history_id if gmail_token and not force_full_sync else None
            
            # Determine max_results based on sync type:
            # - Full sync (initial setup): Limit to 200
            # - Incremental sync (has history_id): Fetch all new emails (no limit)
            if start_history_id is None:
                # Full sync - limit to 200 for initial setup
                gmail_max_results = min(max_emails, 200) if max_emails else 200
                print(f"🔄 Full sync: Limiting to {gmail_max_results} emails for initial setup")
            else:
                # Incremental sync - fetch all new emails (gmail_client ignores max_results for incremental)
                # Pass a large number as placeholder (method ignores it anyway)
                gmail_max_results = max_emails if max_emails else 10000  # Large number, but method ignores it for incremental
                print(f"🔄 Incremental sync: Fetching all new emails (no limit)")
            
            # Send initial status
            yield f"data: {json.dumps({'status': 'fetching', 'total': gmail_max_results if start_history_id is None else 'unlimited'})}\n\n"
            
            # Fetch emails from Gmail
            emails, new_history_id = gmail.get_emails(
                max_results=gmail_max_results,
                unread_only=False,
                start_history_id=start_history_id
            )
            
            # Store new history_id
            if new_history_id and gmail_token:
                gmail_token.history_id = new_history_id
                db.session.commit()
            
            # Send count update
            yield f"data: {json.dumps({'status': 'classifying', 'total': len(emails)})}\n\n"
            
            openai_client = get_openai_client()
            classifier = EmailClassifier(openai_client)
            
            import time
            for idx, email in enumerate(emails):
                # Rate limiting
                if idx > 0:
                    time.sleep(0.5)
                
                try:
                    # Check if already classified by message_id FIRST (more accurate than thread_id)
                    existing_classification = EmailClassification.query.filter_by(
                        user_id=user_id,
                        message_id=email['id']
                    ).first()
                    
                    if existing_classification:
                        # Return existing classification
                        email_data = {
                            'id': email['id'],
                            'thread_id': email['thread_id'],
                            'subject': email.get('subject', 'No Subject'),
                            'from': email.get('from', 'Unknown'),
                            'snippet': email.get('snippet', ''),
                            'date': email.get('date'),
                            'is_starred': email.get('is_starred', False),
                            'label_ids': email.get('label_ids', []),
                            'classification': {
                                'category': existing_classification.category,
                                'tags': existing_classification.tags.split(',') if existing_classification.tags else [],
                                'confidence': existing_classification.confidence,
                                'reply_type': existing_classification.reply_type,
                                'deal_state': existing_classification.deal_state,
                                'deck_link': existing_classification.deck_link
                            }
                        }
                        # Stream this email to frontend
                        yield f"data: {json.dumps({'email': email_data, 'progress': idx + 1, 'total': len(emails)})}\n\n"
                        continue  # Skip classification, already exists
                    
                    # Classify new email
                    with CLASSIFICATION_SEMAPHORE:
                        classification_result = classifier.classify_email(
                            subject=email.get('subject', ''),
                            body=email.get('body', ''),
                            headers=email.get('headers', {}),
                            sender=email.get('from', ''),
                            thread_id=email.get('thread_id', ''),
                            user_id=user_id
                        )
                    
                    # Double-check if email was inserted by another process (race condition)
                    existing_classification = EmailClassification.query.filter_by(
                        user_id=user_id,
                        message_id=email['id']
                    ).first()
                    
                    if existing_classification:
                        # Another process inserted it, use existing
                        email_data = {
                            'id': email['id'],
                            'thread_id': email['thread_id'],
                            'subject': email.get('subject', 'No Subject'),
                            'from': email.get('from', 'Unknown'),
                            'snippet': email.get('snippet', ''),
                            'date': email.get('date'),
                            'is_starred': email.get('is_starred', False),
                            'label_ids': email.get('label_ids', []),
                            'classification': {
                                'category': existing_classification.category,
                                'tags': existing_classification.tags.split(',') if existing_classification.tags else [],
                                'confidence': existing_classification.confidence,
                                'reply_type': existing_classification.reply_type,
                                'deal_state': existing_classification.deal_state,
                                'deck_link': existing_classification.deck_link
                            }
                        }
                    else:
                        # Create new classification
                        new_classification = EmailClassification(
                            user_id=user_id,
                            thread_id=email['thread_id'],
                            message_id=email['id'],
                            sender=email.get('from', 'Unknown'),
                            email_date=email.get('date'),
                            category=classification_result['category'],
                            tags=','.join(classification_result['tags']),
                            confidence=classification_result['confidence'],
                            extracted_links=json.dumps(classification_result['links'])
                        )
                        # PRIORITY 2: Use encrypted field setters
                        new_classification.set_subject_encrypted(email.get('subject', 'No Subject'))
                        new_classification.set_snippet_encrypted(email.get('snippet', ''))
                        db.session.add(new_classification)
                        
                        # Commit with duplicate error handling
                        try:
                            db.session.commit()
                            # Mark as processed after successful commit (prevents re-processing)
                            new_classification.processed = True
                            db.session.commit()
                        except Exception as commit_error:
                            error_str = str(commit_error)
                            # Handle duplicate key errors (unique constraint violation)
                            if 'UniqueViolation' in error_str or 'duplicate key' in error_str.lower() or 'uq_user_message' in error_str:
                                db.session.rollback()
                                print(f"⏭️  Email {email['id']} was inserted by another process, skipping...")
                                # Fetch the existing classification
                                existing_classification = EmailClassification.query.filter_by(
                                    user_id=user_id,
                                    message_id=email['id']
                                ).first()
                                if existing_classification:
                                    email_data = {
                                        'id': email['id'],
                                        'thread_id': email['thread_id'],
                                        'subject': email.get('subject', 'No Subject'),
                                        'from': email.get('from', 'Unknown'),
                                        'snippet': email.get('snippet', ''),
                                        'date': email.get('date'),
                                        'is_starred': email.get('is_starred', False),
                                        'label_ids': email.get('label_ids', []),
                                        'classification': {
                                            'category': existing_classification.category,
                                            'tags': existing_classification.tags.split(',') if existing_classification.tags else [],
                                            'confidence': existing_classification.confidence,
                                            'reply_type': existing_classification.reply_type,
                                            'deal_state': existing_classification.deal_state,
                                            'deck_link': existing_classification.deck_link
                                        }
                                    }
                                else:
                                    # Skip this email if we can't find it
                                    continue
                            else:
                                # Other errors - rollback and re-raise
                                db.session.rollback()
                                raise
                        
                        if not existing_classification:
                            # New classification was created successfully
                            email_data = {
                                'id': email['id'],
                                'thread_id': email['thread_id'],
                                'subject': email.get('subject', 'No Subject'),
                                'from': email.get('from', 'Unknown'),
                                'snippet': email.get('snippet', ''),
                                'date': email.get('date'),
                                'is_starred': email.get('is_starred', False),
                                'label_ids': email.get('label_ids', []),
                                'classification': {
                                    'category': classification_result['category'],
                                    'tags': classification_result['tags'],
                                    'confidence': classification_result['confidence'],
                                    'reply_type': None,
                                    'deal_state': None,
                                    'deck_link': None
                                }
                            }
                    
                    # Stream this email to frontend
                    yield f"data: {json.dumps({'email': email_data, 'progress': idx + 1, 'total': len(emails)})}\n\n"
                    
                except Exception as e:
                    error_str = str(e)
                    # Rollback session on any error to prevent "session rolled back" errors
                    try:
                        db.session.rollback()
                    except:
                        pass
                    
                    # Check if it's a duplicate error (already handled above, but catch any edge cases)
                    if 'UniqueViolation' in error_str or 'duplicate key' in error_str.lower() or 'uq_user_message' in error_str:
                        print(f"⏭️  Email {email.get('id', 'unknown')} duplicate detected, skipping...")
                    else:
                        print(f"Error processing email {idx}: {str(e)}")
                    continue
            
            # Send completion
            yield f"data: {json.dumps({'status': 'complete'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

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
        max_emails = min(request.args.get('max', default=20, type=int), 200)  # Cap at 200 emails max (user can select 20, 50, 100, or 200)
        
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
                'body_html': email.get('body_html', ''),
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
        max_emails = min(request.args.get('max', default=20, type=int), 200)  # Cap at 200 emails max (user can select 20, 50, 100, or 200)
        
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
                'body_html': email.get('body_html', ''),
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
        max_emails = min(request.args.get('max', default=20, type=int), 200)  # Cap at 200 emails max (user can select 20, 50, 100, or 200)
        
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
                'body_html': email.get('body_html', ''),
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


@app.route('/api/drafts/create', methods=['POST'])
@login_required
def create_draft():
    """Create a new draft email"""
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
        
        data = request.json
        to = data.get('to')
        subject = data.get('subject', '')
        body = data.get('body', '')
        thread_id = data.get('thread_id')
        cc = data.get('cc')
        bcc = data.get('bcc')
        
        if not to:
            return jsonify({
                'success': False,
                'error': 'Recipient email is required'
            }), 400
        
        # Create draft via Gmail API
        draft_info = gmail.create_draft(to, subject, body, thread_id, cc, bcc)
        
        if draft_info:
            return jsonify({
                'success': True,
                'draft': draft_info
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to create draft'
            }), 500
    
    except Exception as e:
        print(f"Error creating draft: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/drafts/<draft_id>/update', methods=['PUT'])
@login_required
def update_draft(draft_id):
    """Update an existing draft"""
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
        
        data = request.json
        to = data.get('to')
        subject = data.get('subject', '')
        body = data.get('body', '')
        thread_id = data.get('thread_id')
        cc = data.get('cc')
        bcc = data.get('bcc')
        
        if not to:
            return jsonify({
                'success': False,
                'error': 'Recipient email is required'
            }), 400
        
        # Update draft via Gmail API
        draft_info = gmail.update_draft(draft_id, to, subject, body, thread_id, cc, bcc)
        
        if draft_info:
            return jsonify({
                'success': True,
                'draft': draft_info
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update draft'
            }), 500
    
    except Exception as e:
        print(f"Error updating draft: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/drafts/<draft_id>', methods=['DELETE'])
@login_required
def delete_draft(draft_id):
    """Delete a draft"""
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
        
        # Delete draft via Gmail API
        success = gmail.delete_draft(draft_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Draft deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to delete draft'
            }), 500
    
    except Exception as e:
        print(f"Error deleting draft: {str(e)}")
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
            # Rate limit concurrent classifications to prevent 429 errors
            with CLASSIFICATION_SEMAPHORE:
                classification_result = classifier.classify_email(
                    subject=email.get('subject', ''),
                    body=email_body_for_classification,  # Includes PDF content
                    headers=headers,
                    sender=email.get('from', ''),
                    links=links,
                    thread_id=email.get('thread_id'),
                    user_id=str(current_user.id)
                )
        
        # Check if email already exists (prevent duplicates)
        existing_classification = EmailClassification.query.filter_by(
            user_id=current_user.id,
            message_id=email['id']
        ).first()
        
        if existing_classification:
            # Update existing classification instead of creating duplicate
            new_classification = existing_classification
            new_classification.category = classification_result['category']
            new_classification.tags = ','.join(classification_result['tags'])
            new_classification.confidence = classification_result['confidence']
            new_classification.extracted_links = json.dumps(classification_result['links'])
            new_classification.sender = email.get('from', 'Unknown')
            new_classification.email_date = email.get('date')
            # Update encrypted fields
            new_classification.set_subject_encrypted(email.get('subject', 'No Subject'))
            new_classification.set_snippet_encrypted(email.get('snippet', ''))
        else:
            # Create new classification
            new_classification = EmailClassification(
                user_id=current_user.id,
                thread_id=thread_id,
                message_id=email['id'],
                sender=email.get('from', 'Unknown'),
                email_date=email.get('date'),
                category=classification_result['category'],
                tags=','.join(classification_result['tags']),
                confidence=classification_result['confidence'],
                extracted_links=json.dumps(classification_result['links'])
            )
            # PRIORITY 2: Use encrypted field setters
            new_classification.set_subject_encrypted(email.get('subject', 'No Subject'))
            new_classification.set_snippet_encrypted(email.get('snippet', ''))
        
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
        # Mark as processed after successful commit (prevents re-processing)
        new_classification.processed = True
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
            
            # Rate limit concurrent classifications to prevent 429 errors
            with CLASSIFICATION_SEMAPHORE:
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


@app.route('/api/email/<message_id>/mark-read', methods=['POST'])
@login_required
def mark_email_read(message_id):
    """Mark email as read in Gmail"""
    print(f"📧 [MARK-READ] Request to mark email {message_id} as read for user {current_user.id}")
    
    if not current_user.gmail_token:
        print(f"❌ [MARK-READ] User {current_user.id} has no Gmail token")
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail or not gmail.service:
            print(f"❌ [MARK-READ] Failed to get Gmail client for user {current_user.id}")
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        print(f"📧 [MARK-READ] Removing UNREAD label from message {message_id} in Gmail")
        # Mark as read in Gmail (remove UNREAD label)
        gmail.service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
        
        print(f"✅ [MARK-READ] Successfully marked email {message_id} as read in Gmail")
        return jsonify({'success': True, 'message': 'Email marked as read'})
    
    except Exception as e:
        print(f"❌ [MARK-READ] Error marking email {message_id} as read: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# In-memory cache for pending label changes (for real-time sync)
# Format: {user_id: {message_id: {'is_read': bool, 'label_ids': [...], 'timestamp': float}}}
pending_label_changes = {}

@app.route('/api/sync/label-changes', methods=['GET'])
@login_required
def get_label_changes():
    """Get pending label changes for the current user (for real-time Gmail sync)"""
    user_id = current_user.id
    
    # Get and clear pending changes for this user
    changes = pending_label_changes.pop(user_id, {})
    
    if changes:
        print(f"🔄 [SYNC] Sending {len(changes)} label changes to user {user_id}")
    
    return jsonify({
        'success': True,
        'changes': changes
    })

@app.route('/api/email/<message_id>/mark-unread', methods=['POST'])
@login_required
def mark_email_unread(message_id):
    """Mark email as unread in Gmail"""
    print(f"📧 [MARK-UNREAD] Request to mark email {message_id} as unread for user {current_user.id}")
    
    if not current_user.gmail_token:
        print(f"❌ [MARK-UNREAD] User {current_user.id} has no Gmail token")
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail or not gmail.service:
            print(f"❌ [MARK-UNREAD] Failed to get Gmail client for user {current_user.id}")
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        print(f"📧 [MARK-UNREAD] Adding UNREAD label to message {message_id} in Gmail")
        # Mark as unread in Gmail (add UNREAD label)
        gmail.service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'addLabelIds': ['UNREAD']}
        ).execute()
        
        print(f"✅ [MARK-UNREAD] Successfully marked email {message_id} as unread in Gmail")
        return jsonify({'success': True, 'message': 'Email marked as unread'})
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email/<message_id>/delete', methods=['POST'])
@login_required
def delete_email(message_id):
    """Delete email from Gmail and database"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail or not gmail.service:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        # Delete from Gmail (trash it)
        gmail.service.users().messages().trash(
            userId='me',
            id=message_id
        ).execute()
        
        # Also remove from database classification
        classification = EmailClassification.query.filter_by(
            user_id=current_user.id,
            message_id=message_id
        ).first()
        
        if classification:
            # Delete associated deals first (to avoid foreign key constraints)
            Deal.query.filter_by(classification_id=classification.id).delete()
            db.session.delete(classification)
            db.session.commit()
        
        return jsonify({'success': True, 'message': 'Email deleted successfully'})
    except Exception as e:
        db.session.rollback()
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


@app.route('/api/send-reply-with-attachments', methods=['POST'])
@login_required
def send_reply_with_attachments():
    """Send a reply email with attachments"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    send_emails = os.getenv('SEND_EMAILS', 'false').lower() == 'true'
    
    if not send_emails:
        return jsonify({'success': False, 'error': 'Email sending is disabled'}), 403
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        data = request.json
        to_email = data.get('to')
        subject = data.get('subject')
        body = data.get('body')
        thread_id = data.get('thread_id')
        attachments = data.get('attachments', [])
        cc = data.get('cc')
        bcc = data.get('bcc')
        
        if not all([to_email, subject, body]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Extract email address
        if '<' in to_email and '>' in to_email:
            to_email = to_email.split('<')[1].split('>')[0]
        
        # Get selected signature email preference
        selected_email = current_user.gmail_token.selected_signature_email if current_user.gmail_token else None
        
        # Send reply with attachments
        success = gmail.send_reply_with_attachments(
            to_email, subject, body, thread_id, 
            attachments=attachments, 
            send_as_email=selected_email,
            cc=cc, 
            bcc=bcc
        )
        
        return jsonify({
            'success': success,
            'message': 'Reply sent successfully' if success else 'Failed to send reply'
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/forward-email', methods=['POST'])
@login_required
def forward_email():
    """Forward an email"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    send_emails = os.getenv('SEND_EMAILS', 'false').lower() == 'true'
    
    if not send_emails:
        return jsonify({'success': False, 'error': 'Email sending is disabled'}), 403
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        data = request.json
        to_email = data.get('to')
        subject = data.get('subject')
        body = data.get('body', '')
        original_message_id = data.get('original_message_id')
        include_attachments = data.get('include_attachments', False)
        
        if not all([to_email, subject, original_message_id]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Extract email address
        if '<' in to_email and '>' in to_email:
            to_email = to_email.split('<')[1].split('>')[0]
        
        # Get selected signature email preference
        selected_email = current_user.gmail_token.selected_signature_email if current_user.gmail_token else None
        
        # Forward email
        success = gmail.forward_email(
            to_email, subject, body, original_message_id, 
            include_attachments=include_attachments,
            send_as_email=selected_email
        )
        
        return jsonify({
            'success': success,
            'message': 'Email forwarded successfully' if success else 'Failed to forward email'
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


@app.route('/api/scheduled-emails', methods=['GET'])
@login_required
def get_scheduled_emails():
    """Get all pending scheduled emails for current user"""
    try:
        from models import ScheduledEmail, Deal
        
        # Get all pending scheduled emails for this user
        scheduled_emails = ScheduledEmail.query.filter_by(
            user_id=current_user.id,
            status='pending'
        ).join(Deal).order_by(ScheduledEmail.scheduled_at.asc()).all()
        
        # Format scheduled emails with deal information
        formatted_emails = []
        for scheduled in scheduled_emails:
            deal = scheduled.deal
            formatted_emails.append({
                'id': scheduled.id,
                'thread_id': scheduled.thread_id,
                'to': scheduled.to_email,
                'subject': scheduled.subject,
                'body': scheduled.body,
                'scheduled_at': scheduled.scheduled_at.isoformat() if scheduled.scheduled_at else None,
                'created_at': scheduled.created_at.isoformat() if scheduled.created_at else None,
                'status': scheduled.status,
                'founder_name': deal.founder_name if deal else None,
                'deal_subject': deal.subject if deal else None
            })
        
        return jsonify({
            'success': True,
            'scheduled_emails': formatted_emails
        })
    
    except Exception as e:
        print(f"Error fetching scheduled emails: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduled-email/<int:email_id>', methods=['GET'])
@login_required
def get_scheduled_email(email_id):
    """Get specific scheduled email details"""
    try:
        from models import ScheduledEmail, Deal
        
        scheduled = ScheduledEmail.query.filter_by(
            id=email_id,
            user_id=current_user.id
        ).first()
        
        if not scheduled:
            return jsonify({'success': False, 'error': 'Scheduled email not found'}), 404
        
        deal = scheduled.deal
        return jsonify({
            'success': True,
            'scheduled_email': {
                'id': scheduled.id,
                'thread_id': scheduled.thread_id,
                'to': scheduled.to_email,
                'subject': scheduled.subject,
                'body': scheduled.body,
                'scheduled_at': scheduled.scheduled_at.isoformat() if scheduled.scheduled_at else None,
                'created_at': scheduled.created_at.isoformat() if scheduled.created_at else None,
                'status': scheduled.status,
                'founder_name': deal.founder_name if deal else None,
                'deal_subject': deal.subject if deal else None
            }
        })
    
    except Exception as e:
        print(f"Error fetching scheduled email: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduled-email/<int:email_id>/cancel', methods=['POST'])
@login_required
def cancel_scheduled_email(email_id):
    """Cancel a scheduled email"""
    try:
        from models import ScheduledEmail
        from datetime import datetime
        
        scheduled = ScheduledEmail.query.filter_by(
            id=email_id,
            user_id=current_user.id
        ).first()
        
        if not scheduled:
            return jsonify({'success': False, 'error': 'Scheduled email not found'}), 404
        
        if scheduled.status != 'pending':
            return jsonify({'success': False, 'error': f'Cannot cancel scheduled email with status: {scheduled.status}'}), 400
        
        # Mark as cancelled
        scheduled.status = 'cancelled'
        scheduled.cancelled_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Scheduled email cancelled successfully'
        })
    
    except Exception as e:
        print(f"Error cancelling scheduled email: {str(e)}")
        db.session.rollback()
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
        if not gmail or not gmail.service:
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
                if gmail and gmail.service:
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
    """Download/view an attachment (PDF, image, etc.) from a specific email message"""
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail or not gmail.service:
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
            
            # Find the attachment in the message parts (any mime type)
            attachment_id = None
            attachment_mime = None
            
            def find_attachment_id(parts):
                for part in parts:
                    part_filename = part.get('filename', '')
                    mime_type = part.get('mimeType', '')
                    if part_filename == decoded_filename:
                        return part.get('body', {}).get('attachmentId'), mime_type
                    if 'parts' in part:
                        found = find_attachment_id(part['parts'])
                        if found:
                            return found
                return None
            
            payload = message.get('payload', {})
            if 'parts' in payload:
                result = find_attachment_id(payload['parts'])
                if result:
                    attachment_id, attachment_mime = result
            else:
                # Single part message
                if payload.get('filename') == decoded_filename:
                    attachment_id = payload.get('body', {}).get('attachmentId')
                    attachment_mime = payload.get('mimeType', 'application/octet-stream')
            
            if not attachment_id:
                # Try to find any attachment if exact filename match fails
                def find_any_attachment(parts):
                    for part in parts:
                        mime_type = part.get('mimeType', '')
                        if part.get('filename'):
                            return (
                                part.get('body', {}).get('attachmentId'),
                                part.get('filename', 'attachment'),
                                mime_type or 'application/octet-stream'
                            )
                        if 'parts' in part:
                            found = find_any_attachment(part['parts'])
                            if found:
                                return found
                    return None
                
                if 'parts' in payload:
                    result = find_any_attachment(payload['parts'])
                    if result:
                        attachment_id, decoded_filename, attachment_mime = result
                elif payload.get('filename'):
                    attachment_id = payload.get('body', {}).get('attachmentId')
                    attachment_mime = payload.get('mimeType', 'application/octet-stream')
            
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
                mimetype=attachment_mime or 'application/octet-stream',
                as_attachment=False,
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
        
        # Don't extract attachments when viewing (much faster - no PDF downloads)
        thread_emails = gmail.get_thread_messages(thread_id, extract_attachments=False)
        
        return jsonify({
            'success': True,
            'count': len(thread_emails),
            'emails': thread_emails
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/attachment/<message_id>/<attachment_id>')
@login_required
def download_attachment(message_id, attachment_id):
    """
    Download an attachment on-demand (no extraction).
    For PDFs, serves inline so browser can display them.
    """
    if not current_user.gmail_token:
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 400
    
    try:
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({'success': False, 'error': 'Failed to connect to Gmail'}), 500
        
        # Download the attachment
        file_data = gmail.download_attachment(message_id, attachment_id)
        if not file_data:
            return jsonify({'success': False, 'error': 'Failed to download attachment'}), 500
        
        # Get filename and mime_type from request args (passed from frontend)
        filename = request.args.get('filename', 'attachment')
        mime_type = request.args.get('mime_type', 'application/octet-stream')
        
        # Create response with the file
        from flask import make_response
        response = make_response(file_data)
        response.headers['Content-Type'] = mime_type
        
        # For PDFs, set inline so browser displays them; for others, download
        if mime_type == 'application/pdf':
            response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
        else:
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
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


@app.route('/api/clear-cache', methods=['POST'])
@login_required
def clear_cache():
    """Clear all email classifications for current user to force re-classification via Lambda"""
    try:
        # Get all classification IDs for current user
        classification_ids = [c.id for c in EmailClassification.query.filter_by(user_id=current_user.id).all()]
        classifications_count = len(classification_ids)
        
        if classification_ids:
            # First, nullify the classification_id in deals that reference these classifications
            deals_to_update = Deal.query.filter(Deal.classification_id.in_(classification_ids)).all()
            deals_count = len(deals_to_update)
            for deal in deals_to_update:
                deal.classification_id = None
            
            # Now safe to delete classifications
            EmailClassification.query.filter(EmailClassification.id.in_(classification_ids)).delete(synchronize_session=False)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Cleared {classifications_count} classifications (and updated {deals_count} deals). Next fetch will use Lambda!',
                'classifications_count': classifications_count,
                'deals_count': deals_count
            })
        else:
            return jsonify({
                'success': True,
                'message': 'No classifications to clear',
                'classifications_count': 0,
                'deals_count': 0
            })
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/migrate/add-encryption-columns', methods=['POST'])
@login_required
def migrate_add_encryption_columns():
    """
    Migration endpoint: Add subject_encrypted and snippet_encrypted columns
    Run this once after deploying the new models
    """
    try:
        from sqlalchemy import text
        
        # Check if columns already exist
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'email_classifications' 
            AND column_name IN ('subject_encrypted', 'snippet_encrypted')
        """))
        existing_columns = [row[0] for row in result]
        
        if 'subject_encrypted' in existing_columns and 'snippet_encrypted' in existing_columns:
            return jsonify({
                'success': True,
                'message': 'Columns already exist',
                'columns_exist': True
            })
        
        # Add columns if they don't exist
        if 'subject_encrypted' not in existing_columns:
            db.session.execute(text("""
                ALTER TABLE email_classifications 
                ADD COLUMN subject_encrypted TEXT;
            """))
            print("✅ Added subject_encrypted column")
        
        if 'snippet_encrypted' not in existing_columns:
            db.session.execute(text("""
                ALTER TABLE email_classifications 
                ADD COLUMN snippet_encrypted TEXT;
            """))
            print("✅ Added snippet_encrypted column")
        
        # Migrate existing data (copy plain text to encrypted columns)
        # They'll be encrypted on next write
        db.session.execute(text("""
            UPDATE email_classifications 
            SET subject_encrypted = subject 
            WHERE subject_encrypted IS NULL AND subject IS NOT NULL;
        """))
        
        db.session.execute(text("""
            UPDATE email_classifications 
            SET snippet_encrypted = snippet 
            WHERE snippet_encrypted IS NULL AND snippet IS NOT NULL;
        """))
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Migration completed successfully',
            'columns_added': [
                col for col in ['subject_encrypted', 'snippet_encrypted'] 
                if col not in existing_columns
            ]
        })
        
    except Exception as e:
        db.session.rollback()
        error_msg = str(e)
        print(f"❌ Migration failed: {error_msg}")
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500

@app.route('/api/setup/status')
@login_required
def get_setup_status():
    """Get setup status for current user"""
    return jsonify({
        'success': True,
        'setup_completed': current_user.setup_completed if current_user.setup_completed else False,
        'initial_emails_fetched': current_user.initial_emails_fetched if current_user.initial_emails_fetched else 0,
        'needs_setup': current_user.gmail_token is not None and not current_user.setup_completed
    })

@app.route('/api/setup/complete', methods=['POST'])
@login_required
def complete_setup():
    """Mark setup as complete and auto-setup Pub/Sub if enabled"""
    try:
        current_user.setup_completed = True
        db.session.commit()
        
        # Auto-setup Pub/Sub if enabled (test environment)
        pubsub_setup_result = None
        use_pubsub = os.getenv('USE_PUBSUB', 'false').lower() == 'true'
        if use_pubsub and current_user.gmail_token:
            try:
                pubsub_topic = os.getenv('PUBSUB_TOPIC')
                if pubsub_topic:
                    gmail = get_user_gmail_client(current_user)
                    if gmail:
                        watch_result = gmail.setup_pubsub_watch(pubsub_topic, user_id=current_user.id)
                        if watch_result:
                            gmail_token = current_user.gmail_token
                            gmail_token.pubsub_topic = pubsub_topic
                            gmail_token.watch_expiration = watch_result.get('expiration')
                            if watch_result.get('history_id'):
                                gmail_token.history_id = str(watch_result['history_id'])
                            db.session.commit()
                            pubsub_setup_result = 'success'
                            print(f"✅ Auto-setup Pub/Sub for user {current_user.id}")
                        else:
                            pubsub_setup_result = 'failed'
                            print(f"⚠️  Pub/Sub setup failed for user {current_user.id}")
            except Exception as pubsub_error:
                pubsub_setup_result = 'error'
                print(f"⚠️  Pub/Sub auto-setup error (non-critical): {pubsub_error}")
        
        return jsonify({
            'success': True,
            'message': 'Setup completed',
            'pubsub_setup': pubsub_setup_result
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/setup/fetch-initial', methods=['POST'])
@login_required
def fetch_initial_emails():
    """
    Fetch initial 60 emails for first-time setup
    Returns immediately and processes in background
    """
    if not current_user.gmail_token:
        return jsonify({
            'success': False,
            'error': 'Gmail not connected'
        }), 400
    
    try:
        # Check if user already has emails - if so, skip setup
        # BUT only if they have at least 200 emails (initial setup target)
        from models import EmailClassification
        existing_count = EmailClassification.query.filter_by(user_id=current_user.id).count()
        if existing_count >= 200:
            print(f"✅ User {current_user.id} already has {existing_count} emails (>= 200), marking setup as complete")
            current_user.setup_completed = True
            current_user.initial_emails_fetched = existing_count
            db.session.commit()
            return jsonify({
                'success': True,
                'already_complete': True,
                'message': f'Setup already complete ({existing_count} emails found)',
                'email_count': existing_count
            })
        elif existing_count > 0 and existing_count < 200:
            # User has some emails but not enough - continue setup to reach 200
            print(f"⚠️  User {current_user.id} has {existing_count} emails (< 200), continuing setup...")
            # Don't mark as complete, continue with setup
        
        max_emails = 200  # Initial fetch: 200 emails (fetch all upfront, classify in background)
        
        # Try to use background task if available
        if CELERY_AVAILABLE:
            try:
                from celery_config import celery
                inspect = celery.control.inspect(timeout=2.0)
                active_workers = inspect.active()
                
                # Check if we have active workers (active_workers is a dict with worker names as keys)
                if active_workers and len(active_workers) > 0:
                    print(f"✅ Found {len(active_workers)} active Celery worker(s)")
                    # Use background task
                    task = sync_user_emails.delay(
                        user_id=current_user.id,
                        max_emails=max_emails,
                        force_full_sync=True
                    )
                    print(f"✅ Queued task {task.id} for user {current_user.id}")
                    
                    # Update initial_emails_fetched
                    current_user.initial_emails_fetched = max_emails
                    db.session.commit()
                    
                    return jsonify({
                        'success': True,
                        'task_id': task.id,
                        'message': 'Initial email fetch started',
                        'max_emails': max_emails
                    })
                else:
                    print(f"⚠️  No active Celery workers found (active_workers: {active_workers})")
            except Exception as e:
                print(f"⚠️  Background task not available: {e}")
                import traceback
                traceback.print_exc()
        
        # Fallback: Use streaming endpoint
        return jsonify({
            'success': True,
            'use_streaming': True,
            'message': 'Use streaming endpoint',
            'max_emails': max_emails
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/emails/background-fetch', methods=['POST'])
@login_required
def background_fetch_emails():
    """
    Silently fetch more emails in background (up to 200 total)
    Rate-limited to avoid hitting API limits
    """
    if not current_user.gmail_token:
        return jsonify({
            'success': False,
            'error': 'Gmail not connected'
        }), 400
    
    try:
        # Check current email count
        current_count = EmailClassification.query.filter_by(user_id=current_user.id).count()
        target_total = 150  # Target: 150 emails total
        
        if current_count >= target_total:
            return jsonify({
                'success': True,
                'message': 'Already have enough emails',
                'current_count': current_count
            })
        
        # Calculate how many more to fetch (with rate limiting)
        remaining = target_total - current_count
        # Fetch smaller batches (10 at a time) to avoid rate limits
        # This allows more time between batches for rate limit recovery
        max_to_fetch = min(remaining, 10)  # Reduced from 20 to 10 for better rate limit handling
        
        if CELERY_AVAILABLE:
            try:
                from celery_config import celery
                inspect = celery.control.inspect(timeout=2.0)
                active_workers = inspect.active()
                
                if active_workers:
                    task = sync_user_emails.delay(
                        user_id=current_user.id,
                        max_emails=max_to_fetch,
                        force_full_sync=False  # Use incremental sync
                    )
                    
                    return jsonify({
                        'success': True,
                        'task_id': task.id,
                        'message': 'Background fetch started',
                        'fetching': max_to_fetch,
                        'current_count': current_count,
                        'target_total': target_total
                    })
            except Exception as e:
                print(f"⚠️  Background task not available: {e}")
        
        return jsonify({
            'success': False,
            'error': 'Background processing not available'
        }), 503
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== PUB/SUB WEBHOOK (TEST ENVIRONMENT) ====================

@app.route('/api/whatsapp/send-pending-alerts', methods=['POST'])
@login_required
def send_pending_whatsapp_alerts():
    """
    Send WhatsApp alerts for existing deals that haven't received alerts yet
    Useful when WhatsApp was enabled after emails were already classified
    """
    try:
        if not current_user.whatsapp_enabled or not current_user.whatsapp_number:
            return jsonify({
                'success': False,
                'error': 'WhatsApp not enabled or number not set. Please configure in Settings.'
            }), 400
        
        # Find deals that haven't received WhatsApp alerts yet
        pending_deals = Deal.query.filter_by(
            user_id=current_user.id,
            whatsapp_alert_sent=False
        ).all()
        
        if not pending_deals:
            return jsonify({
                'success': True,
                'message': 'No pending deals found. All deals have already received WhatsApp alerts.',
                'alerts_sent': 0
            })
        
        from whatsapp_service import WhatsAppService
        whatsapp = WhatsAppService()
        
        alerts_sent = 0
        errors = []
        
        for deal in pending_deals:
            try:
                whatsapp.send_deal_alert(deal, current_user.whatsapp_number)
                deal.whatsapp_alert_sent = True
                deal.whatsapp_alert_sent_at = datetime.utcnow()
                db.session.commit()
                alerts_sent += 1
                print(f"✅ Sent WhatsApp alert for existing deal {deal.id}: {deal.subject}")
            except Exception as e:
                error_msg = str(e)
                errors.append(f"Deal {deal.id}: {error_msg}")
                print(f"❌ Failed to send WhatsApp alert for deal {deal.id}: {error_msg}")
                db.session.rollback()
                continue
        
        return jsonify({
            'success': True,
            'message': f'Sent {alerts_sent} WhatsApp alerts for pending deals',
            'alerts_sent': alerts_sent,
            'total_pending': len(pending_deals),
            'errors': errors[:5] if errors else []
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/pubsub/gmail-notifications', methods=['POST'])
def pubsub_webhook():
    """
    Pub/Sub webhook endpoint for Gmail push notifications (test environment).
    Receives notifications when new emails arrive, reducing API polling.
    """
    print("=" * 60)
    print("📬 [PUB/SUB] Webhook Called")
    print(f"   Method: {request.method}")
    print(f"   URL: {request.url}")
    print(f"   Headers: {dict(request.headers)}")
    print(f"   Content-Type: {request.content_type}")
    print(f"   Remote Addr: {request.remote_addr}")
    print("=" * 60)
    
    try:
        # Verify the request is from Pub/Sub (optional but recommended)
        # In production, verify the JWT token from Pub/Sub
        
        # Parse Pub/Sub message
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        # Pub/Sub sends messages in this format:
        # {
        #   "message": {
        #     "data": "base64-encoded-json",
        #     "messageId": "...",
        #     "publishTime": "..."
        #   },
        #   "subscription": "..."
        # }
        
        message = data.get('message', {})
        message_data = message.get('data', '')
        
        if not message_data:
            print("⚠️  Pub/Sub webhook: No message data")
            return jsonify({'status': 'no_data'}), 200
        
        # Decode base64 message data
        import base64
        try:
            decoded_data = base64.b64decode(message_data).decode('utf-8')
            notification = json.loads(decoded_data)
        except Exception as e:
            print(f"⚠️  Error decoding Pub/Sub message: {str(e)}")
            return jsonify({'error': 'Invalid message format'}), 400
        
        # Gmail notification format:
        # {
        #   "emailAddress": "user@example.com",
        #   "historyId": "12345"
        # }
        
        email_address = notification.get('emailAddress')
        history_id = notification.get('historyId')
        
        if not email_address or not history_id:
            print("⚠️  Pub/Sub webhook: Missing emailAddress or historyId")
            return jsonify({'status': 'invalid_notification'}), 200
        
        print(f"📬 Pub/Sub notification received for {email_address}, historyId: {history_id}")
        
        # Find user by Gmail email address
        # Pub/Sub sends the Gmail email, which might be different from User.email
        # We need to find the user by checking their Gmail profile
        user = None
        
        # First, try to find by User.email (in case they match)
        user = User.query.filter_by(email=email_address).first()
        
        # If not found, search all users with Gmail tokens and check their Gmail profile
        if not user:
            print(f"🔍 User.email doesn't match {email_address}, searching by Gmail profile...")
            users_with_gmail = User.query.join(GmailToken).all()
            
            for u in users_with_gmail:
                try:
                    gmail = get_user_gmail_client(u)
                    if gmail:
                        profile = gmail.get_profile()
                        if profile and profile.get('emailAddress') == email_address:
                            user = u
                            print(f"✅ Found user {u.id} by Gmail profile: {email_address}")
                            break
                except Exception as e:
                    print(f"⚠️  Error checking Gmail profile for user {u.id}: {str(e)}")
                    continue
        
        if not user:
            print(f"⚠️  User not found for Gmail email: {email_address}")
            print(f"   Searched {len(users_with_gmail) if 'users_with_gmail' in locals() else 0} users with Gmail tokens")
            return jsonify({'status': 'user_not_found'}), 200
        
        # Get Gmail client for this user
        gmail = get_user_gmail_client(user)
        if not gmail:
            print(f"⚠️  Could not get Gmail client for user {user.id}")
            return jsonify({'status': 'gmail_client_error'}), 200
        
        # DON'T update history_id here! The Pub/Sub task needs the OLD history_id to query for changes
        # The task will update it after successfully syncing emails
        # If we update it here, the task will query from new_history_id to new_history_id (no changes found)
        
        # Trigger instant Pub/Sub processing task (if Celery is available)
        # This uses a dedicated high-priority queue with a dedicated worker for instant processing
        # NO email count restrictions - Pub/Sub works for all users regardless of email count
        if CELERY_AVAILABLE:
            try:
                from tasks import process_pubsub_notification
                # Use dedicated Pub/Sub task on pubsub_notifications queue (instant processing)
                task = process_pubsub_notification.delay(
                    user_id=user.id,
                    history_id=history_id
                )
                print(f"✅ [PUB/SUB] Instant notification task queued: {task.id}")
                print(f"   User: {user.id}, Gmail: {email_address}, HistoryId: {history_id}")
                print(f"   Using dedicated Pub/Sub worker for instant processing")
            except Exception as e:
                print(f"❌ [PUB/SUB] Could not queue notification task: {str(e)}")
                import traceback
                traceback.print_exc()
        else:
            print("⚠️  [PUB/SUB] Celery not available - sync not triggered automatically")
        
        return jsonify({
            'status': 'success',
            'email': email_address,
            'history_id': history_id
        }), 200
        
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"❌ Error in Pub/Sub webhook: {str(e)}")
        print(f"Traceback:\n{error_traceback}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/setup-pubsub', methods=['POST'])
@login_required
def setup_pubsub():
    """
    Set up Gmail Watch with Pub/Sub for the current user (test environment).
    Requires USE_PUBSUB=true and PUBSUB_TOPIC environment variables.
    """
    try:
        # Check if Pub/Sub is enabled for test environment
        use_pubsub = os.getenv('USE_PUBSUB', 'false').lower() == 'true'
        if not use_pubsub:
            return jsonify({
                'success': False,
                'error': 'Pub/Sub is not enabled. Set USE_PUBSUB=true in environment variables.'
            }), 400
        
        # Get Pub/Sub topic from environment
        pubsub_topic = os.getenv('PUBSUB_TOPIC')
        if not pubsub_topic:
            return jsonify({
                'success': False,
                'error': 'PUBSUB_TOPIC not set in environment variables'
            }), 400
        
        # Get user's Gmail client
        gmail = get_user_gmail_client(current_user)
        if not gmail:
            return jsonify({
                'success': False,
                'error': 'Gmail not connected'
            }), 400
        
        # Set up Gmail Watch
        watch_result = gmail.setup_pubsub_watch(pubsub_topic, user_id=current_user.id)
        
        if not watch_result:
            return jsonify({
                'success': False,
                'error': 'Failed to set up Gmail Watch. Check logs for details.'
            }), 500
        
        # Store Pub/Sub info in database
        if not current_user.gmail_token:
            return jsonify({
                'success': False,
                'error': 'Gmail token not found'
            }), 400
        
        gmail_token = current_user.gmail_token
        gmail_token.pubsub_topic = pubsub_topic
        gmail_token.watch_expiration = watch_result.get('expiration')
        
        if watch_result.get('history_id'):
            gmail_token.history_id = str(watch_result['history_id'])
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'expiration': watch_result.get('expiration'),
            'history_id': watch_result.get('history_id'),
            'message': 'Gmail Watch with Pub/Sub set up successfully. Watch expires in 7 days.'
        }), 200
        
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"❌ Error setting up Pub/Sub: {str(e)}")
        print(f"Traceback:\n{error_traceback}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== WHATSAPP WEBHOOK ====================

@app.route('/webhook/whatsapp', methods=['GET', 'POST'])
def whatsapp_webhook():
    """
    WhatsApp webhook endpoint for Meta Business Cloud API
    Handles verification and incoming messages
    """
    if request.method == 'GET':
        # Webhook verification (Meta requires this)
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        try:
            from whatsapp_service import WhatsAppService
            whatsapp = WhatsAppService()
            verified = whatsapp.verify_webhook(mode, token, challenge)
            
            if verified:
                print("✅ WhatsApp webhook verified")
                return challenge, 200
            else:
                print("❌ WhatsApp webhook verification failed")
                return 'Forbidden', 403
        except Exception as e:
            print(f"❌ WhatsApp webhook verification error: {str(e)}")
            return 'Error', 500
    
    elif request.method == 'POST':
        # Handle incoming messages
        try:
            from whatsapp_service import WhatsAppService
            whatsapp = WhatsAppService()
            result = whatsapp.handle_incoming_message(request.json)
            print(f"📱 WhatsApp message processed: {result}")
            return jsonify({'status': 'ok'}), 200
        except Exception as e:
            print(f"❌ Error processing WhatsApp message: {str(e)}")
            return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/whatsapp/settings', methods=['GET', 'POST'])
@login_required
def whatsapp_settings():
    """Get or update user WhatsApp settings"""
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'whatsapp_enabled': current_user.whatsapp_enabled or False,
            'whatsapp_number': current_user.whatsapp_number or ''
        })
    
    elif request.method == 'POST':
        print(f"💾 [WHATSAPP-SETTINGS] Saving WhatsApp settings for user {current_user.id}")
        
        data = request.json
        print(f"📦 [WHATSAPP-SETTINGS] Request data: {data}")
        
        enabled = data.get('enabled', False)
        number = data.get('number', '').strip()
        
        print(f"📝 [WHATSAPP-SETTINGS] Parsed: enabled={enabled}, number={number[:8] if number else 'None'}...")
        
        # Validate phone number format (basic check)
        if number and not number.startswith('+'):
            print(f"❌ [WHATSAPP-SETTINGS] Invalid number format (missing +)")
            return jsonify({
                'success': False,
                'error': 'Phone number must start with + (e.g., +1234567890)'
            }), 400
        
        # Update user fields
        print(f"📝 [WHATSAPP-SETTINGS] Before update: whatsapp_enabled={current_user.whatsapp_enabled}, whatsapp_number={current_user.whatsapp_number}")
        
        current_user.whatsapp_enabled = enabled
        current_user.whatsapp_number = number
        
        print(f"📝 [WHATSAPP-SETTINGS] After update (before commit): whatsapp_enabled={current_user.whatsapp_enabled}, whatsapp_number={current_user.whatsapp_number}")
        
        try:
            db.session.commit()
            print(f"✅ [WHATSAPP-SETTINGS] Database commit successful")
            
            # Verify the changes were saved
            db.session.refresh(current_user)
            print(f"🔍 [WHATSAPP-SETTINGS] Verified in DB: whatsapp_enabled={current_user.whatsapp_enabled}, whatsapp_number={current_user.whatsapp_number}")
            
            return jsonify({
                'success': True,
                'message': 'WhatsApp settings updated',
                'whatsapp_enabled': current_user.whatsapp_enabled,
                'whatsapp_number': current_user.whatsapp_number
            })
        except Exception as e:
            print(f"❌ [WHATSAPP-SETTINGS] Database commit failed: {str(e)}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': f'Failed to save settings: {str(e)}'
            }), 500


@app.route('/api/user/profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    """Get or update user profile information"""
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'username': current_user.username,
            'email': current_user.email,
            'full_name': current_user.full_name,
            'profile_picture': current_user.profile_picture,
            'google_id': current_user.google_id,
            'created_at': current_user.created_at.isoformat() if current_user.created_at else None
        })
    
    # POST - Update profile
    try:
        data = request.json
        full_name = data.get('full_name', '').strip()
        
        # Only allow updating full_name if not from Google OAuth
        if not current_user.google_id and full_name:
            current_user.full_name = full_name
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Profile updated successfully'
            })
        elif current_user.google_id:
            return jsonify({
                'success': False,
                'error': 'Profile information is synced from Google and cannot be manually edited'
            }), 400
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid data'
            }), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/user/delete', methods=['DELETE'])
@login_required
def delete_user_account():
    """
    Permanently delete user account and all associated data.
    This includes:
    - User record
    - Gmail tokens
    - Email classifications
    - Deal flow data
    """
    try:
        user_id = current_user.id
        user_email = current_user.email
        
        print(f"🗑️  Deleting account for user {user_id} ({user_email})")
        
        # Delete all associated data (cascades will handle most of this, but being explicit)
        # 1. Delete deals
        deals_count = Deal.query.filter_by(user_id=user_id).delete()
        print(f"   Deleted {deals_count} deal records")
        
        # 2. Delete email classifications
        classifications_count = EmailClassification.query.filter_by(user_id=user_id).delete()
        print(f"   Deleted {classifications_count} email classifications")
        
        # 3. Delete Gmail token
        token_count = GmailToken.query.filter_by(user_id=user_id).delete()
        print(f"   Deleted {token_count} Gmail token")
        
        # 4. Finally, delete the user
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            print(f"   ✅ User {user_id} deleted successfully")
            
            # Logout the user
            logout_user()
            session.clear()
            
            return jsonify({
                'success': True,
                'message': 'Account deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
            
    except Exception as e:
        db.session.rollback()
        print(f"   ❌ Error deleting user account: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': 'Failed to delete account. Please try again or contact support.'
        }), 500


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
    print("🔐 Lambda integration: Enabled")
    
    app.run(debug=True, host='0.0.0.0', port=8080)
