# WhatsApp Custom Template Setup

## Problem
Currently using `hello_world` template which only sends "Hello World" - not useful for deal alerts.

## Solution
Create a custom message template in Meta Developer Console with variables for deal information.

## Step-by-Step Instructions

### 1. Go to Meta Developer Console
- Visit: https://developers.facebook.com/apps/
- Select your app
- Click **WhatsApp** in left sidebar
- Click **Message Templates** (under "Configuration")

### 2. Create New Template
- Click **"Create Template"** or **"+"** button
- Choose **"Text"** as template type

### 3. Template Details
- **Name:** `deal_flow_alert` (or any name you prefer)
- **Category:** Select **"UTILITY"** (required for non-marketing messages)
- **Language:** English (US)

### 4. Template Content
Enter this template:

```
🚀 *New Deal Flow Alert*

*Subject:* {{1}}
*From:* {{2}}
*Founder:* {{3}}

{{4}}

*Deck:* {{5}}
*State:* {{6}}

View in dashboard for full details.
```

### 5. Add Variables
Click **"Add Variable"** for each `{{1}}`, `{{2}}`, etc.:
- Variable 1: Subject
- Variable 2: Sender email
- Variable 3: Founder name
- Variable 4: Email snippet/preview
- Variable 5: Deck link (or "No deck")
- Variable 6: Deal state

### 6. Submit for Review
- Click **"Submit"**
- Template will be reviewed (usually approved within minutes for utility templates)
- Status will show as "Approved" when ready

### 7. Update Code
Once approved, update `WHATSAPP_TEMPLATE_NAME` in Railway:
- Variable: `WHATSAPP_TEMPLATE_NAME`
- Value: `deal_flow_alert` (or whatever you named it)

## Alternative: Quick Test Template

If you want to test immediately, you can create a simpler template:

**Name:** `deal_alert_test`
**Content:**
```
New Deal: {{1}}

From: {{2}}

{{3}}
```

This will be approved faster and you can test the integration.

## After Template is Approved

1. Update Railway environment variable: `WHATSAPP_TEMPLATE_NAME=deal_flow_alert`
2. Redeploy the web service
3. Test by sending a dealflow email
4. You'll receive WhatsApp with actual deal information!

