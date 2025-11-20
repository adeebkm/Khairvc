# Test Environment Deployment Guide

This guide explains how to deploy changes to your **test environment** within the same Railway project while keeping production separate.

## Railway Environments Setup

Railway supports **environments** within the same project:
- **Production Environment** → `khair.up.railway.app`
- **Test Environment** → `web-aws-test.up.railway.app`

Both environments share the same project but have:
- ✅ Separate environment variables
- ✅ Separate databases (if configured)
- ✅ Separate Redis instances (if configured)
- ✅ Independent deployments

---

## Option 1: Branch-Based Deployment (Recommended)

### Setup

1. **Create a test branch:**
   ```bash
   git checkout -b test
   git push -u origin test
   ```

2. **Configure Railway Environments:**
   - Go to Railway → Your **Project**
   - Go to **Environments** tab
   - You should see: **Production** and **Test** (or create Test if needed)
   - For **Test Environment**:
     - Go to **Settings** → **Source**
     - Click **Connect Branch**
     - Select branch: `test`
   - For **Production Environment**:
     - Ensure it's connected to `main` branch

### Workflow

```bash
# Make changes locally
# ... edit files ...

# Commit to test branch
git checkout test
git add .
git commit -m "Test: your changes"
git push origin test

# Railway will automatically deploy to TEST environment only
# Production environment stays untouched
```

**Production stays safe** - only `main` branch deploys to production environment.

---

## Option 2: Manual Deployment (Same Branch)

### Setup

1. **Both environments connected to `main` branch**
2. **Manually trigger deployments** to test environment when needed

### Workflow

```bash
# Make changes locally
# ... edit files ...

# Commit to main
git add .
git commit -m "Your changes"
git push origin main

# Production environment auto-deploys
# Test environment does NOT auto-deploy

# When ready to test:
# Go to Railway → Project → Test Environment → Deployments
# Click "Redeploy" on latest commit
```

---

## Recommended Setup: Branch-Based with Environments

### Step-by-Step

1. **Create test branch:**
   ```bash
   git checkout -b test
   git push -u origin test
   ```

2. **Configure Railway Test Environment:**
   - Railway Dashboard → Your **Project**
   - **Environments** → **Test** (or create it)
   - **Settings** → **Source**
   - **Connect Branch** → Select `test` branch
   - Railway will auto-deploy on every push to `test`

3. **Configure Railway Production Environment:**
   - Railway Dashboard → Your **Project**
   - **Environments** → **Production**
   - **Settings** → **Source**
   - Ensure it's connected to `main` branch

### Daily Workflow

```bash
# Work on test branch
git checkout test
# ... make changes ...
git add .
git commit -m "Test: feature X"
git push origin test
# → Auto-deploys to TEST environment only

# Test at: https://web-aws-test.up.railway.app

# When ready for production:
git checkout main
git merge test
git push origin main
# → Auto-deploys to PRODUCTION environment
```

---

## Environment Variables

### Test Environment Variables
- Go to Railway → Project → **Test Environment** → **Variables**
- Add variables from `RAILWAY_TEST_ENV_VARS.json`
- Uses test Lambda: `email-classifier-test`
- Uses test domain: `web-aws-test.up.railway.app`

### Production Environment Variables
- Go to Railway → Project → **Production Environment** → **Variables**
- Uses production Lambda: `email-classifier`
- Uses production domain: `khair.up.railway.app`

**Important:** Each environment has its own variables. They don't share variables automatically.

---

## Quick Commands

### Deploy to Test Environment Only
```bash
git checkout test
git add .
git commit -m "Test: your message"
git push origin test
# → Auto-deploys to Test environment
```

### Deploy to Production Environment
```bash
git checkout main
git merge test  # or cherry-pick commits
git push origin main
# → Auto-deploys to Production environment
```

### Check Current Branch
```bash
git branch
```

### Switch Between Branches
```bash
git checkout test    # Switch to test
git checkout main     # Switch to production
```

---

## Railway Environment Management

### View Environments
- Railway Dashboard → Your Project → **Environments** tab
- You'll see: Production, Test (and any preview environments)

### Environment-Specific Settings
- Each environment has its own:
  - Variables
  - Deployments
  - Logs
  - Services (web, worker, database, redis)

### Services in Environments
- **Production Environment:**
  - `web` service → Production variables
  - `worker` service → Production variables
  - `Postgres-FN-L` → Production database
  - `Redis` → Production Redis

- **Test Environment:**
  - `web` service → Test variables (from `RAILWAY_TEST_ENV_VARS.json`)
  - `worker` service → Test variables (from `RAILWAY_TEST_WORKER_ENV_VARS.json`)
  - `Postgres-TEST` → Test database (create if needed)
  - `Redis-TEST` → Test Redis (create if needed)

---

## Troubleshooting

### Test environment not deploying?
1. Check Railway → Project → Test Environment → Settings → Source
2. Verify branch is connected to `test`
3. Check deployment logs in Test environment

### Want to test production code in test environment?
```bash
git checkout main
git push origin main
# Then manually redeploy Test environment from Railway dashboard
```

### Accidentally pushed to wrong branch?
```bash
# Undo last commit (keeps changes)
git reset --soft HEAD~1

# Switch to correct branch
git checkout test
git add .
git commit -m "Your message"
git push origin test
```

---

## Best Practices

1. ✅ **Always test on test branch first**
2. ✅ **Merge to main only after testing**
3. ✅ **Use descriptive commit messages** (`Test:`, `Fix:`, `Feature:`)
4. ✅ **Keep test and production environments separate**
5. ✅ **Test Lambda changes separately** (use `update_lambda_test.sh`)
6. ✅ **Use environment-specific variables** (don't share between environments)

---

## Current Setup Summary

- **Project:** Same Railway project
- **Production Environment:** `main` branch → `khair.up.railway.app`
- **Test Environment:** `test` branch → `web-aws-test.up.railway.app`
- **Production Lambda:** `email-classifier`
- **Test Lambda:** `email-classifier-test`

