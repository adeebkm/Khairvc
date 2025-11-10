# 🚀 Exact Deployment Steps - Step by Step

## Step 1: Prepare Your Code Locally

### 1.1 Generate Keys (Do this first!)
```bash
cd "/Users/adeebkhaja/Documents/gmail openai"
python setup_railway.py
```

**Copy the output** - you'll need these values for Railway:
- `SECRET_KEY`
- `ENCRYPTION_KEY`
- `GOOGLE_CREDENTIALS_JSON`

### 1.2 Initialize Git (if not already done)
```bash
git init
git add .
git commit -m "Initial commit - ready for Railway"
```

**Verify .env is NOT in the commit:**
```bash
git status
# Make sure .env, credentials.json, *.db are NOT listed
```

## Step 2: Push to GitHub

### 2.1 Create GitHub Repository
1. Go to https://github.com
2. Click **"New repository"** (or the **+** icon)
3. Name it (e.g., `gmail-auto-reply` or `khair-email-replier`)
4. **Don't** initialize with README (you already have files)
5. Click **"Create repository"**

### 2.2 Push Your Code
```bash
# Add GitHub remote (replace YOUR_USERNAME and REPO_NAME)
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# Push to GitHub
git branch -M main
git push -u origin main
```

**Verify on GitHub:**
- Go to your repo on GitHub
- Check that `.env` is NOT visible (it should be ignored)
- Check that `credentials.json` is NOT visible

## Step 3: Create Railway Account & Deploy

### 3.1 Sign Up for Railway
1. Go to https://railway.app
2. Click **"Start a New Project"** or **"Login"**
3. Sign up with GitHub (recommended - easier integration)
4. Authorize Railway to access your GitHub

### 3.2 Create New Project
1. In Railway dashboard, click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Choose your repository (`gmail-auto-reply` or whatever you named it)
4. Railway will start deploying automatically

### 3.3 Add PostgreSQL Database
1. In your Railway project, click **"+ New"**
2. Select **"Database"** → **"Add PostgreSQL"**
3. Railway automatically creates the database
4. **Note**: `DATABASE_URL` is automatically set (don't add it manually)

### 3.4 Set Environment Variables
1. Click on your **service** (the web service, not the database)
2. Go to **"Variables"** tab
3. Click **"+ New Variable"** and add each:

```
OPENAI_API_KEY=sk-your-actual-key-here
SEND_EMAILS=false
MAX_EMAILS=20
SECRET_KEY=<paste from setup_railway.py>
ENCRYPTION_KEY=<paste from setup_railway.py>
GOOGLE_CREDENTIALS_JSON=<paste from setup_railway.py>
```

**Important**: 
- Get your Railway domain first (see next step)
- Then add `OAUTH_REDIRECT_URI`

### 3.5 Get Your Railway Domain
1. In your service, go to **"Settings"** tab
2. Scroll to **"Domains"** section
3. You'll see a domain like: `your-app-production.up.railway.app`
4. Or click **"Generate Domain"** to get a custom one
5. **Copy this domain** - you'll need it

### 3.6 Add OAuth Redirect URI
1. Still in **"Variables"** tab
2. Add: `OAUTH_REDIRECT_URI`
3. Value: `https://your-app-production.up.railway.app/oauth2callback`
   (Replace with your actual Railway domain)

### 3.7 Update Google Cloud Console
1. Go to https://console.cloud.google.com
2. **APIs & Services** → **Credentials**
3. Click on your **OAuth 2.0 Client ID**
4. Under **"Authorized redirect URIs"**, click **"+ ADD URI"**
5. Add: `https://your-app-production.up.railway.app/oauth2callback`
6. Click **"SAVE"**

### 3.8 Wait for Deployment
1. Go to **"Deployments"** tab in Railway
2. Watch the build logs
3. Wait for "Deploy successful" ✅

### 3.9 Test Your App
1. Click on your Railway domain (or use the link in Settings → Domains)
2. Your app should load!
3. Create an account
4. Connect Gmail
5. Test email fetching

## 📋 Quick Checklist

**Before GitHub:**
- [ ] Generated keys with `setup_railway.py`
- [ ] Initialized git
- [ ] Verified `.env` is NOT in git status
- [ ] Committed code

**GitHub:**
- [ ] Created GitHub repository
- [ ] Pushed code to GitHub
- [ ] Verified sensitive files are NOT on GitHub

**Railway:**
- [ ] Created Railway account
- [ ] Created new project from GitHub
- [ ] Added PostgreSQL database
- [ ] Set all environment variables
- [ ] Got Railway domain
- [ ] Set `OAUTH_REDIRECT_URI`
- [ ] Updated Google Cloud Console
- [ ] Deployment successful
- [ ] App is accessible

## 🎯 Recommended Order

**Best order:**
1. ✅ Generate keys locally (`setup_railway.py`)
2. ✅ Push to GitHub first
3. ✅ Then create Railway account
4. ✅ Deploy from GitHub
5. ✅ Configure environment variables
6. ✅ Update Google Cloud Console

**Why this order?**
- GitHub first = You have a backup of your code
- Railway can easily connect to GitHub
- You can verify sensitive files aren't on GitHub before deploying

## 🆘 Common Issues

**"credentials.json not found" error:**
- Make sure `GOOGLE_CREDENTIALS_JSON` is set in Railway
- Use the output from `setup_railway.py`

**OAuth not working:**
- Verify `OAUTH_REDIRECT_URI` matches your Railway domain
- Check Google Cloud Console has the redirect URI added

**Database connection error:**
- Railway automatically provides `DATABASE_URL`
- Don't add it manually - it's already there

## 📞 Need Help?

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- Check deployment logs in Railway dashboard

