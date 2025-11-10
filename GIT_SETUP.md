# Git Setup - Protecting Sensitive Files

## ✅ What's Already Protected

Your `.gitignore` file already excludes:
- ✅ `.env` - Environment variables
- ✅ `credentials.json` - Google OAuth credentials
- ✅ `token.json` - Gmail tokens
- ✅ `*.db` - Database files
- ✅ `instance/` - Database instance folder

## 🔒 Before Pushing to GitHub

### 1. Initialize Git (if not already done)
```bash
cd "/Users/adeebkhaja/Documents/gmail openai"
git init
```

### 2. Verify .env is Ignored
```bash
# Check if .env is ignored
git check-ignore .env
# Should output: .env

# Check what will be committed
git status
# .env should NOT appear in the list
```

### 3. If .env Was Already Committed (Remove It)
If `.env` was accidentally committed before, remove it from git (but keep the file):
```bash
# Remove from git tracking (keeps the file locally)
git rm --cached .env

# Commit the removal
git commit -m "Remove .env from git tracking"
```

### 4. Safe Files to Commit
These files are safe to commit:
- ✅ `app.py`
- ✅ `requirements.txt`
- ✅ `Procfile`
- ✅ `railway.json`
- ✅ `runtime.txt`
- ✅ `.gitignore`
- ✅ `templates/`
- ✅ `static/`
- ✅ `*.md` files
- ✅ `.env.example` (template, no secrets)

### 5. Never Commit These
- ❌ `.env` (contains secrets)
- ❌ `credentials.json` (OAuth credentials)
- ❌ `token.json` (user tokens)
- ❌ `*.db` (database files)
- ❌ `instance/` (database folder)

## 🧪 Test Before Pushing

```bash
# See what will be committed
git status

# Make sure .env is NOT listed
# If it is, it's already tracked - remove it with:
git rm --cached .env
```

## ✅ Quick Checklist

Before pushing to GitHub:
- [ ] `.env` is in `.gitignore` ✅
- [ ] `credentials.json` is in `.gitignore` ✅
- [ ] `*.db` files are in `.gitignore` ✅
- [ ] `git status` shows no sensitive files
- [ ] Only code and config files are staged

## 🚨 If You Already Pushed .env

If you accidentally pushed `.env` to GitHub:

1. **Remove it from git**:
   ```bash
   git rm --cached .env
   git commit -m "Remove .env from repository"
   git push
   ```

2. **Rotate your secrets**:
   - Generate new `SECRET_KEY`
   - Generate new `ENCRYPTION_KEY`
   - Update in Railway environment variables

3. **GitHub**: The file will still be in git history, but at least it won't be in future commits.

## 📝 Current .gitignore Status

Your `.gitignore` currently protects:
- `.env` and `.env.*` files
- `credentials.json`
- `token.json`
- All database files (`*.db`, `*.sqlite`, etc.)
- `instance/` folder
- Backup folders

**You're all set!** Your sensitive files are protected. ✅

