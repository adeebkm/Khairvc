# Quick Setup Guide

Follow these steps to get your Gmail Auto-Reply system running in ~10 minutes.

## Step-by-Step Setup

### Step 1: Install Python Dependencies (1 min)

```bash
pip install -r requirements.txt
```

### Step 2: Get Your OpenAI API Key (2 min)

1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Sign in or create an account
3. Click "Create new secret key"
4. Copy the key (starts with `sk-...`)
5. Keep it safe - you'll need it in Step 4

### Step 3: Set Up Gmail API (5 min)

#### 3.1 Create Google Cloud Project

1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "New Project"
3. Name it "Gmail Auto Reply" → Click "Create"
4. Wait for the project to be created (~10 seconds)

#### 3.2 Enable Gmail API

1. In the search bar, type "Gmail API"
2. Click on "Gmail API" in the results
3. Click the blue "Enable" button
4. Wait for it to enable (~5 seconds)

#### 3.3 Create OAuth Credentials

1. Click "Credentials" in the left sidebar
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted to configure consent screen:
   - Click "Configure Consent Screen"
   - Choose "External" → Click "Create"
   - Fill in:
     - App name: "Gmail Auto Reply"
     - User support email: (your email)
     - Developer contact: (your email)
   - Click "Save and Continue" (3 times)
   - Click "Back to Dashboard"
   - Return to Credentials tab
4. Click "Create Credentials" → "OAuth client ID" again
5. Choose "Desktop app"
6. Name it "Gmail Auto Reply Client"
7. Click "Create"

#### 3.4 Download Credentials

1. You'll see a dialog with your client ID and secret
2. Click "Download JSON"
3. Save it to your project folder as `credentials.json`

### Step 4: Configure Environment (1 min)

Create a file named `.env` in the project folder:

```bash
OPENAI_API_KEY=sk-your-actual-key-here
SEND_EMAILS=false
MAX_EMAILS=5
UNREAD_ONLY=true
```

Replace `sk-your-actual-key-here` with the OpenAI key from Step 2.

### Step 5: First Run (1 min)

```bash
python auto_reply.py
```

**What will happen:**
1. A browser window will open
2. Sign in to your Gmail account
3. Click "Allow" to grant permissions
4. The browser will show "authentication successful"
5. Close the browser and return to terminal
6. The script will start processing emails!

## You're Done! 🎉

The script is now running and will:
- ✅ Read your unread emails
- ✅ Analyze them with AI
- ✅ Generate professional replies
- ✅ Show you what it would send
- ⚠️ **NOT send anything** (because `SEND_EMAILS=false`)

## Test It Out

Send yourself a test email to see how it works:

1. From another account, send an email to yourself
2. Run the script: `python auto_reply.py`
3. See the AI-generated reply in the console!

## When Ready to Auto-Send

Once you're confident with the AI replies:

1. Edit `.env` and change:
   ```
   SEND_EMAILS=true
   ```

2. Run again:
   ```bash
   python auto_reply.py
   ```

Now it will actually send replies! 🚀

## Quick Tips

- **Run regularly**: Add to cron or Task Scheduler to check emails automatically
- **Monitor costs**: Check [OpenAI usage dashboard](https://platform.openai.com/usage)
- **Review replies**: Keep `SEND_EMAILS=false` for the first few runs
- **Adjust filters**: Edit the code to customize which emails get replies

## Troubleshooting

**"credentials.json not found"**
→ Make sure you downloaded it to the correct folder in Step 3.4

**"OpenAI API key not found"**
→ Check your `.env` file has `OPENAI_API_KEY=` with your actual key

**"No unread messages found"**
→ Send yourself a test email first!

**Browser doesn't open for Gmail auth**
→ Check for a URL in the terminal and open it manually

---

Need more details? Check out the full `README.md` file!

