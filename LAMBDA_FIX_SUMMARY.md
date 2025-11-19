# Lambda Classification Fix Summary

## Problem
Lambda was returning `NotFound` and `ClientError` when trying to classify emails, causing the system to fall back to local OpenAI classification.

## Root Cause
The Lambda IAM role (`email-classifier-role`) was missing permission to access AWS Secrets Manager where the OpenAI API key is stored.

The role only had:
- `AWSLambdaBasicExecutionRole` (for CloudWatch Logs)

But it needed:
- Permission to call `secretsmanager:GetSecretValue` on the `openai-api-key` secret

## Solution
Added an inline policy to the Lambda IAM role:

```bash
aws iam put-role-policy \
  --role-name email-classifier-role \
  --policy-name SecretsManagerAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "secretsmanager:GetSecretValue"
        ],
        "Resource": "arn:aws:secretsmanager:us-east-1:913092306180:secret:openai-api-key*"
      }
    ]
  }'
```

## Verification
After adding the permission:
- ✅ Lambda successfully retrieves OpenAI API key from Secrets Manager
- ✅ Lambda calls OpenAI API (gpt-4o model)
- ✅ Classification returns correct results
- ✅ Encrypted results are returned to the client

## CloudWatch Logs (Successful Classification)
```
[INFO] {"event": "classification_request", "thread_id": "test-thread", "user_id": "test-user"}
[INFO] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
[INFO] {"event": "classification_result", "label": "general", "confidence": 0.8}
[INFO] Classification completed - Thread: test-thread
```

## Next Steps
**For Railway Deployment:**
You need to add these environment variables to Railway for Lambda to work in production:

1. Go to Railway → Your Project → Variables
2. Add:
   - `LAMBDA_FUNCTION_ARN=arn:aws:lambda:us-east-1:913092306180:function:email-classifier`
   - `AWS_REGION=us-east-1`
   - `AWS_ACCESS_KEY_ID=AKIA5JGEK4UCAODB34MK`
   - `AWS_SECRET_ACCESS_KEY=[your secret key]`

Without these, Railway will fall back to local OpenAI classification (which still works, but doesn't use the privacy-enhanced Lambda flow).

## Status
- ✅ Local development: Lambda working
- ⏳ Railway deployment: Needs AWS credentials added (see above)

