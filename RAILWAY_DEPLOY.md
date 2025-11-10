# Railway Deployment Guide

This guide will help you deploy your Gmail Auto-Reply application to Railway with PostgreSQL database.

## Prerequisites

1. A Railway account (sign up at https://railway.app)
2. GitHub account (for connecting your repository)
3. Google Cloud Console project with Gmail API enabled
4. OpenAI API key

## Step 1: Prepare Your Repository

1. Make sure all files are committed to Git:
```bash
git add .
git commit -m "Prepare for Railway deployment"
```

2. Push to GitHub (if not already):
```bash
git remote add origin <your-github-repo-url>
git push -u origin main
```

## Step 2: Deploy to Railway

1. **Go to Railway Dashboard**: https://railway.app/dashboard

2. **Create New Project**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository

3. **Add PostgreSQL Database**:
   - In your project, click "+ New"
   - Select "Database" → "Add PostgreSQL"
   - Railway will automatically create a PostgreSQL database

4. **Configure Environment Variables**:
   - Go to your service → "Variables" tab
   - Add the following environment variables:

   ```
   OPENAI_API_KEY=your_openai_api_key
   SEND_EMAILS=false
   MAX_EMAILS=20
   SECRET_KEY=generate-a-random-secret-key-here
   ENCRYPTION_KEY=generate-a-32-byte-encryption-key
   ```

   **Important**: 
   - `DATABASE_URL` is automatically provided by Railway (don't add it manually)
   - Generate `SECRET_KEY`: Use a long random string
   - Generate `ENCRYPTION_KEY`: Run this Python command:
     ```python
     from cryptography.fernet import Fernet
     print(Fernet.generate_key().decode())
     ```

5. **Add Google OAuth Credentials**:
   - Convert your `credentials.json` to a single-line JSON string or base64:
     ```bash
     # Option 1: Single-line JSON (recommended)
     cat credentials.json | jq -c
     
     # Option 2: Base64 encoded
     base64 -i credentials.json
     ```
   - Add as environment variable `GOOGLE_CREDENTIALS_JSON` in Railway
   - The app will automatically detect and use it

## Step 3: Update OAuth Redirect URIs

1. **Get your Railway domain**:
   - After deployment, Railway will provide a URL like: `https://your-app.railway.app`
   - Go to your service → "Settings" → "Domains" to see your URL

2. **Update Google Cloud Console**:
   - Go to https://console.cloud.google.com
   - Navigate to "APIs & Services" → "Credentials"
   - Edit your OAuth 2.0 Client ID
   - Add authorized redirect URIs:
     - `https://your-app.railway.app/oauth2callback`
   - Save changes
   
3. **Set OAuth Redirect URI in Railway**:
   - Add environment variable: `OAUTH_REDIRECT_URI`
   - Value: `https://your-app.railway.app/oauth2callback`
   - Replace `your-app.railway.app` with your actual Railway domain

## Step 4: Deploy

1. Railway will automatically detect your `Procfile` and deploy
2. Check the "Deployments" tab to see build logs
3. Once deployed, your app will be available at your Railway domain

## Step 5: Initialize Database

The database will be automatically created on first run. However, if you need to manually initialize:

1. Go to Railway dashboard → Your service → "Postgres" database
2. Click "Connect" to get connection details
3. Or use Railway CLI:
   ```bash
   railway run python
   >>> from app import app, db
   >>> with app.app_context():
   ...     db.create_all()
   ```

## Step 6: Test Your Deployment

1. Visit your Railway URL
2. Create an account
3. Connect your Gmail account
4. Test email fetching and classification

## Environment Variables Reference

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key | Yes | - |
| `SEND_EMAILS` | Enable email sending | No | `false` |
| `MAX_EMAILS` | Max emails per fetch | No | `20` |
| `SECRET_KEY` | Flask session secret | Yes | - |
| `ENCRYPTION_KEY` | Token encryption key | Yes | - |
| `DATABASE_URL` | PostgreSQL connection (auto) | Yes | Auto-provided |
| `GOOGLE_CREDENTIALS_JSON` | Google OAuth credentials (JSON string or base64) | Yes | - |
| `OAUTH_REDIRECT_URI` | OAuth callback URL (e.g., https://your-app.railway.app/oauth2callback) | Yes (for production) | - |

## Troubleshooting

### Database Connection Issues
- Check that PostgreSQL service is running
- Verify `DATABASE_URL` is set (Railway sets this automatically)
- Check build logs for connection errors

### OAuth Issues
- Verify redirect URIs are correct in Google Cloud Console
- Check that `credentials.json` is accessible
- Review Railway logs for OAuth errors

### Build Failures
- Check `requirements.txt` is up to date
- Verify Python version (Railway uses Python 3.9+)
- Check build logs for specific errors

## Custom Domain (Optional)

1. Go to your service → "Settings" → "Domains"
2. Click "Custom Domain"
3. Add your domain and follow DNS setup instructions

## Monitoring

- View logs: Railway dashboard → Your service → "Deployments" → Click on deployment → "View Logs"
- Monitor database: Railway dashboard → PostgreSQL service → "Metrics"

## Backup Database

Railway PostgreSQL has automatic backups, but you can also:

1. Use Railway CLI to export:
   ```bash
   railway connect postgres
   pg_dump > backup.sql
   ```

2. Or use Railway's built-in backup feature in the database service

## Support

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway

