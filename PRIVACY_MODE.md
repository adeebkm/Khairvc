# Privacy Mode (Minimal Logging)

## Overview

By default, the app logs email metadata (sender, subject, category) for debugging purposes. 

**Privacy Mode** disables all metadata logging, showing only essential system messages.

---

## What's Hidden in Privacy Mode

### ❌ **Hidden (Not Logged):**
- Sender email addresses
- Email subjects  
- Categories assigned to emails
- Thread IDs
- Email timestamps
- Any identifiable email metadata

### ✅ **Still Logged (Essential):**
- System status (server start, OAuth success)
- Error messages (for debugging failures)
- Email counts (e.g., "Fetched 12 emails")
- Lambda/OpenAI initialization status

---

## How to Enable Privacy Mode

### On Railway (Production):

1. Go to Railway Dashboard → Your Project → Web Service
2. Click **"Variables"** tab
3. Click **"+ New Variable"**
4. Add:
   ```
   MINIMAL_LOGGING
   true
   ```
5. Railway will auto-redeploy

### Locally (Testing):

Add to your `.env` file:
```bash
MINIMAL_LOGGING=true
```

---

## Logs Comparison

### **Without Privacy Mode (Default):**
```
✓ Lambda client initialized
📧 Appending email from founder@startup.com: Category=DEAL_FLOW, Subject=Seed Funding, Starred=False
📧 Appending email from vc@firm.com: Category=NETWORKING, Subject=Catch up coffee, Starred=True
📧 Loaded from DB: Category=GENERAL, Thread=19a6ed82bc34cfef
✅ Returning 12 emails to frontend
```

### **With Privacy Mode Enabled:**
```
🔒 Privacy mode: ENABLED (metadata logging disabled)
✓ Lambda client initialized
✅ Returning 12 emails to frontend
```

---

## Security Layers

| Layer | Protection | Status |
|-------|------------|--------|
| **Email Body** | Encrypted via Lambda | ✅ Always ON |
| **OpenAI Calls** | Hidden in Lambda logs | ✅ Always ON |
| **Email Metadata** | Hidden in app logs | ✅ Privacy Mode |

---

## When to Use

### **Use Privacy Mode:**
- ✅ Production deployment for customers
- ✅ When handling sensitive VC deal flow
- ✅ Compliance/audit requirements
- ✅ Maximum privacy mode

### **Don't Use Privacy Mode:**
- ❌ Development/debugging
- ❌ Testing new features
- ❌ Troubleshooting classification issues

---

## Important Notes

1. **Privacy Mode only affects Railway logs** (what you see in the dashboard)
2. **Email content is ALWAYS encrypted** via Lambda (regardless of this setting)
3. **Users still see their own emails** in the UI (this doesn't affect frontend)
4. **Errors are still logged** (for debugging critical issues)

---

## Verification

After enabling, check Railway logs. You should see:

```
🔒 Privacy mode: ENABLED (metadata logging disabled)
✓ Lambda client module imported successfully
✓ OpenAI client initialized
✓ Lambda client initialized
```

**No sender emails, subjects, or categories should appear in logs!** 🔒

---

## Cost Impact

**None.** This is just a logging configuration change.

---

## Disable Privacy Mode

Remove or set to `false`:

```bash
MINIMAL_LOGGING=false
```

Or simply delete the variable from Railway.

