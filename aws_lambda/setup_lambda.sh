#!/bin/bash
# Setup script for AWS Lambda function deployment
# This script creates the Lambda function, IAM role, Secrets Manager secret, and CloudWatch Logs

set -e

echo "🚀 Setting up AWS Lambda for email classification..."

# Configuration
FUNCTION_NAME="email-classifier"
REGION="us-east-1"  # Change to your preferred region
ROLE_NAME="email-classifier-role"
SECRET_NAME="gemini-api-key"
BUDGET_NAME="email-classifier-budget"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed. Please install it first:${NC}"
    echo "   https://aws.amazon.com/cli/"
    exit 1
fi

# Check if AWS credentials are configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS credentials not configured. Please run 'aws configure'${NC}"
    exit 1
fi

echo -e "${GREEN}✅ AWS CLI configured${NC}"

# Get Gemini API key from user
echo -e "${YELLOW}📝 Enter your Gemini API key (will be stored in AWS Secrets Manager):${NC}"
read -s GEMINI_API_KEY

if [ -z "$GEMINI_API_KEY" ]; then
    echo -e "${RED}❌ Gemini API key is required${NC}"
    exit 1
fi

# Get budget amount from user
echo -e "${YELLOW}💰 Enter monthly budget limit in USD (e.g., 50):${NC}"
read BUDGET_AMOUNT

if [ -z "$BUDGET_AMOUNT" ]; then
    echo -e "${RED}❌ Budget amount is required${NC}"
    exit 1
fi

# Get email for budget alerts
echo -e "${YELLOW}📧 Enter email address for budget alerts:${NC}"
read BUDGET_EMAIL

if [ -z "$BUDGET_EMAIL" ]; then
    echo -e "${RED}❌ Budget email is required${NC}"
    exit 1
fi

echo ""
echo "📦 Creating deployment package..."

# Create deployment directory
mkdir -p lambda_deployment
cd lambda_deployment

# Copy Lambda function code (from parent directory where script is located)
cp ../classify_email.py .
cp ../requirements.txt .

# Install dependencies for Lambda's Linux runtime
echo "📥 Installing Python dependencies for Lambda (Linux)..."
# Use --platform to ensure compatibility with Lambda's Linux environment
if command -v pip3 &> /dev/null; then
    pip3 install -r requirements.txt -t . --quiet \
        --platform manylinux2014_x86_64 \
        --only-binary=:all: \
        --python-version 3.11
elif command -v pip &> /dev/null; then
    pip install -r requirements.txt -t . --quiet \
        --platform manylinux2014_x86_64 \
        --only-binary=:all: \
        --python-version 3.11
elif command -v python3 &> /dev/null; then
    python3 -m pip install -r requirements.txt -t . --quiet \
        --platform manylinux2014_x86_64 \
        --only-binary=:all: \
        --python-version 3.11
else
    echo "❌ Error: pip not found. Please install pip or use: python3 -m pip install -r requirements.txt -t ."
    exit 1
fi

# Create deployment package
zip -r function.zip . -q
cd ..

echo -e "${GREEN}✅ Deployment package created${NC}"

# Create IAM role for Lambda
echo "🔐 Creating IAM role..."
ROLE_ARN=$(aws iam create-role \
    --role-name $ROLE_NAME \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }' \
    --query 'Role.Arn' \
    --output text 2>/dev/null || aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text)

# Attach basic Lambda execution policy
aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Create policy for Secrets Manager access
aws iam put-role-policy \
    --role-name $ROLE_NAME \
    --policy-name SecretsManagerAccess \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
            ],
            "Resource": "arn:aws:secretsmanager:*:*:secret:gemini-api-key*"
        }]
    }'

echo -e "${GREEN}✅ IAM role created: $ROLE_ARN${NC}"

# Create Secrets Manager secret for Gemini API key
echo "🔑 Creating Secrets Manager secret..."
SECRET_ARN=$(aws secretsmanager create-secret \
    --name $SECRET_NAME \
    --secret-string "{\"api_key\": \"$GEMINI_API_KEY\"}" \
    --region $REGION \
    --query 'ARN' \
    --output text 2>/dev/null || \
    aws secretsmanager update-secret \
    --secret-id $SECRET_NAME \
    --secret-string "{\"api_key\": \"$GEMINI_API_KEY\"}" \
    --region $REGION \
    --query 'ARN' \
    --output text)

echo -e "${GREEN}✅ Secret created: $SECRET_ARN${NC}"

# Create Lambda function
echo "⚡ Creating Lambda function..."
FUNCTION_ARN=$(aws lambda create-function \
    --function-name $FUNCTION_NAME \
    --runtime python3.11 \
    --role $ROLE_ARN \
    --handler classify_email.lambda_handler \
    --zip-file fileb://lambda_deployment/function.zip \
    --timeout 30 \
    --memory-size 256 \
    --environment Variables="{GEMINI_SECRET_NAME=$SECRET_NAME}" \
    --region $REGION \
    --query 'FunctionArn' \
    --output text 2>/dev/null || \
    aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --zip-file fileb://lambda_deployment/function.zip \
    --region $REGION \
    --query 'FunctionArn' \
    --output text)

echo -e "${GREEN}✅ Lambda function created: $FUNCTION_ARN${NC}"

# Create CloudWatch Logs group (with 1-day retention to minimize costs)
echo "📊 Creating CloudWatch Logs group..."
aws logs create-log-group \
    --log-group-name "/aws/lambda/$FUNCTION_NAME" \
    --region $REGION 2>/dev/null || true

aws logs put-retention-policy \
    --log-group-name "/aws/lambda/$FUNCTION_NAME" \
    --retention-in-days 1 \
    --region $REGION

echo -e "${GREEN}✅ CloudWatch Logs configured (1-day retention)${NC}"

# Create AWS Budget
echo "💰 Creating AWS Budget..."
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)

# Create budget JSON
cat > budget.json <<EOF
{
    "BudgetName": "$BUDGET_NAME",
    "BudgetLimit": {
        "Amount": "$BUDGET_AMOUNT",
        "Unit": "USD"
    },
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST",
    "CostFilters": {
        "Service": ["Amazon Lambda", "Amazon CloudWatch", "AWS Secrets Manager"]
    },
    "CalculatedSpend": {
        "ActualSpend": {
            "Amount": "0",
            "Unit": "USD"
        }
    },
    "TimePeriod": {
        "Start": "$(date -u +%Y-%m-01T00:00:00Z)"
    }
}
EOF

# Create budget
aws budgets create-budget \
    --account-id $ACCOUNT_ID \
    --budget file://budget.json \
    --notifications-with-subscribers "[
        {
            \"Notification\": {
                \"NotificationType\": \"ACTUAL\",
                \"ComparisonOperator\": \"GREATER_THAN\",
                \"Threshold\": 80
            },
            \"Subscribers\": [{
                \"SubscriptionType\": \"EMAIL\",
                \"Address\": \"$BUDGET_EMAIL\"
            }]
        },
        {
            \"Notification\": {
                \"NotificationType\": \"FORECASTED\",
                \"ComparisonOperator\": \"GREATER_THAN\",
                \"Threshold\": 100
            },
            \"Subscribers\": [{
                \"SubscriptionType\": \"EMAIL\",
                \"Address\": \"$BUDGET_EMAIL\"
            }]
        }
    ]" \
    --region us-east-1 2>/dev/null || echo -e "${YELLOW}⚠️  Budget creation failed (may already exist or require AWS Budgets service)${NC}"

rm budget.json

echo -e "${GREEN}✅ Budget configured: \$$BUDGET_AMOUNT/month${NC}"

# Cleanup
rm -rf lambda_deployment

echo ""
echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "📋 Configuration Summary:"
echo "   Function Name: $FUNCTION_NAME"
echo "   Function ARN: $FUNCTION_ARN"
echo "   Region: $REGION"
echo "   Secret ARN: $SECRET_ARN"
echo "   Budget: \$$BUDGET_AMOUNT/month"
echo ""
echo "🔗 Next steps:"
echo "   1. Update Railway app to call Lambda function"
echo "   2. Set LAMBDA_FUNCTION_ARN environment variable in Railway"
echo "   3. Test the integration"
echo ""
echo "💡 To get the Lambda function ARN, run:"
echo "   aws lambda get-function --function-name $FUNCTION_NAME --query 'Configuration.FunctionArn' --output text"
