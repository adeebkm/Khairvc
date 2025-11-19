# Technical Documentation - Gmail Auto-Reply Application

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Security Architecture](#security-architecture)
3. [Authentication Flow](#authentication-flow)
4. [Gmail OAuth Flow](#gmail-oauth-flow)
5. [Email Processing Flow](#email-processing-flow)
6. [Database Schema](#database-schema)
7. [API Endpoints](#api-endpoints)
8. [Frontend Architecture](#frontend-architecture)
9. [Deployment Architecture](#deployment-architecture)
10. [Data Flow Diagrams](#data-flow-diagrams)

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Browser)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   HTML/CSS   │  │  JavaScript  │  │  Templates   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            ↕ HTTPS
┌─────────────────────────────────────────────────────────────┐
│                    Flask Application (app.py)               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Routes     │  │  Middleware  │  │  Auth        │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
         ↕                    ↕                    ↕
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Database   │    │  Gmail API   │    │  OpenAI API  │
│ (PostgreSQL) │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
```

### Technology Stack

**Backend:**
- Python 3.11
- Flask 3.0.0 (Web framework)
- SQLAlchemy 3.1.1 (ORM)
- Flask-Login 0.6.3 (Session management)
- Gunicorn 21.2.0 (WSGI server)

**Database:**
- PostgreSQL (Production - Railway)
- SQLite (Local development)

**APIs:**
- Gmail API (Google)
- OpenAI API (GPT-4o-mini)

**Frontend:**
- Vanilla JavaScript (No framework)
- HTML5/CSS3
- Responsive design

**Security:**
- Cryptography (Fernet encryption)
- Werkzeug (Password hashing - pbkdf2:sha256)
- OAuth 2.0 (Google)
- ProxyFix (HTTPS detection)

**Deployment:**
- Railway (Cloud platform)
- Gunicorn (Production server)

---

## Security Architecture

### 1. Authentication & Authorization

#### User Authentication
- **Method**: Username/Password with Flask-Login
- **Password Hashing**: Werkzeug pbkdf2:sha256
- **Session Management**: Flask sessions with signed cookies
- **Session Security**: SECRET_KEY from environment variable

```python
# Password hashing
password_hash = generate_password_hash(password, method='pbkdf2:sha256')
check_password_hash(password_hash, password)
```

#### Multi-User Data Isolation
- Each user has isolated data via `user_id` foreign keys
- Database queries always filter by `current_user.id`
- Users cannot access other users' emails or tokens

### 2. Token Encryption

#### Gmail OAuth Token Storage
- **Encryption**: Fernet (symmetric encryption)
- **Key Storage**: ENCRYPTION_KEY environment variable
- **Algorithm**: AES-128 in CBC mode with HMAC
- **Storage**: Encrypted tokens stored in database as TEXT

```python
# Encryption flow
token_json → encrypt_token() → encrypted_string → Database
Database → encrypted_string → decrypt_token() → token_json
```

**Security Properties:**
- Tokens encrypted at rest
- Key never stored in code or database
- Each user's token independently encrypted
- Automatic token refresh handled by Google Auth library

### 3. HTTPS & Transport Security

#### Production (Railway)
- **HTTPS**: Enforced via Railway's reverse proxy
- **ProxyFix Middleware**: Detects HTTPS from X-Forwarded-Proto header
- **OAuth Redirect**: Must use HTTPS (enforced by Google)

```python
# ProxyFix configuration
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
```

### 4. Session Security

#### Session Serialization Protection
- **Before Request Handler**: Clears non-serializable objects from session
- **Prevents**: InstalledAppFlow objects from being stored in session
- **Automatic Cleanup**: Runs before every request

```python
@app.before_request
def clear_problematic_session_data():
    # Removes non-JSON-serializable objects from session
```

### 5. API Security

#### Rate Limiting
- **Gmail API**: Handles 429 errors with retry information
- **OpenAI API**: 500ms delay between requests (120 req/min)
- **Auto-fetch Pause**: 10-minute pause after rate limit

#### Input Validation
- All user inputs validated
- SQL injection prevention via SQLAlchemy ORM
- XSS prevention via template escaping
- CSRF protection via Flask-Login sessions

### 6. Environment Variables

**Required:**
- `SECRET_KEY` - Flask session signing (32+ bytes)
- `ENCRYPTION_KEY` - Token encryption (Fernet key, 44 chars base64)
- `OPENAI_API_KEY` - OpenAI API access
- `GOOGLE_CREDENTIALS_JSON` - Google OAuth credentials
- `OAUTH_REDIRECT_URI` - OAuth callback URL
- `DATABASE_URL` - PostgreSQL connection (auto-provided by Railway)

**Optional:**
- `SEND_EMAILS` - Email sending toggle (default: false)
- `MAX_EMAILS` - Max emails per fetch (default: 20, capped at 20)

---

## Authentication Flow

### User Registration

```
1. User visits /signup
2. Enters username, email, password
3. Backend validates:
   - Username unique
   - Email unique
   - Password strength
4. Password hashed with pbkdf2:sha256
5. User record created in database
6. User redirected to /login
```

### User Login

```
1. User visits /login
2. Enters username and password
3. Backend:
   - Queries User by username
   - Verifies password hash
   - Creates Flask-Login session
4. Session cookie set (signed with SECRET_KEY)
5. User redirected to /dashboard
```

### Session Management

- **Session Storage**: Server-side (Flask sessions)
- **Session Cookie**: HttpOnly, Secure (in production)
- **Session Expiry**: Default Flask session timeout
- **Logout**: Clears session via `logout_user()`

---

## Gmail OAuth Flow

### Initial Connection

```
1. User clicks "Connect Gmail" → /connect-gmail
2. Backend:
   - Clears any existing OAuth session data
   - Loads Google credentials from GOOGLE_CREDENTIALS_JSON
   - Creates InstalledAppFlow with scopes:
     * gmail.modify
     * gmail.settings.basic
   - Sets redirect_uri from OAUTH_REDIRECT_URI
   - Generates authorization URL with state parameter
   - Stores state in session (NOT the flow object)
3. User redirected to Google OAuth consent screen
4. User authorizes application
5. Google redirects to /oauth2callback?code=...&state=...
```

### OAuth Callback

```
1. Request arrives at /oauth2callback
2. Backend:
   - Validates state parameter matches session
   - Clears any OAuth flow objects from session
   - Recreates InstalledAppFlow from credentials
   - Sets redirect_uri
   - Exchanges authorization code for tokens
   - Gets access token and refresh token
3. Token Encryption:
   - Converts token to JSON string
   - Encrypts with Fernet cipher
   - Stores encrypted token in database
4. Updates/creates GmailToken record:
   - user_id → current_user.id
   - encrypted_token → encrypted JSON
5. Clears OAuth state from session
6. Redirects to /dashboard?connected=true
```

### Token Refresh

```
1. GmailClient.authenticate_from_token() called
2. Decrypts token from database
3. Creates Credentials object
4. If expired:
   - Uses refresh_token to get new access_token
   - Updates encrypted token in database
5. Builds Gmail service with credentials
```

### Disconnection

```
1. User clicks "Disconnect Gmail"
2. Backend:
   - Deletes GmailToken record (cascade deletes)
   - Clears history_id
3. User must re-authenticate to reconnect
```

---

## Email Processing Flow

### Email Fetching

#### Incremental Sync (Preferred)
```
1. Check if user has history_id in GmailToken
2. If yes:
   - Use Gmail History API
   - Fetch only changes since history_id
   - Returns: (new_emails, new_history_id)
   - Update history_id in database
   - 90%+ reduction in API calls
```

#### Full Sync (First Time or Force)
```
1. Use Gmail messages.list() API
2. Query: "in:inbox" (or "is:unread in:inbox")
3. Limit: max_emails (capped at 20)
4. Batch fetch message details
5. Store new history_id for next incremental sync
```

### Email Classification

```
For each email:
1. Extract email content:
   - Subject, body, sender, headers
   - Attachments (PDF/DOCX parsed)
   - Links extracted from body + attachments
2. Check if already classified:
   - Query EmailClassification by thread_id
   - If exists, skip classification
3. Deterministic Pre-filtering:
   - Check headers (From, Subject, List-Unsubscribe)
   - Check keywords in subject/body
   - Check for PDF attachments (deck indicators)
   - Check for deck links (docsend, dataroom, etc.)
4. AI Classification (if not quota exceeded):
   - Send to OpenAI GPT-4o-mini
   - Prompt includes full context (body + attachments)
   - Returns: category, confidence, reasoning
5. Fallback to Deterministic:
   - If OpenAI quota exceeded
   - Uses keyword-based rules
6. Store Classification:
   - Create EmailClassification record
   - Category: DEAL_FLOW, NETWORKING, HIRING, SPAM, GENERAL
   - Tags: DF/Deal, NW/Networking, HR/Hiring, SPAM/Skip, GEN/General
   - Confidence score
   - Extracted links
```

### Classification Categories

1. **DEAL_FLOW**
   - Indicators: Pitch deck, fundraising keywords, startup mentions
   - Tags: DF/Deal, DF/AskMore
   - States: New → Ask-More → Routed

2. **NETWORKING**
   - Indicators: Meeting requests, introductions, coffee chats
   - Tags: NW/Networking
   - Reply: Brief acknowledgment

3. **HIRING**
   - Indicators: Job postings, recruitment, referrals
   - Tags: HR/Hiring
   - Reply: Professional receipt/forwarding note

4. **SPAM**
   - Indicators: Security threats, phishing, clickbait
   - Tags: SPAM/Skip
   - Reply: None

5. **GENERAL**
   - Indicators: Everything else (subscriptions, banter, etc.)
   - Tags: GEN/General
   - Reply: None

### Deal Flow Processing

```
If category == DEAL_FLOW:
1. Extract founder info:
   - Name from email body/headers
   - Email from From header
   - LinkedIn (from deck or search)
2. Check "Four Basics":
   - Has deck (PDF attachment or deck link)
   - Has team info (founders, advisors mentioned)
   - Has traction (MRR, users, pilots, customers)
   - Has round info (amount, committed, lead investor)
3. Determine state:
   - If all basics present → "Routed"
   - If basics missing → "Ask-More"
   - Default → "New"
4. Generate reply:
   - If Ask-More: AI-generated "V0 Ask-More" reply
   - If Routed: Short acknowledgment
5. Create Deal record:
   - Founder name, email
   - Deck link, dataroom link
   - Four basics flags
   - State
   - Linked to EmailClassification
```

### Email Storage Limit

- **Maximum Emails**: 20 per user
- **Cleanup**: After processing, if >20 emails exist:
  - Delete oldest emails (by classified_at)
  - Delete associated Deal records (cascade)
  - Keep latest 20 emails

---

## Database Schema

### Users Table

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Relationships:**
- One-to-one with `gmail_tokens`
- One-to-many with `email_classifications`
- One-to-many with `deals`

### Gmail Tokens Table

```sql
CREATE TABLE gmail_tokens (
    id INTEGER PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL,
    encrypted_token TEXT NOT NULL,
    selected_signature_email VARCHAR(255),
    history_id VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

**Security:**
- `encrypted_token`: Fernet-encrypted JSON token
- `history_id`: Gmail History API ID for incremental sync

### Email Classifications Table

```sql
CREATE TABLE email_classifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    thread_id VARCHAR(255) NOT NULL,
    message_id VARCHAR(255) NOT NULL,
    subject VARCHAR(500),
    sender VARCHAR(255),
    snippet TEXT,
    email_date BIGINT,
    category VARCHAR(20) NOT NULL,
    tags VARCHAR(255),
    reply_type VARCHAR(50),
    reply_sent BOOLEAN DEFAULT FALSE,
    confidence FLOAT,
    classified_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    deal_state VARCHAR(50),
    deck_link TEXT,
    extracted_links TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_thread (user_id, thread_id)
);
```

**Categories:**
- DEAL_FLOW, NETWORKING, HIRING, SPAM, GENERAL

**Tags:**
- DF/Deal, DF/AskMore, NW/Networking, HR/Hiring, SPAM/Skip, GEN/General

### Deals Table

```sql
CREATE TABLE deals (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    thread_id VARCHAR(255) NOT NULL,
    classification_id INTEGER,
    founder_name VARCHAR(255),
    founder_email VARCHAR(255),
    subject VARCHAR(500),
    deck_link TEXT,
    dataroom_link TEXT,
    has_deck BOOLEAN DEFAULT FALSE,
    has_team_info BOOLEAN DEFAULT FALSE,
    has_traction BOOLEAN DEFAULT FALSE,
    has_round_info BOOLEAN DEFAULT FALSE,
    state VARCHAR(50) DEFAULT 'New',
    founder_linkedin TEXT,
    founder_school VARCHAR(255),
    founder_previous_companies TEXT,
    portfolio_overlaps TEXT,
    risk_score FLOAT,
    portfolio_comparison_score FLOAT,
    founder_market_score FLOAT,
    traction_score FLOAT,
    team_background_score FLOAT,
    white_space_score FLOAT,
    overall_score FLOAT,
    white_space_analysis TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (classification_id) REFERENCES email_classifications(id),
    INDEX idx_user_thread_deal (user_id, thread_id)
);
```

**States:**
- New: Initial state
- Ask-More: Missing information, sent ask-more reply
- Routed: All basics present, ready for review

---

## API Endpoints

### Authentication Endpoints

#### `GET /`
- Redirects to `/app` or `/login`

#### `GET /app`
- Redirects to `/dashboard` if logged in, else `/login`

#### `GET /login`
- Renders login page

#### `POST /login`
- Authenticates user
- Creates session
- Redirects to `/dashboard`

#### `GET /signup`
- Renders signup page

#### `POST /signup`
- Creates new user
- Hashes password
- Redirects to `/login`

#### `GET /logout`
- Clears session
- Redirects to `/login`

### Dashboard Endpoints

#### `GET /dashboard`
- Requires: `@login_required`
- Renders dashboard template
- Passes: `has_gmail`, `gmail_email`, `send_emails`, `max_emails`

### Gmail Connection Endpoints

#### `GET /connect-gmail`
- Requires: `@login_required`
- Initiates OAuth flow
- Redirects to Google OAuth consent screen

#### `GET /oauth2callback`
- Requires: `@login_required`
- Handles OAuth callback
- Exchanges code for tokens
- Encrypts and stores tokens
- Redirects to `/dashboard?connected=true`

#### `GET /disconnect-gmail`
- Requires: `@login_required`
- Deletes GmailToken record
- Redirects to `/dashboard`

### Email Endpoints

#### `GET /api/emails`
- Requires: `@login_required`, Gmail connected
- Parameters:
  - `max` (default: 20, capped at 20)
  - `category` (optional filter)
  - `show_spam` (default: false)
  - `force_full_sync` (default: false)
  - `db_only` (default: false)
- Returns: JSON with emails array
- Flow:
  1. Uses incremental sync if history_id exists
  2. Falls back to full sync if needed
  3. Classifies new emails
  4. Returns classified emails
  5. Enforces 20-email limit (deletes oldest)

#### `GET /api/starred-emails`
- Requires: `@login_required`, Gmail connected
- Parameters: `max` (default: 20, capped at 20)
- Returns: JSON with starred emails

#### `GET /api/sent-emails`
- Requires: `@login_required`, Gmail connected
- Parameters: `max` (default: 20, capped at 20)
- Returns: JSON with sent emails

#### `GET /api/drafts`
- Requires: `@login_required`, Gmail connected
- Parameters: `max` (default: 20, capped at 20)
- Returns: JSON with draft emails

#### `GET /api/thread/<thread_id>`
- Requires: `@login_required`, Gmail connected
- Returns: JSON with all messages in thread

### Email Actions

#### `POST /api/reclassify-email`
- Requires: `@login_required`, Gmail connected
- Body: `{"thread_id": "..."}`
- Force reclassifies email
- Returns: Updated classification

#### `POST /api/generate-reply`
- Requires: `@login_required`, Gmail connected
- Body: `{"thread_id": "...", "category": "..."}`
- Generates AI reply based on category
- Returns: Reply text, signature preview

#### `POST /api/send-reply`
- Requires: `@login_required`, Gmail connected
- Body: `{"thread_id": "...", "reply_text": "..."}`
- Sends reply email via Gmail API
- Updates `reply_sent` flag
- Returns: Success status

#### `POST /api/send-email`
- Requires: `@login_required`, Gmail connected
- Body: `{"to": "...", "subject": "...", "body": "...", "cc": "...", "bcc": "..."}`
- Sends new email (not a reply)
- Appends signature automatically
- Returns: Success status

#### `POST /api/mark-read`
- Requires: `@login_required`, Gmail connected
- Body: `{"email_id": "..."}`
- Marks email as read in Gmail
- Returns: Success status

#### `POST /api/toggle-star`
- Requires: `@login_required`, Gmail connected
- Body: `{"email_id": "...", "star": true/false}`
- Stars/unstars email in Gmail
- Syncs bidirectionally with Gmail
- Returns: Success status

### Signature Endpoints

#### `GET /api/signatures`
- Requires: `@login_required`, Gmail connected
- Returns: JSON with all send-as aliases and signatures

#### `POST /api/signature/select`
- Requires: `@login_required`, Gmail connected
- Body: `{"send_as_email": "..."}`
- Saves selected signature email preference
- Returns: Success status

### Deal Flow Endpoints

#### `GET /api/deals`
- Requires: `@login_required`
- Returns: JSON with all deals for user
- Includes classification and scores

#### `POST /api/rescore-all-deals`
- Requires: `@login_required`
- Re-scores all deals (currently disabled)
- Returns: Success status

### Attachment Endpoints

#### `GET /api/attachment/<message_id>/<filename>`
- Requires: `@login_required`, Gmail connected
- Downloads and serves PDF/DOCX attachment
- Returns: File download

### Config Endpoints

#### `GET /api/config`
- Requires: `@login_required`
- Returns: JSON with `send_emails_enabled`, `max_emails`

---

## Frontend Architecture

### Page Structure

#### Dashboard (`templates/dashboard.html`)
- **Navbar**: Logo, search bar, user info, Gmail status, compose button
- **Sidebar**: Collapsible navigation (Inbox, Sent, Starred, Drafts, categories)
- **Main Content**: Email list, filters, modals
- **Modals**: Email viewer, compose, signature selection

### JavaScript Architecture (`static/js/app.js`)

#### State Management
- `emailCache`: Cached emails in memory
- `allEmails`: Current filtered emails
- `currentTab`: Active tab (inbox, sent, starred, etc.)
- `isFetching`: Prevents concurrent fetches
- `autoFetchInterval`: Background polling interval

#### Key Functions

**Email Fetching:**
- `fetchEmails()`: Fetches from `/api/emails`
- `fetchStarredEmails()`: Fetches from `/api/starred-emails`
- `fetchSentEmails()`: Fetches from `/api/sent-emails`
- `fetchDrafts()`: Fetches from `/api/drafts`

**Caching:**
- `loadEmailCacheFromStorage()`: Loads from localStorage
- `saveEmailCacheToStorage()`: Saves to localStorage
- `clearEmailCache()`: Clears cache
- Cache keys: `emailCache_${username}`

**Email Display:**
- `displayEmails()`: Renders email list
- `openEmail()`: Opens email modal (instant from cache)
- `formatEmailBody()`: Formats HTML/plain text emails
- `formatPlainText()`: Smart plain text formatting

**Email Actions:**
- `toggleStar()`: Stars/unstars email
- `generateReply()`: Generates AI reply
- `sendReply()`: Sends reply
- `openComposeModal()`: Opens compose modal
- `sendComposedEmail()`: Sends new email

**Search:**
- `handleSearchInput()`: Real-time search
- `applyFilters()`: Applies search + category filters

**Auto-fetch:**
- `autoFetchNewEmails()`: Background polling
- Uses incremental sync via history_id
- Pauses on rate limit errors

### CSS Architecture

#### Main Stylesheet (`static/css/style.css`)
- Global variables (colors, spacing)
- Navbar styling
- Email list styling
- Modal styling
- Responsive design

#### Sidebar Stylesheet (`static/css/sidebar.css`)
- Sidebar layout
- Collapsible animations
- Icon styling
- Active state indicators

---

## Deployment Architecture

### Railway Deployment

#### Build Process
1. Railway detects `Procfile`
2. Installs dependencies from `requirements.txt`
3. Sets Python version from `runtime.txt`
4. Runs: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`

#### Environment Variables
- Set via Railway dashboard → Variables tab
- Service-specific (not shared)
- Auto-provided: `DATABASE_URL`, `RAILWAY_*` variables

#### Database
- PostgreSQL service on Railway
- Auto-provisioned
- Connection via `DATABASE_URL`
- Migrations: Auto-created on first run via `db.create_all()`

#### HTTPS
- Railway provides HTTPS automatically
- Custom domain: `khair.up.railway.app`
- ProxyFix middleware detects HTTPS from headers

### Production Configuration

#### Gunicorn
- **Workers**: 2
- **Timeout**: 120 seconds
- **Bind**: `0.0.0.0:$PORT`

#### Database Connection
- PostgreSQL connection pooling via SQLAlchemy
- Auto-reconnection on connection loss

---

## Data Flow Diagrams

### Complete Email Processing Flow

```
User Action: "Fetch Emails"
    ↓
Frontend: fetchEmails()
    ↓
API: GET /api/emails
    ↓
Backend: get_emails()
    ↓
Check: history_id exists?
    ├─ Yes → Gmail History API (incremental sync)
    └─ No → Gmail messages.list() (full sync)
    ↓
Gmail API Returns: emails[]
    ↓
For each email:
    ├─ Check: Already classified?
    │   ├─ Yes → Skip classification
    │   └─ No → Continue
    ├─ Extract: Subject, body, attachments, links
    ├─ Parse: PDF/DOCX attachments
    ├─ Classify: Deterministic + AI
    ├─ Store: EmailClassification record
    └─ If DEAL_FLOW:
        ├─ Extract: Founder info, four basics
        ├─ Determine: State (New/Ask-More/Routed)
        ├─ Generate: Reply if needed
        └─ Store: Deal record
    ↓
Enforce: 20-email limit
    ├─ Count: Total classifications
    ├─ If > 20: Delete oldest
    └─ Cascade: Delete associated deals
    ↓
Return: JSON with emails[]
    ↓
Frontend: displayEmails()
    ↓
User sees: Classified emails in UI
```

### OAuth Flow Diagram

```
User clicks "Connect Gmail"
    ↓
GET /connect-gmail
    ↓
Backend:
  ├─ Clear OAuth session data
  ├─ Load GOOGLE_CREDENTIALS_JSON
  ├─ Create InstalledAppFlow
  ├─ Set redirect_uri
  ├─ Generate authorization_url + state
  └─ Store state in session
    ↓
Redirect to Google OAuth
    ↓
User authorizes
    ↓
Google redirects: /oauth2callback?code=...&state=...
    ↓
Backend:
  ├─ Validate state
  ├─ Recreate InstalledAppFlow
  ├─ Exchange code for tokens
  ├─ Encrypt tokens
  └─ Store in database
    ↓
Redirect to /dashboard?connected=true
    ↓
Frontend: Auto-fetches emails
```

### Security Flow

```
Request arrives
    ↓
@app.before_request
  ├─ Clear non-serializable session data
  └─ Continue
    ↓
@login_required (if protected route)
  ├─ Check session
  ├─ Load user from database
  └─ Set current_user
    ↓
Route handler
  ├─ Validate input
  ├─ Filter by user_id (data isolation)
  └─ Process request
    ↓
Response
  ├─ Encrypt sensitive data (if needed)
  └─ Return JSON/HTML
```

---

## Error Handling

### Gmail API Errors
- **429 Rate Limit**: Returns error with retry information, pauses auto-fetch
- **401 Unauthorized**: Token expired, triggers refresh
- **404 Not Found**: Email/thread not found, graceful handling

### OpenAI API Errors
- **429 Rate Limit**: Sets `openai_quota_exceeded` flag, uses deterministic classification
- **401 Unauthorized**: Invalid API key, returns error
- **500 Server Error**: Falls back to deterministic classification

### Database Errors
- **Connection Loss**: SQLAlchemy auto-reconnects
- **Constraint Violations**: Caught and returned as errors

### Session Errors
- **Serialization Errors**: Caught by `@app.before_request`, session cleaned

---

## Performance Optimizations

### Incremental Sync
- Uses Gmail History API
- 90%+ reduction in API calls
- Only fetches new/changed emails

### Batch Requests
- Gmail API batch requests for multiple messages
- Reduces HTTP overhead

### Caching
- Frontend: localStorage cache
- Backend: Email classifications in database
- Instant display from cache

### Email Limit
- Maximum 20 emails per user
- Automatic cleanup of old emails
- Reduces storage and API costs

---

## Monitoring & Logging

### Application Logs
- Print statements for key operations
- Error tracebacks logged
- Railway captures stdout/stderr

### Key Metrics to Monitor
- Gmail API quota usage
- OpenAI API costs
- Database size
- Response times
- Error rates

---

## Future Enhancements

### Potential Improvements
1. **Structured Logging**: Replace print with logging module
2. **Error Tracking**: Integrate Sentry
3. **Analytics**: Track user actions
4. **Caching**: Redis for email cache
5. **Background Jobs**: Celery for async tasks
6. **Webhooks**: Real-time email notifications
7. **Advanced Search**: Full-text search in database
8. **Export**: CSV/Excel export of deals

---

## Conclusion

This application provides a secure, multi-user email management system with:
- **Complete data isolation** between users
- **Encrypted token storage** at rest
- **HTTPS enforcement** in production
- **Efficient email processing** via incremental sync
- **AI-powered classification** with fallback
- **Deal flow management** for VC use case
- **Scalable architecture** ready for production

All security measures are in place to protect user data and ensure privacy.

