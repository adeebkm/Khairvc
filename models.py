"""
Database models for multi-user system
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Import encryption functions for Priority 2 (Field Encryption)
try:
    from auth import encrypt_token, decrypt_token
    ENCRYPTION_AVAILABLE = True
except ImportError:
    # Fallback if auth module not available
    ENCRYPTION_AVAILABLE = False
    def encrypt_token(data):
        return data
    def decrypt_token(data):
        return data

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User model for authentication"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    setup_completed = db.Column(db.Boolean, default=False)  # Track if first-time setup is complete
    initial_emails_fetched = db.Column(db.Integer, default=0)  # Track how many emails fetched during setup
    
    # Relationship to user settings
    gmail_token = db.relationship('GmailToken', backref='user', uselist=False, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set password"""
        # Use pbkdf2:sha256 instead of scrypt for compatibility
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        """Check password"""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'


class GmailToken(db.Model):
    """Encrypted Gmail OAuth tokens per user"""
    __tablename__ = 'gmail_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    encrypted_token = db.Column(db.Text, nullable=False)  # Encrypted JSON token
    selected_signature_email = db.Column(db.String(255))  # Email address of selected send-as alias for signature
    history_id = db.Column(db.String(255))  # Gmail history ID for incremental sync
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<GmailToken for user {self.user_id}>'


class EmailClassification(db.Model):
    """Email classification and tags per thread"""
    __tablename__ = 'email_classifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    thread_id = db.Column(db.String(255), nullable=False)  # Gmail thread ID
    message_id = db.Column(db.String(255), nullable=False)  # Gmail message ID
    
    # Email metadata (stored for display when loading from cache)
    # PRIORITY 2: Encrypted fields for sensitive data
    subject_encrypted = db.Column(db.Text)  # Encrypted email subject
    snippet_encrypted = db.Column(db.Text)  # Encrypted email preview snippet
    
    # Legacy plain text fields (kept for backward compatibility during migration)
    subject = db.Column(db.String(500))  # Legacy: plain text subject (deprecated)
    sender = db.Column(db.String(255))  # Sender email/name (not encrypted - less sensitive)
    snippet = db.Column(db.Text)  # Legacy: plain text snippet (deprecated)
    email_date = db.Column(db.BigInteger)  # Gmail internalDate timestamp
    
    category = db.Column(db.String(20), nullable=False)  # DEAL_FLOW, NETWORKING, HIRING, SPAM, GENERAL
    tags = db.Column(db.String(255))  # Comma-separated tags: DF/Deal, DF/AskMore, NW/Networking, HR/Hiring, SPAM/Skip
    reply_type = db.Column(db.String(50))  # ack, ask-more, none
    reply_sent = db.Column(db.Boolean, default=False)
    confidence = db.Column(db.Float)  # Classification confidence score
    classified_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Deal Flow specific
    deal_state = db.Column(db.String(50))  # New, Ask-More, Routed (for Deal Flow only)
    deck_link = db.Column(db.Text)  # Detected deck/dataroom link
    extracted_links = db.Column(db.Text)  # JSON array of all links
    
    # Index for quick lookups
    __table_args__ = (
        db.Index('idx_user_thread', 'user_id', 'thread_id'),
    )
    
    # PRIORITY 2: Helper methods for encrypted fields
    # Note: We keep direct column access for backward compatibility
    # New code should use set_subject_encrypted() and get_subject_decrypted()
    
    def set_subject_encrypted(self, value):
        """Set subject with automatic encryption"""
        if value:
            self.subject_encrypted = encrypt_token(str(value))
            # Keep legacy field for backward compatibility
            self.subject = str(value)
        else:
            self.subject_encrypted = None
            self.subject = None
    
    def get_subject_decrypted(self):
        """Get subject with automatic decryption"""
        if self.subject_encrypted:
            try:
                return decrypt_token(self.subject_encrypted)
            except Exception:
                # Fallback to legacy plain text
                return self.subject or ''
        return self.subject or ''
    
    def set_snippet_encrypted(self, value):
        """Set snippet with automatic encryption"""
        if value:
            self.snippet_encrypted = encrypt_token(str(value))
            # Keep legacy field for backward compatibility
            self.snippet = str(value)
        else:
            self.snippet_encrypted = None
            self.snippet = None
    
    def get_snippet_decrypted(self):
        """Get snippet with automatic decryption"""
        if self.snippet_encrypted:
            try:
                return decrypt_token(self.snippet_encrypted)
            except Exception:
                # Fallback to legacy plain text
                return self.snippet or ''
        return self.snippet or ''
    
    def __repr__(self):
        return f'<EmailClassification {self.category} for thread {self.thread_id}>'


class Deal(db.Model):
    """Deal Flow tracking - founders and deals"""
    __tablename__ = 'deals'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    thread_id = db.Column(db.String(255), nullable=False)  # Gmail thread ID
    classification_id = db.Column(db.Integer, db.ForeignKey('email_classifications.id'))
    
    # Founder/deal info
    founder_name = db.Column(db.String(255))
    founder_email = db.Column(db.String(255))
    subject = db.Column(db.String(500))
    deck_link = db.Column(db.Text)
    dataroom_link = db.Column(db.Text)
    
    # Four basics tracking
    has_deck = db.Column(db.Boolean, default=False)
    has_team_info = db.Column(db.Boolean, default=False)
    has_traction = db.Column(db.Boolean, default=False)  # MRR/users/pilots
    has_round_info = db.Column(db.Boolean, default=False)  # amount/committed/lead
    
    state = db.Column(db.String(50), default='New')  # New, Ask-More, Routed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Portfolio matching and scoring
    founder_linkedin = db.Column(db.Text)  # LinkedIn URL
    founder_school = db.Column(db.String(255))  # Extracted from LinkedIn/email
    founder_previous_companies = db.Column(db.Text)  # JSON array
    
    # Portfolio overlaps
    portfolio_overlaps = db.Column(db.Text)  # JSON: overlaps with portfolio
    
    # Scores (0-100) - Old system (kept for backward compatibility)
    risk_score = db.Column(db.Float)
    portfolio_comparison_score = db.Column(db.Float)
    founder_market_score = db.Column(db.Float)
    traction_score = db.Column(db.Float)
    
    # New Tracxn-based scores
    team_background_score = db.Column(db.Float)  # From Tracxn Excel
    white_space_score = db.Column(db.Float)  # From OpenAI web search analysis
    overall_score = db.Column(db.Float)  # Weighted average: 60% team + 40% white space
    
    # White space analysis details (JSON)
    white_space_analysis = db.Column(db.Text)  # JSON with subsector, competition, market size, etc.
    
    # Relationship
    classification = db.relationship('EmailClassification', backref='deal')
    
    __table_args__ = (
        db.Index('idx_user_thread_deal', 'user_id', 'thread_id'),
    )
    
    def __repr__(self):
        return f'<Deal {self.state} from {self.founder_email}>'

