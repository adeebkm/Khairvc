# Railway + Lambda Setup Summary

## ✅ What Was Implemented

### 1. AWS Lambda Function (`aws_lambda/classify_email.py`)
- **Zero OpenAI Logging**: Disabled all OpenAI library logging
- **Zero Email Content Logging**: Only logs metadata (thread_id, user_id)
- **Encrypted Communication**: Email content encrypted before sending to Lambda
- **Secrets Manager Integration**: OpenAI API key stored securely in AWS Secrets Manager

### 2. Lambda Client (`lambda_client.py`)
- **Automatic Fallback**: Falls back to direct OpenAI if Lambda unavailable
- **Encryption**: Encrypts email data with one-time keys
- **Error Handling**: Graceful fallback on Lambda failures

### 3. Email Classifier Updates (`email_classifier.py`)
- **Lambda Integration**: Prefers Lambda over direct OpenAI
- **Thread/User Context**: Passes thread_id and user_id for logging
- **Backward Compatible**: Works with or without Lambda

### 4. Setup Scripts
- **`setup_lambda.sh`**: Automated Lambda deployment
  - Creates IAM role
  - Creates Secrets Manager secret
  - Deploys Lambda function
  - Configures CloudWatch Logs (1-day retention)
  - Sets up AWS Budget

- **`setup_iam_user.sh`**: Creates IAM user for Railway
  - Minimal permissions (only `lambda:InvokeFunction`)
  - Generates access keys

### 5. Documentation
- **`DEPLOYMENT_GUIDE.md`**: Complete step-by-step guide
- **`QUICKSTART.md`**: 5-minute setup guide
- **`README.md`**: Lambda function documentation

## 🔒 Security Features

✅ **Zero Email Content in Logs**: Email content never appears in CloudWatch Logs  
✅ **Zero OpenAI API Logging**: OpenAI requests/responses disabled  
✅ **Encrypted Communication**: Email encrypted before Lambda  
✅ **Secrets Manager**: OpenAI API key stored securely  
✅ **IAM Least Privilege**: Railway user has only Lambda invoke permission  
✅ **Budget Alerts**: Automatic cost monitoring  

## 📋 Next Steps

### 1. Run Setup Scripts

```bash
cd aws_lambda
chmod +x setup_lambda.sh setup_iam_user.sh
./setup_lambda.sh
./setup_iam_user.sh
```

### 2. Add to Railway

Add these environment variables:

```
LAMBDA_FUNCTION_ARN=<from setup_lambda.sh>
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<from setup_iam_user.sh>
AWS_SECRET_ACCESS_KEY=<from setup_iam_user.sh>
```

### 3. Deploy

Railway will automatically:
- Install `boto3` (already added to requirements.txt)
- Use Lambda for classification
- Fall back to OpenAI if Lambda fails

## 💰 Cost Estimate

**With AWS Free Tier:**
- Lambda: $0 (1M requests/month free)
- Secrets Manager: $0 (10K API calls/month free)
- CloudWatch Logs: $0-2/month (with 1-day retention)
- **Total: $0-2/month**

**Without Free Tier:**
- Lambda: $0-5/month
- Secrets Manager: $0-1/month
- CloudWatch Logs: $1-5/month
- **Total: $2-10/month**

## 🔍 Verification

### Check Lambda Logs (should only see metadata):

```bash
aws logs tail /aws/lambda/email-classifier --follow
```

**Expected output:**
```
Classification request - Thread: xxx, User: yyy
Classification completed - Thread: xxx
```

**NOT:**
- Email content
- OpenAI requests/responses
- Classification results

### Check Railway Logs:

Should see messages like:
- "Lambda classification" (if Lambda works)
- "Lambda classification failed, falling back to OpenAI" (if Lambda fails)

## 🆘 Troubleshooting

See `aws_lambda/DEPLOYMENT_GUIDE.md` for detailed troubleshooting.

**Common Issues:**
1. **Lambda not found**: Check `LAMBDA_FUNCTION_ARN` in Railway
2. **Access denied**: Verify IAM user credentials
3. **High costs**: Check CloudWatch retention (should be 1 day)
4. **Classification fails**: Check Lambda logs for errors

## 📁 Files Created/Modified

### New Files:
- `aws_lambda/classify_email.py` - Lambda function
- `aws_lambda/requirements.txt` - Lambda dependencies
- `aws_lambda/setup_lambda.sh` - Lambda setup script
- `aws_lambda/setup_iam_user.sh` - IAM user setup script
- `aws_lambda/README.md` - Lambda documentation
- `aws_lambda/DEPLOYMENT_GUIDE.md` - Deployment guide
- `aws_lambda/QUICKSTART.md` - Quick start guide
- `lambda_client.py` - Lambda client wrapper

### Modified Files:
- `email_classifier.py` - Added Lambda support
- `app.py` - Pass thread_id/user_id to classifier
- `requirements.txt` - Added boto3

## ✨ Key Benefits

1. **Privacy**: Email content never logged
2. **Security**: OpenAI API key in Secrets Manager
3. **Cost Control**: Budget alerts configured
4. **Reliability**: Automatic fallback to OpenAI
5. **Scalability**: Lambda handles high volume

## 🎯 Success Criteria

✅ Lambda function deployed  
✅ Railway configured with Lambda  
✅ Classification works via Lambda  
✅ CloudWatch logs show only metadata  
✅ Budget alerts configured  
✅ Fallback to OpenAI works  

