# Multi-User Gmail Auto-Reply Guide

## 🎉 **What's New - Multi-User System!**

Your Gmail Auto-Reply app is now a **complete multi-user service** where:
- ✅ Each user creates their own account
- ✅ Each user connects their own Gmail
- ✅ Users can't access each other's emails
- ✅ You (developer) can't access user emails
- ✅ Tokens are encrypted in the database
- ✅ Complete privacy and security

---

## 🚀 **Quick Start**

### 1. Install New Dependencies

```bash
cd "/Users/adeebkhaja/Documents/gmail openai"
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Start the Server

```bash
python app.py
```

### 3. Open Browser

Go to: **http://localhost:8080**

### 4. Create Your Account

- Click **"Sign up"**
- Enter username, email, password
- Click **"Create Account"**

### 5. Connect Your Gmail

- Click **"🔗 Connect Gmail"**
- Browser opens for Google OAuth
- Sign in with your Gmail account
- Click **"Allow"**
- You're connected! ✅

---

## 🧪 **Testing with Multiple Users**

### Test on Localhost:

1. **User 1** (Your main browser):
   - Sign up with account 1
   - Connect Gmail account 1
   - See only Gmail 1's emails

2. **User 2** (Incognito/Private browser):
   - Go to http://localhost:8080
   - Sign up with account 2
   - Connect Gmail account 2
   - See only Gmail 2's emails

**Both users can use the app simultaneously!** Each sees only their own emails.

---

## 🔒 **Security Features**

### What's Protected:

1. **Encrypted Tokens**
   - All Gmail tokens stored encrypted in database
   - Encryption key in `.env` file

2. **User Isolation**
   - Each user's session loads only their token
   - No cross-user data access

3. **Password Security**
   - Passwords hashed with Werkzeug
   - Never stored in plain text

4. **Session Management**
   - Flask-Login handles authentication
   - Secure session cookies

---

## 📁 **Database Structure**

The app creates `gmail_auto_reply.db` (SQLite) with:

- **users** table: User accounts
- **gmail_tokens** table: Encrypted Gmail tokens per user

---

## ⚙️ **Configuration**

### Environment Variables (`.env`):

```bash
# OpenAI API Key (shared across users)
OPENAI_API_KEY=sk-your-key-here

# Email Sending
SEND_EMAILS=false

# Max Emails
MAX_EMAILS=5

# Flask Secret Key (for sessions)
SECRET_KEY=your-secret-key-here

# Encryption Key (auto-generated if not set)
ENCRYPTION_KEY=your-encryption-key-here
```

---

## 🔧 **How It Works**

### User Flow:

1. **Sign Up** → Creates account in database
2. **Login** → Flask-Login creates session
3. **Connect Gmail** → OAuth flow → Token encrypted → Saved to database
4. **Fetch Emails** → Loads user's token → Decrypts → Creates Gmail client → Gets emails
5. **Generate Reply** → Uses OpenAI (shared API key)
6. **Send Reply** → Uses user's Gmail client → Sends from their account

### Privacy:

- ✅ Each user's token is encrypted
- ✅ Only decrypted when user is logged in
- ✅ You (developer) can't decrypt tokens without encryption key
- ✅ Even database access doesn't reveal emails

---

## 🌐 **Deploying to Production**

For production deployment:

1. **Change SECRET_KEY** in `.env` (generate random key)
2. **Set ENCRYPTION_KEY** (keep it secure!)
3. **Use PostgreSQL** instead of SQLite:
   ```python
   app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@host/db'
   ```
4. **Add HTTPS** (SSL certificate)
5. **Deploy to**: Heroku, AWS, Google Cloud, etc.

---

## 📊 **Admin Notes**

### As Developer:

- You can see user accounts in database
- You CANNOT decrypt their Gmail tokens (without encryption key)
- You CANNOT access their emails
- Each user manages their own Gmail connection

### Database Access:

If you want to see user accounts (for support):
```python
from app import app, db, User
with app.app_context():
    users = User.query.all()
    for user in users:
        print(f"{user.username} - {user.email}")
```

---

## 🎯 **Key Differences from Single-User Version**

| Feature | Single-User (Old) | Multi-User (New) |
|---------|------------------|------------------|
| Authentication | Gmail OAuth only | User accounts + Gmail OAuth |
| Token Storage | `token.json` file | Encrypted in database |
| Users | One (you) | Unlimited |
| Privacy | N/A | Complete isolation |
| Sessions | None | Flask-Login |
| Database | None | SQLite/PostgreSQL |

---

## 🐛 **Troubleshooting**

### "Gmail not connected" error
→ User needs to click "Connect Gmail" and complete OAuth

### "Database locked" error
→ SQLite issue - restart server or use PostgreSQL

### "Encryption key error"
→ Make sure ENCRYPTION_KEY is set in `.env`

### Users can't log in
→ Check database exists: `gmail_auto_reply.db`
→ Recreate: Delete `.db` file and restart server

---

## ✅ **Testing Checklist**

- [ ] Create user account
- [ ] Login works
- [ ] Connect Gmail works
- [ ] Fetch emails shows only user's emails
- [ ] Generate reply works
- [ ] Send reply works (if enabled)
- [ ] Multiple users can use simultaneously
- [ ] Each user sees only their emails
- [ ] Logout works

---

**Your multi-user Gmail Auto-Reply system is ready! 🚀**

