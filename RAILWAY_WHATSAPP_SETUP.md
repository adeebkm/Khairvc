# WhatsApp Integration Setup for Railway

This guide covers setting up WhatsApp Business Cloud API integration on Railway.

## Step 1: Add Environment Variables in Railway

Go to your Railway project → **Variables** tab and add:

```bash
# WhatsApp Meta API Configuration
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here
WHATSAPP_ACCESS_TOKEN=your_access_token_here
WHATSAPP_VERIFY_TOKEN=your_secure_verify_token_here
WHATSAPP_API_VERSION=v21.0
```

**Where to get these values:**
- `WHATSAPP_PHONE_NUMBER_ID`: From Meta App Dashboard → WhatsApp → API Setup
- `WHATSAPP_ACCESS_TOKEN`: From Meta App Dashboard → WhatsApp → API Setup (generate token)
- `WHATSAPP_VERIFY_TOKEN`: Create a random secure string (e.g., `your_random_token_12345`)
- `WHATSAPP_API_VERSION`: Usually `v21.0` (check Meta docs for latest)

## Step 2: Update Procfile for Celery Beat

You need to add a Celery Beat service to run follow-up tasks. Update your `Procfile`:

```procfile
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 300 --worker-class sync --threads 2
worker: celery -A celery_config worker --loglevel=info --concurrency=10
beat: celery -A celery_config beat --loglevel=info
```

**Note:** Railway will create 3 services:
1. **web** - Your Flask app
2. **worker** - Celery worker for background tasks
3. **beat** - Celery Beat scheduler for periodic tasks (follow-ups)

## Step 3: Run Database Migration

After deploying, you need to run the migration. You have two options:

### Option A: One-time Migration Script (Recommended)

Create a one-time migration service in Railway:

1. In Railway, add a new service
2. Set the command to: `python migrations/add_whatsapp_fields.py`
3. Run it once, then you can delete the service

### Option B: Run via Railway CLI

```bash
railway run python migrations/add_whatsapp_fields.py
```

### Option C: Add to App Startup (Auto-migration)

Add this to `app.py` in the database initialization section (around line 200):

```python
# Auto-run WhatsApp migration on startup (only if columns don't exist)
try:
    with app.app_context():
        from sqlalchemy import text
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name = 'whatsapp_number'
        """))
        if not result.fetchone():
            print("🔄 Running WhatsApp migration...")
            from migrations.add_whatsapp_fields import run_migration
            run_migration()
            print("✅ WhatsApp migration completed")
except Exception as e:
    print(f"⚠️  WhatsApp migration check failed: {e}")
```

## Step 4: Configure Webhook in Meta Dashboard

1. Go to Meta App Dashboard → WhatsApp → Configuration
2. Under **Webhook**, click **Edit**
3. Set **Callback URL**: `https://your-railway-domain.up.railway.app/webhook/whatsapp`
   - Replace `your-railway-domain` with your actual Railway domain
   - You can find your domain in Railway → Settings → Domains
4. Set **Verify Token**: Same value as `WHATSAPP_VERIFY_TOKEN` in Railway
5. Subscribe to **messages** field
6. Click **Verify and Save**

**Important:** Railway domain must be publicly accessible (not localhost)

## Step 5: Deploy to Railway

1. Commit all changes:
   ```bash
   git add .
   git commit -m "Add WhatsApp integration"
   git push
   ```

2. Railway will automatically:
   - Build your app
   - Start web service
   - Start worker service
   - Start beat service (if added to Procfile)

## Step 6: Verify Services Are Running

In Railway dashboard, check that all 3 services are running:
- ✅ **web** - Status: Running
- ✅ **worker** - Status: Running  
- ✅ **beat** - Status: Running

## Step 7: Test Webhook

1. In Meta Dashboard → WhatsApp → Configuration
2. Click **Test** next to your webhook
3. Meta will send a test message
4. Check Railway logs to see if webhook received it

## Step 8: Test WhatsApp Integration

1. Create a test deal flow email
2. Check Railway logs for:
   - `✅ [TASK] WhatsApp alert sent for deal X`
3. Check your WhatsApp for the alert message
4. Wait 6 hours (or manually trigger follow-up) to test follow-ups

## Railway-Specific Considerations

### Service Limits
- Railway free tier: Limited resources
- Consider upgrading if you have many users
- Monitor service usage in Railway dashboard

### Logs
- Check logs in Railway → Deployments → [Latest] → Logs
- Look for WhatsApp-related messages:
  - `📱 [WHATSAPP]` - Follow-up task logs
  - `✅ [TASK] WhatsApp alert sent` - Alert confirmation
  - `❌ WhatsApp` - Error messages

### Environment Variables
- All WhatsApp variables must be set in Railway
- Don't commit tokens to git
- Use Railway's Variables tab for secrets

### Celery Beat on Railway
- Beat service runs continuously
- It checks every 30 minutes for deals needing follow-ups
- If beat service stops, follow-ups won't work (but alerts still will)

## Troubleshooting

### Webhook verification fails
- Check Railway domain is accessible: `curl https://your-domain.up.railway.app/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=test`
- Verify `WHATSAPP_VERIFY_TOKEN` matches Meta dashboard
- Check Railway logs for webhook errors

### Messages not sending
- Verify all environment variables are set correctly
- Check Railway logs for API errors
- Verify phone number is verified in Meta Business Manager

### Follow-ups not working
- Check that `beat` service is running in Railway
- Check Railway logs for beat service errors
- Verify deals have `whatsapp_alert_sent = True` in database

### Migration fails
- Check database connection in Railway
- Verify PostgreSQL service is running
- Check migration script logs in Railway

## Cost on Railway

- **WhatsApp API**: FREE (up to 1,000 conversations/month)
- **Railway**: Depends on your plan
  - Free tier: Limited hours
  - Hobby: $5/month
  - Pro: $20/month

## Security Best Practices

1. ✅ Never commit access tokens to git
2. ✅ Use Railway Variables for all secrets
3. ✅ Rotate access tokens periodically
4. ✅ Use permanent tokens (not temporary) for production
5. ✅ Enable 2FA on Meta Business Account
6. ✅ Monitor Railway logs for suspicious activity

## Next Steps

After setup is complete:
1. Test with a real deal flow email
2. Verify alerts are sent
3. Wait 6 hours and verify follow-ups work
4. Add UI for users to configure WhatsApp settings
5. Monitor usage and costs

