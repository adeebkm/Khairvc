#!/bin/bash

# Update TEST Lambda function with correct dependencies for Linux

set -e

echo "🔄 Updating TEST Lambda function with Linux-compatible dependencies..."

cd "$(dirname "$0")"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install it first."
    exit 1
fi

# Clean previous builds
rm -rf package function.zip
mkdir -p package

# Copy Lambda function code
echo "📝 Copying function code..."
cp classify_email.py package/

# Install dependencies for Lambda's Linux environment
echo "📥 Installing Python dependencies for Lambda (Linux)..."
cd package

# Use Docker to build for Linux (alternative approach)
if command -v docker &> /dev/null; then
    echo "🐳 Using Docker to build Lambda-compatible package..."
    cd ..
    docker run --rm -v "$PWD":/var/task public.ecr.aws/sam/build-python3.11 \
        pip install -r requirements.txt -t package/ --upgrade
    cd package
else
    echo "⚙️  Using pip with Linux platform target..."
    # Fallback to pip with platform flag
    pip3 install -r ../requirements.txt -t . --upgrade \
        --platform manylinux2014_x86_64 \
        --only-binary=:all: \
        --python-version 3.11 || \
    pip3 install -r ../requirements.txt -t . --upgrade
fi

# Create deployment package
echo "📦 Creating deployment package..."
zip -r ../function.zip . -q

cd ..

# Update TEST Lambda function
echo "⚡ Updating TEST Lambda function..."
aws lambda update-function-code \
    --function-name email-classifier-test \
    --zip-file fileb://function.zip \
    --region us-east-1

echo "✅ TEST Lambda function updated successfully!"

# Clean up
rm -rf package function.zip

echo ""
echo "🧪 Test your Lambda function with: python3 test_lambda.py"
echo "   (Make sure LAMBDA_FUNCTION_ARN points to email-classifier-test)"

