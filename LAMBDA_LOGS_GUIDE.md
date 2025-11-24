# How to Check AWS Lambda Logs

## Method 1: AWS Console (Easiest) 🌐

1. **Go to AWS CloudWatch Console:**
   - https://console.aws.amazon.com/cloudwatch/

2. **Navigate to Logs:**
   - Click "Logs" in left sidebar
   - Click "Log groups"
   - Find: `/aws/lambda/YOUR_FUNCTION_NAME`

3. **View Recent Logs:**
   - Click on the log group
   - Click on most recent log stream
   - See all log events with timestamps

4. **Filter Logs:**
   - Use search box to filter by keyword (e.g., "ERROR", "Exception")
   - Use time range selector for specific periods

---

## Method 2: AWS CLI (Command Line) 💻

### Quick Check (Last 24 hours):
```bash
# Set your function name
FUNCTION_NAME="your-lambda-function-name"

# Get recent log streams
aws logs describe-log-streams \
    --log-group-name "/aws/lambda/$FUNCTION_NAME" \
    --order-by LastEventTime \
    --descending \
    --max-items 5

# Get recent log events
aws logs filter-log-events \
    --log-group-name "/aws/lambda/$FUNCTION_NAME" \
    --start-time $(($(date +%s) - 86400))000 \
    --max-items 50 \
    --query 'events[*].[timestamp,message]' \
    --output table
```

### Check for Errors Only:
```bash
aws logs filter-log-events \
    --log-group-name "/aws/lambda/$FUNCTION_NAME" \
    --start-time $(($(date +%s) - 86400))000 \
    --filter-pattern "ERROR" \
    --query 'events[*].message' \
    --output text
```

### Watch Logs in Real-Time:
```bash
aws logs tail "/aws/lambda/$FUNCTION_NAME" --follow
```

---

## Method 3: Using the Python Script (If boto3 installed)

```bash
# Install boto3 first
pip install boto3

# Run the script
python3 check_lambda_logs.py 24  # Last 24 hours
```

---

## Method 4: Check Lambda Metrics (Invocation Count, Errors)

1. **AWS Console:**
   - Go to Lambda → Your Function → Monitoring tab
   - See graphs for:
     - Invocations
     - Errors
     - Duration
     - Throttles

2. **AWS CLI:**
```bash
aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Invocations \
    --dimensions Name=FunctionName,Value=YOUR_FUNCTION_NAME \
    --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 3600 \
    --statistics Sum
```

---

## What to Look For:

### ✅ Good Signs:
- `START RequestId: ...` - Function invoked
- `END RequestId: ...` - Function completed
- `REPORT RequestId: ... Duration: XXXms` - Performance metrics
- Classification results: `label: dealflow`, `confidence: 0.95`

### ❌ Error Signs:
- `ERROR` or `Exception` - Something failed
- `Timeout` - Function took too long
- `Memory exceeded` - Out of memory
- `AccessDenied` - Permission issues

### 🔍 Common Issues:

1. **No logs at all:**
   - Lambda function hasn't been invoked
   - Wrong function name/ARN
   - Log group doesn't exist

2. **Access Denied:**
   - IAM user needs `logs:DescribeLogStreams` and `logs:GetLogEvents` permissions

3. **Function not found:**
   - Check `LAMBDA_FUNCTION_ARN` environment variable
   - Verify function exists in AWS Console

---

## Quick Diagnostic Commands:

```bash
# 1. List all Lambda functions
aws lambda list-functions --query 'Functions[*].[FunctionName,Runtime]' --output table

# 2. Get function details
aws lambda get-function --function-name YOUR_FUNCTION_NAME

# 3. Check recent invocations
aws lambda list-event-source-mappings --function-name YOUR_FUNCTION_NAME

# 4. Test invoke (if needed)
aws lambda invoke \
    --function-name YOUR_FUNCTION_NAME \
    --payload '{"test": "data"}' \
    response.json
```

---

## From Your Railway/Server:

If you're running this on Railway, you can also check logs there:
- Railway Dashboard → Your Service → Logs tab
- Filter for "Lambda" or "ERROR" keywords

