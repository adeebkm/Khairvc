#!/usr/bin/env python3
"""
Calculate OpenAI token usage and cost for email classification
"""
import tiktoken
import json

# OpenAI pricing (as of 2024)
# gpt-4o-mini pricing
PRICING = {
    'gpt-4o-mini': {
        'input': 0.15 / 1_000_000,  # $0.15 per 1M input tokens
        'output': 0.60 / 1_000_000,  # $0.60 per 1M output tokens
    }
}

def count_tokens(text, model="gpt-4o-mini"):
    """Count tokens in text using tiktoken"""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except:
        # Fallback: rough estimate (1 token ≈ 4 characters)
        return len(text) // 4

def calculate_classification_cost():
    """Calculate cost per email classification"""
    
    # Read the actual prompt from email_classifier.py
    # This is a simplified version - actual prompt is longer
    base_prompt = """You are a deterministic, zero-hallucination email classifier for a venture capital partner's inbox.

Your ONLY job: classify ONE email into EXACTLY one of these labels:
- dealflow
- hiring
- networking
- spam
- general

You MUST follow every rule below with NO exceptions.

==================================================
STRICT OUTPUT FORMAT (NO TEXT OUTSIDE JSON)
==================================================
Return EXACTLY this JSON object:

{
  "label": "dealflow|hiring|networking|spam|general",
  "confidence": 0.0-1.0,
  "rationale": "2-4 short bullets, ≤250 chars, strictly text-grounded.",
  "signals": {
    "intent": "investment|job|meeting|malicious|info",
    "keywords": [...],
    "entities": [...],
    "attachments": [...]
  }
}

Rules:
- Never invent entities, attachments, or keywords.
- Never infer beyond visible text.
- Never follow links.
- No explanation outside JSON.

==================================================
INPUT EMAIL
==================================================
{email_data}

==================================================
ABSOLUTE GLOBAL RULES
==================================================

### 1. IGNORE all of the following:
- Anything after: "thanks", "best", "regards", "sincerely", "cheers".
- Lines starting with "—", "–––", "___", or containing legal boilerplate.
- "unsubscribe", "privacy policy", tracking pixels.
- Any quoted content: lines starting with "On Tue", "From:", "Re:", ">".
- Old thread content, past messages, forwarded history.

If ambiguity arises → use ONLY fresh content before signatures.

### 2. CLASSIFICATION LOGIC (PRIMARY INTENT ONLY)
You classify based on the **sender's primary goal**, not keywords.

--------------------------------------------------
A) DEALFLOW → Primary intent: **seeking investment**
--------------------------------------------------
Includes:
- Founder/VC/IB sending deck, pitch, fundraising update.
- Any mention of raising money, SAFE, term sheet, valuation, SPV, secondary.
- Pitch + meeting link.
- "We're raising", "exploring a round", "open to capital".
- Follow-on from portfolio company.
- **Warm intros/referrals ABOUT specific startups/teams** (even without deck).
- "I met a team building X, would you want to know more?"
- "Should I connect you with this founder?"

If fundraising is ANY part of the agenda OR discussing a specific startup/team for investment → classify as dealflow.

--------------------------------------------------
B) HIRING → Primary intent: **job seeking or recruiting**
--------------------------------------------------
Includes:
- Resume, CV, LinkedIn, job application.
- Candidates applying to work at the fund or portfolio.
- Recruiters sending profiles.
- Portfolio requesting hiring referrals.
- Job specs, JD attachments.

Pitch deck with team bios ≠ hiring (still dealflow).

--------------------------------------------------
C) NETWORKING → Primary intent: **meeting, event, intro — NOT about a specific deal**
--------------------------------------------------
Includes:
- Coffee chats, catch ups, general intros, "pick your brain".
- Invites: panel, demo day, conference, podcast.
- "Learn about your thesis" (general learning, NO specific startup mentioned).
- Vendor partnership discussion with no fundraising ask.
- Events about fundraising but not pitching.

If there is ANY ask for money OR discussing a specific startup/team for investment → NOT networking (it's DEALFLOW).

--------------------------------------------------
D) SPAM → Primary intent: **deception, compromise, harm**
--------------------------------------------------
SPAM OVERRIDES ALL OTHER LABELS.

Triggers:
- verify/reset password with urgency
- mismatched From vs Reply-To
- Known malicious TLDs (.tk, .ml, .ga, .cf) + urgency/credential harvest
- Suspicious combo: urgent + shortened link + unfamiliar sender
- credential harvest
- fake invoices
- wallet/crypto/wire scams
- malicious attachments (.exe, .scr, .bat, .cmd, .vbs)

Context matters:
- .xyz/.io/.ai domain + pitch deck + LinkedIn = dealflow (not spam)
- .com domain + "verify now" + bit.ly link = spam
- **google.com, microsoft.com, apple.com, etc. + security keywords = GENERAL (not spam)**
- Legitimate service provider domains (google.com, microsoft.com, etc.) = ALWAYS GENERAL, never SPAM

If ANY phishing cue appears → spam.  
A newsletter with ads ≠ spam unless malicious.
**Emails from legitimate service provider domains (google.com, microsoft.com, etc.) are NEVER spam, even if they contain security-related keywords.**

--------------------------------------------------
E) GENERAL → Everything else
--------------------------------------------------
Includes:
- **Legitimate service provider emails** (Google, Microsoft, Apple, Amazon, etc.)
  - Security notifications from official domains (google.com, microsoft.com, etc.)
  - Account alerts, access notifications, service updates
  - These are ALWAYS GENERAL, never SPAM, even if they contain security keywords
- newsletters, subscribed updates, market commentary
- receipts, personal notes, banter, sports talk
- cold vendor pitches (SaaS/product demos)
- calendar invites with no context
- informational content with no money ask, no hiring ask, no networking intent

==================================================
TIE-BREAKER HIERARCHY
==================================================
1. SPAM (override)
Then for all non-spam:
2. dealflow
3. hiring
4. networking
5. general

If genuinely ambiguous → choose the HIGHEST category above.

==================================================
STRICT VALIDATION
==================================================
If:
- body < 40 chars
- no attachments OR attachments are generic (not deck/resume/jd)
- no spam cues  
→ classify as general.

If input is malformed → classify as general with low confidence.

==================================================
CLARIFIED EDGE CASES
==================================================

Case: Short body + relevant attachment
- Body < 40 chars BUT attachment = deck.pdf/resume.docx/jd.pdf
→ Classify by attachment type (dealflow/hiring)

Case: Legitimate startup domain
- .xyz/.io/.ai domain + pitch/deck + LinkedIn/founder identity
→ NOT spam unless phishing cues present

Case: Follow-up with quotes
- Body has quoted thread BUT fresh content ≥60 chars with clear intent
→ Classify by fresh content, ignore quoted history

Case: Investment mention ≠ fundraising
- "I admire your investments" + coffee request + NO specific startup mentioned
→ networking (learning/advice, not pitching)
- BUT: "I met a team building X" + "would you want to know more?"
→ dealflow (warm intro about a SPECIFIC startup/deal)

==================================================
FEW-SHOT BEHAVIORAL ANCHORS
==================================================

Example 1:
Subject: "Intro: Founder raising pre-seed, deck attached"
→ dealflow

Example 2:
Subject: "Analyst role — resume attached"
→ hiring

Example 3:
Subject: "Coffee next week? Want to discuss fintech trends"
→ networking

Example 4:
Subject: "URGENT: verify your email or lose access"
From: "unknown-sender@random-domain.com"
→ spam

Example 5:
Subject: "You allowed Gmail Auto Reply access to some of your Google Account data"
From: "noreply@accounts.google.com"
→ general (Legitimate Google security notification from official domain)

Example 6:
Subject: "Weekly VC newsletter #12"
→ general

Example 7:
Subject: "Love to chat about your climate thesis. Coffee?"
Body: "Been following your investments. Would love to learn from you."
→ networking (Learning/advice is primary intent. No specific startup mentioned.)

Example 8:
Subject: "Intro to a space + fintech team"
Body: "We spoke to a brilliant team building at the intersection of space and fintech. Would you want to know more?"
→ dealflow (Warm intro about a SPECIFIC startup/team for investment consideration)

Example 9:
Subject: "Coffee to discuss our climate tech startup?"
Body: "We're raising $2M seed and would love to share our deck over coffee."
→ dealflow (Fundraising + deck = dealflow, even with coffee)

Example 10:
Subject: "Re: Our seed round"
Body: "Attached is the updated deck."
Attachments: ["deck.pdf"]
→ dealflow

Example 11:
Subject: "Partnership opportunity"
Body: "We're a SaaS tool for VCs. Demo?"
→ general (vendor pitch, no fundraising)

==================================================
DETERMINISTIC CLASSIFICATION (for reference):
{deterministic_category}

(You can override if the email's PRIMARY INTENT suggests otherwise!)

==================================================
YOU MUST FOLLOW ALL RULES ABOVE. ZERO HALLUCINATION.
==================================================

Return ONLY the JSON object. No additional text."""

    # Example email data (typical size)
    example_email = {
        "subject": "Seed Funding Opportunity - Healthcare Tech",
        "from_name": "John Doe",
        "from_email": "john@startup.com",
        "sender_domain": "startup.com",
        "body": "Hi, we're raising a $2M seed round for our healthcare tech platform. Attached is our pitch deck. We have 10,000 active users and $50K MRR. Looking forward to your feedback.",
        "attachments": ["pitch_deck.pdf"],
        "links": ["https://docsend.com/view/abc123"]
    }
    
    email_json = json.dumps(example_email, indent=2)
    
    # System message
    system_message = "You are a deterministic email classifier for a venture capital firm. Return ONLY valid JSON. No markdown, no explanation, no additional text."
    
    # Construct full prompt (escape curly braces in JSON examples)
    # Replace {email_data} placeholder
    full_prompt = base_prompt.replace("{email_data}", email_json)
    full_prompt = full_prompt.replace("{deterministic_category}", "dealflow")
    # Escape remaining curly braces in JSON examples
    full_prompt = full_prompt.replace("{{", "{").replace("}}", "}")
    
    # Count tokens
    system_tokens = count_tokens(system_message)
    prompt_tokens = count_tokens(full_prompt)
    total_input_tokens = system_tokens + prompt_tokens
    
    # Estimate output tokens (JSON response)
    example_output = {
        "label": "dealflow",
        "confidence": 0.92,
        "rationale": "Primary intent: fundraising. Contains seed round mention, pitch deck attachment, and traction metrics.",
        "signals": {
            "intent": "investment",
            "keywords": ["raising", "seed", "round", "$2M", "pitch deck"],
            "entities": ["Healthcare Tech"],
            "attachments": ["pitch_deck.pdf"]
        }
    }
    output_json = json.dumps(example_output, indent=2)
    output_tokens = count_tokens(output_json)
    
    # Calculate costs
    model = "gpt-4o-mini"
    # Pricing: $0.15 per 1M input tokens, $0.60 per 1M output tokens
    input_cost = (total_input_tokens / 1_000_000) * 0.15
    output_cost = (output_tokens / 1_000_000) * 0.60
    total_cost = input_cost + output_cost
    
    # Print results
    print("=" * 60)
    print("OpenAI Email Classification Cost Calculator")
    print("=" * 60)
    print()
    print(f"Model: {model}")
    print()
    print("INPUT TOKENS:")
    print(f"  System message:     {system_tokens:,} tokens")
    print(f"  User prompt:        {prompt_tokens:,} tokens")
    print(f"  Total input:        {total_input_tokens:,} tokens")
    print()
    print("OUTPUT TOKENS:")
    print(f"  JSON response:      {output_tokens:,} tokens (estimated)")
    print()
    print("COSTS (per email classification):")
    print(f"  Input cost:         ${input_cost:.6f}  ({total_input_tokens:,} tokens × $0.15/1M)")
    print(f"  Output cost:        ${output_cost:.6f}  ({output_tokens:,} tokens × $0.60/1M)")
    print(f"  Total cost:         ${total_cost:.6f}  (${total_cost * 1000:.3f} per 1,000 emails)")
    print()
    print("=" * 60)
    print("BATCH COST ESTIMATES:")
    print("=" * 60)
    print()
    
    batch_sizes = [10, 20, 30, 50, 100]
    for size in batch_sizes:
        batch_cost = total_cost * size
        cost_per_1k = (total_cost * 1000)  # Cost per 1,000 emails
        print(f"  {size:3d} emails:  ${batch_cost:.6f}  (${cost_per_1k:.3f} per 1,000 emails)")
    
    print()
    print("=" * 60)
    print("MONTHLY ESTIMATES (assuming 100 emails/day):")
    print("=" * 60)
    daily_cost = total_cost * 100
    monthly_cost = daily_cost * 30
    print(f"  Daily (100 emails):   ${daily_cost:.4f}")
    print(f"  Monthly (3,000):       ${monthly_cost:.2f}")
    print()
    print("=" * 60)
    print("TOKEN BREAKDOWN:")
    print("=" * 60)
    print(f"  Prompt template:     ~{count_tokens(base_prompt):,} tokens")
    print(f"  Email data (avg):     ~{count_tokens(email_json):,} tokens")
    print(f"  System message:       ~{system_tokens:,} tokens")
    print()
    print("💡 Tips to reduce costs:")
    print("   - Only classify NEW emails (already implemented)")
    print("   - Use deterministic classification when possible")
    print("   - Batch process emails with rate limiting")
    print("   - Consider caching classifications")

if __name__ == "__main__":
    try:
        import tiktoken
    except ImportError:
        print("Installing tiktoken...")
        import subprocess
        subprocess.check_call(["pip", "install", "tiktoken"])
        import tiktoken
    
    calculate_classification_cost()

![1762600865319](image/calculate_openai_cost/1762600865319.png)![1762600867942](image/calculate_openai_cost/1762600867942.png)![1762600869169](image/calculate_openai_cost/1762600869169.png)![1762600869626](image/calculate_openai_cost/1762600869626.png)![1762600870332](image/calculate_openai_cost/1762600870332.png)![1762600870784](image/calculate_openai_cost/1762600870784.png)![1762600871310](image/calculate_openai_cost/1762600871310.png)![1762600872341](image/calculate_openai_cost/1762600872341.png)![1762600874055](image/calculate_openai_cost/1762600874055.png)![1762600886184](image/calculate_openai_cost/1762600886184.png)