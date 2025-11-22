# WhatsApp Integration Setup Guide

This guide will help you set up WhatsApp Business Cloud API (Meta) for deal flow alerts.

## Prerequisites

1. Meta Business Account
2. WhatsApp Business Account
3. Meta for Developers account

## Step 1: Create Meta App

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Click "My Apps" → "Create App"
3. Select "Business" type
4. Fill in app details and create

## Step 2: Add WhatsApp Product

1. In your app dashboard, click "Add Product"
2. Find "WhatsApp" and click "Set Up"
3. Follow the setup wizard

## Step 3: Get Phone Number ID

1. In WhatsApp product settings, go to "API Setup"
2. Find your "Phone number ID" (looks like: `123456789012345`)
3. Copy this value

## Step 4: Generate Access Token

1. In WhatsApp product settings, go to "API Setup"
2. Under "Temporary access token", click "Generate token"
3. **Important**: For production, create a System User and generate a permanent token
4. Copy the access token

## Step 5: Set Up Webhook

1. In WhatsApp product settings, go to "Configuration"
2. Under "Webhook", click "Edit"
3. Set callback URL: `https://your-domain.com/webhook/whatsapp`
4. Set verify token: (create a random string, e.g., `your_secure_token_here`)
5. Subscribe to `messages` field
6. Click "Verify and Save"

## Step 6: Environment Variables

Add these to your Railway/environment:

```bash
# WhatsApp Meta API
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_ACCESS_TOKEN=your_access_token_here
WHATSAPP_VERIFY_TOKEN=your_secure_token_here
WHATSAPP_API_VERSION=v21.0
```

## Step 7: Run Migration

```bash
python migrations/add_whatsapp_fields.py
```

## Step 8: Enable Celery Beat (for follow-ups)

If not already running, start Celery Beat:

```bash
celery -A celery_config beat --loglevel=info
```

## Step 9: User Setup

1. Users go to dashboard settings
2. Enable WhatsApp notifications
3. Enter their WhatsApp number (format: +1234567890)
4. Save settings

## Testing

1. Create a test deal flow email
2. Check that WhatsApp alert is sent
3. Wait 6 hours (or manually trigger follow-up task)
4. Verify follow-up message is sent

## Commands

- **STOP**: User can reply "STOP" to disable follow-ups
- **START**: User can reply "START" to re-enable follow-ups

## Troubleshooting

### Webhook verification fails

- Check that `WHATSAPP_VERIFY_TOKEN` matches the token in Meta dashboard
- Ensure webhook URL is publicly accessible (not localhost)

### Messages not sending

- Verify `WHATSAPP_PHONE_NUMBER_ID` and `WHATSAPP_ACCESS_TOKEN` are correct
- Check Meta dashboard for API errors
- Ensure phone number is verified in Meta Business Manager

### Follow-ups not working

- Verify Celery Beat is running
- Check task logs for errors
- Ensure deals have `whatsapp_alert_sent = True`

## Cost

Meta WhatsApp Business Cloud API is **FREE** for:

- Up to 1,000 conversations per month
- Each conversation = 24-hour window of messages

After 1,000 conversations, pricing applies (varies by country).

## Security Notes

- Never commit access tokens to git
- Use environment variables for all secrets
- Rotate access tokens periodically
- Use permanent tokens for production (not temporary)
