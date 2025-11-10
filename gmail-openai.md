# Gmail OpenAI Auto-Reply Project Documentation

## Project Overview

An automated email reply system that integrates Gmail with OpenAI's GPT models to intelligently read emails and generate contextual, professional responses.

## Architecture

### Components

1. **Gmail Client** (`gmail_client.py`)
   - Handles OAuth 2.0 authentication
   - Fetches unread emails
   - Sends reply emails
   - Marks emails as read
   - Manages email threads

2. **OpenAI Client** (`openai_client.py`)
   - Generates AI-powered email replies
   - Analyzes emails to determine if they need replies
   - Filters spam and automated messages

3. **Main Automation Script** (`auto_reply.py`)
   - Orchestrates the workflow
   - Processes emails in batch
   - Handles configuration
   - Provides test mode

4. **Web Application** (`app.py`) - NEW!
   - Flask-based web server
   - REST API endpoints
   - Web interface for email management
   - Real-time AI reply generation
   - Interactive email viewer

5. **Frontend** (`templates/` and `static/`)
   - Modern, responsive HTML/CSS interface
   - JavaScript for interactive features
   - Beautiful gradient design
   - Mobile-friendly layout

6. **Configuration** (`config.py`)
   - Manages environment variables
   - Validates API keys
   - Stores application settings

## System Flow

```
Start
  ↓
Initialize Gmail & OpenAI Clients
  ↓
Fetch Unread Emails (up to MAX_EMAILS)
  ↓
For Each Email:
  ↓
  Analyze with AI → Should Reply?
  ↓              ↓
  No            Yes
  ↓              ↓
  Mark Read     Generate AI Reply
                 ↓
                 Send (if SEND_EMAILS=true) or Preview
                 ↓
                 Mark as Read
  ↓
End
```

## Dependencies

### Python Packages
- `google-auth-oauthlib` (1.2.0) - Gmail OAuth authentication
- `google-auth-httplib2` (0.2.0) - HTTP library for Google APIs
- `google-api-python-client` (2.108.0) - Gmail API client
- `openai` (1.51.0) - OpenAI API client
- `python-dotenv` (1.0.0) - Environment variable management

## Configuration Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPENAI_API_KEY` | string | (required) | OpenAI API key |
| `SEND_EMAILS` | boolean | `false` | Enable actual email sending |
| `MAX_EMAILS` | integer | `5` | Max emails per run |
| `UNREAD_ONLY` | boolean | `true` | Process only unread emails |

## API Integrations

### Gmail API
- **Scope**: `https://www.googleapis.com/auth/gmail.modify`
- **Permissions**: Read, send, and modify emails
- **Authentication**: OAuth 2.0 with Desktop app flow
- **Files**:
  - `credentials.json` - OAuth client credentials (from Google Cloud Console)
  - `token.json` - User authentication token (auto-generated after first auth)

### OpenAI API
- **Model**: `gpt-4o-mini` (cost-effective)
- **Temperature**: 0.7 (balanced creativity)
- **Max Tokens**: 500 (reply length limit)
- **Features Used**:
  - Email reply generation
  - Spam/newsletter detection
  - Context-aware responses

## Security Considerations

1. **Credentials Storage**:
   - All sensitive files in `.gitignore`
   - Environment variables for API keys
   - OAuth tokens stored locally only

2. **Gmail Permissions**:
   - Minimal scope (no delete permissions)
   - User can revoke anytime from Google Account
   - OAuth flow requires explicit user consent

3. **Test Mode**:
   - Default to `SEND_EMAILS=false`
   - Preview all generated replies before sending
   - Mark emails as read without sending

## Error Handling

- **Gmail API Errors**: Graceful failure with error messages
- **OpenAI API Errors**: Falls back to not replying
- **Authentication Errors**: Clear instructions for re-authentication
- **Missing Configuration**: Validation on startup

## Features Implemented

✅ OAuth 2.0 Gmail authentication  
✅ Fetch unread emails from inbox  
✅ AI-powered reply generation  
✅ Spam/newsletter filtering  
✅ Thread-aware replies  
✅ Test mode (preview without sending)  
✅ Configurable behavior via environment variables  
✅ Automatic email marking as read  
✅ Professional, context-aware responses  
✅ Cost-effective model selection  
✅ **Web interface with REST API** (NEW!)  
✅ **Interactive email viewer** (NEW!)  
✅ **Real-time AI reply generation in browser** (NEW!)  
✅ **Mobile-responsive design** (NEW!)  
✅ **Edit replies before sending** (NEW!)  

## Usage Patterns

### Development/Testing
```bash
# .env configuration
SEND_EMAILS=false
MAX_EMAILS=2

# Run
python auto_reply.py
```

### Production
```bash
# .env configuration
SEND_EMAILS=true
MAX_EMAILS=10

# Run manually or via cron
python auto_reply.py
```

### Automated (Cron)
```bash
# Check every hour
0 * * * * cd /path/to/project && python auto_reply.py >> log.txt 2>&1
```

## Future Enhancements

Potential improvements:
- Web dashboard for monitoring
- Custom reply templates
- Email categorization and routing
- Multi-account support
- Reply approval workflow
- Analytics and reporting
- Integration with other email providers
- Custom AI prompt templates
- Database logging
- Webhook support

## File Structure

```
/Users/adeebkhaja/Documents/gmail openai/
├── auto_reply.py              # Main automation script (CLI)
├── app.py                     # Flask web application (NEW!)
├── gmail_client.py            # Gmail API wrapper
├── openai_client.py           # OpenAI API wrapper
├── config.py                  # Configuration management
├── requirements.txt           # Python dependencies (includes Flask)
├── README.md                  # User documentation
├── setup_guide.md            # Quick setup instructions
├── WEB_APP_GUIDE.md          # Web interface guide (NEW!)
├── gmail-openai.md           # This file (project documentation)
├── setup.py                   # Interactive setup helper
├── test_setup.py             # Setup verification script
├── .gitignore                 # Git ignore rules
├── .env                       # Environment variables (user creates)
├── env_template.txt          # Environment template
├── credentials.json           # Gmail OAuth credentials (user downloads)
├── token.json                 # Gmail auth token (auto-generated)
├── templates/                 # HTML templates (NEW!)
│   └── index.html            # Main web interface
└── static/                    # Static files (NEW!)
    ├── css/
    │   └── style.css         # Styles and design
    └── js/
        └── app.js            # JavaScript logic
```

## Milestones

### Phase 1: Core Functionality ✅
- Gmail API integration
- OpenAI integration
- Basic auto-reply workflow
- Test mode

### Phase 2: Documentation ✅
- Comprehensive README
- Quick setup guide
- Project documentation
- Code comments

### Phase 3: Production Ready ✅
- Error handling
- Configuration validation
- Security best practices
- Test mode by default

## Cost Analysis

### Gmail API
- **Cost**: Free
- **Limits**: 
  - 1 billion quota units per day
  - Read: 5 units per request
  - Send: 100 units per request
  - Typical usage: ~1,000 emails/day well within limits

### OpenAI API (using gpt-4o-mini)
- **Input**: ~$0.15 per 1M tokens
- **Output**: ~$0.60 per 1M tokens
- **Per Email Estimate**: $0.01-0.05
- **100 emails/day**: ~$1-5/day

## Maintenance Notes

- **Token Expiry**: OAuth tokens refresh automatically
- **API Updates**: Pin dependency versions in `requirements.txt`
- **Logs**: Consider adding file logging for production
- **Monitoring**: Check OpenAI usage dashboard regularly

## Version History

### v1.0 (Initial Release)
- Gmail authentication and email reading
- OpenAI-powered reply generation
- Spam filtering
- Test mode
- Complete documentation

---

*Last Updated: November 3, 2025*

