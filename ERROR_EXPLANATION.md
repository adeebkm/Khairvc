# Error Explanation

## Summary of Errors in Logs

### 1. Duplicate Key Errors (Expected & Handled)

**Error Message:**
```
ERROR: duplicate key value violates unique constraint "uq_user_message"
DETAIL: Key (user_id, message_id)=(25, 19aa6f289b53417d) already exists.
```

**What's Happening:**
- Multiple Celery workers are processing the same email simultaneously
- Race condition: Both workers check if email exists (line 235-238 in `tasks.py`), both find it doesn't exist, then both try to insert
- PostgreSQL enforces the unique constraint `uq_user_message` on `(user_id, message_id)`
- The first insert succeeds, the second fails with this error

**Why It's Logged:**
- PostgreSQL logs the error **before** the exception is caught by Python
- The code **does handle it gracefully** (lines 301-305 in `tasks.py`):
  ```python
  elif 'UniqueViolation' in error_str or 'duplicate key' in error_str.lower() or 'uq_user_message' in error_str:
      db.session.rollback()
      print(f"⏭️  Email {email.get('id', '')} was inserted by another process, skipping...")
      duplicate_detected = True
      break
  ```

**Impact:**
- ✅ **No data corruption** - one insert succeeds, the other is skipped
- ✅ **No functional issues** - emails are still processed correctly
- ⚠️ **Noisy logs** - PostgreSQL error appears before Python catches it

**Is This a Problem?**
- **No** - This is expected behavior in a multi-worker environment
- The unique constraint is working as designed to prevent duplicates
- The code handles it correctly

**Potential Improvements (Optional):**
1. Use database-level `INSERT ... ON CONFLICT DO NOTHING` (PostgreSQL-specific)
2. Use row-level locking (`SELECT FOR UPDATE`) before insert
3. Suppress PostgreSQL error logs for this specific constraint (not recommended)

---

### 2. AccessDeniedException for Secrets Manager (Needs Fix)

**Error Message:**
```
AccessDeniedException: User is not authorized to perform: secretsmanager:GetSecretValue
```

**What's Happening:**
- AWS Lambda function is trying to retrieve the OpenAI/Moonshot API key from AWS Secrets Manager
- The Lambda execution role doesn't have permission to read the secret

**Root Cause:**
- IAM role policy might be missing or incorrectly scoped
- Secret name might not match the policy resource pattern
- Lambda role might not be attached correctly

**How to Fix:**

1. **Check Lambda Role Permissions:**
   ```bash
   # Get the Lambda function's role
   aws lambda get-function --function-name email-classifier --query 'Configuration.Role' --output text
   
   # Check the role's policies
   aws iam list-role-policies --role-name <role-name>
   aws iam get-role-policy --role-name <role-name> --policy-name SecretsManagerAccess
   ```

2. **Verify Secret Name:**
   - Check the `OPENAI_SECRET_NAME` environment variable in Lambda
   - Ensure it matches the actual secret name in Secrets Manager

3. **Update IAM Policy:**
   The policy should allow access to the secret. Example:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": [
         "secretsmanager:GetSecretValue",
         "secretsmanager:DescribeSecret"
       ],
       "Resource": "arn:aws:secretsmanager:*:*:secret:openai-api-key*"
     }]
   }
   ```
   
   **Important:** Replace `openai-api-key*` with your actual secret name pattern

4. **Re-run Setup Script:**
   ```bash
   cd aws_lambda
   ./setup_lambda.sh
   ```

**Impact:**
- ❌ **Classification fails** - Falls back to OpenAI (if available) or errors
- ❌ **Increased costs** - May use more expensive OpenAI API instead of Lambda
- ⚠️ **Functionality degraded** - Email classification may not work optimally

---

## Recommendations

### For Duplicate Key Errors:
- **Action:** No action needed - these are expected and handled
- **Optional:** Consider using `INSERT ... ON CONFLICT DO NOTHING` for cleaner handling

### For AccessDeniedException:
- **Action:** Fix IAM permissions immediately
- **Priority:** High - affects functionality
- **Steps:** Follow the fix instructions above

---

## Additional Notes

### Why Multiple Workers?
- Celery workers run in parallel to process emails faster
- This is intentional for performance
- The unique constraint prevents data corruption from race conditions

### Why PostgreSQL Logs Errors?
- PostgreSQL logs all constraint violations at the database level
- Python catches the exception after PostgreSQL logs it
- This is normal database behavior - the error is handled correctly

### Monitoring
- Monitor the "⏭️ Email was inserted by another process" messages
- If this happens frequently, consider:
  - Reducing number of workers (if not needed)
  - Using database-level conflict resolution
  - Adding more sophisticated locking mechanisms

