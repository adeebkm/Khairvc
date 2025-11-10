# Gmail Auto-Reply with OpenAI

Automatically read Gmail emails and generate intelligent AI-powered replies using OpenAI's GPT models.

## Features

- 🤖 **AI-Powered Replies**: Uses OpenAI GPT-4 to generate contextual, professional email responses
- 📧 **Smart Filtering**: Automatically identifies which emails need replies (filters out spam, newsletters, etc.)
- 🔒 **Secure Authentication**: Uses OAuth 2.0 for Gmail access
- 🧪 **Test Mode**: Preview generated replies before enabling automatic sending
- ⚙️ **Configurable**: Customize behavior through environment variables
- 🌐 **Web Interface**: Beautiful, modern web UI for managing emails and replies (NEW!)
- 📱 **Mobile Responsive**: Works great on phones, tablets, and desktops

## Prerequisites

- Python 3.8 or higher
- OpenAI API key
- Gmail account
- Google Cloud Project with Gmail API enabled

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Google Gmail API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the Gmail API:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Gmail API"
   - Click "Enable"
4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Choose "Desktop app" as application type
   - Name it (e.g., "Gmail Auto Reply")
   - Click "Create"
5. Download the credentials:
   - Click the download icon next to your OAuth 2.0 Client ID
   - Save the file as `credentials.json` in the project root directory

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here

# Gmail Settings
# Set to 'true' to actually send emails, 'false' for testing
SEND_EMAILS=false

# Maximum number of emails to process per run
MAX_EMAILS=5

# Only reply to unread emails (true/false)
UNREAD_ONLY=true
```

Replace `your_openai_api_key_here` with your actual OpenAI API key.

### 4. First Run - Authenticate with Gmail

Run the script for the first time:

```bash
python auto_reply.py
```

This will:
- Open your browser for Gmail authentication
- Ask you to authorize the application
- Save the authentication token in `token.json`

**Note**: Keep `SEND_EMAILS=false` for your first runs to test the system!

## Usage

You can use this system in two ways:

### Option 1: Web Interface (Recommended - NEW! 🌐)

Start the web server:
```bash
python app.py
```

Then open your browser to: **http://localhost:5000**

Features:
- ✨ Beautiful, modern interface
- 📧 View all unread emails
- 🤖 Generate AI replies with one click
- ✏️ Edit replies before sending
- ✉️ Send replies from the browser
- 📱 Works on mobile and desktop

See `WEB_APP_GUIDE.md` for detailed instructions.

### Option 2: Command Line

#### Test Mode (Recommended First)

```bash
python auto_reply.py
```

With `SEND_EMAILS=false` in your `.env` file, the script will:
- Read unread emails
- Generate AI replies
- Show you what would be sent
- Mark emails as read
- **NOT actually send any emails**

#### Production Mode

Once you're confident with the replies being generated, enable sending:

1. Update `.env`:
   ```
   SEND_EMAILS=true
   ```

2. Run the script:
   ```bash
   python auto_reply.py
   ```

### Automate with Cron (Optional)

To run automatically every hour:

```bash
# Edit crontab
crontab -e

# Add this line (adjust path to your project):
0 * * * * cd /Users/adeebkhaja/Documents/gmail\ openai && /usr/bin/python3 auto_reply.py >> log.txt 2>&1
```

## Configuration Options

Edit `.env` to customize behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | Your OpenAI API key |
| `SEND_EMAILS` | `false` | Set to `true` to actually send replies |
| `MAX_EMAILS` | `5` | Maximum emails to process per run |
| `UNREAD_ONLY` | `true` | Only process unread emails |

## How It Works

1. **Authentication**: Connects to Gmail using OAuth 2.0
2. **Fetch Emails**: Retrieves unread emails from your inbox
3. **AI Analysis**: OpenAI analyzes each email to determine if it needs a reply
4. **Filter Spam**: Automatically skips spam, newsletters, and automated emails
5. **Generate Reply**: Creates a contextual, professional response
6. **Send or Preview**: Either sends the reply or shows it in test mode
7. **Mark as Read**: Marks processed emails as read

## File Structure

```
gmail-openai-auto-reply/
├── auto_reply.py          # Main script
├── gmail_client.py        # Gmail API integration
├── openai_client.py       # OpenAI API integration
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create this)
├── .gitignore            # Git ignore rules
├── credentials.json      # Gmail OAuth credentials (download from Google)
├── token.json            # Gmail authentication token (auto-generated)
└── README.md             # This file
```

## Security Notes

⚠️ **Important Security Considerations:**

- Never commit `credentials.json`, `token.json`, or `.env` to version control
- Keep your OpenAI API key secure
- Review generated replies before enabling `SEND_EMAILS=true`
- The app only requests Gmail permissions needed for reading and sending emails
- You can revoke access anytime from your [Google Account settings](https://myaccount.google.com/permissions)

## Troubleshooting

### "credentials.json not found"
- Download OAuth credentials from Google Cloud Console
- Save as `credentials.json` in the project root

### "OpenAI API key not found"
- Create `.env` file with your OpenAI API key
- Ensure the key is valid and has sufficient credits

### "Token has been expired or revoked"
- Delete `token.json`
- Run the script again to re-authenticate

### Emails not being processed
- Check that you have unread emails in your inbox
- Verify `MAX_EMAILS` setting in `.env`
- Check the console output for error messages

## Customization

### Modify AI Reply Behavior

Edit `openai_client.py` to customize:
- Reply tone and style
- Email filtering logic
- OpenAI model used (currently `gpt-4o-mini`)
- Temperature and max tokens

### Change Email Filters

Edit `gmail_client.py` to modify:
- Email query filters (e.g., specific labels, senders)
- Number of emails fetched
- How email bodies are parsed

## Cost Considerations

- **Gmail API**: Free for personal use (generous limits)
- **OpenAI API**: Charges per token
  - Using `gpt-4o-mini` (cost-effective)
  - Approximately $0.01-0.05 per email depending on length
  - Monitor usage at [OpenAI Dashboard](https://platform.openai.com/usage)

## License

This project is provided as-is for educational and personal use.

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review error messages in the console
3. Verify your API credentials and configuration

---

**Happy Automating! 🚀**

