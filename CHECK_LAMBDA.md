# How to See Lambda Classification Logs

## Current Status:
- ✅ Flask server running on `http://localhost:8080`
- ✅ boto3/Lambda client initialized (line 347-348)
- ✅ Gmail connected successfully

## To See Lambda in Action:

### Option 1: In Your Browser (RECOMMENDED)
1. Go to `http://localhost:8080` in your browser
2. Click **"Fetch Emails"** button
3. **Watch your terminal window in real-time**
4. You should see logs like:
   ```
   ✓ Lambda client initialized
   📧 Full sync: Fetching up to 20 emails...
   Classification request - Thread: xxx
   Lambda classification succeeded
   ```

### Option 2: Force Terminal Output
Run this in a NEW terminal window to see live logs:

```bash
cd "/Users/adeebkhaja/Documents/gmail openai"

# Kill the background Flask server
pkill -f "python3 app.py"

# Restart Flask in foreground (so you see all logs)
source venv/bin/activate
python3 app.py
```

Then open `http://localhost:8080` in your browser and click "Fetch Emails"

---

## What You Should See:

### ✅ Lambda Working:
```
✓ Lambda client initialized
📧 Full sync: Fetching up to 20 emails...
✅ Successfully created Gmail client for user 2
⚠️  Database is empty but historyId exists. Forcing full sync...
📧 Full sync: Fetching up to 20 emails...
✓ OpenAI client initialized
# ... Lambda classification logs here ...
✅ Full sync: Fetched X emails with Y API calls
```

### ❌ Lambda Failing (would fall back to OpenAI):
```
⚠️ Lambda classification failed, falling back to OpenAI
```

---

## Current Situation:

Based on your terminal (line 349), the last action was:
- `GET /api/emails?max=20&show_spam=true` returned `200`

This means **emails were loaded from database** (no new classification needed).

**To trigger Lambda classification**, you need to:
1. Click "Fetch Emails" to fetch NEW emails from Gmail
2. Or delete the database again and re-fetch

---

## Quick Command to Test Lambda Right Now:

```bash
cd "/Users/adeebkhaja/Documents/gmail openai"
source venv/bin/activate
python3 test_lambda.py
```

This will test Lambda classification directly without the web app.

