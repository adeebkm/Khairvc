# 🚀 Quick Start - Web Interface

Get your Gmail Auto-Reply web interface running in **5 minutes**!

## Prerequisites Checklist

Before starting, make sure you have:
- [ ] Python 3.8+ installed
- [ ] OpenAI API key
- [ ] Gmail account
- [ ] Completed basic setup (credentials.json and .env)

If you haven't done the basic setup yet, run:
```bash
python setup.py
```

## Step 1: Install Flask

If you already ran `pip install -r requirements.txt`, you're good to go!

If not:
```bash
pip install flask
```

## Step 2: Start the Web Server

```bash
python app.py
```

You should see:
```
============================================================
Gmail Auto-Reply Web Interface
============================================================

Starting web server...
Open your browser to: http://localhost:5000

Press Ctrl+C to stop the server
============================================================
```

## Step 3: Open in Browser

Open your web browser and go to:
```
http://localhost:5000
```

## Step 4: Use the Interface

### First Time?

1. Click **"🔄 Fetch Emails"**
2. If prompted, authenticate with Gmail (browser will open)
3. Your emails will appear!

### View and Reply to Emails

1. **Click on any email card** to open it
2. Click **"🤖 Generate Reply"** to create an AI response
3. **Review the reply** - looks good?
4. Click **"✉️ Send Reply"** to send (or **"✏️ Edit"** to modify first)

### Skip an Email

Don't want to reply? Click **"✓ Mark as Read (Skip)"**

## Important Notes

### Test Mode

By default, `SEND_EMAILS=false` in your `.env` file. This means:
- ✅ You can generate replies
- ✅ You can see what would be sent
- ❌ Emails won't actually be sent

To enable sending, edit `.env`:
```
SEND_EMAILS=true
```

Then click **"⚙️ Refresh Config"** in the web interface.

### Configuration

Your configuration is shown at the top of the page:
- **Email Sending**: Shows if emails will actually be sent
- **Max Emails**: How many emails are fetched at once

## Common Issues

### Port Already in Use

If port 5000 is taken, edit `app.py` and change the port:
```python
app.run(debug=True, host='0.0.0.0', port=8000)
```

### Can't Fetch Emails

1. Make sure you ran `python auto_reply.py` at least once to authenticate
2. Check that `credentials.json` exists
3. Check that `token.json` was created

### OpenAI Errors

1. Verify your API key in `.env`
2. Check you have credits at: https://platform.openai.com/account/usage
3. Try regenerating your API key

## Pro Tips

🎯 **Start in Test Mode**: Review AI replies for quality before enabling sending

🎨 **Mobile Friendly**: Open on your phone - it works great!

⌨️ **Keyboard Shortcut**: Press ESC to close the email modal

🔄 **Refresh Often**: Click "Fetch Emails" to check for new messages

✏️ **Edit Before Sending**: Always review and edit AI replies if needed

## What's Next?

Once you're comfortable with the interface:

1. **Enable Sending**: Set `SEND_EMAILS=true` in `.env`
2. **Process Emails**: Work through your inbox systematically
3. **Automate**: Keep the web server running or use the CLI with cron

## Need More Help?

- **Web Interface Details**: Read `WEB_APP_GUIDE.md`
- **General Setup**: Read `README.md`
- **Initial Configuration**: Read `setup_guide.md`

## Screenshots (What to Expect)

### Home Screen
- Clean, modern interface
- Purple gradient header
- Config bar showing your settings
- "Fetch Emails" button

### Email List
- Cards showing each email
- Subject, sender, and preview
- Click to open full email

### Email Modal
- Full email content
- "Generate Reply" button
- AI-generated response
- Options to send, edit, or skip

## Stop the Server

When done, press **Ctrl+C** in the terminal where `app.py` is running.

---

**Happy email managing! 📧✨**

Questions? Check the other documentation files or the code comments.

