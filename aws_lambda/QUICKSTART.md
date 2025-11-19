# Quick Start: Railway + Lambda Setup

## 🚀 5-Minute Setup

### Step 1: Deploy Lambda Function

```bash
cd aws_lambda
chmod +x setup_lambda.sh
./setup_lambda.sh
```

**Inputs:**
- OpenAI API key
- Budget limit (e.g., $50)
- Alert email

**Output:** Lambda function ARN (save this!)

### Step 2: Create IAM User for Railway

```bash
chmod +x setup_iam_user.sh
./setup_iam_user.sh
```

**Input:** Lambda ARN (or press Enter to auto-detect)

**Output:** AWS credentials (save these!)

### Step 3: Add to Railway

Go to Railway → Variables → Add:

```
LAMBDA_FUNCTION_ARN=<from step 1>
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<from step 2>
AWS_SECRET_ACCESS_KEY=<from step 2>
```

### Step 4: Deploy

Railway will automatically:
- Install `boto3` dependency
- Use Lambda for classification
- Fall back to OpenAI if Lambda fails

## ✅ Verify It Works

1. **Check Railway logs** - Should see "Lambda classification" messages
2. **Check CloudWatch logs** - Should only see metadata (no email content):
   ```bash
   aws logs tail /aws/lambda/email-classifier --follow
   ```
3. **Test email classification** - Connect Gmail and fetch emails

## 🔒 Security Checklist

- [x] Lambda has OpenAI logging disabled
- [x] CloudWatch Logs retention = 1 day
- [x] IAM user has only `lambda:InvokeFunction` permission
- [x] Budget alerts configured
- [x] Email content encrypted before Lambda

## 💰 Cost Monitoring

Check costs:
```bash
aws budgets describe-budgets --account-id $(aws sts get-caller-identity --query Account --output text)
```

Expected: **$0-2/month** (within free tier)

## 🆘 Troubleshooting

**Lambda not working?**
- Check Railway env vars match setup
- Verify Lambda function exists: `aws lambda list-functions`
- Check Lambda logs: `aws logs tail /aws/lambda/email-classifier`

**High costs?**
- Check CloudWatch retention (should be 1 day)
- Review Lambda invocations
- Check budget alerts are configured

**Need help?**
See `DEPLOYMENT_GUIDE.md` for detailed troubleshooting.

