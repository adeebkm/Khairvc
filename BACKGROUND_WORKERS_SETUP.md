# Phase 1: Background Workers Setup Guide

## ✅ What Was Implemented

### 1. **Celery + Redis Infrastructure**
- ✅ Added Celery and Redis dependencies
- ✅ Created `celery_config.py` for Celery configuration
- ✅ Created `tasks.py` with background email sync task
- ✅ Updated `Procfile` to run Celery worker

### 2. **API Endpoints**
- ✅ `POST /api/emails/sync` - Trigger background sync
- ✅ `GET /api/emails/sync/status/<task_id>` - Get sync status

### 3. **Frontend Integration**
- ✅ Updated `fetchEmails()` to use background tasks
- ✅ Added `pollTaskStatus()` for real-time progress
- ✅ Added `loadEmailsFromDatabase()` to load results
- ✅ Falls back to streaming endpoint if Celery unavailable

---

## 🚀 Setup Instructions

### Step 1: Add Redis to Railway

1. Go to Railway dashboard
2. Click "New" → "Database" → "Add Redis"
3. Railway will create a Redis instance
4. Copy the `REDIS_URL` from the Redis service variables

### Step 2: Add Redis URL to Web Service

1. Go to your web service in Railway
2. Click "Variables" tab
3. Add new variable:
   - **Key**: `REDIS_URL`
   - **Value**: Copy from Redis service (e.g., `redis://default:password@redis.railway.internal:6379`)

### Step 3: Deploy

Railway will automatically:
- Install new dependencies (Celery, Redis)
- Start the Celery worker (from Procfile)
- Make background tasks available

---

## 📊 How It Works

### User Flow:

```
1. User clicks "Fetch Emails"
   ↓
2. Frontend calls POST /api/emails/sync
   ↓
3. Backend queues background task (instant response!)
   ↓
4. Frontend polls GET /api/emails/sync/status/<task_id>
   ↓
5. Worker processes emails in background
   ↓
6. Frontend shows real-time progress
   ↓
7. When complete, frontend loads emails from database
```

### Benefits:

- ✅ **Instant response** (< 100ms) - no waiting
- ✅ **No timeouts** - processing happens in background
- ✅ **Real-time progress** - user sees what's happening
- ✅ **Scalable** - handles 100+ users simultaneously
- ✅ **Rate limit safe** - workers process slowly

---

## 🔧 Configuration

### Celery Worker Settings

In `celery_config.py`:
- **Concurrency**: 10 workers (processes 10 emails at once)
- **Queue**: `email_sync` (all tasks go here)
- **Prefetch**: 1 (prevents rate limit conflicts)

### Task Settings

In `tasks.py`:
- **Max emails**: 100 per task
- **Rate limiting**: Semaphore(10) shared across workers
- **Timeout**: 10 minutes per task

---

## 🐛 Troubleshooting

### Issue: "Background tasks not available"

**Cause**: Celery not installed or Redis not configured

**Fix**:
1. Check `REDIS_URL` is set in Railway
2. Check Celery worker is running (Railway logs)
3. Verify dependencies installed (`pip list | grep celery`)

### Issue: Tasks stuck in PENDING

**Cause**: Worker not running

**Fix**:
1. Check Railway logs for worker process
2. Verify Procfile has worker line
3. Restart Railway service

### Issue: Tasks failing

**Cause**: Database connection or import errors

**Fix**:
1. Check Railway logs for error messages
2. Verify `DATABASE_URL` is set
3. Check all dependencies installed

---

## 📈 Monitoring

### Check Worker Status

```bash
# Via Railway CLI
railway logs --service web | grep celery

# Or check Railway dashboard → Logs
```

### Check Task Queue

Tasks are stored in Redis. You can monitor via:
- Railway Redis dashboard
- Or connect to Redis directly

---

## 🎯 Next Steps (Phase 2)

Once Phase 1 is working:

1. **Request Queuing** - Per-user queues
2. **Smart Caching** - Skip unchanged emails
3. **WebSocket Updates** - Real-time push (no polling)

---

## ✅ Testing

### Local Testing (without Railway):

1. **Start Redis**:
   ```bash
   # macOS
   brew install redis
   brew services start redis
   
   # Or use Docker
   docker run -d -p 6379:6379 redis
   ```

2. **Set environment**:
   ```bash
   export REDIS_URL="redis://localhost:6379/0"
   ```

3. **Start worker** (in separate terminal):
   ```bash
   celery -A celery_config worker --loglevel=info
   ```

4. **Start Flask app**:
   ```bash
   python app.py
   ```

5. **Test**:
   - Click "Fetch Emails" in UI
   - Should see "Starting email sync..." message
   - Should see progress updates
   - Should complete and show emails

---

## 📝 Notes

- **Backward Compatible**: Falls back to streaming if Celery unavailable
- **No Breaking Changes**: Existing `/api/emails` endpoint still works
- **Gradual Rollout**: Can test with one user first

---

## 🎉 Success Criteria

✅ User clicks "Fetch" → Instant response  
✅ Progress updates every second  
✅ No request timeouts  
✅ Emails appear when complete  
✅ Works with 10+ simultaneous users  

