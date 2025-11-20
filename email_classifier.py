"""
Email Classification System for VC Categories
Classifies emails into: Deal Flow, Networking, Hiring, Spam
"""
import re
import json
from typing import Dict, List, Tuple, Optional
from openai import OpenAI
import os

# Try to import Lambda client (optional - falls back to OpenAI if not available)
try:
    from lambda_client import LambdaClient
    LAMBDA_AVAILABLE = True
    print("✓ Lambda client module imported successfully")
except ImportError as e:
    LAMBDA_AVAILABLE = False
    LambdaClient = None
    print(f"⚠️  Lambda client module not available: {str(e)}")
except Exception as e:
    LAMBDA_AVAILABLE = False
    LambdaClient = None
    print(f"⚠️  Error importing Lambda client: {str(e)}")


# Category constants
CATEGORY_DEAL_FLOW = "DEAL_FLOW"
CATEGORY_NETWORKING = "NETWORKING"
CATEGORY_HIRING = "HIRING"
CATEGORY_SPAM = "SPAM"
CATEGORY_GENERAL = "GENERAL"

# Deal Flow states
STATE_NEW = "New"
STATE_ASK_MORE = "Ask-More"
STATE_ROUTED = "Routed"

# Tags
TAG_DEAL = "DF/Deal"
TAG_ASK_MORE = "DF/AskMore"
TAG_NETWORKING = "NW/Networking"
TAG_HIRING = "HR/Hiring"
TAG_SPAM = "SPAM/Skip"
TAG_GENERAL = "GEN/General"


class EmailClassifier:
    """Classify emails into VC categories using deterministic rules + OpenAI/Lambda"""
    
    def __init__(self, openai_client=None):
        self.openai_client = openai_client
        # Try to initialize Lambda client if available
        self.lambda_client = None
        if LAMBDA_AVAILABLE:
            try:
                self.lambda_client = LambdaClient()
                print("✓ Lambda client initialized")
            except Exception as e:
                print(f"⚠️  Lambda client initialization failed: {str(e)}")
                self.lambda_client = None
        else:
            print("⚠️  Lambda not available (module not imported)")
    
    def extract_links(self, text: str) -> List[str]:
        """Extract all URLs from email body"""
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]'
        urls = re.findall(url_pattern, text)
        return urls
    
    def check_legitimate_service_provider(self, sender: str) -> bool:
        """Check if email is from a legitimate service provider (Google, Microsoft, etc.)"""
        # Extract domain from sender email
        sender_lower = sender.lower()
        
        # Extract email domain
        if '@' in sender_lower:
            domain = sender_lower.split('@')[-1].strip('>').strip()
        else:
            domain = sender_lower
        
        # List of legitimate service provider domains
        legitimate_domains = [
            # Google services
            'google.com',
            'gmail.com',
            'googlemail.com',
            'accounts.google.com',
            'mail.google.com',
            'myaccount.google.com',
            'support.google.com',
            'noreply.google.com',
            # Microsoft services
            'microsoft.com',
            'outlook.com',
            'hotmail.com',
            'live.com',
            'msn.com',
            'office.com',
            'office365.com',
            'microsoftonline.com',
            # Apple services
            'apple.com',
            'icloud.com',
            'me.com',
            'mac.com',
            # Amazon services
            'amazon.com',
            'aws.amazon.com',
            'amazonaws.com',
            # Other major providers
            'github.com',
            'githubusercontent.com',
            'slack.com',
            'zoom.us',
            'stripe.com',
            'paypal.com',
            'salesforce.com',
            'hubspot.com',
        ]
        
        # Check if domain matches any legitimate provider
        for legit_domain in legitimate_domains:
            if domain == legit_domain or domain.endswith('.' + legit_domain):
                return True
        
        return False
    
    def check_security_threat(self, subject: str, body: str, headers: Dict[str, str], sender: str = '') -> bool:
        """Check if email is a security threat (phishing, malicious)"""
        # If from legitimate service provider, it's not spam (even if it has security keywords)
        if sender and self.check_legitimate_service_provider(sender):
            return False
        
        # Actual security threats - these are SPAM
        threat_indicators = [
            'verify your account',
            'urgent action required',
            'suspended account',
            'unusual activity',
            'confirm your identity',
            'click here immediately',
            'account will be closed',
            'wire transfer',
            'bitcoin',
            'cryptocurrency wallet',
            'claim your prize',
            'you have won',
            'inheritence',
            'nigerian prince'
        ]
        
        text = f"{subject} {body}".lower()
        
        # Check for phishing patterns
        for indicator in threat_indicators:
            if indicator in text:
                return True
        
        # Check for suspicious headers
        spam_score = headers.get('X-Spam-Score', '')
        if spam_score and float(spam_score.split('/')[0]) > 5:
            return True
        
        return False
    
    def check_noreply_sender(self, sender: str) -> bool:
        """Check if sender is a no-reply address or automated system"""
        noreply_patterns = [
            'noreply',
            'no-reply',
            'donotreply',
            'do-not-reply',
            'mailer-daemon',
            'mailer@',
            'automated@',
            'notification@',
            'notifications@',
            'alerts@',
            'news@',
            'newsletter@',
            'updates@'
        ]
        
        sender_lower = sender.lower()
        return any(pattern in sender_lower for pattern in noreply_patterns)
    
    def check_newsletter_sender(self, sender: str, subject: str, headers: Dict[str, str]) -> bool:
        """Check if email is from a newsletter service"""
        # Common newsletter platforms and services
        newsletter_domains = [
            'substack.com',
            'beehiiv.com',
            'ghost.io',
            'mailchimp.com',
            'sendgrid.net',
            'constantcontact.com',
            'mailerlite.com',
            'convertkit.com',
            'sendinblue.com',
            'mail.google.com',  # Google notifications
            'accounts.google.com',  # Google account alerts
            'bounce.google.com'
        ]
        
        sender_lower = sender.lower()
        
        # Check domain
        if any(domain in sender_lower for domain in newsletter_domains):
            return True
        
        # Check for unsubscribe links in headers
        if 'List-Unsubscribe' in headers or 'List-Id' in headers:
            return True
        
        # Check subject for newsletter indicators
        subject_lower = subject.lower()
        newsletter_subject_patterns = [
            'newsletter',
            'digest',
            'weekly',
            'daily',
            'monthly',
            'roundup',
            'briefing',
            'security alert',
            'account alert',
            'suspicious activity',
            'sign-in',
            'knowledge, review your'
        ]
        
        return any(pattern in subject_lower for pattern in newsletter_subject_patterns)
    
    def check_fundraising_keywords(self, subject: str, body: str) -> bool:
        """Check for fundraising/pitch keywords"""
        keywords = [
            'raising', 'seed', 'series', 'pitch', 'invest', 'round',
            'deck', 'dataroom', 'docsend', 'drive', 'dropbox', 'notion',
            'fundraising', 'funding', 'capital', 'investor', 'vc',
            'investment', 'startup', 'founder', 'equity', 'valuation'
        ]
        
        text = f"{subject} {body}".lower()
        return any(keyword in text for keyword in keywords)
    
    def check_warm_intro(self, subject: str, body: str) -> bool:
        """Check if email is a warm intro/referral about a specific startup"""
        text = f"{subject} {body}".lower()
        
        # Patterns indicating a warm intro about a startup
        intro_patterns = [
            'met a team', 'met a founder', 'spoke to a team', 'spoke to a founder',
            'brilliant team', 'interesting team', 'great team',
            'would you want to know more', 'should i connect', 'should i introduce',
            'would you be interested', 'worth connecting', 'worth meeting',
            'they\'re building', 'team building', 'founder building',
            'startup building', 'company building'
        ]
        
        # Must have intro pattern AND mention of team/startup/founder
        has_intro_pattern = any(pattern in text for pattern in intro_patterns)
        has_startup_mention = any(word in text for word in ['team', 'founder', 'startup', 'building', 'company'])
        
        return has_intro_pattern and has_startup_mention
    
    def check_follow_up_indicators(self, subject: str, body: str) -> bool:
        """Check if email is a follow-up that might be investment-related"""
        follow_up_phrases = [
            'we discussed', 'discussed last', 'following up', 'follow up',
            'per our conversation', 'as discussed', 'from our meeting',
            'timeline', 'deliverables', 'next steps', 'next steps on'
        ]
        
        # Also check for investment context in follow-ups
        investment_context = [
            'investment', 'deal', 'round', 'funding', 'partnership',
            'collaboration', 'opportunity', 'venture', 'startup'
        ]
        
        text = f"{subject} {body}".lower()
        has_follow_up = any(phrase in text for phrase in follow_up_phrases)
        has_investment_context = any(context in text for context in investment_context)
        
        # If it's a follow-up AND mentions investment-related terms, likely Deal Flow
        return has_follow_up and has_investment_context
    
    def check_deck_links(self, links: List[str]) -> bool:
        """Check if links contain deck/dataroom indicators"""
        deck_indicators = [
            'docsend',
            'dataroom',
            'deck',
            'pitch',
            'drive.google.com',
            'dropbox.com',
            'notion.so'
        ]
        
        links_text = ' '.join(links).lower()
        return any(indicator in links_text for indicator in deck_indicators)
    
    def check_hiring_keywords(self, subject: str, body: str) -> bool:
        """Check for hiring keywords"""
        keywords = [
            'jd', 'job description', 'opening', 'apply', 'cv', 'resume',
            'candidate', 'referral', 'recruiter', 'role', 'position',
            'hiring', 'recruitment'
        ]
        
        text = f"{subject} {body}".lower()
        return any(keyword in text for keyword in keywords)
    
    def check_networking_request(self, subject: str, body: str) -> bool:
        """Check if email is a networking/meeting request (NOT a pitch or warm intro about a startup)"""
        networking_indicators = [
            # Meeting requests
            'coffee', 'catch up', 'grab a', 'get together', 
            'are you in', 'will you be in', 'visiting', 'in town',
            
            # Advice/learning requests (general, not about a specific startup)
            'learn from you', 'seek advice', 'pick your brain', 
            'guidance', 'mentor', 'feedback', 'thoughts on',
            'wanted to learn', 'wanted to understand',
            
            # Event/ecosystem
            'invite you', 'speaking', 'panel', 'conference', 'event'
        ]
        
        text = f"{subject} {body}".lower()
        has_networking_pattern = any(indicator in text for indicator in networking_indicators)
        
        # If it has networking patterns BUT also mentions a specific startup/team being discussed,
        # it's likely a warm intro (deal flow), not general networking
        # Check for warm intro exclusions
        warm_intro_exclusions = [
            'met a team', 'met a founder', 'spoke to a team', 'spoke to a founder',
            'brilliant team', 'interesting team', 'great team',
            'they\'re building', 'team building', 'founder building'
        ]
        
        has_warm_intro_pattern = any(pattern in text for pattern in warm_intro_exclusions)
        
        # Return True only if it has networking indicators AND is NOT a warm intro
        return has_networking_pattern and not has_warm_intro_pattern
    
    def deterministic_classify(
        self, 
        subject: str, 
        body: str, 
        headers: Dict[str, str],
        sender: str,
        links: List[str],
        has_pdf_attachment: bool = False
    ) -> Tuple[str, float]:
        """
        Deterministic classification using rules
        Returns: (category, confidence)
        """
        # RULE 1: LEGITIMATE SERVICE PROVIDER CHECK (HIGHEST PRIORITY)
        # Check if email is from a legitimate service provider (Google, Microsoft, etc.)
        # These should ALWAYS be GENERAL, not SPAM, even if they contain security keywords
        is_legitimate_provider = self.check_legitimate_service_provider(sender)
        
        if is_legitimate_provider:
            return (CATEGORY_GENERAL, 0.98)
        
        # RULE 2: SECURITY THREAT CHECK
        # Check for actual security threats (phishing, malicious) - these are SPAM
        # Only check if NOT from legitimate provider (already handled above)
        is_security_threat = self.check_security_threat(subject, body, headers, sender)
        
        if is_security_threat:
            return (CATEGORY_SPAM, 0.98)
        
        # RULE 3: GENERAL CHECK (newsletters, automated emails, subscriptions)
        # Check for newsletters and automated emails BEFORE deal flow
        # These should NEVER be deal flow, even if they mention startup keywords
        is_newsletter = self.check_newsletter_sender(sender, subject, headers)
        is_noreply = self.check_noreply_sender(sender)
        
        if is_newsletter or is_noreply:
            return (CATEGORY_GENERAL, 0.95)
        
        # RULE 4: NETWORKING CHECK (meeting/advice requests)
        # Check for networking requests BEFORE deal flow
        # These should be NETWORKING even if they mention investment keywords
        is_networking_request = self.check_networking_request(subject, body)
        
        if is_networking_request:
            return (CATEGORY_NETWORKING, 0.85)
        
        # RULE 5: Deal Flow (only for legitimate startup pitches)
        # Check for fundraising/deal flow indicators
        has_fundraising = self.check_fundraising_keywords(subject, body)
        has_deck = self.check_deck_links(links)
        is_warm_intro = self.check_warm_intro(subject, body)
        
        # If it has fundraising keywords, deck links, PDF attachment, OR is a warm intro about a startup
        # PDF attachments are strong indicators of deal flow (pitch decks)
        # Warm intros about specific startups should be tracked as deal flow
        if has_fundraising or has_deck or has_pdf_attachment or is_warm_intro:
            if has_pdf_attachment:
                confidence = 0.95  # Highest confidence for PDF decks
            elif is_warm_intro:
                confidence = 0.88  # High confidence for warm intros
            else:
                confidence = 0.90  # High confidence for other deal flow indicators
            return (CATEGORY_DEAL_FLOW, confidence)
        
        # Rule 5: Hiring (if keywords present and no fundraising)
        has_hiring = self.check_hiring_keywords(subject, body)
        
        if has_hiring and not has_fundraising:
            return (CATEGORY_HIRING, 0.80)
        
        # Rule 3.5: Check for follow-up indicators that might be investment-related
        # In VC context, follow-ups with "project", "timeline", "deliverables" could be deal-related
        text = f"{subject} {body}".lower()
        follow_up_keywords = ['we discussed', 'discussed last', 'project', 'timeline', 'deliverables']
        has_follow_up = any(kw in text for kw in follow_up_keywords)
        
        # If it's a follow-up mentioning project/timeline/deliverables, lean toward Deal Flow
        # (OpenAI will validate/override if wrong)
        if has_follow_up:
            return (CATEGORY_DEAL_FLOW, 0.65)  # Lower confidence, let OpenAI decide
        
        # Rule 5: Default to Networking
        # General will be determined by OpenAI if needed
        return (CATEGORY_NETWORKING, 0.60)
    
    def openai_classify(
        self,
        subject: str,
        body: str,
        headers: Dict[str, str],
        sender: str,
        links: List[str],
        deterministic_category: str,
        has_pdf_attachment: bool = False,
        thread_id: str = None,
        user_id: str = None
    ) -> Tuple[str, float]:
        """
        Use OpenAI (via Lambda or direct) to validate/override deterministic classification
        Returns: (category, confidence)
        
        Uses a comprehensive zero-hallucination prompt for accurate classification.
        Prefers Lambda if available (more secure, no logging).
        """
        # Prefer Lambda if available (more secure, no email content logging)
        if self.lambda_client:
            try:
                return self.lambda_client.classify_email(
                    subject=subject,
                    body=body,
                    headers=headers,
                    sender=sender,
                    links=links,
                    deterministic_category=deterministic_category,
                    has_pdf_attachment=has_pdf_attachment,
                    thread_id=thread_id,
                    user_id=user_id
                )
            except Exception as e:
                print(f"⚠️  Lambda classification failed, falling back to OpenAI: {str(e)}")
                # Fall through to OpenAI fallback
        
        # Fallback to direct OpenAI if Lambda not available or failed
        if not self.openai_client:
            return (deterministic_category, 0.70)
        
        try:
            # Extract sender domain
            sender_email = sender.split('<')[-1].strip('>') if '<' in sender else sender
            sender_domain = sender_email.split('@')[-1] if '@' in sender_email else "unknown"
            sender_name = sender.split('<')[0].strip() if '<' in sender else sender_email.split('@')[0]
            
            # Extract attachments info
            attachment_names = []
            if has_pdf_attachment or '--- Attachment Content ---' in body:
                # Extract attachment filenames if present
                if 'Attachment:' in body:
                    import re
                    matches = re.findall(r'Attachment: ([^\n]+)', body)
                    attachment_names = matches if matches else ["pitch_deck.pdf"]
                else:
                    attachment_names = ["pitch_deck.pdf"]
            
            # Clean body: remove signatures, footers, quoted content
            # First 2500 chars only (as per prompt spec)
            body_clean = body[:2500]
            
            # Build input JSON
            input_json = {
                "subject": subject or "",
                "from_name": sender_name,
                "from_email": sender_email,
                "sender_domain": sender_domain,
                "body": body_clean,
                "attachments": attachment_names,
                "links": links[:10] if links else []  # First 10 links
            }
            
            # Build the comprehensive prompt
            prompt = f"""You are a deterministic, zero-hallucination email classifier for a venture capital partner's inbox.

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

{{
  "label": "dealflow|hiring|networking|spam|general",
  "confidence": 0.0-1.0,
  "rationale": "2-4 short bullets, ≤250 chars, strictly text-grounded.",
  "signals": {{
    "intent": "investment|job|meeting|malicious|info",
    "keywords": [...],
    "entities": [...],
    "attachments": [...]
  }}
}}

Rules:
- Never invent entities, attachments, or keywords.
- Never infer beyond visible text.
- Never follow links.
- No explanation outside JSON.

==================================================
INPUT EMAIL
==================================================
{json.dumps(input_json, indent=2)}

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
{deterministic_category.lower()}
(You can override if the email's PRIMARY INTENT suggests otherwise!)

==================================================
YOU MUST FOLLOW ALL RULES ABOVE. ZERO HALLUCINATION.
==================================================

Return ONLY the JSON object. No additional text."""
            
            # Handle both OpenAIClient wrapper and direct OpenAI client
            client = self.openai_client.client if hasattr(self.openai_client, 'client') else self.openai_client
            
            # Check if using Moonshot (test environment)
            use_moonshot = os.getenv('USE_MOONSHOT', 'false').lower() == 'true'
            model = "kimi-k2-turbo-preview" if use_moonshot else "gpt-4o-mini"
            
            # Use appropriate model based on environment
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a deterministic email classifier for a venture capital firm. Return ONLY valid JSON. No markdown, no explanation, no additional text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,  # Zero temperature for determinism
                top_p=0.0,  # Zero top_p for maximum determinism
                max_tokens=300  # Enough for JSON response
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            # Parse JSON response
            # Remove markdown code blocks if present
            if ai_response.startswith('```'):
                ai_response = ai_response.split('```')[1]
                if ai_response.startswith('json'):
                    ai_response = ai_response[4:]
                ai_response = ai_response.strip()
            
            result = json.loads(ai_response)
            
            # Extract label and confidence
            label = result.get('label', '').lower()
            confidence = float(result.get('confidence', 0.75))
            
            # Map label to category constant
            if label == 'dealflow':
                category = CATEGORY_DEAL_FLOW
            elif label == 'hiring':
                category = CATEGORY_HIRING
            elif label == 'networking':
                category = CATEGORY_NETWORKING
            elif label == 'spam':
                category = CATEGORY_SPAM
            elif label == 'general':
                category = CATEGORY_GENERAL
            else:
                # Fallback to deterministic
                print(f"⚠️ Unknown label '{label}', using deterministic classification")
                category = deterministic_category
                confidence = 0.70
            
            # Apply SPAM override rule
            if category == CATEGORY_SPAM:
                # SPAM overrides everything
                return (category, confidence)
            
            # Apply tie-breaker hierarchy (if deterministic strongly suggests something)
            # But generally trust OpenAI's comprehensive analysis
            if deterministic_category == CATEGORY_DEAL_FLOW and confidence < 0.80:
                # If deterministic strongly believes it's deal flow, and AI is uncertain, lean toward deal flow
                category = CATEGORY_DEAL_FLOW
                confidence = 0.85
            
            return (category, confidence)
        
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON parsing error in OpenAI response: {str(e)}")
            # Try to extract label from malformed response
            try:
                ai_response_upper = ai_response.upper()
                if 'DEALFLOW' in ai_response_upper or 'DEAL_FLOW' in ai_response_upper:
                    return (CATEGORY_DEAL_FLOW, 0.75)
                elif 'HIRING' in ai_response_upper:
                    return (CATEGORY_HIRING, 0.75)
                elif 'NETWORKING' in ai_response_upper:
                    return (CATEGORY_NETWORKING, 0.75)
                elif 'SPAM' in ai_response_upper:
                    return (CATEGORY_SPAM, 0.75)
                elif 'GENERAL' in ai_response_upper:
                    return (CATEGORY_GENERAL, 0.75)
            except:
                pass
            return (deterministic_category, 0.70)
        
        except Exception as e:
            error_str = str(e)
            # Check for quota/rate limit errors
            if '429' in error_str or 'insufficient_quota' in error_str.lower() or 'quota' in error_str.lower():
                print(f"⚠️ OpenAI quota/rate limit exceeded. Using deterministic classification only.")
                print(f"   Error: {error_str[:200]}")  # Truncate long error messages
                # Return deterministic classification with lower confidence
                return (deterministic_category, 0.70)
            else:
                print(f"⚠️ Error in OpenAI classification: {error_str[:200]}")
                return (deterministic_category, 0.70)
    
    def classify_email(
        self,
        subject: str,
        body: str,
        headers: Dict[str, str],
        sender: str,
        links: List[str] = None,
        has_pdf_attachment: bool = False,
        thread_id: str = None,
        user_id: str = None
    ) -> Dict:
        """
        Main classification method
        Returns: {
            'category': str,
            'confidence': float,
            'tags': List[str],
            'links': List[str]
        }
        """
        if links is None:
            links = self.extract_links(body)
        
        # Step 1: Deterministic classification
        det_category, det_confidence = self.deterministic_classify(
            subject, body, headers, sender, links, has_pdf_attachment
        )
        
        # Step 2: OpenAI validation/override (via Lambda if available)
        final_category, confidence = self.openai_classify(
            subject, body, headers, sender, links, det_category, has_pdf_attachment,
            thread_id=thread_id, user_id=user_id
        )
        
        # Step 3: Determine tags
        tags = []
        if final_category == CATEGORY_DEAL_FLOW:
            tags.append(TAG_DEAL)
        elif final_category == CATEGORY_NETWORKING:
            tags.append(TAG_NETWORKING)
        elif final_category == CATEGORY_HIRING:
            tags.append(TAG_HIRING)
        elif final_category == CATEGORY_SPAM:
            tags.append(TAG_SPAM)
        
        return {
            'category': final_category,
            'confidence': confidence,
            'tags': tags,
            'links': links
        }
    
    def check_four_basics(self, subject: str, body: str, links: List[str], attachment_text: Optional[str] = None) -> Dict[str, bool]:
        """
        Check if Deal Flow email has the four basics:
        1. Deck link (or PDF attachment)
        2. Team info
        3. Traction (MRR/users/pilots + month)
        4. Round info (amount/committed/lead)
        
        Args:
            attachment_text: Optional text extracted from PDF/document attachments
        """
        # Include attachment text in analysis
        combined_body = body
        if attachment_text:
            combined_body = f"{body}\n\n{attachment_text}"
        
        text = f"{subject} {combined_body}".lower()
        links_text = ' '.join(links).lower()
        
        has_deck = any(indicator in links_text for indicator in [
            'docsend', 'dataroom', 'deck', 'drive.google.com', 'dropbox.com', 'notion.so'
        ])
        # Also check if attachment text contains deck-related keywords
        if attachment_text and not has_deck:
            att_text_lower = attachment_text.lower()
            deck_keywords = ['pitch', 'deck', 'presentation', 'fundraising', 'investment', 'valuation', 
                           'market opportunity', 'traction', 'revenue', 'mrr', 'arr', 'customers', 
                           'users', 'team', 'founder', 'co-founder', 'round', 'seed', 'series']
            if any(keyword in att_text_lower for keyword in deck_keywords):
                has_deck = True
        
        has_team_info = any(keyword in text for keyword in [
            'founder', 'co-founder', 'team', 'ceo', 'cto', 'founders'
        ])
        
        has_traction = any(keyword in text for keyword in [
            'mrr', 'arr', 'users', 'customers', 'revenue', 'pilots', 'month',
            'traction', 'growth', 'customers'
        ])
        
        has_round_info = any(keyword in text for keyword in [
            'seed', 'series', 'round', 'raising', 'amount', 'committed', 'lead',
            'investor', 'funding', 'capital', '$', 'k', 'million'
        ])
        
        return {
            'has_deck': has_deck or bool(links),
            'has_team_info': has_team_info,
            'has_traction': has_traction,
            'has_round_info': has_round_info
        }
    
    def generate_deal_flow_reply(
        self,
        basics: Dict[str, bool],
        has_deck_link: bool,
        subject: str = "",
        body: str = "",
        sender: str = "",
        score: Optional[float] = None,
        team_score: Optional[float] = None,
        white_space_score: Optional[float] = None
    ) -> Tuple[str, str, str]:
        """
        Generate Deal Flow reply based on four basics using AI
        Returns: (reply_text, reply_type, state)
        """
        all_basics = all(basics.values())
        
        if all_basics or has_deck_link:
            # All basics present or deck link exists - generate score-based acknowledgment
            if self.openai_client:
                try:
                    # Handle both OpenAIClient wrapper and direct OpenAI client
                    client = self.openai_client.client if hasattr(self.openai_client, 'client') else self.openai_client
                    
                    # Check if body includes PDF attachment content
                    has_pdf_content = '--- Attachment Content ---' in body or 'attachment' in body.lower()
                    pdf_context = "\n\nNote: This email includes PDF attachment content that has been analyzed. The body text includes the full content of any attached pitch deck or documents." if has_pdf_content else ""
                    
                    # Score-based DECISION and response guidance
                    decision_context = ""
                    if score is not None:
                        if score >= 75:
                            decision_context = """
SCORE: HIGH (75+) - This is a strong opportunity with excellent team background and market white space.
DECISION: Move forward with interest
REPLY GUIDANCE:
- Express genuine interest and enthusiasm
- Mention specific positive aspects (strong team, interesting market, etc.)
- Indicate next steps (schedule a call, discuss further, etc.)
- Be warm and encouraging
- Example tone: "We're very interested in discussing this opportunity further..."
"""
                        elif score >= 60:
                            decision_context = """
SCORE: MODERATE (60-74) - This is a decent opportunity worth exploring further.
DECISION: Proceed with cautious interest
REPLY GUIDANCE:
- Acknowledge the opportunity positively
- Express interest but be measured
- Request follow-up information or a call
- Be professional and encouraging but not overly enthusiastic
- Example tone: "We'd like to learn more about..."
"""
                        elif score >= 50:
                            decision_context = """
SCORE: MODERATE-LOW (50-59) - This opportunity needs more evaluation and may not be a strong fit.
DECISION: Request more information or politely decline
REPLY GUIDANCE:
- Be professional and respectful
- Acknowledge the pitch but express concerns or need for more info
- Either request additional details or politely decline
- Be neutral and professional
- Example tone: "While we appreciate you sharing this, we need to see more traction/revenue/etc. before moving forward..."
"""
                        else:
                            decision_context = """
SCORE: LOW (<50) - This opportunity is not a strong fit based on team background and/or market analysis.
DECISION: Politely decline
REPLY GUIDANCE:
- Be polite and respectful
- Thank them for sharing
- Clearly but politely decline (don't string them along)
- Be brief and professional
- Example tone: "Thank you for sharing your pitch. Unfortunately, this doesn't align with our current investment focus..."
"""
                    else:
                        # No scores available - generate generic acknowledgment
                        decision_context = """
SCORE: Not available (N/A) - Scoring system has been removed. Generate a professional acknowledgment reply.
DECISION: Acknowledge receipt and indicate review
REPLY GUIDANCE:
- Thank them for sharing the pitch/deck
- Indicate that the team will review
- Be professional and brief
- Do not make specific investment decisions without scores
"""
                    
                    prompt = f"""You are a venture capital partner making a decision on whether to pursue a startup investment opportunity.

Email from: {sender}
Subject: {subject}
Email preview: {body[:2000] if body else "No preview available"}{pdf_context}

The startup has provided all necessary information (deck, team info, traction, round details).
If the email body includes "--- Attachment Content ---", the full content of attached PDF documents has been analyzed.{decision_context}

ANALYSIS SUMMARY:
- Team Background Score: {team_score if team_score else 'N/A'}
- White Space Score: {white_space_score if white_space_score else 'N/A'}
- Overall Score: {score if score else 'N/A'}

Generate a professional reply that:
1. Makes a CLEAR DECISION based on the score:
   - High score (75+): Express strong interest and propose next steps (call, meeting)
   - Moderate score (60-74): Show interest but request more info or a call
   - Moderate-Low score (50-59): Request additional details OR politely decline if not aligned
   - Low score (<50): Politely but clearly decline

2. Be specific about the decision:
   - If interested: Propose concrete next steps (e.g., "Let's schedule a call next week", "I'd like to discuss this further")
   - If declining: Be clear and respectful (e.g., "This doesn't align with our current focus", "We're not investing in this space right now")

3. Match the tone to the score and decision

4. Be concise (3-5 sentences)

IMPORTANT: 
- Make a REAL decision - don't just say "we'll review and get back"
- Respond DIRECTLY to the founder - do not mention redirecting to other VC people
- Be honest and clear about interest level
- Do NOT include signature placeholders like "[Your Name]", "[Your Position]", "[Your Firm]". The actual signature will be added automatically."""
                    
                    # Check if using Moonshot (test environment)
                    use_moonshot = os.getenv('USE_MOONSHOT', 'false').lower() == 'true'
                    model = "kimi-k2-turbo-preview" if use_moonshot else "gpt-4o-mini"
                    
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "You are a venture capital partner making investment decisions. Generate clear, professional replies that make real decisions (interested/decline/need more info) based on the opportunity score, not generic acknowledgments."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=250  # Increased for more detailed decision-based replies
                    )
                    
                    reply = response.choices[0].message.content.strip()
                    return reply, "ack", STATE_ROUTED
                    
                except Exception as e:
                    print(f"Error generating AI reply: {str(e)}")
                    # Fallback to hardcoded
                    reply = """Thanks for sharing the deck—our team will review and get back to you."""
                    return reply, "ack", STATE_ROUTED
            else:
                # No OpenAI client - use hardcoded
                reply = """Thanks for sharing the deck—our team will review and get back to you."""
                return reply, "ack", STATE_ROUTED
        else:
            # Missing basics - ask for more using AI
            missing = [k.replace('has_', '').replace('_', ' ') for k, v in basics.items() if not v]
            
            if self.openai_client:
                try:
                    # Handle both OpenAIClient wrapper and direct OpenAI client
                    client = self.openai_client.client if hasattr(self.openai_client, 'client') else self.openai_client
                    
                    # Check if body includes PDF attachment content
                    has_pdf_content = '--- Attachment Content ---' in body or 'attachment' in body.lower()
                    pdf_context = "\n\nNote: This email includes PDF attachment content. If information is still missing, it may not be in the attached documents either." if has_pdf_content else ""
                    
                    prompt = f"""Generate a professional email for a venture capital firm responding to a startup pitch that is missing some key information.

Email from: {sender}
Subject: {subject}
Email preview: {body[:1000] if body else "No preview available"}{pdf_context}

Missing information:
{chr(10).join([f"- {item}" for item in missing])}

If the email body includes "--- Attachment Content ---", the full content of any attached PDF documents has been analyzed. If information is still missing, it means it's not present in the email body or attached documents.

Generate a professional reply that:
- Thanks them for reaching out
- Politely requests the missing information (deck, team info, traction metrics, round details)
- Is concise (4-5 sentences max)
- Maintains a professional but friendly tone
- Does not invent facts or make promises

Format as a clear, professional email.
IMPORTANT: Do NOT include signature placeholders like "[Your Name]", "[Your Position]", "[Your Firm]". The actual signature will be added automatically."""
                    
                    # Check if using Moonshot (test environment)
                    use_moonshot = os.getenv('USE_MOONSHOT', 'false').lower() == 'true'
                    model = "kimi-k2-turbo-preview" if use_moonshot else "gpt-4o-mini"
                    
                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "You are a professional email assistant for a venture capital firm. Generate concise, professional replies that request missing information."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=200
                    )
                    
                    reply = response.choices[0].message.content.strip()
                    return reply, "ask-more", STATE_ASK_MORE
                    
                except Exception as e:
                    print(f"Error generating AI reply: {str(e)}")
                    # Fallback to hardcoded
                    reply = f"""Thanks for reaching out. To help us evaluate your opportunity, could you please share:

1. Deck or pitch materials
2. Team background and experience
3. Current traction metrics (MRR, users, pilots, revenue, etc.)
4. Round details (amount, committed capital, lead investor, etc.)

Once we have these details, we'll review and get back to you."""
                    return reply, "ask-more", STATE_ASK_MORE
            else:
                # No OpenAI client - use hardcoded
                reply = f"""Thanks for reaching out. To help us evaluate your opportunity, could you please share:

1. Deck or pitch materials
2. Team background and experience
3. Current traction metrics (MRR, users, pilots, revenue, etc.)
4. Round details (amount, committed capital, lead investor, etc.)

Once we have these details, we'll review and get back to you."""
                return reply, "ask-more", STATE_ASK_MORE
    
    def generate_category_reply(self, category: str, context: Dict = None) -> Tuple[str, str]:
        """
        Generate appropriate reply for each category
        Returns: (reply_text, reply_type)
        """
        if category == CATEGORY_DEAL_FLOW:
            basics = context.get('basics', {})
            has_deck = context.get('has_deck_link', False)
            reply, reply_type, _ = self.generate_deal_flow_reply(basics, has_deck)
            return reply, reply_type
        
        elif category == CATEGORY_NETWORKING:
            return "Thanks for reaching out! I appreciate the connection.", "ack"
        
        elif category == CATEGORY_HIRING:
            return """Thank you for your interest. I'll forward your information to our HR team for review.""", "ack"
        
        elif category == CATEGORY_SPAM:
            return None, "none"
        
        return None, "none"

