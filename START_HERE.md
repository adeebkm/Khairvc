# 🚀 START HERE - Complete Setup Guide

**Welcome!** Follow these steps to set up your Gmail Auto-Reply system.

---

## 📋 Prerequisites

Before starting, you need:

1. **Python 3.8+** installed on your computer
   - Check: `python3 --version`
   - Install from: https://www.python.org/downloads/

2. **OpenAI API Key**
   - Get it from: https://platform.openai.com/api-keys
   - Create an account if you don't have one
   - Click "Create new secret key"
   - Copy and save it (starts with `sk-`)

3. **Gmail Account**
   - Any Gmail account will work

---

## 🎯 Quick Setup (Automated)

### Option 1: One-Command Setup (Easiest!)

```bash
cd "/Users/adeebkhaja/Documents/gmail openai"
./setup_environment.sh
```

This script will:
- ✓ Check Python installation
- ✓ Create virtual environment
- ✓ Install all dependencies
- ✓ Help you create .env file
- ✓ Verify your setup

**Then follow the prompts to add your OpenAI API key!**

---

## 🔧 Manual Setup (Step by Step)

### Step 1: Create Virtual Environment

```bash
cd "/Users/adeebkhaja/Documents/gmail openai"
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Create Configuration

```bash
python setup.py
```

Enter your OpenAI API key when prompted.

### Step 4: Get Gmail Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable Gmail API
3. Create OAuth credentials (Desktop app)
4. Download as `credentials.json`
5. Place in this directory

**Detailed instructions:** See `setup_guide.md`

### Step 5: Test Setup

```bash
python test_setup.py
```

### Step 6: Authenticate Gmail

```bash
python auto_reply.py
```

Browser will open → Sign in → Allow permissions

---

## 🎉 You're Ready!

### Start the Web Interface

```bash
source venv/bin/activate  # If not already activated
python app.py
```

Open in browser: **http://localhost:5000**

### Or Use Command Line

```bash
python auto_reply.py
```

---

## 📁 What You Need

After setup, you should have these files:

```
✓ venv/              (created by setup)
✓ .env               (your configuration)
✓ credentials.json   (from Google)
✓ token.json         (created after first Gmail auth)
```

---

## 🆘 Troubleshooting

### "python3 not found"
Install Python from: https://www.python.org/downloads/

### "pip not found"
```bash
python3 -m pip install --upgrade pip
```

### "credentials.json not found"
You need to download it from Google Cloud Console.
See: `setup_guide.md` for step-by-step instructions.

### "OpenAI API key invalid"
- Check you copied the full key (starts with `sk-`)
- Verify at: https://platform.openai.com/api-keys
- Make sure your account has credits

---

## 📚 Documentation

- **`ENVIRONMENT_SETUP.md`** - Detailed environment setup guide
- **`setup_guide.md`** - Google Cloud Console walkthrough
- **`QUICKSTART_WEB.md`** - Web interface quick start
- **`WEB_APP_GUIDE.md`** - Complete web interface guide
- **`README.md`** - Full project documentation

---

## 🎯 Quick Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Run automated setup
./setup_environment.sh

# Test configuration
python test_setup.py

# Start web interface
python app.py

# Run command line version
python auto_reply.py
```

---

## 💡 Tips

1. **Start in Test Mode**: Default is `SEND_EMAILS=false` so you can safely test
2. **Use Web Interface**: Much easier than command line - try `python app.py`
3. **Review AI Replies**: Always check before enabling automatic sending
4. **Keep Credentials Safe**: Never commit `.env`, `credentials.json`, or `token.json` to git

---

## 🌟 What's Next?

Once everything is set up:

1. **Test it out**: `python app.py` → http://localhost:5000
2. **Fetch some emails**: Click "Fetch Emails" button
3. **Generate a reply**: Click on an email, then "Generate Reply"
4. **Review quality**: Check if AI responses look good
5. **Enable sending**: When ready, set `SEND_EMAILS=true` in `.env`

---

## ✅ Setup Checklist

- [ ] Python 3.8+ installed
- [ ] Virtual environment created (`venv/`)
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created with OpenAI API key
- [ ] `credentials.json` downloaded from Google
- [ ] Gmail authenticated (`token.json` created)
- [ ] Setup test passed (`python test_setup.py`)
- [ ] Tried web interface (`python app.py`)

---

**Need Help?** Check the documentation files or review the code - it's well commented!

**Ready to go?** Run: `./setup_environment.sh`

🚀 **Happy automating!**

