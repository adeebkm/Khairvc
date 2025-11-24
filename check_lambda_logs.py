#!/usr/bin/env python3
"""
Check AWS Lambda logs for email classification function
Shows recent invocations, errors, and performance metrics
"""
import os
import json
import boto3
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# AWS Configuration
FUNCTION_ARN = os.getenv('LAMBDA_FUNCTION_ARN')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

def get_function_name_from_arn(arn):
    """Extract function name from ARN"""
    # ARN format: arn:aws:lambda:region:account:function:name
    parts = arn.split(':')
    return parts[-1] if len(parts) >= 7 else arn

def get_lambda_logs(hours=24, limit=50):
    """Fetch Lambda logs from CloudWatch"""
    if not all([FUNCTION_ARN, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY]):
        print("❌ Missing AWS credentials or LAMBDA_FUNCTION_ARN")
        print("   Required env vars: LAMBDA_FUNCTION_ARN, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")
        return
    
    function_name = get_function_name_from_arn(FUNCTION_ARN)
    log_group_name = f"/aws/lambda/{function_name}"
    
    print(f"🔍 Checking Lambda logs for: {function_name}")
    print(f"📅 Last {hours} hours")
    print(f"{'='*80}\n")
    
    try:
        # Initialize CloudWatch Logs client
        logs_client = boto3.client(
            'logs',
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        
        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        # Fetch log streams
        print(f"📊 Fetching log streams since {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC...")
        
        streams_response = logs_client.describe_log_streams(
            logGroupName=log_group_name,
            orderBy='LastEventTime',
            descending=True,
            limit=10
        )
        
        if not streams_response.get('logStreams'):
            print(f"⚠️  No log streams found for {log_group_name}")
            print("   This could mean:")
            print("   - Lambda function hasn't been invoked recently")
            print("   - Log group doesn't exist")
            print("   - Wrong function name/ARN")
            return
        
        print(f"✅ Found {len(streams_response['logStreams'])} log stream(s)\n")
        
        # Fetch log events from recent streams
        all_events = []
        for stream in streams_response['logStreams'][:5]:  # Check top 5 streams
            stream_name = stream['logStreamName']
            
            events_response = logs_client.get_log_events(
                logGroupName=log_group_name,
                logStreamName=stream_name,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                limit=100
            )
            
            for event in events_response.get('events', []):
                all_events.append({
                    'timestamp': datetime.fromtimestamp(event['timestamp'] / 1000),
                    'message': event['message'],
                    'stream': stream_name
                })
        
        # Sort by timestamp
        all_events.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Display logs
        print(f"📋 Recent Log Events ({len(all_events)} total):\n")
        
        error_count = 0
        invocation_count = 0
        
        for i, event in enumerate(all_events[:limit], 1):
            timestamp = event['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            message = event['message'].strip()
            
            # Color coding
            if 'ERROR' in message or 'error' in message.lower() or 'Exception' in message:
                print(f"❌ [{timestamp}] {message}")
                error_count += 1
            elif 'START RequestId' in message:
                print(f"🚀 [{timestamp}] {message}")
                invocation_count += 1
            elif 'END RequestId' in message:
                print(f"✅ [{timestamp}] {message}")
            elif 'REPORT RequestId' in message:
                # Extract duration and memory
                if 'Duration:' in message:
                    duration = message.split('Duration:')[1].split('ms')[0].strip()
                    memory = message.split('Memory Size:')[1].split('MB')[0].strip() if 'Memory Size:' in message else 'N/A'
                    print(f"📊 [{timestamp}] Duration: {duration}ms | Memory: {memory}MB")
            else:
                print(f"ℹ️  [{timestamp}] {message}")
        
        print(f"\n{'='*80}")
        print(f"📈 Summary:")
        print(f"   Total events shown: {len(all_events[:limit])}")
        print(f"   Invocations: {invocation_count}")
        print(f"   Errors: {error_count}")
        
        # Check Lambda function metrics
        print(f"\n🔍 Checking Lambda function metrics...")
        try:
            cloudwatch = boto3.client(
                'cloudwatch',
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY
            )
            
            metrics = cloudwatch.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Invocations',
                Dimensions=[
                    {'Name': 'FunctionName', 'Value': function_name}
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # 1 hour periods
                Statistics=['Sum']
            )
            
            total_invocations = sum(point['Sum'] for point in metrics.get('Datapoints', []))
            print(f"   Total invocations (last {hours}h): {int(total_invocations)}")
            
            # Error rate
            error_metrics = cloudwatch.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Errors',
                Dimensions=[
                    {'Name': 'FunctionName', 'Value': function_name}
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,
                Statistics=['Sum']
            )
            
            total_errors = sum(point['Sum'] for point in error_metrics.get('Datapoints', []))
            print(f"   Total errors (last {hours}h): {int(total_errors)}")
            
            if total_invocations > 0:
                error_rate = (total_errors / total_invocations) * 100
                print(f"   Error rate: {error_rate:.2f}%")
            
        except Exception as e:
            print(f"   ⚠️  Could not fetch metrics: {str(e)}")
        
    except Exception as e:
        print(f"❌ Error fetching logs: {str(e)}")
        print("\nTroubleshooting:")
        print("1. Check AWS credentials are correct")
        print("2. Verify LAMBDA_FUNCTION_ARN is correct")
        print("3. Ensure IAM user has CloudWatch Logs read permissions")
        print("4. Check if Lambda function exists and has been invoked")

if __name__ == "__main__":
    import sys
    
    hours = 24
    if len(sys.argv) > 1:
        try:
            hours = int(sys.argv[1])
        except ValueError:
            print("Usage: python check_lambda_logs.py [hours]")
            print("Example: python check_lambda_logs.py 12  # Last 12 hours")
            sys.exit(1)
    
    get_lambda_logs(hours=hours)

