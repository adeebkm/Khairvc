#!/bin/bash
# Create IAM user for Railway TEST environment
# This user can only invoke the TEST Lambda function

set -e

echo "🧪 Creating IAM user for Railway TEST environment..."

# Configuration
IAM_USER_NAME="railway-lambda-invoker-test"
FUNCTION_NAME="email-classifier-test"
REGION="us-east-1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI not found${NC}"
    exit 1
fi

# Get Lambda function ARN (or use provided)
echo -e "${YELLOW}Enter Lambda function ARN (or press Enter to auto-detect):${NC}"
read FUNCTION_ARN_INPUT

if [ -z "$FUNCTION_ARN_INPUT" ]; then
    echo "🔍 Auto-detecting Lambda function ARN..."
    FUNCTION_ARN=$(aws lambda get-function \
        --function-name $FUNCTION_NAME \
        --region $REGION \
        --query 'Configuration.FunctionArn' \
        --output text 2>/dev/null)
    
    if [ -z "$FUNCTION_ARN" ]; then
        echo -e "${RED}❌ Could not find Lambda function: $FUNCTION_NAME${NC}"
        echo "   Please create it first using setup_lambda_test.sh"
        exit 1
    fi
else
    FUNCTION_ARN=$FUNCTION_ARN_INPUT
fi

echo -e "${GREEN}✅ Using Lambda ARN: $FUNCTION_ARN${NC}"

# Create IAM user
echo "👤 Creating IAM user..."
aws iam create-user --user-name $IAM_USER_NAME 2>/dev/null || \
    echo -e "${YELLOW}⚠️  User already exists, continuing...${NC}"

# Create policy document
cat > /tmp/test-lambda-policy.json <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "lambda:InvokeFunction",
            "Resource": "$FUNCTION_ARN"
        }
    ]
}
EOF

# Create and attach policy
POLICY_NAME="railway-test-lambda-invoke-policy"
echo "📝 Creating IAM policy..."
POLICY_ARN=$(aws iam create-policy \
    --policy-name $POLICY_NAME \
    --policy-document file:///tmp/test-lambda-policy.json \
    --query 'Policy.Arn' \
    --output text 2>/dev/null || \
    aws iam get-policy --policy-arn "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/$POLICY_NAME" \
    --query 'Policy.Arn' --output text)

# Attach policy to user
echo "🔗 Attaching policy to user..."
aws iam attach-user-policy \
    --user-name $IAM_USER_NAME \
    --policy-arn $POLICY_ARN

# Create access key
echo "🔑 Creating access key..."
ACCESS_KEY_OUTPUT=$(aws iam create-access-key --user-name $IAM_USER_NAME --output json)

ACCESS_KEY_ID=$(echo $ACCESS_KEY_OUTPUT | jq -r '.AccessKey.AccessKeyId')
SECRET_ACCESS_KEY=$(echo $ACCESS_KEY_OUTPUT | jq -r '.AccessKey.SecretAccessKey')

# Cleanup
rm /tmp/test-lambda-policy.json

echo ""
echo -e "${GREEN}✅ IAM user created successfully!${NC}"
echo ""
echo "📋 TEST Environment Credentials:"
echo "   IAM User: $IAM_USER_NAME"
echo "   Lambda Function: $FUNCTION_NAME"
echo "   Lambda ARN: $FUNCTION_ARN"
echo ""
echo "🔑 Add these to Railway TEST environment (web-aws-test.up.railway.app):"
echo ""
echo "   AWS_ACCESS_KEY_ID=$ACCESS_KEY_ID"
echo "   AWS_SECRET_ACCESS_KEY=$SECRET_ACCESS_KEY"
echo "   LAMBDA_FUNCTION_ARN=$FUNCTION_ARN"
echo "   AWS_REGION=$REGION"
echo ""
echo -e "${RED}⚠️  IMPORTANT: Save these credentials now - the secret key won't be shown again!${NC}"
echo ""
echo "💡 To view credentials later, run:"
echo "   aws iam list-access-keys --user-name $IAM_USER_NAME"

