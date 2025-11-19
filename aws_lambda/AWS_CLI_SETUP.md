# AWS CLI Setup Guide

Complete guide to install and configure AWS CLI for Lambda deployment.

## 📦 Installation

### macOS (using Homebrew - Recommended)

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install AWS CLI
brew install awscli

# Verify installation
aws --version
```

**Expected output:**
```
aws-cli/2.x.x Python/3.x.x Darwin/x.x.x source/x86_64
```

### macOS (using pip)

```bash
# Install pip if needed
python3 -m ensurepip --upgrade

# Install AWS CLI
pip3 install awscli --upgrade

# Verify installation
aws --version
```

### Linux

```bash
# Download AWS CLI installer
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"

# Unzip
unzip awscliv2.zip

# Install
sudo ./aws/install

# Verify installation
aws --version
```

### Windows

1. Download AWS CLI MSI installer: https://awscli.amazonaws.com/AWSCLIV2.msi
2. Run the installer
3. Follow the installation wizard
4. Open Command Prompt and verify:
   ```cmd
   aws --version
   ```

## 🔐 Configuration

### Step 1: Get AWS Credentials

You need:
- **AWS Access Key ID**
- **AWS Secret Access Key**

**How to get them:**

1. **Sign in to AWS Console**: https://console.aws.amazon.com
2. **Go to IAM**: Search "IAM" in the top search bar
3. **Click "Users"** in the left sidebar
4. **Click your username** (or create a new user)
5. **Go to "Security credentials" tab**
6. **Click "Create access key"**
7. **Select "Command Line Interface (CLI)"**
8. **Download or copy** the Access Key ID and Secret Access Key

⚠️ **Important**: Save these credentials securely. The secret key cannot be retrieved again!

### Step 2: Configure AWS CLI

Run the configuration command:

```bash
aws configure
```

**You'll be prompted for:**

1. **AWS Access Key ID**: Paste your Access Key ID
2. **AWS Secret Access Key**: Paste your Secret Access Key
3. **Default region name**: Enter `us-east-1` (or your preferred region)
4. **Default output format**: Enter `json` (recommended)

**Example:**
```
$ aws configure
AWS Access Key ID [None]: AKIAIOSFODNN7EXAMPLE
AWS Secret Access Key [None]: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
Default region name [None]: us-east-1
Default output format [None]: json
```

### Step 3: Verify Configuration

Test your configuration:

```bash
# Check your AWS identity
aws sts get-caller-identity
```

**Expected output:**
```json
{
    "UserId": "AIDAIOSFODNN7EXAMPLE",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/your-username"
}
```

If you see this, AWS CLI is configured correctly! ✅

## 🔍 Troubleshooting

### Error: "aws: command not found"

**Solution:**
- Verify AWS CLI is installed: `which aws`
- If not found, check your PATH:
  ```bash
  echo $PATH
  # Should include AWS CLI installation directory
  ```
- On macOS with Homebrew, try:
  ```bash
  brew link awscli
  ```

### Error: "Unable to locate credentials"

**Solution:**
- Run `aws configure` again
- Check credentials file exists: `cat ~/.aws/credentials`
- Verify credentials are correct

### Error: "Access Denied"

**Solution:**
- Verify your IAM user has necessary permissions
- Check if you're using the correct AWS account
- Verify your access key hasn't been rotated/deleted

### Error: "Invalid credentials"

**Solution:**
- Double-check Access Key ID and Secret Access Key
- Make sure there are no extra spaces when copying
- Try creating a new access key in AWS Console

## 📝 Configuration Files

AWS CLI stores configuration in:

**macOS/Linux:**
- Credentials: `~/.aws/credentials`
- Config: `~/.aws/config`

**Windows:**
- Credentials: `C:\Users\YourUsername\.aws\credentials`
- Config: `C:\Users\YourUsername\.aws\config`

### View Current Configuration

```bash
# View credentials (be careful - contains secrets!)
cat ~/.aws/credentials

# View config
cat ~/.aws/config
```

### Multiple AWS Profiles

You can configure multiple AWS accounts:

```bash
# Configure a named profile
aws configure --profile production

# Use a specific profile
aws s3 ls --profile production

# Set default profile
export AWS_PROFILE=production
```

## ✅ Pre-Flight Checklist

Before running the Lambda setup scripts, verify:

- [ ] AWS CLI installed: `aws --version`
- [ ] AWS CLI configured: `aws sts get-caller-identity` works
- [ ] You have AWS account access
- [ ] You have IAM permissions to create Lambda functions
- [ ] You have IAM permissions to create IAM roles/users
- [ ] You have Secrets Manager permissions

### Test Permissions

```bash
# Test Lambda access
aws lambda list-functions

# Test IAM access
aws iam list-users

# Test Secrets Manager access
aws secretsmanager list-secrets
```

If any of these fail, you may need additional IAM permissions.

## 🚀 Next Steps

Once AWS CLI is configured:

1. **Run Lambda setup**:
   ```bash
   cd aws_lambda
   ./setup_lambda.sh
   ```

2. **Run IAM user setup**:
   ```bash
   ./setup_iam_user.sh
   ```

3. **Add credentials to Railway** (from IAM user setup output)

## 📚 Additional Resources

- **AWS CLI Documentation**: https://docs.aws.amazon.com/cli/
- **AWS CLI Command Reference**: https://docs.aws.amazon.com/cli/latest/reference/
- **IAM Best Practices**: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
- **AWS Free Tier**: https://aws.amazon.com/free/

## 🔒 Security Best Practices

1. **Never commit credentials**: Add `~/.aws/` to `.gitignore`
2. **Use IAM users**: Don't use root account credentials
3. **Rotate keys regularly**: Change access keys every 90 days
4. **Use least privilege**: Only grant necessary permissions
5. **Enable MFA**: Use multi-factor authentication for AWS Console

## 💡 Tips

- **Region selection**: Choose a region close to your users for lower latency
- **Output format**: Use `json` for scripts, `table` for human-readable output
- **Profiles**: Use profiles to manage multiple AWS accounts
- **Credentials helper**: Consider using AWS SSO or credential helper for better security

---

**Ready?** Proceed to `QUICKSTART.md` or `DEPLOYMENT_GUIDE.md` to deploy Lambda!

