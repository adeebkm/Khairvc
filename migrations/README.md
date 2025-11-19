# Security Migrations: RLS + Field Encryption

This directory contains migrations for implementing Priority 1 (Row-Level Security) and Priority 2 (Field Encryption).

## What These Migrations Do

### Priority 1: Row-Level Security (RLS)
- **Database-level security** that enforces user isolation at the PostgreSQL level
- Even if application code is bypassed, users can only see their own data
- Protects against SQL injection, bugs, and direct database access

### Priority 2: Field Encryption
- **Encrypts sensitive fields** (subject, snippet) at rest in the database
- Uses Fernet encryption (AES-128 + HMAC)
- Transparent encryption/decryption via model methods

## Running the Migration

### Local Development (SQLite)
```bash
# SQLite doesn't support RLS, but encryption columns will be added
python migrations/add_rls_and_encryption.py
```

### Production (PostgreSQL on Railway)
```bash
# Option 1: Via Railway CLI
railway run python migrations/add_rls_and_encryption.py

# Option 2: Connect to database directly
# Get DATABASE_URL from Railway dashboard
export DATABASE_URL="postgresql://..."
python migrations/add_rls_and_encryption.py
```

## What Gets Changed

### Database Schema
1. **New columns added:**
   - `email_classifications.subject_encrypted` (TEXT)
   - `email_classifications.snippet_encrypted` (TEXT)

2. **RLS enabled (PostgreSQL only):**
   - Row-Level Security enabled on `email_classifications` table
   - Policy created: `user_isolation` (filters by `user_id`)

3. **Helper function created:**
   - `set_user_context(user_id)` - Sets user context for RLS

### Application Code
1. **Models (`models.py`):**
   - Added `set_subject_encrypted()` and `get_subject_decrypted()` methods
   - Added `set_snippet_encrypted()` and `get_snippet_decrypted()` methods

2. **App (`app.py`):**
   - Added `@app.before_request` handler to set user context for RLS
   - Updated all `EmailClassification` creation to use encrypted setters
   - Updated all subject/snippet reads to use decrypted getters

## Backward Compatibility

- **Legacy fields kept:** `subject` and `snippet` columns remain for backward compatibility
- **Automatic fallback:** If decryption fails, falls back to legacy plain text fields
- **Gradual migration:** Existing data is copied to encrypted fields (will be encrypted on next write)

## Security Benefits

### Before Migration
- ❌ Application-level filtering only
- ❌ Plain text subjects/snippets in database
- ❌ Vulnerable to SQL injection
- ❌ Direct DB access exposes all data

### After Migration
- ✅ Database-level filtering (RLS)
- ✅ Encrypted subjects/snippets in database
- ✅ Protected against SQL injection
- ✅ Direct DB access still filtered by user

## Troubleshooting

### "RLS context not set" warnings
- **Normal for SQLite:** RLS is PostgreSQL-only
- **Normal before migration:** RLS not enabled yet
- **After migration:** Should work automatically

### "Decryption failed" errors
- **Check ENCRYPTION_KEY:** Must match the key used for encryption
- **Legacy data:** Old plain text data will fall back automatically
- **New data:** Will be encrypted automatically

## Next Steps

1. **Run migration** on production database
2. **Test thoroughly** with multiple users
3. **Monitor logs** for any RLS or encryption errors
4. **Remove legacy fields** (optional, after confirming everything works)

