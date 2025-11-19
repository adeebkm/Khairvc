# Railway + AWS Lambda Deployment Guide

Complete guide to deploy email classification with **zero email content logging** using Railway + AWS Lambda.

## Architecture Overview

```
Railway App (Flask)
    ↓ (encrypted email)
AWS Lambda Function
    ↓ (no logging)
OpenAI API
    ↓ (encrypted result)
Railway App
```

**Security Features:**
- ✅ Email content encrypted before sending to Lambda
- ✅ OpenAI logging disabled in Lambda
- ✅ Only metadata logged (thread_id, user_id)
- ✅ OpenAI API key stored in AWS Secrets Manager
- ✅ Budget alerts configured

## Prerequisites

1. **AWS Account** (sign up at https://aws.amazon.com)
2. **Railway Account** (already deployed)
3. **OpenAI API Key**
4. **AWS CLI** installed and configured (`aws configure`)

## Step 1: Deploy AWS Lambda Function

### 1.1 Run Setup Script

```bash
cd aws_lambda
chmod +x setup_lambda.sh
./setup_lambda.sh
```

The script will:
- Create IAM role for Lambda
- Create Secrets Manager secret for OpenAI API key
- Deploy Lambda function
- Configure CloudWatch Logs (1-day retention)
- Set up AWS Budget

**Inputs required:**
- OpenAI API key
- Monthly budget limit (e.g., $50)
- Email for budget alerts

### 1.2 Get Lambda Function ARN

```bash
aws lambda get-function --function-name email-classifier --query 'Configuration.FunctionArn' --output text
```

Save this ARN - you'll need it for Railway.

**Example output:**
```
arn:aws:lambda:us-east-1:123456789012:function:email-classifier
```

## Step 2: Create IAM User for Railway

### 2.1 Run IAM Setup Script

```bash
cd aws_lambda
chmod +x setup_iam_user.sh
./setup_iam_user.sh
```

**Inputs required:**
- Lambda function ARN (or press Enter to auto-detect)

The script will:
- Create IAM user `railway-lambda-invoker`
- Create policy with only `lambda:InvokeFunction` permission
- Generate access key and secret key

**Save the credentials** - you'll add them to Railway.

## Step 3: Configure Railway

### 3.1 Add Environment Variables

Go to your Railway project → Variables tab → Add:

```
LAMBDA_FUNCTION_ARN=arn:aws:lambda:us-east-1:123456789012:function:email-classifier
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<from setup_iam_user.sh>
AWS_SECRET_ACCESS_KEY=<from setup_iam_user.sh>
```

**Important:** Use the credentials from `setup_iam_user.sh`, NOT your main AWS account credentials.

### 3.2 Install boto3 Dependency

Add `boto3` to `requirements.txt`:

```bash
echo "boto3>=1.28.0" >> requirements.txt
```

Railway will automatically install it on next deploy.

## Step 4: Test Deployment

### 4.1 Test Lambda Function Directly

```bash
# Test payload
cat > test_payload.json <<EOF
{
    "encrypted_email": "test",
    "encryption_key": "test",
    "user_encryption_key": "test",
    "thread_id": "test123",
    "user_id": "user456"
}
EOF

# Invoke Lambda
aws lambda invoke \
    --function-name email-classifier \
    --payload file://test_payload.json \
    response.json

cat response.json
```

### 4.2 Test from Railway

1. Deploy your Railway app
2. Connect Gmail
3. Fetch emails
4. Check Railway logs - should see "Lambda classification" messages

### 4.3 Verify No Email Content in Logs

```bash
# Check CloudWatch Logs (should only see metadata)
aws logs tail /aws/lambda/email-classifier --follow
```

You should see:
```
Classification request - Thread: xxx, User: yyy
Classification completed - Thread: xxx
```

**NOT:**
- Email content
- OpenAI requests/responses
- Classification results

## Step 5: Monitor Costs

### 5.1 Check AWS Budget

```bash
aws budgets describe-budgets --account-id $(aws sts get-caller-identity --query Account --output text)
```

### 5.2 View Costs in AWS Console

1. Go to AWS Cost Explorer
2. Filter by service: Lambda, CloudWatch, Secrets Manager
3. Set time period to current month

### 5.3 Set Up Additional Alerts

```bash
# Create SNS topic for alerts
aws sns create-topic --name lambda-cost-alerts

# Subscribe email
aws sns subscribe \
    --topic-arn <topic-arn> \
    --protocol email \
    --notification-endpoint your-email@example.com
```

## Troubleshooting

### Lambda Function Not Found

**Error:** `Function not found`

**Solution:**
```bash
# Verify function exists
aws lambda list-functions --query 'Functions[?FunctionName==`email-classifier`]'

# Check region matches
aws configure get region
```

### Access Denied

**Error:** `AccessDeniedException`

**Solution:**
1. Verify IAM user has `lambda:InvokeFunction` permission
2. Check Lambda function ARN matches Railway env var
3. Verify AWS credentials in Railway

### Secrets Manager Access Denied

**Error:** `Cannot retrieve secret`

**Solution:**
1. Check Lambda IAM role has `secretsmanager:GetSecretValue` permission
2. Verify secret name matches `OPENAI_SECRET_NAME` env var
3. Check secret exists: `aws secretsmanager describe-secret --secret-id openai-api-key`

### High Costs

**Symptoms:** Unexpected AWS charges

**Solution:**
1. Check CloudWatch Logs retention (should be 1 day)
2. Review Lambda invocations: `aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Invocations`
3. Check budget alerts are configured
4. Review Cost Explorer for unexpected services

### Classification Falls Back to OpenAI

**Symptoms:** Railway logs show "Lambda classification failed, falling back to OpenAI"

**Solution:**
1. Check Lambda function logs: `aws logs tail /aws/lambda/email-classifier`
2. Verify encryption keys match between Railway and Lambda
3. Test Lambda function directly (Step 4.1)
4. Check Lambda function timeout (should be 30 seconds)

## Security Checklist

- [ ] Lambda function has OpenAI logging disabled
- [ ] CloudWatch Logs retention set to 1 day
- [ ] IAM user has only `lambda:InvokeFunction` permission
- [ ] OpenAI API key stored in Secrets Manager (not in code)
- [ ] Email content encrypted before sending to Lambda
- [ ] Budget alerts configured
- [ ] Railway credentials are IAM user (not root account)

## Cost Optimization

### Current Setup (Optimized)

- **CloudWatch Logs**: 1-day retention (minimizes storage costs)
- **Lambda Memory**: 256MB (sufficient for classification)
- **Lambda Timeout**: 30 seconds (prevents long-running functions)
- **Budget Alerts**: Configured at 80% and 100%

### Estimated Monthly Costs

**With Free Tier:**
- Lambda: $0 (within free tier)
- Secrets Manager: $0 (within free tier)
- CloudWatch Logs: $0-2 (depends on volume)
- **Total: $0-2/month**

**Without Free Tier:**
- Lambda: $0-5 (depends on invocations)
- Secrets Manager: $0-1
- CloudWatch Logs: $1-5
- **Total: $2-10/month**

## Rollback Plan

If you need to rollback to direct OpenAI:

1. Remove Railway environment variables:
   ```
   LAMBDA_FUNCTION_ARN
   AWS_REGION
   AWS_ACCESS_KEY_ID
   AWS_SECRET_ACCESS_KEY
   ```

2. Redeploy Railway app

3. The app will automatically fall back to direct OpenAI calls

## Support

For issues:
1. Check CloudWatch Logs: `aws logs tail /aws/lambda/email-classifier`
2. Check Railway logs
3. Verify environment variables in Railway
4. Test Lambda function directly

## Next Steps

- [ ] Monitor costs for first week
- [ ] Adjust budget if needed
- [ ] Set up additional CloudWatch alarms
- [ ] Review Lambda function performance metrics

