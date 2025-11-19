# Active Files in Production

## Core Application Files (Required)

### Backend Python Files
- **app.py** - Main Flask application, routes, API endpoints
- **models.py** - Database models (User, GmailToken, EmailClassification, Deal)
- **auth.py** - Token encryption/decryption functions
- **gmail_client.py** - Gmail API integration, email fetching, sending, starring
- **openai_client.py** - OpenAI API integration
- **email_classifier.py** - Email classification logic (5 categories)

### Frontend Files
- **templates/dashboard.html** - Main dashboard UI
- **templates/login.html** - Login page
- **templates/signup.html** - Signup page
- **static/css/style.css** - Main stylesheet
- **static/css/sidebar.css** - Sidebar styles
- **static/js/app.js** - Frontend JavaScript logic

### Configuration Files
- **Procfile** - Railway deployment configuration (Gunicorn)
- **requirements.txt** - Python dependencies
- **runtime.txt** - Python version specification
- **railway.json** - Railway project configuration

## Environment Variables (Railway)
- `OPENAI_API_KEY` - OpenAI API key
- `SECRET_KEY` - Flask session secret
- `ENCRYPTION_KEY` - Token encryption key
- `GOOGLE_CREDENTIALS_JSON` - Google OAuth credentials
- `OAUTH_REDIRECT_URI` - OAuth callback URL
- `SEND_EMAILS` - Email sending toggle
- `MAX_EMAILS` - Maximum emails to process (capped at 20)
- `DATABASE_URL` - PostgreSQL connection (auto-provided by Railway)

## Database
- PostgreSQL (Railway) - Production database
- SQLite (local) - Development database (instance/gmail_auto_reply.db)

## Not Currently Used (Legacy/Development)
- `auto_reply.py.old` - Old CLI script
- `tracxn_scorer.py` - Scoring system (disabled)
- `vc_portfolio.py` - Portfolio matching (removed)
- `calculate_openai_cost.py` - Cost calculation utility
- `check_openai_quota.py` - Quota checking utility
- `config.py` - Old config management
- `setup.py` - Setup helper
- `init_db.py` - Database initialization
- `khair-website/` - Separate Next.js marketing site (not part of email app)

## File Dependencies

### app.py imports:
- models.py (database models)
- auth.py (encryption)
- gmail_client.py (Gmail operations)
- openai_client.py (OpenAI operations)
- email_classifier.py (classification)

### gmail_client.py uses:
- PyPDF2 (PDF parsing)
- python-docx (DOCX parsing)

### email_classifier.py uses:
- openai_client.py (for AI classification)

## Deployment Files
- **Procfile** - `web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- **railway.json** - Project name configuration
- **runtime.txt** - Python 3.11.0

