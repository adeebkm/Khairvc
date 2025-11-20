# Railway Worker Service Setup

## 🎯 Problem

Railway only runs the `web` process by default. The `worker` process from your Procfile needs a separate service.

## ✅ Solution: Create Worker Service

### Step 1: Create New Service from Same Repo

1. **Go to Railway Dashboard**
   - Open your project
   - Click **"New"** button (top right)
   - Select **"GitHub Repo"** (or "Empty Service" if you prefer)

2. **Link to Same Repository**
   - Select the same GitHub repository
   - Railway will create a new service

3. **Configure the Service**
   - Railway will auto-detect your code
   - **Important**: Don't use the default start command

### Step 2: Set Custom Start Command

1. **Go to Service Settings**
   - Click on the new service
   - Go to **"Settings"** tab
   - Scroll to **"Deploy"** section

2. **Set Start Command**
   - Find **"Start Command"** field
   - Enter:
     ```
     celery -A celery_config worker --loglevel=info --concurrency=10 --queues=email_sync --max-tasks-per-child=1000
     ```
   - Click **"Save"**
   
   **Note**: The `--max-tasks-per-child=1000` flag helps prevent memory leaks and keeps the worker stable on Railway.

### Step 3: Add Environment Variables

The worker service needs the same environment variables as the web service:

1. **Go to Variables Tab**
   - Click **"Variables"** tab
   - Click **"+ New Variable"**

2. **Add Required Variables**
   - `DATABASE_URL` - Copy from web service
   - `REDIS_URL` - Copy from Redis service
   - `OPENAI_API_KEY` - Copy from web service
   - `SECRET_KEY` - Copy from web service
   - `ENCRYPTION_KEY` - Copy from web service
   - `GOOGLE_CREDENTIALS_JSON` - Copy from web service
   - `OAUTH_REDIRECT_URI` - Copy from web service
   - `AWS_LAMBDA_FUNCTION_NAME` - Copy from web service (if using Lambda)
   - `AWS_REGION` - Copy from web service (if using Lambda)
   - `AWS_ACCESS_KEY_ID` - Copy from web service (if using Lambda)
   - `AWS_SECRET_ACCESS_KEY` - Copy from web service (if using Lambda)

   **Tip**: Railway allows you to "Reference Variable" from another service. Use this to avoid duplicating values!

### Step 4: Reference Variables (Recommended)

Instead of copying values, you can reference them:

1. **Click "+ New Variable"**
2. **Click "Reference Variable"** (instead of typing)
3. **Select the source service** (your web service)
4. **Select the variable** (e.g., `DATABASE_URL`)
5. **Click "Add"**

This way, if you update a variable in the web service, the worker automatically gets the update!

### Step 5: Deploy

1. Railway will automatically deploy the worker service
2. Wait for deployment to complete (green checkmark)
3. Check logs to verify worker is running:
   ```
   ✅ Celery configured with broker: redis://...
   ```

---

## ✅ Verify It's Working

### Check 1: Railway Logs

1. Go to **worker service** → **"Logs"** tab
2. Look for:
   ```
   celery@hostname v5.3.4 (singularity)
   ```
3. Should see:
   ```
   [INFO/MainProcess] Connected to redis://...
   [INFO/MainProcess] celery@hostname ready.
   ```

### Check 2: Test in UI

1. Go to your app
2. Click **"Fetch Emails"**
3. Should see: **"Starting email sync..."** (instant response)
4. Should see progress updates
5. Should complete without "waiting for worker" timeout

---

## 🐛 Troubleshooting

### Issue: Worker service not starting

**Check:**
- Is the start command correct?
- Are all environment variables set?
- Check logs for errors

**Fix:**
- Verify start command matches exactly:
  ```
  celery -A celery_config worker --loglevel=info --concurrency=10 --queues=email_sync
  ```

### Issue: "No Celery workers available"

**Cause**: Worker service not running or can't connect to Redis

**Fix:**
1. Check worker service is running (green checkmark)
2. Check `REDIS_URL` is set correctly
3. Check worker logs for connection errors

### Issue: Tasks still stuck in PENDING

**Cause**: Worker can't connect to Redis or database

**Fix:**
1. Verify `REDIS_URL` is correct (should be from Redis service)
2. Verify `DATABASE_URL` is correct (should be from PostgreSQL service)
3. Check worker logs for connection errors

---

## 💰 Cost

**Additional Service:**
- Railway charges per service
- Worker service uses minimal resources (mostly idle)
- Estimated: ~$5-10/month for worker service

**Alternative**: If cost is a concern, the app will automatically fall back to the streaming endpoint when workers aren't available.

---

## 🎯 Summary

**What to do:**
1. ✅ Create new service from same repo
2. ✅ Set start command: `celery -A celery_config worker --loglevel=info --concurrency=10 --queues=email_sync`
3. ✅ Add/reference all environment variables
4. ✅ Wait for deployment
5. ✅ Test!

**That's it!** Your worker will now process background tasks. 🚀

