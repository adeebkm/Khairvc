# Web Frontend Guide

## Overview

The web frontend provides an easy-to-use interface for managing Gmail auto-replies with AI. No more command-line - everything is visual and interactive!

## Features

✨ **Visual Email Management**
- View all unread emails in a clean, modern interface
- Click to see full email content
- Beautiful, responsive design that works on desktop and mobile

🤖 **Interactive AI Replies**
- Click a button to generate AI-powered replies
- Edit replies before sending
- Preview exactly what will be sent

⚡ **Real-time Actions**
- Send replies with one click
- Mark emails as read without replying
- Instant feedback on all actions

🎨 **Modern UI/UX**
- Beautiful gradient design
- Smooth animations and transitions
- Mobile-responsive layout
- Loading indicators for all async actions

## Quick Start

### 1. Install Dependencies

If you haven't already:
```bash
pip install -r requirements.txt
```

### 2. Make Sure Your Configuration is Ready

You need:
- ✓ `.env` file with your OpenAI API key
- ✓ `credentials.json` from Google Cloud Console
- ✓ Gmail authentication (run `python auto_reply.py` once to authenticate)

### 3. Start the Web Server

```bash
python app.py
```

You'll see:
```
============================================================
Gmail Auto-Reply Web Interface
============================================================

Starting web server...
Open your browser to: http://localhost:5000

Press Ctrl+C to stop the server
============================================================
```

### 4. Open Your Browser

Navigate to: **http://localhost:5000**

## Using the Web Interface

### Home Screen

When you first open the app, you'll see:
- **Header**: Project title and branding
- **Config Bar**: Shows if email sending is enabled and max emails setting
- **Controls**: Buttons to fetch emails and refresh config
- **Email List**: Will populate when you fetch emails

### Fetching Emails

1. Click the **"🔄 Fetch Emails"** button
2. The app will retrieve unread emails from your Gmail
3. You'll see a count of how many emails were found
4. Each email appears as a card showing:
   - Subject
   - Sender
   - Preview snippet

### Viewing an Email

1. Click on any email card
2. A modal window opens showing:
   - Full subject line
   - Sender information
   - Complete email body
   - AI reply section

### Generating a Reply

1. In the email modal, click **"🤖 Generate Reply"**
2. AI analyzes the email and generates a response
3. The reply appears in a highlighted box
4. Three options become available:
   - **✉️ Send Reply** - Send the AI-generated response
   - **✏️ Edit** - Modify the reply before sending
   - **✓ Mark as Read (Skip)** - Skip without replying

### Editing a Reply

1. Click **"✏️ Edit"** button
2. A text editor appears with the AI reply
3. Make your changes
4. Click **"💾 Save Edit"** to save your changes
5. Then click **"✉️ Send Reply"** to send

### Sending a Reply

1. Click **"✉️ Send Reply"**
2. Confirm the action in the popup
3. The reply is sent to the original sender
4. Email is automatically marked as read
5. Email is removed from your list
6. Success notification appears

**Note**: Sending only works if `SEND_EMAILS=true` in your `.env` file!

### Skipping an Email

1. Click **"✓ Mark as Read (Skip)"**
2. Confirm the action
3. Email is marked as read (without sending a reply)
4. Email is removed from your list

## Configuration Panel

At the top of the page, you'll see your current settings:

- **Email Sending**: 
  - 🟢 "Enabled ✓" - Replies will actually be sent
  - 🟡 "Disabled (Test Mode)" - Replies won't be sent (for testing)

- **Max Emails**: Shows how many emails are fetched per request

To change these settings, edit your `.env` file and click **"⚙️ Refresh Config"**

## Test Mode vs Production

### Test Mode (Recommended First)
`.env` setting: `SEND_EMAILS=false`

In test mode:
- ✓ Generate and view AI replies
- ✓ Edit replies
- ✗ Cannot actually send emails
- ✓ Can mark as read

**Perfect for**: Testing the system, reviewing AI quality

### Production Mode
`.env` setting: `SEND_EMAILS=true`

In production mode:
- ✓ All test mode features
- ✓ Actually send email replies
- ✓ Confirmation prompts before sending

**Use when**: You're confident with the AI replies

## API Endpoints

The web app uses these REST API endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main web interface |
| `/api/emails` | GET | Fetch unread emails |
| `/api/generate-reply` | POST | Generate AI reply |
| `/api/send-reply` | POST | Send email reply |
| `/api/mark-read` | POST | Mark email as read |
| `/api/config` | GET | Get current configuration |

## Keyboard Shortcuts

- **ESC** - Close the email modal

## Mobile Support

The interface is fully responsive and works great on:
- 📱 Phones
- 📱 Tablets
- 💻 Laptops
- 🖥️ Desktops

All features work the same across devices!

## Troubleshooting

### "Failed to fetch emails"

**Possible causes:**
1. Gmail authentication not set up
   - Run `python auto_reply.py` once to authenticate
2. Server not running
   - Make sure `python app.py` is running
3. No internet connection

### "Failed to send reply"

**Possible causes:**
1. `SEND_EMAILS=false` in `.env`
   - Change to `true` if you want to send
2. Gmail API error
   - Check console for details
3. Invalid email address

### Web page won't load

**Solutions:**
1. Make sure server is running: `python app.py`
2. Try accessing: `http://127.0.0.1:5000`
3. Check firewall settings
4. Make sure port 5000 is not in use

### AI reply generation fails

**Possible causes:**
1. Invalid OpenAI API key in `.env`
2. Insufficient API credits
3. Network issues

Check browser console (F12) for detailed error messages.

## Running on a Different Port

By default, the app runs on port 5000. To change:

Edit `app.py` and modify the last line:
```python
app.run(debug=True, host='0.0.0.0', port=8000)  # Change 8000 to your preferred port
```

## Running in Production

For production deployment, don't use Flask's development server. Use a production WSGI server like Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Security Notes

⚠️ **Important:**
- The web interface runs locally by default
- Don't expose to the internet without proper authentication
- Keep your `.env` file secure
- Use HTTPS if deploying publicly

## Architecture

```
Browser (HTML/CSS/JS)
      ↕
Flask Web Server (app.py)
      ↕
Gmail Client (gmail_client.py) + OpenAI Client (openai_client.py)
      ↕
Gmail API + OpenAI API
```

## File Structure

```
gmail openai/
├── app.py                    # Flask web server
├── templates/
│   └── index.html           # HTML template
├── static/
│   ├── css/
│   │   └── style.css        # Styles
│   └── js/
│       └── app.js           # JavaScript logic
├── gmail_client.py          # Gmail integration
└── openai_client.py         # OpenAI integration
```

## Tips for Best Experience

1. **Start in Test Mode**: Get familiar with the interface before enabling sending
2. **Review AI Replies**: Always review before sending, use the edit feature
3. **Refresh Regularly**: Click "Fetch Emails" to get new messages
4. **Use Filters**: The AI automatically filters spam - trust it!
5. **Stay Organized**: Process emails regularly to keep inbox clean

## Customization

### Changing Colors

Edit `static/css/style.css` and modify the gradient:
```css
background: linear-gradient(135deg, #YOUR_COLOR_1 0%, #YOUR_COLOR_2 100%);
```

### Changing AI Behavior

Edit `openai_client.py` to modify:
- Reply tone and style
- Spam detection rules
- Model parameters

### Adding Features

The modular architecture makes it easy to add:
- Email filters
- Custom templates
- Analytics dashboard
- Scheduling system
- Multi-account support

## Support

Having issues? Check:
1. Browser console (F12) for JavaScript errors
2. Terminal where `app.py` is running for server errors
3. `README.md` for general setup help
4. `setup_guide.md` for initial configuration

---

**Enjoy your beautiful Gmail auto-reply interface! 🚀**

