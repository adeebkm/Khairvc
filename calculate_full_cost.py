#!/usr/bin/env python3
"""
Calculate TOTAL OpenAI token usage and cost for ALL features
"""
import tiktoken
import json

# OpenAI pricing (as of 2024)
PRICING = {
    'gpt-4o-mini': {
        'input': 0.15 / 1_000_000,  # $0.15 per 1M input tokens
        'output': 0.60 / 1_000_000,  # $0.60 per 1M output tokens
    },
    'gpt-4o': {
        'input': 2.50 / 1_000_000,  # $2.50 per 1M input tokens (MUCH MORE EXPENSIVE!)
        'output': 10.00 / 1_000_000,  # $10.00 per 1M output tokens
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

def calculate_all_costs():
    """Calculate cost for ALL OpenAI features"""
    
    print("=" * 70)
    print("COMPLETE OpenAI Cost Analysis - All Features")
    print("=" * 70)
    print()
    
    costs = {}
    
    # 1. EMAIL CLASSIFICATION
    print("1️⃣  EMAIL CLASSIFICATION")
    print("-" * 70)
    classification_prompt = """[Full classification prompt - ~1,970 tokens]"""
    classification_input = 1970  # From previous calculation
    classification_output = 112
    classification_input_cost = (classification_input / 1_000_000) * 0.15
    classification_output_cost = (classification_output / 1_000_000) * 0.60
    classification_total = classification_input_cost + classification_output_cost
    costs['classification'] = classification_total
    
    print(f"   Input:  {classification_input:,} tokens = ${classification_input_cost:.6f}")
    print(f"   Output: {classification_output:,} tokens = ${classification_output_cost:.6f}")
    print(f"   Total:  ${classification_total:.6f} per email")
    print()
    
    # 2. DEAL SCORING - Team Background Extraction
    print("2️⃣  DEAL SCORING - Team Background Extraction")
    print("-" * 70)
    team_extraction_prompt = """Extract the founder's background information from this email/pitch.

Founder Name: {founder_name}
Email: {founder_email}
Subject: {subject}
Email Body: {email_body[:2000]}

Extract:
1. Previous companies they worked at
2. Education background
3. Years of experience
4. Any notable achievements

Return JSON format."""
    
    example_team_data = {
        "founder_name": "John Doe",
        "founder_email": "john@startup.com",
        "subject": "Seed Funding Opportunity",
        "email_body": "Hi, I'm John. Previously worked at Google and Microsoft. MIT graduate with 10 years experience..."
    }
    
    # Format the prompt manually to avoid issues with curly braces
    team_prompt = team_extraction_prompt.replace("{founder_name}", example_team_data["founder_name"])
    team_prompt = team_prompt.replace("{founder_email}", example_team_data["founder_email"])
    team_prompt = team_prompt.replace("{subject}", example_team_data["subject"])
    team_prompt = team_prompt.replace("{email_body[:2000]}", example_team_data["email_body"][:2000])
    team_input = count_tokens(team_prompt) + 50  # System message
    team_output = 150  # Estimated JSON response
    team_input_cost = (team_input / 1_000_000) * 0.15
    team_output_cost = (team_output / 1_000_000) * 0.60
    team_total = team_input_cost + team_output_cost
    costs['team_extraction'] = team_total
    
    print(f"   Input:  {team_input:,} tokens = ${team_input_cost:.6f}")
    print(f"   Output: {team_output:,} tokens = ${team_output_cost:.6f}")
    print(f"   Total:  ${team_total:.6f} per deal")
    print()
    
    # 3. DEAL SCORING - White Space Analysis (GPT-4o - EXPENSIVE!)
    print("3️⃣  DEAL SCORING - White Space Analysis (GPT-4o)")
    print("-" * 70)
    print("   ⚠️  THIS IS THE EXPENSIVE ONE!")
    print()
    
    white_space_prompt = """Analyze the market white space for this startup:

Startup: {startup_name}
Sector: {sector}
Description: {description}

USE WEB SEARCH FOR CURRENT DATA:
1. Search for recent funding in this sector (2022-2025)
2. Search for market size and growth projections
3. Search for competitors and competitive intensity
4. Assess white space opportunity

Provide detailed analysis with data."""
    
    example_white_space = {
        "startup_name": "Healthcare Tech Platform",
        "sector": "Healthcare",
        "description": "AI-powered platform for healthcare providers..."
    }
    
    # Format the prompt manually
    ws_prompt = white_space_prompt.replace("{startup_name}", example_white_space["startup_name"])
    ws_prompt = ws_prompt.replace("{sector}", example_white_space["sector"])
    ws_prompt = ws_prompt.replace("{description}", example_white_space["description"])
    ws_input = count_tokens(ws_prompt, "gpt-4o") + 100  # System message + web search context
    ws_output = 500  # Detailed analysis response
    ws_input_cost = (ws_input / 1_000_000) * 2.50  # GPT-4o pricing
    ws_output_cost = (ws_output / 1_000_000) * 10.00  # GPT-4o pricing
    ws_total = ws_input_cost + ws_output_cost
    costs['white_space'] = ws_total
    
    print(f"   Input:  {ws_input:,} tokens = ${ws_input_cost:.6f} (GPT-4o)")
    print(f"   Output: {ws_output:,} tokens = ${ws_output_cost:.6f} (GPT-4o)")
    print(f"   Total:  ${ws_total:.6f} per deal")
    print(f"   ⚠️  This is {ws_total / classification_total:.1f}x more expensive than classification!")
    print()
    
    # 4. REPLY GENERATION - Deal Flow (with scores)
    print("4️⃣  REPLY GENERATION - Deal Flow Acknowledgment")
    print("-" * 70)
    reply_prompt = """Generate a professional email reply for a venture capital firm.

Email from: {sender}
Subject: {subject}
Email preview: {body[:2000]}

SCORE: HIGH (75+) - This is a strong opportunity...
DECISION: Move forward with interest

Generate a professional reply that makes a CLEAR DECISION..."""
    
    example_reply = {
        "sender": "founder@startup.com",
        "subject": "Seed Funding Opportunity",
        "body": "We're raising $2M seed round..."
    }
    
    # Format the prompt manually
    reply_p = reply_prompt.replace("{sender}", example_reply["sender"])
    reply_p = reply_p.replace("{subject}", example_reply["subject"])
    reply_p = reply_p.replace("{body[:2000]}", example_reply["body"][:2000])
    reply_input = count_tokens(reply_p) + 50
    reply_output = 200  # Professional reply
    reply_input_cost = (reply_input / 1_000_000) * 0.15
    reply_output_cost = (reply_output / 1_000_000) * 0.60
    reply_total = reply_input_cost + reply_output_cost
    costs['reply_generation'] = reply_total
    
    print(f"   Input:  {reply_input:,} tokens = ${reply_input_cost:.6f}")
    print(f"   Output: {reply_output:,} tokens = ${reply_output_cost:.6f}")
    print(f"   Total:  ${reply_total:.6f} per reply")
    print()
    
    # 5. ASK-MORE REPLY GENERATION
    print("5️⃣  REPLY GENERATION - Ask-More (Missing Info)")
    print("-" * 70)
    ask_more_input = 800  # Simpler prompt
    ask_more_output = 150
    ask_more_input_cost = (ask_more_input / 1_000_000) * 0.15
    ask_more_output_cost = (ask_more_output / 1_000_000) * 0.60
    ask_more_total = ask_more_input_cost + ask_more_output_cost
    costs['ask_more'] = ask_more_total
    
    print(f"   Input:  {ask_more_input:,} tokens = ${ask_more_input_cost:.6f}")
    print(f"   Output: {ask_more_output:,} tokens = ${ask_more_output_cost:.6f}")
    print(f"   Total:  ${ask_more_total:.6f} per reply")
    print()
    
    # SUMMARY
    print("=" * 70)
    print("📊 COST SUMMARY")
    print("=" * 70)
    print()
    
    print("Per Email Classification:")
    print(f"   Classification only:        ${classification_total:.6f}")
    print()
    
    print("Per Deal Flow Email (Full Processing):")
    deal_flow_total = (
        classification_total +  # Classify email
        team_total +  # Extract team background
        ws_total +  # White space analysis (EXPENSIVE!)
        reply_total  # Generate reply
    )
    print(f"   Classification:            ${classification_total:.6f}")
    print(f"   Team extraction:           ${team_total:.6f}")
    print(f"   White space analysis:       ${ws_total:.6f} ⚠️  (GPT-4o)")
    print(f"   Reply generation:          ${reply_total:.6f}")
    print(f"   ─────────────────────────────────────")
    print(f"   TOTAL per deal:            ${deal_flow_total:.6f}")
    print()
    
    print("=" * 70)
    print("💰 REAL-WORLD SCENARIOS")
    print("=" * 70)
    print()
    
    scenarios = [
        ("10 emails (all new, 3 are deals)", 
         10 * classification_total + 3 * (team_total + ws_total + reply_total)),
        ("20 emails (all new, 5 are deals)", 
         20 * classification_total + 5 * (team_total + ws_total + reply_total)),
        ("30 emails (all new, 8 are deals)", 
         30 * classification_total + 8 * (team_total + ws_total + reply_total)),
        ("100 emails (all new, 20 are deals)", 
         100 * classification_total + 20 * (team_total + ws_total + reply_total)),
    ]
    
    for scenario, cost in scenarios:
        print(f"   {scenario:40s} ${cost:.4f}")
    
    print()
    print("=" * 70)
    print("⚠️  KEY FINDINGS")
    print("=" * 70)
    print()
    print("1. White Space Analysis is EXPENSIVE:")
    print(f"   - Uses GPT-4o (not gpt-4o-mini): {ws_total / classification_total:.1f}x more expensive")
    print(f"   - Cost per deal: ${ws_total:.6f} (vs ${classification_total:.6f} for classification)")
    print()
    print("2. Deal Flow emails cost MUCH more:")
    print(f"   - Classification: ${classification_total:.6f}")
    print(f"   - Full deal processing: ${deal_flow_total:.6f} ({deal_flow_total / classification_total:.1f}x more)")
    print()
    print("3. If you process 20 deals with full scoring:")
    print(f"   - Cost: ${20 * deal_flow_total:.4f}")
    print(f"   - White space alone: ${20 * ws_total:.4f} ({(20 * ws_total) / (20 * deal_flow_total) * 100:.1f}% of total)")
    print()
    print("💡 COST OPTIMIZATION TIPS:")
    print("   1. Only score deals when needed (not on every fetch)")
    print("   2. Consider using gpt-4o-mini for white space (if accuracy allows)")
    print("   3. Cache white space analysis results")
    print("   4. Skip white space for low-priority deals")
    print("   5. Use deterministic classification when possible")

if __name__ == "__main__":
    try:
        import tiktoken
    except ImportError:
        print("Installing tiktoken...")
        import subprocess
        subprocess.check_call(["pip", "install", "tiktoken"])
        import tiktoken
    
    calculate_all_costs()

