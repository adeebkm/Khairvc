#!/bin/bash
# Create IAM user for Railway with minimal Lambda invoke permissions
# This user will be used by Railway to call Lambda function

set -e

echo "🔐 Setting up IAM user for Railway..."

# Configuration
IAM_USER_NAME="railway-lambda-invoker"
POLICY_NAME="RailwayLambdaInvokePolicy"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed${NC}"
    exit 1
fi

# Get Lambda function ARN (auto-detect)
echo "🔍 Auto-detecting Lambda function..."
LAMBDA_ARN=$(aws lambda list-functions --query 'Functions[?FunctionName==`email-classifier`].FunctionArn' --output text)

if [ -z "$LAMBDA_ARN" ]; then
    echo -e "${YELLOW}⚠️  Could not auto-detect Lambda function.${NC}"
    echo -e "${YELLOW}📝 Enter Lambda function ARN manually:${NC}"
    read LAMBDA_ARN
    
    if [ -z "$LAMBDA_ARN" ]; then
        echo -e "${RED}❌ Lambda ARN is required${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✅ Using Lambda ARN: $LAMBDA_ARN${NC}"

# Create IAM user
echo "👤 Creating IAM user..."
aws iam create-user --user-name $IAM_USER_NAME 2>/dev/null || echo "User already exists"

# Create policy document
cat > policy.json <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "lambda:InvokeFunction"
            ],
            "Resource": "$LAMBDA_ARN"
        }
    ]
}
EOF

# Create policy
POLICY_ARN=$(aws iam create-policy \
    --policy-name $POLICY_NAME \
    --policy-document file://policy.json \
    --query 'Policy.Arn' \
    --output text 2>/dev/null || \
    aws iam get-policy --policy-arn "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/$POLICY_NAME" --query 'Policy.Arn' --output text)

echo -e "${GREEN}✅ Policy created: $POLICY_ARN${NC}"

# Attach policy to user
aws iam attach-user-policy \
    --user-name $IAM_USER_NAME \
    --policy-arn $POLICY_ARN

echo -e "${GREEN}✅ Policy attached to user${NC}"

# Create access key
echo "🔑 Creating access key..."
ACCESS_KEY_OUTPUT=$(aws iam create-access-key --user-name $IAM_USER_NAME --output json)

ACCESS_KEY_ID=$(echo $ACCESS_KEY_OUTPUT | jq -r '.AccessKey.AccessKeyId')
SECRET_ACCESS_KEY=$(echo $ACCESS_KEY_OUTPUT | jq -r '.AccessKey.SecretAccessKey')

echo ""
echo -e "${GREEN}✅ IAM user setup complete!${NC}"
echo ""
echo "📋 Add these to Railway environment variables:"
echo ""
echo "AWS_ACCESS_KEY_ID=$ACCESS_KEY_ID"
echo "AWS_SECRET_ACCESS_KEY=$SECRET_ACCESS_KEY"
echo ""
echo "⚠️  IMPORTANT: Save these credentials securely. The secret key cannot be retrieved again!"
echo ""
echo "💡 To revoke access, run:"
echo "   aws iam delete-access-key --user-name $IAM_USER_NAME --access-key-id $ACCESS_KEY_ID"

# Cleanup
rm policy.json

