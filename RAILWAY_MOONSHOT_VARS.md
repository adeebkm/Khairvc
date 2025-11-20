# Railway Environment Variables for Moonshot (Test Environment)

## Required Variables

Set these in Railway for the **test environment**:

### 1. `USE_MOONSHOT`
- **Value**: `true`
- **Type**: String (case-insensitive, but use lowercase)
- **Purpose**: Enables Moonshot API usage instead of OpenAI
- **Used by**: `openai_client.py`, `email_classifier.py`

### 2. `MOONSHOT_API_KEY` (Recommended)
- **Value**: `sk-8ePPoLg8vofcVFhVIWWLDzkN10Awq1D4VcIslxWvZAqQz4qD`
- **Type**: String
- **Purpose**: Moonshot API key for authentication
- **Used by**: `openai_client.py` (primary)

### 3. `OPENAI_API_KEY` (Fallback)
- **Value**: `sk-8ePPoLg8vofcVFhVIWWLDzkN10Awq1D4VcIslxWvZAqQz4qD`
- **Type**: String
- **Purpose**: Used as fallback if `MOONSHOT_API_KEY` is not set
- **Used by**: `openai_client.py` (fallback), `email_classifier.py` (for fallback classification)

## How It Works

1. **When `USE_MOONSHOT=true`**:
   - `openai_client.py` uses Moonshot API with `kimi-k2-thinking` model
   - `email_classifier.py` uses `kimi-k2-thinking` for fallback classification
   - API key is read from `MOONSHOT_API_KEY` (or `OPENAI_API_KEY` as fallback)

2. **When `USE_MOONSHOT` is not set or `false`**:
   - Uses OpenAI API with `gpt-4o-mini` model
   - API key is read from `OPENAI_API_KEY`

## Railway Setup Instructions

1. Go to Railway → Your Test Environment → Variables
2. Add/Update these variables:

```
USE_MOONSHOT = true
MOONSHOT_API_KEY = sk-8ePPoLg8vofcVFhVIWWLDzkN10Awq1D4VcIslxWvZAqQz4qD
OPENAI_API_KEY = sk-8ePPoLg8vofcVFhVIWWLDzkN10Awq1D4VcIslxWvZAqQz4qD
```

**Note**: You can set both `MOONSHOT_API_KEY` and `OPENAI_API_KEY` to the same value, or just set `OPENAI_API_KEY` (it will be used as fallback).

## Verification

After setting variables, check the logs:
- Should see: `✓ Moonshot (Kimi) client initialized`
- Should NOT see: `✓ OpenAI client initialized`

