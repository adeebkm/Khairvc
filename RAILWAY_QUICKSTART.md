# Railway Quick Start Guide

## 🚀 Quick Deployment Steps

### 1. Prepare Your Code

```bash
# Make sure everything is committed
git add .
git commit -m "Ready for Railway deployment"
git push
```

### 2. Generate Required Keys

Run the setup helper:
```bash
python setup_railway.py
```

This will generate:
- `SECRET_KEY` - For Flask sessions
- `ENCRYPTION_KEY` - For encrypting Gmail tokens
- `GOOGLE_CREDENTIALS_JSON` - Formatted credentials for Railway

### 3. Deploy to Railway

1. **Go to Railway**: https://railway.app
2. **New Project** → **Deploy from GitHub repo**
3. **Select your repository**

### 4. Add PostgreSQL Database

1. In your Railway project, click **"+ New"**
2. Select **"Database"** → **"Add PostgreSQL"**
3. Railway automatically provides `DATABASE_URL` (don't add it manually)

### 5. Set Environment Variables

Go to your service → **"Variables"** tab and add:

```
OPENAI_API_KEY=sk-your-key-here
SEND_EMAILS=false
MAX_EMAILS=20
SECRET_KEY=<from setup_railway.py>
ENCRYPTION_KEY=<from setup_railway.py>
GOOGLE_CREDENTIALS_JSON=<from setup_railway.py>
OAUTH_REDIRECT_URI=https://your-app.railway.app/oauth2callback
```

**Important**: Replace `your-app.railway.app` with your actual Railway domain (get it from Settings → Domains)

### 6. Update Google Cloud Console

1. Go to https://console.cloud.google.com
2. **APIs & Services** → **Credentials**
3. Edit your OAuth 2.0 Client ID
4. Add **Authorized redirect URI**:
   - `https://your-app.railway.app/oauth2callback`
5. Save

### 7. Deploy!

Railway will automatically:
- Detect your `Procfile`
- Install dependencies from `requirements.txt`
- Use PostgreSQL database
- Deploy your app

### 8. Test

1. Visit your Railway URL
2. Create an account
3. Connect Gmail
4. Test email fetching

## 📋 Checklist

- [ ] Code pushed to GitHub
- [ ] PostgreSQL database added in Railway
- [ ] All environment variables set
- [ ] Google Cloud Console redirect URI updated
- [ ] Railway deployment successful
- [ ] App accessible at Railway URL
- [ ] Gmail connection works
- [ ] Email fetching works

## 🔧 Troubleshooting

**Build fails?**
- Check build logs in Railway dashboard
- Verify `requirements.txt` is correct
- Check Python version (should be 3.11)

**Database connection error?**
- Verify PostgreSQL service is running
- Check `DATABASE_URL` is set (Railway sets this automatically)

**OAuth not working?**
- Verify `GOOGLE_CREDENTIALS_JSON` is set correctly
- Check `OAUTH_REDIRECT_URI` matches your Railway domain
- Verify redirect URI is added in Google Cloud Console

**App crashes?**
- Check logs in Railway dashboard
- Verify all environment variables are set
- Check that `SECRET_KEY` and `ENCRYPTION_KEY` are valid

## 📚 Full Documentation

See `RAILWAY_DEPLOY.md` for detailed instructions.

