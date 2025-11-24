#!/bin/bash
# Check AWS Lambda logs using AWS CLI
# Usage: ./check_lambda_logs.sh [hours]

HOURS=${1:-24}
FUNCTION_ARN="${LAMBDA_FUNCTION_ARN}"

if [ -z "$FUNCTION_ARN" ]; then
    echo "❌ LAMBDA_FUNCTION_ARN environment variable not set"
    exit 1
fi

# Extract function name from ARN
FUNCTION_NAME=$(echo $FUNCTION_ARN | awk -F: '{print $NF}')
LOG_GROUP="/aws/lambda/$FUNCTION_NAME"

echo "🔍 Checking Lambda logs for: $FUNCTION_NAME"
echo "📅 Last $HOURS hours"
echo "📊 Log Group: $LOG_GROUP"
echo "============================================================"
echo ""

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Install it first:"
    echo "   https://aws.amazon.com/cli/"
    exit 1
fi

# Fetch recent log streams
echo "📋 Fetching recent log streams..."
aws logs describe-log-streams \
    --log-group-name "$LOG_GROUP" \
    --order-by LastEventTime \
    --descending \
    --max-items 5 \
    --query 'logStreams[*].[logStreamName,lastEventTime]' \
    --output table

echo ""
echo "📄 Fetching log events from last $HOURS hours..."
echo ""

# Calculate start time (hours ago)
START_TIME=$(date -u -v-${HOURS}H +%s)000

# Fetch and display logs
aws logs filter-log-events \
    --log-group-name "$LOG_GROUP" \
    --start-time $START_TIME \
    --max-items 50 \
    --query 'events[*].[timestamp,message]' \
    --output text | \
    while IFS=$'\t' read -r timestamp message; do
        # Convert timestamp to readable date
        date_str=$(date -r $((timestamp/1000)) '+%Y-%m-%d %H:%M:%S')
        
        # Color code by message type
        if [[ $message == *"ERROR"* ]] || [[ $message == *"error"* ]] || [[ $message == *"Exception"* ]]; then
            echo "❌ [$date_str] $message"
        elif [[ $message == *"START RequestId"* ]]; then
            echo "🚀 [$date_str] $message"
        elif [[ $message == *"END RequestId"* ]]; then
            echo "✅ [$date_str] $message"
        elif [[ $message == *"REPORT RequestId"* ]]; then
            echo "📊 [$date_str] $message"
        else
            echo "ℹ️  [$date_str] $message"
        fi
    done

echo ""
echo "============================================================"
echo "💡 Tip: For more detailed logs, use AWS Console:"
echo "   https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$LOG_GROUP"

