# Token Usage Analysis

## What's Eating Tokens

### 1. **Email Classification Prompt** (Lines 505-748 in `email_classifier.py`)
- **Size**: ~240 lines of detailed instructions
- **Content**:
  - Comprehensive classification rules
  - 11 few-shot examples
  - Edge case handling
  - Tie-breaker hierarchy
  - Input email JSON (subject, body, sender, links, attachments)
- **Input tokens per email**: ~2,000-3,000 tokens
  - Prompt: ~1,500-2,000 tokens
  - Email body (truncated to 2500 chars): ~500-1,000 tokens
  - JSON structure: ~100-200 tokens
- **Output tokens**: Max 300 tokens (JSON response)

### 2. **Reply Generation Prompts** (Lines 1038-1071, 1112-1131)
- **Deal Flow Reply** (when all basics present):
  - Prompt: ~500-800 tokens
  - Email context: ~500-1,000 tokens
  - Output: Max 250 tokens
- **Ask-More Reply** (when basics missing):
  - Prompt: ~300-500 tokens
  - Email context: ~500-1,000 tokens
  - Output: Max 200 tokens

### 3. **Per Email Token Breakdown**

**Classification:**
- Input: ~2,000-3,000 tokens
- Output: ~50-150 tokens (usually)
- **Total per email: ~2,050-3,150 tokens**

**Reply Generation (if needed):**
- Input: ~800-1,800 tokens
- Output: ~100-250 tokens
- **Total per reply: ~900-2,050 tokens**

**Total per email (with reply): ~2,950-5,200 tokens**

## Expected Output Format

### 1. **Classification Output** (JSON)
```json
{
  "label": "dealflow|hiring|networking|spam|general",
  "confidence": 0.0-1.0,
  "rationale": "2-4 short bullets, ≤250 chars, strictly text-grounded.",
  "signals": {
    "intent": "investment|job|meeting|malicious|info",
    "keywords": ["keyword1", "keyword2", ...],
    "entities": ["entity1", "entity2", ...],
    "attachments": ["attachment1.pdf", ...]
  }
}
```

### 2. **Reply Generation Output** (Plain Text)
- Professional email reply text
- No signature placeholders
- 3-5 sentences for acknowledgments
- 4-5 sentences for ask-more requests

## Token Optimization Opportunities

### Current Issues:
1. **Massive classification prompt** (~1,500-2,000 tokens)
   - Very comprehensive but verbose
   - Could be condensed while maintaining accuracy

2. **Email body truncation** (2500 chars)
   - Could be reduced to 1500-2000 chars for most emails
   - Only include first part before signatures/quotes

3. **Multiple API calls per email**
   - Classification: 1 call
   - Reply generation: 1 call (if needed)
   - Could potentially combine in some cases

### Recommendations:
1. **Shorten classification prompt** by:
   - Removing redundant examples
   - Condensing rules
   - Using more concise language
   - Target: Reduce from ~1,500 to ~800-1,000 tokens

2. **Reduce email body size**:
   - Truncate to 1500 chars instead of 2500
   - Better signature/quoted content removal
   - Target: Save ~200-400 tokens per email

3. **Optimize reply prompts**:
   - Make more concise
   - Remove redundant context
   - Target: Reduce by ~200-300 tokens

4. **Total potential savings**: ~1,000-1,500 tokens per email
   - For 200 emails: ~200,000-300,000 tokens saved

## Current Token Usage Estimate

**For 200 emails:**
- Classification: 200 × 2,500 avg = **500,000 tokens**
- Replies (if 50% need replies): 100 × 1,500 avg = **150,000 tokens**
- **Total: ~650,000 tokens**

**With optimizations:**
- Classification: 200 × 1,500 avg = **300,000 tokens**
- Replies: 100 × 1,200 avg = **120,000 tokens**
- **Total: ~420,000 tokens** (35% reduction)

