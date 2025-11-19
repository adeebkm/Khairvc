# AWS Lambda Email Classifier Setup

This directory contains the AWS Lambda function for email classification with **zero logging of email content or OpenAI API calls**.

## Architecture

```
Railway App → AWS Lambda → OpenAI API
              ↓
         Secrets Manager (API Key)
              ↓
         CloudWatch Logs (metadata only)
```

## Security Features

✅ **Zero Email Content Logging**: Email content never appears in CloudWatch Logs  
✅ **Zero OpenAI API Logging**: OpenAI requests/responses disabled via logging configuration  
✅ **Encrypted Communication**: Email content encrypted before sending to Lambda  
✅ **Secrets Manager**: OpenAI API key stored securely in AWS Secrets Manager  
✅ **IAM Roles**: Least-privilege access for Lambda function  
✅ **Budget Alerts**: Automatic cost monitoring and alerts  

## Setup Instructions

### Prerequisites

1. **AWS Account**: Sign up at https://aws.amazon.com
2. **AWS CLI**: Install and configure (`aws configure`)
3. **OpenAI API Key**: Your OpenAI API key
4. **Python 3.11+**: For local testing

### Step 1: Run Setup Script

```bash
cd aws_lambda
chmod +x setup_lambda.sh
./setup_lambda.sh
```

The script will:
- Create IAM role for Lambda
- Create Secrets Manager secret for OpenAI API key
- Create Lambda function
- Configure CloudWatch Logs (1-day retention)
- Set up AWS Budget with alerts

### Step 2: Get Lambda Function ARN

```bash
aws lambda get-function --function-name email-classifier --query 'Configuration.FunctionArn' --output text
```

Copy this ARN - you'll need it for Railway configuration.

### Step 3: Configure Railway

Add these environment variables to your Railway project:

```
LAMBDA_FUNCTION_ARN=arn:aws:lambda:us-east-1:123456789012:function:email-classifier
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

**Important**: Create a dedicated IAM user for Railway with only `lambda:InvokeFunction` permission.

### Step 4: Test Lambda Function

```bash
# Test locally (requires AWS credentials)
python test_lambda.py
```

## Cost Estimation

### AWS Lambda
- **Free Tier**: 1M requests/month, 400K GB-seconds/month
- **After Free Tier**: $0.20 per 1M requests, $0.0000166667 per GB-second
- **Estimated Cost**: ~$0-5/month for typical usage

### AWS Secrets Manager
- **Free Tier**: First 10K API calls/month
- **After Free Tier**: $0.05 per 10K API calls
- **Estimated Cost**: ~$0/month (within free tier)

### CloudWatch Logs
- **Free Tier**: 5GB ingestion, 5GB storage/month
- **After Free Tier**: $0.50 per GB ingested, $0.03 per GB stored
- **Estimated Cost**: ~$0-2/month (with 1-day retention)

### Total Estimated Cost
- **With Free Tier**: $0-2/month
- **Without Free Tier**: $2-10/month (depending on volume)

## Budget Configuration

The setup script creates an AWS Budget that:
- Monitors Lambda, CloudWatch, and Secrets Manager costs
- Sends email alerts at 80% of budget
- Sends forecast alerts at 100% of budget

To update budget:

```bash
aws budgets update-budget \
    --account-id YOUR_ACCOUNT_ID \
    --budget file://budget.json
```

## Monitoring

### View Lambda Logs (metadata only)

```bash
aws logs tail /aws/lambda/email-classifier --follow
```

You should see only:
- `Classification request - Thread: xxx, User: yyy`
- `Classification completed - Thread: xxx`
- Error types (not content)

### View Lambda Metrics

```bash
aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Invocations \
    --dimensions Name=FunctionName,Value=email-classifier \
    --start-time 2024-01-01T00:00:00Z \
    --end-time 2024-01-02T00:00:00Z \
    --period 3600 \
    --statistics Sum
```

## Troubleshooting

### Lambda Function Not Found
- Check function name: `aws lambda list-functions`
- Verify region matches your configuration

### Secrets Manager Access Denied
- Check IAM role has `secretsmanager:GetSecretValue` permission
- Verify secret name matches `OPENAI_SECRET_NAME` environment variable

### Budget Not Working
- AWS Budgets requires AWS account to be at least 24 hours old
- Verify email address is correct
- Check AWS Budgets service is enabled in your region

### High Costs
- Check CloudWatch Logs retention (should be 1 day)
- Review Lambda function memory/timeout settings
- Monitor AWS Cost Explorer for unexpected charges

## Security Best Practices

1. **Never log email content** - Only log metadata (thread_id, user_id)
2. **Use encryption** - Encrypt email content before sending to Lambda
3. **Rotate API keys** - Regularly rotate OpenAI API key in Secrets Manager
4. **Monitor access** - Use CloudTrail to monitor Lambda invocations
5. **Set budgets** - Configure budget alerts to prevent unexpected costs

## Files

- `classify_email.py` - Lambda function code (no logging)
- `requirements.txt` - Python dependencies
- `setup_lambda.sh` - Automated setup script
- `README.md` - This file

## Support

For issues or questions:
1. Check CloudWatch Logs for error messages
2. Review IAM permissions
3. Verify Secrets Manager configuration
4. Check AWS Budget alerts

