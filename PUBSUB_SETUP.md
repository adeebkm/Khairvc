# Google Pub/Sub Setup for Gmail Push Notifications (Test Environment)

## Overview

Google Pub/Sub enables **push notifications** from Gmail instead of polling, dramatically reducing API calls and avoiding rate limits.

**Benefits:**
- ✅ Real-time email notifications (no polling delays)
- ✅ 90%+ reduction in Gmail API calls
- ✅ Avoids rate limit errors
- ✅ More efficient and cost-effective

## Prerequisites

1. **Google Cloud Project** with:
   - Gmail API enabled
   - Pub/Sub API enabled
   - Service account with Pub/Sub permissions

2. **Pub/Sub Topic** created in Google Cloud Console

3. **Pub/Sub Subscription** (optional, for testing)

## Setup Steps

### 1. Enable APIs in Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Enable these APIs:
   - **Gmail API** (already enabled)
   - **Cloud Pub/Sub API** (new)

### 2. Create Pub/Sub Topic

```bash
# Using gcloud CLI
gcloud pubsub topics create gmail-notifications --project=YOUR_PROJECT_ID

# Or via Google Cloud Console:
# 1. Go to Pub/Sub → Topics
# 2. Click "Create Topic"
# 3. Name: gmail-notifications
# 4. Click "Create"
```

**Topic Name Format:**
```
projects/YOUR_PROJECT_ID/topics/gmail-notifications
```

### 3. Grant Gmail Service Account Permissions

Gmail needs permission to publish to your Pub/Sub topic:

1. Go to Pub/Sub → Topics → `gmail-notifications`
2. Click "Permissions" tab
3. Click "Add Principal"
4. Add: `gmail-api-push@system.gserviceaccount.com`
5. Role: **Pub/Sub Publisher**
6. Click "Save"

### 4. Set Railway Environment Variables

Add these to your **test environment** in Railway:

```bash
USE_PUBSUB=true
PUBSUB_TOPIC=projects/YOUR_PROJECT_ID/topics/gmail-notifications
```

**Example:**
```
USE_PUBSUB=true
PUBSUB_TOPIC=projects/innate-gizmo-477223-f4/topics/gmail-notifications
```

### 5. Update OAuth Scopes

Users need to re-authenticate with the new Pub/Sub scope. The code automatically includes:
```
https://www.googleapis.com/auth/pubsub
```

**Note:** Existing users will need to disconnect and reconnect Gmail to get the new scope.

### 6. Set Up Webhook Endpoint

The webhook endpoint is automatically available at:
```
https://web-aws-test.up.railway.app/api/pubsub/gmail-notifications
```

**Configure in Pub/Sub (if using push subscription):**
1. Go to Pub/Sub → Subscriptions
2. Create subscription (optional - webhook receives directly from Gmail)
3. Set delivery type: **Push**
4. Endpoint URL: `https://web-aws-test.up.railway.app/api/pubsub/gmail-notifications`

**Note:** Gmail publishes directly to the topic, so a subscription is optional.

### 7. Initialize Watch for Users

After setting environment variables, users can set up Pub/Sub watch:

**Option A: Via API**
```bash
POST /api/setup-pubsub
Authorization: Bearer <token>
```

**Option B: Automatically on Gmail connection** (if implemented)

## How It Works

1. **User connects Gmail** → System sets up Gmail Watch with Pub/Sub topic
2. **New email arrives** → Gmail publishes notification to Pub/Sub topic
3. **Pub/Sub delivers** → Webhook receives notification at `/api/pubsub/gmail-notifications`
4. **System processes** → Updates history_id and triggers background email sync
5. **Watch expires** → After 7 days, must be renewed (auto-renewal can be implemented)

## Watch Expiration

Gmail Watch expires after **7 days** (604,800 seconds). The system stores the expiration timestamp in the database.

**Auto-renewal** (recommended):
- Check expiration daily
- Renew watch if expires within 24 hours
- Can be done via scheduled Celery task

## Testing

1. **Set environment variables** in Railway
2. **Connect Gmail** (user must re-authenticate)
3. **Call setup endpoint**: `POST /api/setup-pubsub`
4. **Send test email** to the Gmail account
5. **Check logs** for Pub/Sub notification
6. **Verify** email appears in inbox without polling

## Troubleshooting

### Error: "403 Permission Denied"
- **Fix:** Grant `gmail-api-push@system.gserviceaccount.com` Pub/Sub Publisher role on the topic

### Error: "404 Topic Not Found"
- **Fix:** Verify `PUBSUB_TOPIC` environment variable matches the exact topic name
- **Format:** `projects/PROJECT_ID/topics/TOPIC_NAME`

### No Notifications Received
- **Check:** Gmail Watch is active (expiration timestamp in database)
- **Check:** Webhook endpoint is publicly accessible (Railway domain)
- **Check:** Pub/Sub API is enabled in Google Cloud Console

### Watch Expired
- **Fix:** Call `/api/setup-pubsub` again to renew
- **Auto-renewal:** Implement scheduled task to renew before expiration

## Environment Variables Summary

```bash
# Test Environment (Railway)
USE_PUBSUB=true
PUBSUB_TOPIC=projects/YOUR_PROJECT_ID/topics/gmail-notifications
```

## Database Schema Changes

New fields in `gmail_tokens` table:
- `pubsub_topic` - Pub/Sub topic name
- `pubsub_subscription` - Subscription name (optional)
- `watch_expiration` - Unix timestamp when watch expires

## Migration

The database migration is automatic. New columns are added on app startup if they don't exist.

