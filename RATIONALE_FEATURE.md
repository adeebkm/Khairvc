# Classification Rationale Feature

## Overview
This feature adds AI-generated explanations for why each email was classified into its category. Users can now understand the reasoning behind classifications, improving transparency and trust in the system.

## What Was Added

### 1. Database Changes
- **New column**: `rationale` (TEXT) added to `email_classifications` table
- Stores the AI-generated explanation from OpenAI/Lambda

### 2. Backend Changes (`app.py`)
- Classification storage now saves the `rationale` field from AI responses
- API endpoints return `rationale` with email classification data
- Two storage locations updated:
  - Fresh email classification storage (line ~857)
  - Manual reclassification storage (line ~1373)
- Two API response locations updated:
  - Fresh fetch response (line ~1017)
  - Database load response (line ~652)

### 3. Frontend Changes (`static/js/app.js`)
- Added `rationale` extraction from classification data (line ~1089)
- Created info icon (ℹ️) next to category badges when rationale exists (line ~1092)
- Added `showRationaleModal()` function to display rationale in a popup (line ~2244)
- Modal shows the full rationale text with proper formatting

### 4. Styling (`static/css/style.css`)
- Added `.rationale-icon` class for the info icon
- Hover effects: opacity change and scale animation
- Responsive and accessible design

## How It Works

1. **Classification**: When Lambda classifies an email, it generates a `rationale` field explaining the decision
2. **Storage**: The backend stores this rationale in the database alongside other classification data
3. **Display**: The frontend shows a small ℹ️ icon next to the category badge
4. **Interaction**: Users can:
   - **Hover** over the icon to see a tooltip (browser default)
   - **Click** the icon to open a modal with the full explanation

## Example Rationales

### DEALFLOW
> "Founder pitching their startup, mentions raising a round, includes deck attachment. Explicitly seeks YOUR investment in a specific company."

### NETWORKING
> "Event invitation to attend 'Founder Presentation Series' where multiple startups will pitch. You are attending to see pitches, not being directly pitched to."

### GENERAL
> "Meeting summary from Lyra automated tool. This is YOUR OWN internal documentation, not an external pitch or networking opportunity."

### SPAM
> "Suspicious sender domain, contains phishing indicators, no legitimate business purpose."

## User Benefits

1. **Transparency**: Understand why emails are categorized
2. **Trust**: Verify that the AI classification is correct
3. **Learning**: See patterns in how different emails are classified
4. **Debugging**: Quickly identify and report misclassifications

## Technical Details

- **Database**: Column automatically created on Railway deploy (SQLAlchemy migration)
- **Performance**: No impact - rationale is generated during classification (no extra API calls)
- **Privacy**: Rationale is stored in the database (same privacy as other classification data)
- **Backward Compatibility**: Works with existing classifications (shows empty for old emails without rationale)

## Deployment

✅ **Deployed to Railway**: Changes pushed to GitHub, Railway auto-deploys
✅ **Database Migration**: SQLAlchemy creates the `rationale` column on startup
✅ **Local Testing**: Tested locally with SQLite database

## Future Enhancements

- Add ability to provide feedback on rationale accuracy
- Use rationale feedback to improve classification prompts
- Show rationale trends for better insights

