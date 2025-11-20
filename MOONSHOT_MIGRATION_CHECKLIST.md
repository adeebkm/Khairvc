# Moonshot API Migration Checklist (Test Environment)

## ✅ Already Completed

1. **AWS Lambda Function** (`aws_lambda/classify_email.py`)
   - ✅ Updated to use Moonshot API base URL: `https://api.moonshot.cn/v1`
   - ✅ Updated model to: `kimi-k2-thinking`
   - ✅ Updated secret retrieval to support Moonshot API key

2. **AWS Secrets Manager**
   - ✅ Test secret (`openai-api-key-test`) updated with Moonshot API key
   - ✅ Key: `REDACTED_MOONSHOT_API_KEY`

3. **Lambda Deployment**
   - ✅ Lambda function redeployed with Moonshot configuration

---

## ⚠️ Still Needs Updating (Test Environment Only)

### 1. Railway Environment Variables

**File:** `RAILWAY_TEST_ENV_VARS.json`

**Current:**
```json
"OPENAI_API_KEY": "REDACTED_OPENAI_API_KEY"
```

**Should be:**
```json
"OPENAI_API_KEY": "REDACTED_MOONSHOT_API_KEY"
```

**Why:** This is used for fallback when Lambda fails, and for reply generation.

---

### 2. Fallback OpenAI Calls in `email_classifier.py`

**Location:** Lines 754-763, 1071, 1128

**Current:** Uses `gpt-4o-mini` with OpenAI API

**Options:**
- **Option A (Recommended):** Add environment variable check to use Moonshot in test
- **Option B:** Keep OpenAI fallback (simpler, but uses OpenAI credits)

**If choosing Option A**, need to:
- Add `MOONSHOT_API_KEY` environment variable check
- Update `email_classifier.py` to use Moonshot when Lambda fails (test env only)
- Update `openai_client.py` to support Moonshot base URL

---

### 3. Reply Generation (`openai_client.py`)

**Location:** Lines 41-42, 89-90

**Current:** Uses OpenAI `gpt-4o-mini` for reply generation

**Options:**
- **Option A:** Update to use Moonshot in test environment
- **Option B:** Keep OpenAI for replies (replies are less frequent than classification)

**If choosing Option A**, need to:
- Update `OpenAIClient` to accept `base_url` parameter
- Add environment variable to detect test environment
- Use Moonshot API for test, OpenAI for production

---

## 📋 Summary

### Critical (Must Update):
1. ✅ **Lambda Function** - DONE
2. ✅ **AWS Secrets Manager** - DONE
3. ⚠️ **Railway Test Environment Variables** - Update `OPENAI_API_KEY` to Moonshot key

### Optional (Nice to Have):
4. ⚠️ **Fallback Classification** (`email_classifier.py`) - Update to use Moonshot when Lambda fails
5. ⚠️ **Reply Generation** (`openai_client.py`) - Update to use Moonshot for replies

---

## 🎯 Recommended Approach

### Minimal Changes (Test Environment):
1. Update Railway test environment `OPENAI_API_KEY` to Moonshot key
2. Keep fallback and reply generation using OpenAI (they're less frequent)

### Full Migration (Test Environment):
1. Update Railway test environment `OPENAI_API_KEY` to Moonshot key
2. Add environment variable `USE_MOONSHOT=true` for test environment
3. Update `email_classifier.py` to check `USE_MOONSHOT` and use Moonshot API
4. Update `openai_client.py` to check `USE_MOONSHOT` and use Moonshot API

---

## 🔄 Production Environment

**No changes needed** - Production continues using:
- OpenAI API (`gpt-4o-mini`)
- Production Lambda with OpenAI
- Production Railway environment variables

---

## 📝 Next Steps

1. **Update Railway Test Environment Variables:**
   - Go to Railway → Test Environment → Variables
   - Update `OPENAI_API_KEY` to: `YOUR_MOONSHOT_API_KEY`

2. **Optional: Update Fallback & Reply Generation:**
   - Add `USE_MOONSHOT=true` to test environment variables
   - Update `email_classifier.py` and `openai_client.py` to support Moonshot

