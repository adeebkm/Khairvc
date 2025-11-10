#!/bin/bash

# Gmail Auto-Reply Environment Setup Script
# This script automates the environment setup process

echo "============================================================"
echo "Gmail Auto-Reply - Environment Setup"
echo "============================================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Step 1: Check Python version
echo "Step 1: Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_success "Python $PYTHON_VERSION found"
else
    print_error "Python 3 not found. Please install Python 3.8 or higher."
    exit 1
fi

# Step 2: Create virtual environment
echo ""
echo "Step 2: Creating virtual environment..."
if [ -d "venv" ]; then
    print_info "Virtual environment already exists. Skipping..."
else
    python3 -m venv venv
    if [ $? -eq 0 ]; then
        print_success "Virtual environment created"
    else
        print_error "Failed to create virtual environment"
        exit 1
    fi
fi

# Step 3: Activate virtual environment
echo ""
echo "Step 3: Activating virtual environment..."
source venv/bin/activate
if [ $? -eq 0 ]; then
    print_success "Virtual environment activated"
else
    print_error "Failed to activate virtual environment"
    exit 1
fi

# Step 4: Upgrade pip
echo ""
echo "Step 4: Upgrading pip..."
pip install --upgrade pip -q
print_success "pip upgraded"

# Step 5: Install dependencies
echo ""
echo "Step 5: Installing dependencies..."
echo "This may take a minute..."
pip install -r requirements.txt -q
if [ $? -eq 0 ]; then
    print_success "All dependencies installed"
    echo "  - google-auth-oauthlib"
    echo "  - google-api-python-client"
    echo "  - openai"
    echo "  - flask"
    echo "  - python-dotenv"
else
    print_error "Failed to install dependencies"
    exit 1
fi

# Step 6: Check for .env file
echo ""
echo "Step 6: Checking configuration..."
if [ -f ".env" ]; then
    print_success ".env file already exists"
else
    print_info ".env file not found. Let's create it..."
    echo ""
    python setup.py
fi

# Step 7: Check for credentials.json
echo ""
echo "Step 7: Checking Gmail credentials..."
if [ -f "credentials.json" ]; then
    print_success "credentials.json found"
else
    print_error "credentials.json not found"
    echo ""
    echo "You need to download OAuth credentials from Google Cloud Console:"
    echo "1. Go to: https://console.cloud.google.com/"
    echo "2. Create a project and enable Gmail API"
    echo "3. Create OAuth 2.0 credentials (Desktop app)"
    echo "4. Download as 'credentials.json' to this directory"
    echo ""
    echo "See 'setup_guide.md' for detailed instructions."
fi

# Step 8: Run setup test
echo ""
echo "Step 8: Testing setup..."
python test_setup.py

# Final instructions
echo ""
echo "============================================================"
echo "Setup Complete!"
echo "============================================================"
echo ""
echo "Virtual environment is activated (you'll see 'venv' in your prompt)"
echo ""
echo "Next steps:"
echo ""
echo "1. If you haven't already, download credentials.json from Google Cloud Console"
echo "   See: setup_guide.md for instructions"
echo ""
echo "2. Authenticate with Gmail (first time only):"
echo "   python auto_reply.py"
echo ""
echo "3. Start the web interface:"
echo "   python app.py"
echo "   Then open: http://localhost:5000"
echo ""
echo "To activate the virtual environment in future sessions:"
echo "   source venv/bin/activate"
echo ""
echo "To deactivate:"
echo "   deactivate"
echo ""
echo "============================================================"

