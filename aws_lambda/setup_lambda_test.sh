#!/bin/bash
# Setup script for AWS Lambda TEST function deployment
# This creates a separate test Lambda function: email-classifier-test

set -e

echo "🧪 Setting up AWS Lambda TEST environment for email classification..."

# Configuration - TEST ENVIRONMENT
FUNCTION_NAME="email-classifier-test"
REGION="us-east-1"
ROLE_NAME="email-classifier-test-role"
SECRET_NAME="openai-api-key"  # Can reuse same secret or create separate one
BUDGET_NAME="email-classifier-test-budget"

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

# Try to get OpenAI API key from existing secret first
echo "🔍 Checking for existing OpenAI API key secret..."
EXISTING_SECRET=$(aws secretsmanager get-secret-value --secret-id $SECRET_NAME --region $REGION --query 'SecretString' --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_SECRET" ]; then
    # Try to parse JSON format
    if echo "$EXISTING_SECRET" | grep -q '"api_key"'; then
        OPENAI_API_KEY=$(echo "$EXISTING_SECRET" | grep -o '"api_key": "[^"]*' | cut -d'"' -f4)
    else
        # Assume it's plain text
        OPENAI_API_KEY="$EXISTING_SECRET"
    fi
    echo -e "${GREEN}✅ Found existing API key in secret, reusing it${NC}"
else
    # Get OpenAI API key from user
    echo -e "${YELLOW}📝 Enter your OpenAI API key (will be stored in AWS Secrets Manager):${NC}"
    read -s OPENAI_API_KEY
    
    if [ -z "$OPENAI_API_KEY" ]; then
        echo -e "${RED}❌ OpenAI API key is required${NC}"
        exit 1
    fi
fi

# Get budget amount from user
echo -e "${YELLOW}💰 Enter monthly budget limit in USD for TEST environment (e.g., 10):${NC}"
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

# Copy Lambda function code
cp ../classify_email.py .
cp ../requirements.txt .

# Install dependencies for Lambda's Linux runtime
echo "📥 Installing Python dependencies for Lambda (Linux)..."
if command -v pip3 &> /dev/null; then
    pip3 install -r requirements.txt -t . --quiet \
        --platform manylinux2014_x86_64 \
        --only-binary=:all: \
        --python-version 3.11 || \
    pip3 install -r requirements.txt -t . --quiet
elif command -v pip &> /dev/null; then
    pip install -r requirements.txt -t . --quiet \
        --platform manylinux2014_x86_64 \
        --only-binary=:all: \
        --python-version 3.11 || \
    pip install -r requirements.txt -t . --quiet
else
    echo "❌ Error: pip not found"
    exit 1
fi

# Create deployment package
zip -r function.zip . -q
cd ..

echo -e "${GREEN}✅ Deployment package created${NC}"

# Create IAM role for Lambda (TEST)
echo "🔐 Creating IAM role for TEST environment..."
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
            "Resource": "arn:aws:secretsmanager:*:*:secret:openai-api-key*"
        }]
    }'

echo -e "${GREEN}✅ IAM role created: $ROLE_ARN${NC}"

# Create or update Secrets Manager secret for OpenAI API key
echo "🔑 Creating/updating Secrets Manager secret..."
SECRET_ARN=$(aws secretsmanager create-secret \
    --name $SECRET_NAME \
    --secret-string "$OPENAI_API_KEY" \
    --region $REGION \
    --query 'ARN' \
    --output text 2>/dev/null || \
    aws secretsmanager update-secret \
    --secret-id $SECRET_NAME \
    --secret-string "$OPENAI_API_KEY" \
    --region $REGION \
    --query 'ARN' \
    --output text)

echo -e "${GREEN}✅ Secret created/updated: $SECRET_ARN${NC}"

# Create Lambda function (TEST)
echo "⚡ Creating TEST Lambda function..."
FUNCTION_ARN=$(aws lambda create-function \
    --function-name $FUNCTION_NAME \
    --runtime python3.11 \
    --role $ROLE_ARN \
    --handler classify_email.lambda_handler \
    --zip-file fileb://lambda_deployment/function.zip \
    --timeout 30 \
    --memory-size 256 \
    --environment Variables="{OPENAI_SECRET_NAME=$SECRET_NAME}" \
    --description "TEST environment - Email classifier using gpt-4o-mini" \
    --region $REGION \
    --query 'FunctionArn' \
    --output text 2>/dev/null || \
    aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --zip-file fileb://lambda_deployment/function.zip \
    --region $REGION && \
    aws lambda get-function --function-name $FUNCTION_NAME --query 'Configuration.FunctionArn' --output text)

echo -e "${GREEN}✅ TEST Lambda function created: $FUNCTION_ARN${NC}"

# Create CloudWatch Logs group (with 1-day retention)
echo "📊 Creating CloudWatch Logs group for TEST..."
aws logs create-log-group \
    --log-group-name "/aws/lambda/$FUNCTION_NAME" \
    --region $REGION 2>/dev/null || true

aws logs put-retention-policy \
    --log-group-name "/aws/lambda/$FUNCTION_NAME" \
    --retention-in-days 1 \
    --region $REGION

echo -e "${GREEN}✅ CloudWatch Logs configured (1-day retention)${NC}"

# Create AWS Budget for TEST
echo "💰 Creating AWS Budget for TEST environment..."
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)

cat > budget_test.json <<EOF
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

aws budgets create-budget \
    --account-id $ACCOUNT_ID \
    --budget file://budget_test.json \
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
        }
    ]" \
    --region us-east-1 2>/dev/null || echo -e "${YELLOW}⚠️  Budget creation failed (may already exist)${NC}"

rm budget_test.json

echo -e "${GREEN}✅ Budget configured: \$$BUDGET_AMOUNT/month${NC}"

# Cleanup
rm -rf lambda_deployment

echo ""
echo -e "${GREEN}✅ TEST Lambda setup complete!${NC}"
echo ""
echo "📋 Configuration Summary:"
echo "   Function Name: $FUNCTION_NAME"
echo "   Function ARN: $FUNCTION_ARN"
echo "   Region: $REGION"
echo "   Secret ARN: $SECRET_ARN"
echo "   Budget: \$$BUDGET_AMOUNT/month"
echo ""
echo "🔗 Next steps:"
echo "   1. Add this ARN to Railway TEST environment:"
echo "      LAMBDA_FUNCTION_ARN=$FUNCTION_ARN"
echo "   2. Create IAM user for Railway TEST (run setup_iam_user_test.sh)"
echo "   3. Add AWS credentials to Railway TEST environment"
echo ""
echo "💡 To get the Lambda function ARN later, run:"
echo "   aws lambda get-function --function-name $FUNCTION_NAME --query 'Configuration.FunctionArn' --output text"

