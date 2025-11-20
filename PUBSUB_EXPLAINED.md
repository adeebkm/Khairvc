# How Google Pub/Sub Works for Gmail Notifications

## 🎯 The Problem It Solves

**Without Pub/Sub (Polling):**
- System constantly asks Gmail: "Any new emails?" (every few minutes)
- Wastes API quota even when inbox is empty
- Hits rate limits with multiple users
- Delayed email detection (up to polling interval)

**With Pub/Sub (Push Notifications):**
- Gmail tells your system: "Hey, new email arrived!"
- Zero API calls when inbox is empty
- Real-time notifications (instant)
- Avoids rate limits

---

## 📊 Complete Flow Diagram

```
┌─────────────┐
│   User      │
│  Connects   │
│   Gmail     │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Your App (Railway)                 │
│  POST /api/setup-pubsub             │
│                                     │
│  1. Calls Gmail API:               │
│     users().watch()                 │
│                                     │
│  2. Tells Gmail:                   │
│     "Send notifications to:        │
│      projects/.../topics/..."       │
│                                     │
│  3. Gmail responds:                │
│     ✅ Watch active                 │
│     Expires: 7 days                 │
│     History ID: 12345               │
└──────┬──────────────────────────────┘
       │
       │ Stores in database:
       │ - pubsub_topic
       │ - watch_expiration
       │ - history_id
       │
       ▼
┌─────────────────────────────────────┐
│  Google Cloud Pub/Sub               │
│                                     │
│  Topic: gmail-notifications         │
│                                     │
│  Gmail has permission to publish    │
│  to this topic                      │
└─────────────────────────────────────┘
       │
       │ (Waiting...)
       │
       ▼
┌─────────────────────────────────────┐
│  New Email Arrives in Gmail         │
│                                     │
│  User receives email:               │
│  "Hello from sender@example.com"    │
└──────┬──────────────────────────────┘
       │
       │ Gmail automatically publishes
       │ notification to Pub/Sub topic
       │
       ▼
┌─────────────────────────────────────┐
│  Google Pub/Sub Topic               │
│                                     │
│  Receives notification:             │
│  {                                  │
│    "emailAddress": "user@...",      │
│    "historyId": "12346"             │
│  }                                  │
└──────┬──────────────────────────────┘
       │
       │ Pub/Sub delivers to webhook
       │ (HTTP POST request)
       │
       ▼
┌─────────────────────────────────────┐
│  Your App Webhook                   │
│  POST /api/pubsub/gmail-notifications│
│                                     │
│  1. Receives notification           │
│  2. Decodes base64 message          │
│  3. Extracts:                       │
│     - emailAddress                  │
│     - historyId                    │
│  4. Finds user by email             │
│  5. Updates history_id in DB        │
│  6. Triggers background sync        │
└──────┬──────────────────────────────┘
       │
       │ Queues Celery task
       │
       ▼
┌─────────────────────────────────────┐
│  Celery Worker                      │
│                                     │
│  Task: sync_user_emails()          │
│                                     │
│  1. Uses history_id for            │
│     incremental sync                │
│  2. Fetches only NEW emails        │
│     (since last history_id)         │
│  3. Classifies new emails           │
│  4. Stores in database             │
└──────┬──────────────────────────────┘
       │
       │ Updates UI
       │
       ▼
┌─────────────────────────────────────┐
│  User's Inbox                       │
│                                     │
│  ✅ New email appears instantly!    │
└─────────────────────────────────────┘
```

---

## 🔧 Step-by-Step Technical Details

### Step 1: Setting Up the Watch

**When:** User connects Gmail or calls `/api/setup-pubsub`

**What happens:**
```python
# In gmail_client.py
watch_request = {
    'topicName': 'projects/innate-gizmo-477223-f4/topics/gmail-notifications',
    'labelIds': ['INBOX'],  # Only watch inbox
    'labelFilterAction': 'include'
}

response = gmail_service.users().watch(
    userId='me',
    body=watch_request
).execute()
```

**Gmail Response:**
```json
{
  "expiration": "1764273285981",  // Unix timestamp (milliseconds)
  "historyId": "2609"              // Current history ID
}
```

**What we store:**
- `pubsub_topic`: The topic name
- `watch_expiration`: When the watch expires (7 days from now)
- `history_id`: Last known state of inbox

---

### Step 2: Gmail Publishes Notification

**When:** New email arrives in user's inbox

**What Gmail does:**
1. Detects new email in INBOX
2. Publishes notification to your Pub/Sub topic
3. Notification contains:
   - `emailAddress`: User's email
   - `historyId`: New history ID (incremented)

**Pub/Sub Message Format:**
```json
{
  "emailAddress": "user@example.com",
  "historyId": "2610"
}
```

---

### Step 3: Pub/Sub Delivers to Webhook

**How Pub/Sub delivers:**
- Makes HTTP POST request to your webhook URL
- Message is base64-encoded in the request body

**Request Format:**
```json
{
  "message": {
    "data": "eyJlbWFpbEFkZHJlc3MiOiJ1c2VyQGV4YW1wbGUuY29tIiwiaGlzdG9yeUlkIjoiMjYxMCJ9",
    "messageId": "1234567890",
    "publishTime": "2025-11-20T20:00:00Z"
  },
  "subscription": "projects/.../subscriptions/..."
}
```

**The `data` field is base64-encoded JSON:**
```python
import base64
decoded = base64.b64decode("eyJlbWFpbEFkZHJlc3MiOiJ1c2VyQGV4YW1wbGUuY29tIiwiaGlzdG9yeUlkIjoiMjYxMCJ9")
# Result: {"emailAddress":"user@example.com","historyId":"2610"}
```

---

### Step 4: Webhook Processes Notification

**Endpoint:** `POST /api/pubsub/gmail-notifications`

**What happens:**
```python
# 1. Decode the message
decoded_data = base64.b64decode(message_data).decode('utf-8')
notification = json.loads(decoded_data)

# 2. Extract info
email_address = notification['emailAddress']  # "user@example.com"
history_id = notification['historyId']        # "2610"

# 3. Find user
user = User.query.filter_by(email=email_address).first()

# 4. Update history_id
user.gmail_token.history_id = history_id
db.session.commit()

# 5. Trigger background sync
sync_user_emails.delay(user.id, start_history_id=history_id)
```

---

### Step 5: Background Sync

**Celery Task:** `sync_user_emails()`

**What it does:**
```python
# Uses incremental sync with history_id
emails = gmail_client.get_emails(
    max_results=100,
    start_history_id=history_id  # Only fetch emails after this ID
)

# Only NEW emails are fetched (not all emails)
# This is super efficient!
```

**Result:**
- Only new emails are processed
- No redundant API calls
- Fast and efficient

---

## ⏰ Watch Expiration

**Important:** Gmail Watch expires after **7 days** (604,800 seconds)

**Why:**
- Gmail doesn't allow permanent watches
- Prevents abandoned watches from consuming resources

**What happens when expired:**
- No more notifications received
- System falls back to polling (if implemented)
- Must renew watch by calling `/api/setup-pubsub` again

**Auto-renewal (recommended):**
```python
# Check daily if watch expires within 24 hours
if watch_expiration - now < 86400:  # 24 hours
    # Renew watch
    setup_pubsub_watch()
```

---

## 🔐 Security & Permissions

### Required Permissions

1. **Gmail API:**
   - `gmail.modify` - Read emails
   - `gmail.settings.basic` - Access settings
   - `pubsub` - Set up watch (NEW)

2. **Pub/Sub Topic:**
   - Gmail service account needs **Publisher** role
   - Service account: `gmail-api-push@system.gserviceaccount.com`

### Webhook Security

**Current implementation:**
- No authentication (for testing)
- Anyone can POST to webhook

**Production recommendation:**
- Verify Pub/Sub JWT token
- Check request signature
- Validate message format

---

## 📈 Benefits Comparison

| Metric | Without Pub/Sub | With Pub/Sub |
|--------|----------------|--------------|
| **API Calls (empty inbox)** | 1 per minute | 0 |
| **API Calls (new email)** | 1 per minute | 1 (only when email arrives) |
| **Detection Delay** | Up to polling interval | Instant |
| **Rate Limit Risk** | High (constant polling) | Low (only on events) |
| **Cost** | Higher (more API calls) | Lower (fewer API calls) |

**Example:**
- 10 users, polling every 5 minutes
- **Without Pub/Sub:** 2,880 API calls/day (even if no emails)
- **With Pub/Sub:** ~50 API calls/day (only when emails arrive)

**Savings:** ~98% reduction in API calls! 🎉

---

## 🐛 Troubleshooting

### No Notifications Received

**Check:**
1. Watch is active (check `watch_expiration` in database)
2. Watch hasn't expired (must be < 7 days old)
3. Pub/Sub topic exists and is correct
4. Gmail service account has Publisher permission
5. Webhook URL is publicly accessible

### Watch Expired

**Symptoms:**
- No notifications for >7 days
- `watch_expiration` timestamp is in the past

**Fix:**
```bash
# Call setup endpoint again
POST /api/setup-pubsub
```

### 403 Permission Denied

**Error:** `Permission denied on topic`

**Fix:**
1. Go to Google Cloud Console → Pub/Sub → Topics
2. Select your topic → Permissions
3. Add: `gmail-api-push@system.gserviceaccount.com`
4. Role: **Pub/Sub Publisher**

---

## 🎓 Key Concepts

### History ID
- Unique identifier for inbox state
- Increments with each change
- Used for incremental sync (only fetch what changed)

### Watch
- Subscription to Gmail changes
- Expires after 7 days
- Must be renewed periodically

### Pub/Sub Topic
- Message queue in Google Cloud
- Gmail publishes notifications here
- Your webhook receives from here

### Webhook
- HTTP endpoint that receives notifications
- Must be publicly accessible
- Processes notifications asynchronously

---

## 🚀 Current Implementation Status

✅ **Implemented:**
- Gmail Watch setup (`setup_pubsub_watch()`)
- Webhook endpoint (`/api/pubsub/gmail-notifications`)
- Automatic watch setup on Gmail connection
- Database storage of watch info
- Background sync trigger

⏳ **To Do:**
- Auto-renewal of expired watches
- Webhook authentication/verification
- Error handling for failed notifications
- Monitoring/alerting for watch expiration

---

## 📝 Code Locations

**Watch Setup:**
- `gmail_client.py` → `setup_pubsub_watch()`
- `app.py` → `/api/setup-pubsub` endpoint

**Webhook:**
- `app.py` → `/api/pubsub/gmail-notifications` endpoint

**Database:**
- `models.py` → `GmailToken` model (pubsub fields)
- Auto-migration in `app.py`

**Background Processing:**
- `tasks.py` → `sync_user_emails()` (Celery task)

