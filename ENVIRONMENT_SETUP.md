# Environment Setup Guide

Complete guide to setting up your Gmail Auto-Reply environment from scratch.

## Method 1: Automatic Setup (Easiest)

### Step 1: Create Python Virtual Environment

```bash
# Navigate to your project directory
cd "/Users/adeebkhaja/Documents/gmail openai"

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate
```

You should see `(venv)` at the start of your terminal prompt.

### Step 2: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs:
- google-auth-oauthlib (Gmail authentication)
- google-api-python-client (Gmail API)
- openai (OpenAI API)
- flask (Web interface)
- python-dotenv (Environment variables)

### Step 3: Create .env File

Run the interactive setup:
```bash
python setup.py
```

This will ask you for:
- Your OpenAI API key
- Email sending preference (false for testing)
- Max emails to process
- Unread only preference

**Or manually create `.env`:**
```bash
# Copy the template
cp env_template.txt .env

# Edit it
nano .env  # or use any text editor
```

Add your OpenAI API key to `.env`:
```
OPENAI_API_KEY=sk-your-actual-key-here
SEND_EMAILS=false
MAX_EMAILS=5
UNREAD_ONLY=true
```

### Step 4: Get Gmail Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable Gmail API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download as `credentials.json`
6. Place it in the project directory

**Detailed instructions**: See `setup_guide.md`

### Step 5: Verify Setup

```bash
python test_setup.py
```

This checks:
- ✓ All dependencies installed
- ✓ .env file configured
- ✓ credentials.json present
- ✓ OpenAI API key valid

### Step 6: First Authentication

```bash
python auto_reply.py
```

This will:
- Open your browser for Gmail authentication
- Create `token.json` file
- Show you how the system works

### Step 7: Start Using!

**Option A - Web Interface:**
```bash
python app.py
```
Then open: http://localhost:5000

**Option B - Command Line:**
```bash
python auto_reply.py
```

---

## Method 2: Manual Step-by-Step

### 1. Check Python Version

```bash
python3 --version
```

You need Python 3.8 or higher.

### 2. Create Virtual Environment

```bash
# Create venv
python3 -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
# venv\Scripts\activate
```

### 3. Install Each Package

```bash
pip install google-auth-oauthlib==1.2.0
pip install google-auth-httplib2==0.2.0
pip install google-api-python-client==2.108.0
pip install openai==1.51.0
pip install python-dotenv==1.0.0
pip install flask==3.0.0
```

### 4. Get OpenAI API Key

1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Sign in or create account
3. Click "Create new secret key"
4. Copy the key (starts with `sk-`)
5. Save it securely

### 5. Create .env File Manually

Create a file named `.env` in the project directory:

```bash
touch .env
```

Add this content:
```
OPENAI_API_KEY=sk-your-key-here
SEND_EMAILS=false
MAX_EMAILS=5
UNREAD_ONLY=true
```

Replace `sk-your-key-here` with your actual OpenAI API key.

### 6. Get Gmail Credentials

#### A. Create Google Cloud Project

1. Visit https://console.cloud.google.com/
2. Click "Select a project" → "New Project"
3. Name: "Gmail Auto Reply"
4. Click "Create"

#### B. Enable Gmail API

1. In search bar: "Gmail API"
2. Click "Gmail API"
3. Click "Enable"

#### C. Create OAuth Credentials

1. Go to "Credentials" in left sidebar
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure consent screen:
   - Choose "External"
   - App name: "Gmail Auto Reply"
   - Your email for support
   - Click "Save and Continue" (3 times)
4. Back to "Create Credentials" → "OAuth client ID"
5. Application type: "Desktop app"
6. Name: "Gmail Auto Reply Client"
7. Click "Create"

#### D. Download Credentials

1. Click download icon (⬇️) next to your OAuth 2.0 Client
2. Save as `credentials.json`
3. Move to your project directory

### 7. Test Your Setup

```bash
python test_setup.py
```

### 8. Authenticate with Gmail

```bash
python auto_reply.py
```

A browser will open:
1. Choose your Gmail account
2. Click "Allow" (may show unverified app warning - click "Advanced" → "Go to Gmail Auto Reply")
3. Grant permissions
4. Browser shows "authentication successful"
5. Close browser, return to terminal

This creates `token.json` for future use.

---

## Troubleshooting

### Virtual Environment Issues

**Problem**: `venv/bin/activate` not found

**Solution**:
```bash
# Make sure you created it first
python3 -m venv venv

# Check if it exists
ls -la venv/bin/
```

### Python Version Issues

**Problem**: Python 2.x or old version

**Solution**:
```bash
# Install Python 3.8+ from python.org
# Or use homebrew on macOS
brew install python@3.11
```

### pip Not Found

**Solution**:
```bash
python3 -m pip install --upgrade pip
```

### OpenAI API Key Not Working

**Check**:
1. Key starts with `sk-`
2. No spaces in `.env` file
3. No quotes around the key
4. Account has credits: https://platform.openai.com/account/usage

### credentials.json Issues

**Problem**: File not found

**Solution**:
1. Make sure it's in the project root directory
2. Check filename is exactly `credentials.json` (no spaces)
3. Re-download from Google Cloud Console if needed

### Gmail Authentication Fails

**Problem**: Browser doesn't open or shows error

**Solution**:
1. Delete `token.json` if it exists
2. Run `python auto_reply.py` again
3. Manually copy the URL from terminal if browser doesn't open
4. Make sure you're using the correct Google account

---

## Environment Variables Explained

### OPENAI_API_KEY
- **Required**: Yes
- **Format**: `sk-...` (starts with sk-)
- **Get it from**: https://platform.openai.com/api-keys

### SEND_EMAILS
- **Required**: No
- **Default**: `false`
- **Values**: `true` or `false`
- **Purpose**: Controls if emails are actually sent
- **Recommendation**: Keep as `false` for testing

### MAX_EMAILS
- **Required**: No
- **Default**: `5`
- **Values**: Any positive number
- **Purpose**: Limits how many emails to process per run

### UNREAD_ONLY
- **Required**: No
- **Default**: `true`
- **Values**: `true` or `false`
- **Purpose**: Only process unread emails vs all inbox emails

---

## File Checklist

After setup, you should have:

```
/Users/adeebkhaja/Documents/gmail openai/
├── venv/                      ✓ Virtual environment
├── .env                       ✓ Your configuration
├── credentials.json           ✓ Gmail OAuth credentials
├── token.json                 ✓ Created after first auth
├── requirements.txt           ✓ Already exists
├── app.py                     ✓ Already exists
├── auto_reply.py              ✓ Already exists
└── [other project files]      ✓ Already exist
```

---

## Quick Commands Reference

```bash
# Activate virtual environment
source venv/bin/activate

# Deactivate virtual environment
deactivate

# Install/update dependencies
pip install -r requirements.txt

# Test setup
python test_setup.py

# Run CLI version
python auto_reply.py

# Run web version
python app.py

# Create .env interactively
python setup.py
```

---

## Next Steps After Setup

1. ✓ Virtual environment created and activated
2. ✓ Dependencies installed
3. ✓ .env file configured
4. ✓ credentials.json downloaded
5. ✓ Gmail authenticated (token.json created)
6. → **Start using the system!**

**Try the web interface:**
```bash
python app.py
```

Then open http://localhost:5000 in your browser!

---

## Common Workflow

```bash
# Daily usage:

# 1. Activate environment (if not already active)
source venv/bin/activate

# 2. Start web interface
python app.py

# 3. Open browser to http://localhost:5000

# 4. When done, press Ctrl+C to stop server

# 5. Optionally deactivate environment
deactivate
```

---

Need more help? Check:
- `setup_guide.md` - Initial setup details
- `QUICKSTART_WEB.md` - Web interface quick start
- `README.md` - Full documentation

